"""Carry packets between boards on one host -- a hub in a box.

Packet names are `<league><game><source><dest>.<seq>`: `900f0102.001` is
league 900, Falcon's Eye, board 01 to board 02, sequence 001. Board indices are
hex. The games write them in either case.

`carry()` does what a hub's routing does for direct traffic and nothing more:
no sequence checks, no HOST relaying. It is for exercising two or three boards
against each other, not for standing in for a hub under test.
"""
import re
import shutil
from pathlib import Path

PACKET = re.compile(r"^(\d{3})([a-z])([0-9a-f]{2})([0-9a-f]{2})\.(\d{3})$", re.I)


def parse(name: str):
    """(league, game, source, dest, seq) for a packet filename, or None."""
    m = PACKET.match(name)
    if not m:
        return None
    league, game, src, dst, seq = m.groups()
    return league, game.upper(), int(src, 16), int(dst, 16), int(seq)


def carry(boards: dict) -> list:
    """Move every packet in each board's OUTBOUND to its destination's INBOUND.

    `boards` maps board index to Install. Returns [(name, source, dest)] for
    what moved; packets for a board not in `boards`, and non-packet files
    (fenodes.900, the nodelist a hub would read), are left where they are.
    """
    moved = []
    for index, install in boards.items():
        outbound = Path(install.path) / "OUTBOUND"
        for f in sorted(outbound.iterdir()):
            p = parse(f.name)
            if not p or p[3] not in boards or p[3] == index:
                continue
            shutil.move(str(f), str(Path(boards[p[3]].path) / "INBOUND" / f.name))
            moved.append((f.name, index, p[3]))
    return moved


__all__ = ["carry", "parse"]
