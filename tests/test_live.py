"""Against a real game under dosemu. Skipped unless pointed at the media:

    SR_HARNESS_BRE_ZIP=~/bre_sj1.zip uv run pytest tests/test_live.py -s

The zip holds one top-level directory with the game in it. A scratch install is
built under ~/.dosemu/drive_c/bbs/doors/srh/ and removed afterwards.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from sr_harness import Install, bre, provision
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
    for junk in ("inuse.flg", "route.cfg", "DUPES.TXT", "DATA/BRE.LOC", "DATA/bre.loc"):
        (target / junk).unlink(missing_ok=True)
    for sub in ("INBOUND", "OUTBOUND", "BACKUP"):
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
