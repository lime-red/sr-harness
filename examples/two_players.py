#!/usr/bin/env python3
"""Two players on one Barren Realms Elite board, end to end, with sr-harness.

What it does, all on one board with no inter-BBS traffic:

  1. builds a brand-new game from the BRE media zip (unzip, BBS.CFG, the nodes
     file, BREDATA, then RESET walked through its configuration editor);
  2. player one joins, founds "Realm Alpha" and plays three turns;
  3. player two joins, founds "Realm Beta" and sends Realm Alpha local mail;
  4. player one comes back and reads it.

Run it on a machine with dosemu2 and the media zip:

    uv run python examples/two_players.py ~/bre_sj1.zip
    uv run python examples/two_players.py ~/bre_sj1.zip --keep --logs /tmp/demo

Every session's full transcript (raw terminal bytes, ANSI and all) goes to
--logs, which is where to look when a walk does something you didn't expect.
The game is built under ~/.dosemu/drive_c/bbs/doors/srh/ and removed at the end
unless --keep is given.
"""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from sr_harness import Install, bre, provision
from sr_harness.install import DRIVE_C

# 8.3 or the game silently ignores it: every component of the DOS path must be
# at most eight characters. Install() refuses a path that breaks this.
GAME_DIR = DRIVE_C / "bbs" / "doors" / "srh" / "b900demo"

# Donor state shipped in the media that means nothing to a new game.
JUNK = ("inuse.flg", "route.cfg", "DUPES.TXT", "DATA/BRE.LOC", "DOORFILE.SR")


def unpack(media: Path, target: Path):
    """The zip holds one top-level directory with the game in it."""
    shutil.rmtree(target, ignore_errors=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["unzip", "-q", str(media), "-d", tmp], check=True)
        (top,) = [p for p in Path(tmp).iterdir() if p.is_dir()]
        shutil.move(str(top), str(target))
    for name in JUNK:
        (target / name).unlink(missing_ok=True)
    for sub in ("INBOUND", "OUTBOUND", "BACKUP"):
        for f in (target / sub).glob("*"):
            if f.is_file():
                f.unlink()


def build(media: Path, logs: Path) -> Install:
    """A virgin single-board league (900), ready to play."""
    unpack(media, GAME_DIR)
    game = Install(GAME_DIR, "BRE.EXE")    # dos_path derived: C:\BBS\DOORS\SRH\B900DEMO
    provision.write_bbs_cfg(game, sysop="Demo Sysop", board="Demo Board",
                            address="900:900/1", league="900")
    provision.write_nodes(game, "BRNODES.DAT", [(1, "Demo Board", "900:900/1")])
    if provision.gamedata(game, "BREDATA.EXE", logs / "gamedata.log") != 0:
        raise SystemExit(f"BREDATA failed; see {logs / 'gamedata.log'}")
    provision.reset(game, transcript=logs / "reset.log")
    if not (GAME_DIR / "DATA" / "GAME.DAT").exists():
        raise SystemExit(f"RESET did not complete; see {logs / 'reset.log'}")
    return game


def show(title: str, status: dict):
    fields = ", ".join(f"{k}={v}" for k, v in status.items() if k != "realm_name")
    print(f"  {title}: {status.get('realm_name')}: {fields}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("media", type=Path, help="the BRE media zip")
    ap.add_argument("--logs", type=Path, default=Path(tempfile.gettempdir()) / "srh-demo")
    ap.add_argument("--keep", action="store_true", help="leave the game installed")
    a = ap.parse_args()
    a.logs.mkdir(parents=True, exist_ok=True)

    print(f"building a new game in {GAME_DIR}")
    game = build(a.media.expanduser(), a.logs)

    try:
        # ── player one: join, play three turns ───────────────────────────
        # The door user name identifies the player; a name the game has not
        # seen founds a new realm, with the name given here.
        print("player one joins and plays")
        one = bre.Player(game, realm="Realm Alpha", user="PLAYER ONE",
                         transcript=a.logs / "player_one.log").start()
        try:
            show("before", one.status())
            one.play_turns(3)            # every default: the do-nothing turn
            show("after 3 turns", one.status())
            alpha = one.letter           # "A": how local mail addresses this realm
        finally:
            one.quit()                   # always quit through the menus

        # ── player two: join, write to player one ────────────────────────
        print(f"player two joins and writes to realm {alpha}")
        two = bre.Player(game, realm="Realm Beta", user="PLAYER TWO",
                         transcript=a.logs / "player_two.log").start()
        try:
            show("new realm", two.status())
            two.send_message(alpha, "Greetings, Realm Alpha.\nRealm Beta comes in peace.")
        finally:
            two.quit()

        # ── player one again: read it ────────────────────────────────────
        print("player one comes back and reads mail")
        one = bre.Player(game, realm="Realm Alpha", user="PLAYER ONE",
                         transcript=a.logs / "player_one_again.log").start()
        try:
            said = one.read_messages()
        finally:
            one.quit()

        # The reader box, from the sender to the reader's own prompt.
        start, end = said.find("Message From"), said.find("[R] Reply")
        if start < 0:
            raise SystemExit(f"no message arrived; see {a.logs / 'player_one_again.log'}")
        for line in said[start:end].splitlines():
            if line.strip():
                print("  " + line.strip())
        print(f"done; transcripts in {a.logs}")
    finally:
        if not a.keep:
            shutil.rmtree(GAME_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
