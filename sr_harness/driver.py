"""What every game's player walk has in common.

A game module (`bre`, `fe`) subclasses `Driver` and supplies three things: how
to recognise its main menu, which lines on screen are permanent furniture rather
than a prompt, and its table of (prompt, answer) pairs. Everything about *how* a
walk answers prompts lives here, because the traps are the same in both games.
"""
import re
import time

# A menu's title bar: "──────[Main Menu]──────", or "[International Messages]"
# on its own. The whole line must be the header, so "[R] Reply" in a mail
# reader and "[Hit a key]" never count.
_HEADER = re.compile(r"^\s*[─═]*\[([A-Za-z0-9' .-]+)\][─═]*\s*$")

from sr_harness.session import DosSession


class Driver:
    # Regex that only matches when the main menu is fully drawn. Anchor on the
    # menu's own text, never on the input prompt alone: "Choice>" also appears on
    # every submenu, and inside the game's own help.
    main_menu: re.Pattern = None
    # The prompt the main menu waits on.
    menu_prompt: str = "Choice>"
    # A pagination marker; while it is up, a menu key is swallowed.
    paused: str = None
    # Regexes for lines that are always on screen and are never the prompt.
    furniture: tuple = ()

    def __init__(self, session: DosSession):
        self.session = session
        self.events = []

    # ── reading the screen ────────────────────────────────────────────────
    @property
    def screen(self) -> str:
        return self.session.screen_text()

    @property
    def prompt(self) -> str:
        """The line the game is waiting on: the last non-empty screen line that
        is not furniture.

        Answers are matched against this and never against the session's
        `raw_text()`: that is append-only history, so a prompt seen once matches
        forever and its answer re-fires into whatever is on screen later. On a
        short walk that never shows; on a player walk it types stray keys into a
        name field and wanders into the buy menus.
        """
        for line in reversed(self.screen.splitlines()):
            text = line.strip()
            if text and not any(re.search(f, text) for f in self.furniture):
                return text
        return ""

    @property
    def menu(self) -> str:
        """The title of the menu most recently drawn, or "" if none is on screen.

        The prompt line alone cannot say where a walk is: "Choice>" is the
        prompt of every menu in both games, and FE even pre-fills it with the
        default item. The last title bar on screen can.
        """
        for line in reversed(self.screen.splitlines()):
            m = _HEADER.match(line)
            if m:
                return m.group(1)
        return ""

    def at_main_menu(self) -> bool:
        screen = self.screen
        return bool(self.main_menu.search(screen)) and self.menu_prompt in self.prompt \
            and not (self.paused and re.search(self.paused, screen))

    # ── driving ───────────────────────────────────────────────────────────
    def answer_until(self, done, prompts, timeout=300.0, label="walk"):
        """Answer the live prompt until `done(self)`, or give up.

        `prompts` is a list of (regex, keys) or (regex, keys, menu_regex); the
        first whose regex matches the live prompt -- and, when given, whose
        menu_regex matches `self.menu` -- fires, so order specific prompts before
        generic ones. `keys` may be a callable, evaluated when it fires, so a
        count can live in it.

        An answer re-fires only once the whole screen has changed since it last
        fired. Keying that on the prompt *line* instead stalls forever: every
        page of a game's instructions ends in the same "Continue? (Y/n)".
        """
        compiled = [(re.compile(p[0], re.I), p[1],
                     re.compile(p[2], re.I) if len(p) > 2 else None) for p in prompts]
        fired, deadline = {}, time.time() + timeout
        while time.time() < deadline and not self.session.closed:
            self.session.pump(0.5)
            screen, prompt = self.screen, self.prompt
            if done(self):
                return True
            menu = self.menu
            for i, (rx, keys, in_menu) in enumerate(compiled):
                if not rx.search(prompt) or (in_menu and not in_menu.search(menu)):
                    continue
                if fired.get(i) == screen:
                    break
                keys = keys() if callable(keys) else keys
                self.events.append(f"{label}: {prompt!r} <- {keys!r}")
                self.session.send(keys)
                fired[i] = screen
                time.sleep(0.5)
                break
        return False

    def choose(self, key: str, settle: float = 1.5):
        """Press a key at a menu and let the screen catch up.

        Never press a bare <CR> to "settle" a screen: at a menu an empty line
        selects the default item, which in both games is (1) Play Game.
        """
        self.session.send(key)
        time.sleep(settle)
        self.session.pump(settle)

    def back_to_menu(self, prompts, timeout=180.0, label="menu"):
        if not self.answer_until(lambda p: p.at_main_menu(), prompts, timeout, label):
            raise TimeoutError(
                f"{label}: never got back to the main menu; last prompt was "
                f"{self.prompt!r}\n--- screen ---\n{self.screen}"
            )

    def leave(self, key="0", timeout=180.0):
        """Quit through the main menu and wait for the game to exit.

        Quitting properly is not politeness: FULL's outbound half runs on the way
        out -- it packs the day's mail into a packet -- and a killed session
        leaves the inuse.flg mutex behind.
        """
        self.choose(key)
        deadline = time.time() + timeout
        while not self.session.closed and time.time() < deadline:
            self.session.pump(1.0)
            if self.paused and re.search(self.paused, self.screen):
                self.session.send("\r")
        return self.session.close(grace=15)
