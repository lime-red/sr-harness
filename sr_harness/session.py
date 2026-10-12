"""Drive an interactive DOS program under dosemu2 through a pty.

The screen is reconstructed with pyte, so `screen_text()` returns the real 80x25
character grid rather than a concatenation of redraws. This is the seam a scripted
player -- or later a model -- plugs into.

Notes that matter for dosemu specifically:
  * the pty is given an explicit 80x25 winsize (DOS needs 25 lines; a pty
    inherited from a non-tty context has no size at all)
  * TERM is pinned (dosemu refuses to start under TERM=dumb)
  * output is read until the pty reports EOF, not until the first child exits
"""
import errno
import fcntl
import os
import pty
import re
import select
import signal
import struct
import termios
import time

import pyte

_ANSI = re.compile(rb"\x1b\[[0-9;?]*[a-zA-Z]|\x1b[()][A-Z0-9]|\x1b[=>]|\x1b\][^\x07]*\x07")
_C0 = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

KEYMAP = {"<CR>": "\r", "<LF>": "\n", "<ESC>": "\x1b", "<SP>": " ", "<TAB>": "\t"}


def expand(keys: str) -> str:
    """Turn `<CR>`-style tokens into the bytes they stand for."""
    for k, v in KEYMAP.items():
        keys = keys.replace(k, v)
    return keys


def strip(raw: bytes) -> str:
    """Plain text from a terminal byte stream: drop ANSI, then C0 controls."""
    text = _ANSI.sub(b"", raw).decode("utf-8", errors="replace")
    return _C0.sub("", text).replace("\r", "\n")


class _Screen(pyte.Screen):
    """pyte trips over some private CSI sequences dosemu emits (notably a private
    DECSTBM, `set_margins(..., private=True)`). Swallow the extra kwarg rather than
    losing the whole stream."""

    def set_margins(self, *args, **kwargs):
        kwargs.pop("private", None)
        return super().set_margins(*args, **kwargs)


class DosSession:
    def __init__(self, cmd, cwd=None, term="linux", rows=25, cols=80, transcript=None):
        self.rows, self.cols = rows, cols
        self.screen = _Screen(cols, rows)
        self.stream = pyte.ByteStream(self.screen)
        self.transcript = open(transcript, "wb") if transcript else None
        self.closed = False
        self._buf = bytearray()
        self._wedged = False

        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        env = dict(os.environ)
        env.update(TERM=term, LINES=str(rows), COLUMNS=str(cols))

        pid = os.fork()
        if pid == 0:
            os.setsid()
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
            for fd in (0, 1, 2):
                os.dup2(slave, fd)
            if slave > 2:
                os.close(slave)
            os.close(master)
            if cwd:
                os.chdir(cwd)
            try:
                os.execvpe(cmd[0], list(cmd), env)
            finally:
                os._exit(127)

        os.close(slave)
        self.pid, self.master = pid, master

    def pump(self, timeout=0.5):
        """Read whatever is available and feed it to the terminal emulator."""
        deadline = time.time() + timeout
        got = False
        while not self.closed:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                r, _, _ = select.select([self.master], [], [], remaining)
            except InterruptedError:
                continue
            if self.master not in r:
                break
            try:
                chunk = os.read(self.master, 65536)
            except OSError as e:
                if e.errno == errno.EIO:      # pty EOF: all writers gone
                    self.closed = True
                    break
                raise
            if not chunk:
                self.closed = True
                break
            self._buf += chunk
            try:
                self.stream.feed(chunk)
            except Exception:
                # A parse error leaves pyte's parser generator dead, so every later
                # feed silently does nothing and the screen freezes -- which looks
                # exactly like "the program stopped responding". Rebuild instead.
                self._wedged = True
            if self._wedged:
                self._rebuild()
            if self.transcript:
                self.transcript.write(chunk)
                self.transcript.flush()
            got = True
        return got

    def _rebuild(self):
        """Re-render the whole byte history onto a fresh emulator."""
        self.screen = _Screen(self.cols, self.rows)
        self.stream = pyte.ByteStream(self.screen)
        try:
            self.stream.feed(bytes(self._buf))
            self._wedged = False
        except Exception:
            self._wedged = True

    def screen_text(self):
        return "\n".join(line.rstrip() for line in self.screen.display)

    def raw_text(self, tail=20000):
        """ANSI-stripped view of the recent byte stream.

        The emulated screen is the right thing to *read*, but pyte can wedge on a
        sequence it does not understand, and then the screen silently stops updating.
        Prompt matching therefore also consults the raw stream, which cannot wedge.

        It is append-only history, though: a prompt seen once matches forever.
        Never answer prompts off it in a long walk -- see `driver.Driver.prompt`.
        """
        return strip(bytes(self._buf[-tail:]))

    def mark(self) -> int:
        """A position in the byte stream, for `text_since`."""
        return len(self._buf)

    def text_since(self, mark: int) -> str:
        """Everything printed since `mark`, as plain text.

        This is how to keep what a screen *said* once it has scrolled or been
        repainted away -- the emulated screen only ever holds the last 25 lines.
        """
        return strip(bytes(self._buf[mark:]))

    def send(self, keys):
        os.write(self.master, keys.encode("latin-1"))

    def mash(self, keys, until_gone, max_presses=60, gap=0.25):
        """Send `keys` repeatedly until `until_gone` leaves the screen (or we exit).

        dosemu consumes a lone ESC as the start of an escape sequence, so a single
        press is usually swallowed; repeated presses get one through. This is the
        documented human workaround, mechanised.
        """
        rx = re.compile(until_gone, re.I)
        for i in range(1, max_presses + 1):
            self.send(keys)
            time.sleep(gap)
            self.pump(0.15)
            # Screen only: raw_text is append-only history, so a marker that has
            # scrolled away would still match and the mash would never terminate.
            if self.closed or not rx.search(self.screen_text()):
                return i
        return None

    def until(self, goal, answers, timeout=120.0):
        """Pump until `goal` appears, answering any prompt in `answers` on the way.

        Interactive DOS programs branch on their own data, so the prompts before a
        given screen are not a fixed sequence. Rather than script an exact order,
        state the destination and how to answer whatever shows up.

        Answers are repeatable -- pagination prompts ("Paused", "Continue? (Y/n)")
        recur many times in one run, so firing each only once wedges the walk. To
        stop a prompt that never clears from being hammered, an answer re-fires only
        once the screen has actually changed since it was last used.

        Matches against the raw history as well as the screen, so it suits short
        walks whose prompts do not recur (a RESET). For a long walk -- playing the
        game -- use `driver.Driver.answer_until`, which matches the live prompt only.
        """
        rx_goal = re.compile(goal, re.I)
        pending = [(re.compile(p, re.I), k) for p, k in answers]
        last_fired = {}
        deadline = time.time() + timeout
        while time.time() < deadline and not self.closed:
            self.pump(0.4)
            screen = self.screen_text()
            if rx_goal.search(screen):
                return True
            view = screen + "\n" + self.raw_text(6000)
            for i, (rx, keys) in enumerate(pending):
                if rx.search(view) and last_fired.get(i) != screen:
                    self.send(expand(keys))
                    last_fired[i] = screen
                    time.sleep(0.6)
                    break
        return False

    def wait_for(self, pattern, timeout=30.0):
        """Pump until `pattern` (regex) appears on screen. Returns the match or None."""
        rx = re.compile(pattern, re.I)
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.pump(0.4)
            m = rx.search(self.screen_text()) or rx.search(self.raw_text())
            if m:
                return m
            if self.closed:
                break
        return None

    def drain(self, timeout):
        """Pump until the program exits or `timeout` passes. True if it exited."""
        deadline = time.time() + timeout
        while not self.closed and time.time() < deadline:
            self.pump(1.0)
        return self.closed

    def close(self, grace=3.0):
        deadline = time.time() + grace
        while not self.closed and time.time() < deadline:
            self.pump(0.3)
        try:
            os.killpg(os.getpgid(self.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            _, status = os.waitpid(self.pid, 0)
        except ChildProcessError:
            status = 0
        os.close(self.master)
        if self.transcript:
            self.transcript.close()
        return os.waitstatus_to_exitcode(status) if status else 0
