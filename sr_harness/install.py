"""One game install, and how to start dosemu on it.

Everything here is about the *shape* of a run rather than any one game: the
batch file dosemu executes, the door file that gets a player in, the mutex a
killed run leaves behind, and faking the date.
"""
import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Optional

from sr_harness.dospath import dos_path_problems
from sr_harness.run import run as _run
from sr_harness.session import DosSession

DRIVE_C = Path.home() / ".dosemu" / "drive_c"

# A local-mode door file: COM port 0. Without it the games wait on a modem that
# is not there. Seven lines, CRLF, as SETUP.SR documents; BRE and FE share it.
DOORFILE = "{name}\r\n1\r\n1\r\n0\r\n38400\r\n0\r\n-1\r\n{name}\r\n"


def default_conf() -> Path:
    """The dosemu conf shipped with the package: VGA video, fixed 80x25."""
    return Path(str(resources.files("sr_harness") / "data" / "dosemu.conf"))


def find_ci(directory: Path, name: str) -> Optional[Path]:
    """`directory/name`, matching case-insensitively.

    DOS sees one namespace; Linux sees two. FE writes DATA/ in lower case where
    BRE writes upper, and the media ships BBS.CFG where a hand-written config is
    often bbs.cfg -- so look the way DOS would.
    """
    direct = Path(directory) / name
    if direct.exists():
        return direct
    for entry in Path(directory).iterdir():
        if entry.name.lower() == name.lower():
            return entry
    return None


def crlf(*lines) -> bytes:
    return "".join(f"{line}\r\n" for line in lines).encode("latin-1")


@dataclass
class Install:
    """A BRE or FE install on disk, and the DOS path it is reached by.

    dosemu is started as `dosemu -f <conf> -K <install> -E <BATCH>`. Do not use
    the bare-path form (`dosemu -f <conf> /abs/BATCH.BAT`): on current dosemu2 it
    remaps C: to the batch file's own directory, the batch's `CD` then fails, the
    game never runs, and dosemu still exits 0.

    The batch changes to `dos_path` on C:, which is ~/.dosemu/drive_c -- so an
    install outside drive_c needs `dos_path` given explicitly and a conf that
    maps it.
    """
    path: Path
    exe: str                         # "BRE.EXE" / "FE.EXE"
    dos_path: Optional[str] = None   # derived from drive_c when not given
    conf: Optional[Path] = None      # dosemu conf; the packaged one when not given
    dosemu: str = "/usr/bin/dosemu"
    redate: Optional[Path] = None    # REDATE.COM, needed only to fake the date

    def __post_init__(self):
        self.path = Path(self.path)
        if self.dos_path is None:
            try:
                rel = self.path.resolve().relative_to(DRIVE_C.resolve())
            except ValueError:
                raise ValueError(
                    f"{self.path} is not under {DRIVE_C}; pass dos_path explicitly"
                ) from None
            self.dos_path = "C:\\" + "\\".join(p.upper() for p in rel.parts)
        problems = dos_path_problems(self.dos_path)
        if problems:
            raise ValueError("; ".join(problems))
        self.conf = Path(self.conf) if self.conf else default_conf()

    # ── files the game reads ──────────────────────────────────────────────
    def write_batch(self, name: str, *commands: str):
        (self.path / name).write_bytes(
            crlf("@ECHO OFF", "C:", f"CD {self.dos_path}", *commands, "EXIT"))

    def write_doorfile(self, user: str):
        """DOORFILE.SR for a local player called `user`.

        The name should be unique across the league: with duplicate checking on
        (a league setting), a name already playing on another board is refused
        outright and the session never reaches the main menu.
        """
        (self.path / "DOORFILE.SR").write_bytes(DOORFILE.format(name=user).encode("latin-1"))

    def clear_mutex(self):
        """Remove inuse.flg, the game's mutex.

        A killed run leaves one behind, and every later run then exits 1 having
        printed nothing about why.
        """
        for name in ("inuse.flg", "INUSE.FLG"):
            (self.path / name).unlink(missing_ok=True)

    def command(self, batch: str) -> list:
        return [self.dosemu, "-f", str(self.conf), "-K", str(self.path), "-E", batch]

    def _game_lines(self, args: str, date: Optional[str]) -> list:
        """The batch body: the game, optionally wrapped in REDATE.

        `date` is "YYYYMMDD". REDATE.COM hooks int 21h AH=2Ah (GET-DATE) only --
        exactly where Turbo Pascal's GetDate goes -- so the game sees the faked
        date and nothing else does. It is installed and removed around the one
        command so it cannot leak into the next. (libfaketime is not an option:
        it deadlocks dosemu2's timer handler, even at +0d.)
        """
        line = f"{self.exe} {args}".strip()
        if not date:
            return [line]
        if not self.redate:
            raise ValueError("faking the date needs Install.redate (REDATE.COM)")
        shutil.copy(self.redate, self.path / "REDATE.COM")
        return [f"REDATE /i{date}", line, "REDATE /r"]

    # ── running it ────────────────────────────────────────────────────────
    def run(self, args: str, log, timeout=300.0, date: Optional[str] = None,
            batch: str = "RUN.BAT") -> int:
        """Run `<EXE> <args>` unattended and return dosemu's exit code.

        `FULL` is refused: it is the player path, and headless it blocks forever
        on "Do you want ANSI Graphics? (Y/n)". Use a game's Player for that.
        """
        if args.split()[:1] and args.split()[0].upper() == "FULL":
            raise ValueError("FULL is interactive; use bre.Player / fe.Player")
        self.write_batch(batch, *self._game_lines(args, date))
        self.clear_mutex()
        try:
            return _run(self.command(batch), log, timeout=timeout)
        finally:
            self.clear_mutex()

    def session(self, args: str, transcript=None, date: Optional[str] = None,
                batch: str = "PLAY.BAT") -> DosSession:
        """Start `<EXE> <args>` on a pty and hand back the live session."""
        self.write_batch(batch, *self._game_lines(args, date))
        self.clear_mutex()
        return DosSession(self.command(batch), term="linux", transcript=transcript)
