"""The 8.3 guard.

A DOS path with an over-long component does not produce an error anywhere. The
16-bit Turbo Pascal the games are built with simply fails to traverse it, so the
game runs to completion, prints every phase marker, and ingests nothing at all.
The only cheap way to catch it is to look at the configured paths before
trusting a run.
"""
from pathlib import Path


def dos_path_problems(dos_path: str) -> list:
    """Components of a DOS path that 16-bit code cannot traverse."""
    problems = []
    for part in str(dos_path).split("\\"):
        if not part or part.endswith(":"):
            continue
        stem, _, ext = part.partition(".")
        if len(stem) > 8 or len(ext) > 3:
            problems.append(
                f"path component {part!r} breaks DOS 8.3, so the game will "
                f"silently ingest nothing from {dos_path!r}"
            )
    return problems


def bbs_cfg_inbound(install: Path) -> str:
    """Line 4 of bbs.cfg: the DOS path the game reads packets from."""
    cfg = Path(install) / "bbs.cfg"
    if not cfg.exists():
        cfg = Path(install) / "BBS.CFG"
    lines = cfg.read_bytes().decode("latin-1").split("\r\n")
    return lines[3] if len(lines) > 3 else ""
