"""Against a real game under dosemu. Skipped unless pointed at the media:

    SR_HARNESS_BRE_ZIP=~/bre_sj1.zip SR_HARNESS_FE_ZIP=~/fe_sj1.zip \
        uv run pytest tests/test_live.py -s

The zip holds one top-level directory with the game in it. A scratch install is
built under ~/.dosemu/drive_c/bbs/doors/srh/ and removed afterwards.
"""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from sr_harness import Install, bre, fe, mail, provision
from sr_harness.install import DRIVE_C

ROOT = DRIVE_C / "bbs" / "doors" / "srh"
LOGS = Path(os.environ.get("SR_HARNESS_LOGS", tempfile.gettempdir()))

needs_dosemu = pytest.mark.skipif(not Path("/usr/bin/dosemu").exists(),
                                  reason="no dosemu")


def _unpack(zip_env: str, dirname: str) -> Path:
    media = os.environ.get(zip_env)
    if not media:
        pytest.skip(f"{zip_env} not set")
    target = ROOT / dirname
    shutil.rmtree(target, ignore_errors=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["unzip", "-q", os.path.expanduser(media), "-d", tmp], check=True)
        (top,) = [p for p in Path(tmp).iterdir() if p.is_dir()]
        shutil.move(str(top), str(target))
    # Donor game state means nothing to a new game; RESET rebuilds it.
    for junk in ("inuse.flg", "route.cfg", "DUPES.TXT", "DATA/BRE.LOC", "DATA/bre.loc",
                 "DATA/fe.loc", "DATA/FE.LOC", "DATA/dupes.fe", "routes.lst", "routes.bad",
                 "BBSINFO.LST", "PROBLEMS.LOG", "DOORFILE.SR"):
        (target / junk).unlink(missing_ok=True)
    for sub in ("INBOUND", "OUTBOUND", "BACKUP", "BULLETIN"):
        for f in (target / sub).glob("*"):
            if f.is_file():
                f.unlink()
    return target


@pytest.fixture
def bre_game():
    path = _unpack("SR_HARNESS_BRE_ZIP", "b900n01")
    game = Install(path, "BRE.EXE")
    provision.write_bbs_cfg(game, "Test Sysop", "Harness Board", "900:900/1", "900")
    provision.write_nodes(game, "BRNODES.DAT", [(1, "Harness Board", "900:900/1")])
    assert provision.gamedata(game, "BREDATA.EXE", LOGS / "srh_bre_gamedata.log") == 0
    provision.reset(game, transcript=LOGS / "srh_bre_reset.log")
    assert (path / "DATA" / "GAME.DAT").exists(), "RESET did not complete"
    yield game
    shutil.rmtree(path, ignore_errors=True)


@needs_dosemu
def test_bre_a_played_turn_moves_the_score(bre_game):
    p = bre.Player(bre_game, realm="Harness Realm", user="TEST PILOT 01",
                   transcript=LOGS / "srh_bre_play.log").start()
    try:
        before = p.status()
        assert before["realm_name"] == "Harness Realm"
        assert p.play_turns(1) == 1
        after = p.status()
    finally:
        rc = p.quit()
    assert after["turns"] == before["turns"] - 1
    assert after["score"] != before["score"]
    assert rc == 0
    assert not (bre_game.path / "inuse.flg").exists()


@needs_dosemu
def test_bre_local_mail_between_two_realms(bre_game):
    """Local mail: realm B writes to realm A on the same board; A reads it
    under (6). It never becomes a packet."""
    one = bre.Player(bre_game, realm="Realm Alpha", user="PLAYER ONE",
                     transcript=LOGS / "srh_bre_mail1.log").start()
    try:
        alpha = one.letter
    finally:
        one.quit()
    assert alpha == "A"

    two = bre.Player(bre_game, realm="Realm Beta", user="PLAYER TWO",
                     transcript=LOGS / "srh_bre_mail2.log").start()
    try:
        assert two.letter == "B"
        two.send_message(alpha, "Greetings from Realm Beta.")
    finally:
        two.quit()

    one = bre.Player(bre_game, realm="Realm Alpha", user="PLAYER ONE",
                     transcript=LOGS / "srh_bre_mail3.log").start()
    try:
        said = one.read_messages()
    finally:
        one.quit()
    assert re.search(r"Message From: Realm Beta", said)
    assert "Greetings from Realm Beta." in said
    assert not list((bre_game.path / "OUTBOUND").glob("*")), "local mail made a packet"


FE_BOARDS = [(1, "Board One", "900:900/1"), (2, "Board Two", "900:900/2")]


def _fe_board(index: int) -> Install:
    """One board of a two-board FE league, through its day-one PLANETARY.

    FE's world -- planet.fe and the rest -- only appears on the first
    PLANETARY, which is also game-day one and emits packets.
    """
    _, name, address = FE_BOARDS[index - 1]
    game = Install(_unpack("SR_HARNESS_FE_ZIP", f"f900n0{index}"), "FE.EXE")
    provision.write_bbs_cfg(game, "Test Sysop", name, address, "900")
    provision.write_nodes(game, "FENODES.DAT", FE_BOARDS)
    assert provision.gamedata(game, "FEDATA.EXE", LOGS / f"srh_fe{index}_gamedata.log") == 0
    provision.reset(game, transcript=LOGS / f"srh_fe{index}_reset.log")
    assert (game.path / "DATA" / "game.dat").exists(), "RESET did not complete"
    assert game.run("PLANETARY /DETAILED", LOGS / f"srh_fe{index}_planetary.log") == 0
    return game


@pytest.fixture
def fe_game():
    game = _fe_board(1)
    yield game
    shutil.rmtree(game.path, ignore_errors=True)


@pytest.fixture
def fe_league():
    boards = {1: _fe_board(1), 2: _fe_board(2)}
    mail.carry(boards)
    yield boards
    for game in boards.values():
        shutil.rmtree(game.path, ignore_errors=True)


@needs_dosemu
def test_fe_join_play_and_message(fe_game):
    p = fe.Player(fe_game, county="Harness County", user="TEST PILOT 01",
                  transcript=LOGS / "srh_fe_play.log").start()
    try:
        before = p.status()
        assert before["county"] == "Harness County"
        assert p.play_turns(2) == 2
        assert p.month == (2, before["months_per_year"])
        after = p.status()
        p.send_world_message("HARNESS FE WORLD MESSAGE")
        p.rankings("players_by_score")
        p.read_messages()
    finally:
        rc = p.quit()
    assert after["silver"] != before["silver"]
    assert rc == 0
    assert not (fe_game.path / "inuse.flg").exists()
    packets = list((fe_game.path / "OUTBOUND").glob("900f0102.*"))
    assert any(b"HARNESS FE WORLD MESSAGE" in f.read_bytes() for f in packets)


@needs_dosemu
def test_fe_mail_from_a_county_the_other_board_has_not_heard_of(fe_league):
    """A county's mail, its recon, and the >>Unknown<< trap.

    Board 2 learns that a county exists only from a recon. A message ingested
    before the sender's recon names the board but not the county --
    "Message From: >>Unknown<< (Board One)". The name is looked up when the
    message is *shown*, so the same stored message names its sender once later
    traffic has taught board 2 the county. A county that sends mail in the
    session it was founded in therefore
    reaches other boards as >>Unknown<< at first.
    """
    one, two = fe_league[1], fe_league[2]

    # Found a county and send mail in the same session.
    p = fe.Player(one, county="County One", user="PILOT ONE",
                  transcript=LOGS / "srh_fe1_play.log").start()
    try:
        p.play_turns(1)
        p.send_world_message("FIRST HELLO")
    finally:
        p.quit()
    # Then announce it. RECON only queues the recon; an outbound run packs it.
    # (The sequence number of what comes out depends on whether the day-one
    # packet was collected: FE appends to an uncollected packet.)
    assert one.run("RECON", LOGS / "srh_fe1_recon.log") == 0
    assert one.run("OUTBOUND /DETAILED", LOGS / "srh_fe1_outbound.log") == 0
    assert {(s, d) for _, s, d in mail.carry(fe_league)} == {(1, 2)}

    # Board 2 ingests both -- message first -- on its way in. Mail is shown on
    # entry; Q leaves it unread, so Read Messages shows it again.
    p = fe.Player(two, county="County Two", user="PILOT TWO",
                  transcript=LOGS / "srh_fe2_play.log").start()
    try:
        assert re.search(r"Message From:\s*>>Unknown<<\s*\(Board One\)", p.entry_text)
        assert "FIRST HELLO" in p.entry_text
        assert "FIRST HELLO" in p.read_messages()
    finally:
        p.quit()

    # Mail sent now, after the recon has been ingested, names its sender.
    p = fe.Player(one, county="County One", user="PILOT ONE",
                  transcript=LOGS / "srh_fe1_play2.log").start()
    try:
        p.send_world_message("SECOND HELLO")
    finally:
        p.quit()
    mail.carry(fe_league)
    # Rankings are built by SCORES, not by ingesting packets.
    assert two.run("SCORES", LOGS / "srh_fe2_scores.log") == 0
    p = fe.Player(two, county="County Two", user="PILOT TWO",
                  transcript=LOGS / "srh_fe2_play2.log").start()
    try:
        assert "County Two" in p.rankings("players_by_score")
    finally:
        p.quit()
    # County One is NOT in those rankings, recon or no recon: neither founding
    # it, nor playing, nor RECON sends anything rankings are built from. In
    # the day-by-day runs an unplayed league only ever sends Config Update,
    # Recon Update, Recon Request, Routing List and Time Check. What does carry
    # a score is still open.
    # Both messages are shown -- the reader walk shows each once -- and FIRST
    # HELLO, still stored, now names its sender. The name is looked up when a
    # message is displayed, not when it arrives, so the >>Unknown<< above
    # healed once later traffic from board 1 taught board 2 the county.
    assert "SECOND HELLO" in p.entry_text
    assert not re.search(r">>Unknown<<", p.entry_text)
    assert len(re.findall(r"Message From:\s*County One\s*\(Board One\)", p.entry_text)) >= 2
