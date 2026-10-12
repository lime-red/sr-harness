"""Turn a copy of the game files into a virgin, playable game.

This is not the file copy it looks like. `BREDATA -Y` / `FEDATA -Y` regenerate
GAME/ (help text, events, news templates) but not DATA/; virgin game state only
comes from `<EXE> RESET`, which is interactive.

BRE and FE are close relatives here: the same 7-line CRLF BBS.CFG, the same
nodes-file format with its "1 HOST 2 3 4" routing line, the same RESET walk.
"""
from pathlib import Path

from sr_harness.dospath import dos_path_problems
from sr_harness.install import Install, crlf
from sr_harness.session import expand


def write_bbs_cfg(install: Install, sysop: str, board: str, address: str,
                  league: str, inbound: str = None, netmail: str = None):
    """BBS.CFG: who this board is, and where it reads packets from.

    Line 4 must point at this install's own INBOUND. A stale or untraversable
    path there is silently fatal: the game "succeeds" having ingested nothing.
    """
    inbound = inbound or f"{install.dos_path}\\INBOUND"
    netmail = netmail or f"{install.dos_path}\\NETMAIL"
    problems = dos_path_problems(inbound)
    if problems:
        raise ValueError("; ".join(problems))
    for name in ("bbs.cfg", "BBS.CFG"):
        (install.path / name).unlink(missing_ok=True)
    (install.path / "BBS.CFG").write_bytes(
        crlf(sysop, board, address, inbound, netmail, league, "NONE"))
    for sub in ("INBOUND", "OUTBOUND", "NETMAIL", "BACKUP"):
        (install.path / sub).mkdir(exist_ok=True)


def write_nodes(install: Install, filename: str, boards, host: int = 1):
    """BRNODES.DAT / FENODES.DAT. `boards` is [(index, name, address), ...].

    The host board's first line HOSTs the rest -- that line, not a route.cfg, is
    where routing comes from. (The media ships a route.cfg of "ROUTE * 2", which
    sends a leaf board's mail to itself; no working install has one.)
    """
    hosted = " ".join(str(i) for i, _, _ in boards if i != host)
    lines = [f"{host} HOST {hosted}".strip()]
    for index, name, address in boards:
        if index != host:
            lines.append(str(index))
        lines += [name, address, "Nowhere", "XX", "XXX", ""]
    (install.path / filename).write_bytes(crlf(*lines))
    (install.path / "route.cfg").unlink(missing_ok=True)


def gamedata(install: Install, data_exe: str, log, timeout=120.0) -> int:
    """`BREDATA -Y` / `FEDATA -Y`: regenerate GAME/."""
    install.write_batch("GAMEDATA.BAT", f"{Path(data_exe).stem} -Y")
    install.clear_mutex()
    from sr_harness.run import run
    return run(install.command("GAMEDATA.BAT"), log, timeout=timeout)


def reset(install: Install, transcript=None, timeout=180.0):
    """Drive `<EXE> RESET` to a virgin game.

    The prompt sequence is neither fixed nor in the order the flow implies:
    confirm, then the *Configuration Editor* opens, and only after ESCaping out
    of it does the league-wide question appear -- and only on the board whose
    address matches the HOST entry. So state the destination and answer what
    turns up.

    RESET deletes stray .BAT files from the game directory, so anything that
    needs one must write it afterwards.
    """
    session = install.session("RESET", transcript=transcript, batch="RESET.BAT")
    try:
        if not session.until(r"Configuration Editor", [(r"reset the Game", "Y")],
                             timeout=timeout):
            raise RuntimeError(
                f"RESET never reached the config editor for {install.path}\n"
                f"--- screen ---\n{session.screen_text()}"
            )
        # dosemu treats a lone ESC as the start of an escape sequence and
        # swallows it; repeated presses get one through.
        session.mash(expand("<ESC>"), "Configuration Editor", max_presses=80)
        if session.wait_for(r"league-wide reset", timeout=60):
            session.send("n")
        session.drain(60)
    finally:
        session.close()
        install.clear_mutex()
