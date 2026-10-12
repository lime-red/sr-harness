"""`sr-harness`: run and explore a game by hand.

    sr-harness run     --install DIR --exe BRE.EXE PLANETARY /DETAILED
    sr-harness observe --install DIR --exe FE.EXE --user ME FULL

    sr-harness hold    fe --install DIR --exe FE.EXE --user ME FULL
    sr-harness keys    fe "1"            # press keys, print what came back
    sr-harness keys    fe "Bob<CR>"
    sr-harness screen  fe
    sr-harness release fe

`hold` keeps one game session alive in the background between commands. That is
how an unfamiliar game gets mapped: press a key, read the screen, decide the next
key -- which is exactly what a person at a terminal does, and what a scripted
walk cannot do until somebody has done it once.

Keys take `<CR>`, `<ESC>`, `<SP>`, `<TAB>`, `<LF>` tokens.
"""
import argparse
import json
import os
import select
import socket
import subprocess
import sys
import time
from pathlib import Path

from sr_harness.install import Install
from sr_harness.session import expand


def _install(a) -> Install:
    return Install(Path(a.install), a.exe, dos_path=a.dos_path, conf=a.conf,
                   redate=a.redate)


def _socket_path(name: str) -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return Path(base) / f"sr-harness-{os.getuid()}-{name}.sock"


def _launch_args(ap):
    ap.add_argument("--install", required=True, help="the game directory")
    ap.add_argument("--exe", required=True, help="BRE.EXE / FE.EXE")
    ap.add_argument("--dos-path", help="defaults to its place under ~/.dosemu/drive_c")
    ap.add_argument("--conf", help="dosemu conf; defaults to the packaged one")
    ap.add_argument("--redate", help="REDATE.COM, for --date")
    ap.add_argument("--date", help="YYYYMMDD the game should believe it is")
    ap.add_argument("--user", help="write a local DOORFILE.SR for this player")
    ap.add_argument("--transcript", help="write the raw byte stream here")
    ap.add_argument("args", nargs=argparse.REMAINDER, help="arguments to the game")


def _args(a) -> str:
    rest = a.args[1:] if a.args[:1] == ["--"] else a.args
    return " ".join(rest)


# ── one-shot commands ─────────────────────────────────────────────────────
def cmd_run(a):
    log = a.transcript or "run.log"
    rc = _install(a).run(_args(a), log, timeout=a.timeout, date=a.date)
    print(f"exit {rc}; transcript in {log}")
    return rc


def cmd_observe(a):
    install = _install(a)
    if a.user:
        install.write_doorfile(a.user)
    s = install.session(_args(a), transcript=a.transcript, date=a.date)
    end = time.time() + a.duration
    while time.time() < end and not s.closed:
        s.pump(a.interval)
        print("=" * 80, f"\nt={time.time() % 1000:.1f} closed={s.closed}")
        print(s.screen_text())
        sys.stdout.flush()
    print("=" * 80, "\nFINAL SCREEN:\n" + s.screen_text())
    rc = s.close()
    install.clear_mutex()
    return rc


# ── hold / keys / screen / release ────────────────────────────────────────
def _serve(a):
    """The background half of `hold`: own the session, answer the socket."""
    install = _install(a)
    if a.user:
        install.write_doorfile(a.user)
    session = install.session(_args(a), transcript=a.transcript, date=a.date)
    path = _socket_path(a.name)
    path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    os.chmod(path, 0o600)
    server.listen(4)
    try:
        while True:
            r, _, _ = select.select([server] + ([] if session.closed else [session.master]),
                                    [], [], 1.0)
            if session.master in r:
                session.pump(0.05)
            if server not in r:
                continue
            conn, _ = server.accept()
            with conn:
                req = json.loads(conn.makefile().readline() or "{}")
                op = req.get("op")
                mark = session.mark()
                if op == "keys" and not session.closed:
                    session.send(expand(req["keys"]))
                    # Wait for output to start, then for it to go quiet.
                    deadline = time.time() + req.get("settle", 2.0)
                    while time.time() < deadline and not session.closed:
                        if session.pump(0.4):
                            deadline = max(deadline, time.time() + 0.6)
                reply = {"screen": session.screen_text(), "said": session.text_since(mark),
                         "closed": session.closed}
                conn.sendall((json.dumps(reply) + "\n").encode())
                if op == "release":
                    break
    finally:
        server.close()
        path.unlink(missing_ok=True)
        session.close(grace=1.0)
        install.clear_mutex()


def _ask(name, req) -> dict:
    path = _socket_path(name)
    if not path.exists():
        sys.exit(f"no held session called {name!r} ({path} missing)")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
        c.connect(str(path))
        c.sendall((json.dumps(req) + "\n").encode())
        return json.loads(c.makefile().readline())


def cmd_hold(a):
    path = _socket_path(a.name)
    if path.exists():
        sys.exit(f"a session called {a.name!r} is already held ({path})")
    argv = [sys.executable, "-m", "sr_harness.cli", "_serve", a.name] + sys.argv[3:]
    log = open(a.log or os.devnull, "ab")
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                     start_new_session=True)
    for _ in range(100):
        if path.exists():
            break
        time.sleep(0.1)
    else:
        sys.exit("the held session never came up; rerun with --log to see why")
    time.sleep(a.settle)
    _print(_ask(a.name, {"op": "screen"}), said=False)


def _print(reply, said):
    if said and reply["said"].strip():
        print("--- said ---\n" + reply["said"].rstrip())
        print("--- screen ---")
    print(reply["screen"])
    if reply["closed"]:
        print("[the game has exited]")


def cmd_keys(a):
    _print(_ask(a.name, {"op": "keys", "keys": a.keys, "settle": a.settle}), said=a.said)


def cmd_screen(a):
    _print(_ask(a.name, {"op": "screen"}), said=False)


def cmd_release(a):
    # Kills dosemu: quit through the game's own menu first if its outbound half
    # matters. The mutex is cleared either way.
    _print(_ask(a.name, {"op": "release"}), said=False)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sr-harness", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="run a command unattended")
    _launch_args(p)
    p.add_argument("--timeout", type=float, default=300.0)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("observe", help="run and print the screen every few seconds")
    p.add_argument("--interval", type=float, default=3.0)
    p.add_argument("--duration", type=float, default=30.0)
    _launch_args(p)
    p.set_defaults(fn=cmd_observe)

    p = sub.add_parser("hold", help="start a session that stays up between commands")
    p.add_argument("name")
    p.add_argument("--log", help="where the background process writes its errors")
    p.add_argument("--settle", type=float, default=8.0,
                   help="seconds to let the game draw before printing")
    _launch_args(p)
    p.set_defaults(fn=cmd_hold)

    p = sub.add_parser("_serve")
    p.add_argument("name")
    p.add_argument("--log")
    p.add_argument("--settle", type=float)
    _launch_args(p)
    p.set_defaults(fn=_serve)

    p = sub.add_parser("keys", help="press keys in a held session")
    p.add_argument("name")
    p.add_argument("keys")
    p.add_argument("--settle", type=float, default=2.0)
    p.add_argument("--said", action="store_true",
                   help="also print everything output, not just the final screen")
    p.set_defaults(fn=cmd_keys)

    p = sub.add_parser("screen", help="print a held session's screen")
    p.add_argument("name")
    p.set_defaults(fn=cmd_screen)

    p = sub.add_parser("release", help="end a held session")
    p.add_argument("name")
    p.set_defaults(fn=cmd_release)

    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
