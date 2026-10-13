"""Drive Falcon's Eye as a *player*.

FE is BRE's sibling -- same author, same door file, same RESET walk, same
inter-BBS plumbing -- but it plays differently, and the differences are exactly
where a BRE walk would go wrong:

  * **Two menu levels.** The outer menu ("[Falcon's Eye]": Join/Enter Game,
    scores, news) is not the game. (1) Join Game creates a county; afterwards
    the same key reads (1) Enter Game. Inside is "[Main Menu]". Quitting the
    county drops back to the outer menu, which must be quit as well.
  * **The prompt line cannot say where you are.** "Choice>" is the prompt of
    every menu, pre-filled with the default item ("Choice> Labor"). So answers
    here are keyed on the menu title as well -- see Driver.menu.
  * **A turn is one key, not a sequence.** The main menu is a hub of things to
    manage; (-) Take Turn plays one month. A day is a year of `Months per Year`
    months (8 by default). BRE's turn walks every phase in order instead.
  * **Defaults are not the do-nothing path.** "Take your next turn? (y/N)"
    defaults to *No* whenever the advisers have warnings, so taking every
    default never plays a turn. The race menu defaults to (0) Quit.
  * **FE has debt.** Each month 25% of expenses is taken; the rest is asked
    for ("Give how much silver? (189; 189)"), and what is not paid accrues
    interest. The default is to pay it all, which is what a walk does.
  * **First visits print help.** The first time a menu is opened in a session
    its help page is shown and pauses. Walks clear pauses wherever they are.
  * **International mail is shown on entry**, before the main menu, in a
    reader that waits on "(Reply, Delete, Ignore, or Quit)". Quit means *quit
    reading*: every later message goes unshown. Ignore leaves it unread and
    moves on, and unlike BRE (7) Communications, (1) Read Messages shows it
    again.
  * **Rankings come from `FE.EXE SCORES`**, not from the packets directly. A
    board can have ingested another's counties and still show empty rankings
    until SCORES has run there (it writes BULLETIN/ply*.txt and bbs*.txt).

Mapped by hand against a v1.06 install (`sr-harness hold`), 2026-10-13.
"""
import re

from sr_harness.driver import Driver, mail_reader
from sr_harness.install import Install

PAUSED = r">Paused<"

OUTER = r"^Falcon's Eye$"
MAIN = r"^Main Menu$"

# Race Selection keys. Humans are the documented beginner's choice: no
# adjustments.
RACES = {"humans": "1", "barbarians": "2", "birdmen": "3", "centaurs": "4",
         "dwarves": "5", "elves": "6", "faeries": "7", "ghosts": "8",
         "ghouls": "9", "goblins": "A", "halflings": "B", "mermaids": "C",
         "minotaurs": "D", "ogres": "E", "orcs": "F", "puppets": "G",
         "sprites": "H", "trolls": "I", "wolves": "J", "zombies": "K"}

# Paging through anything and backing out of any submenu. Submenus default to
# (0) Quit, but "0" is sent rather than <CR> so a default that changes never
# selects something.
_PAGER = [
    (PAUSED, "\r"),
    (r"Continue\?", "Y"),
    (r"\[Hit a key\]|any key", "\r"),
]


READER = r"Reply, Delete, Ignore, or Quit"


def reader(screen):
    """Answer FE's mail reader so that every message is shown exactly once.

    See `driver.mail_reader`: Q quits reading altogether, and I moves on but
    wraps round to the first message forever. What each message said is in the
    transcript (Player.entry_text, read_messages()).
    """
    return mail_reader(screen, "(Reply")


def _then_quit(key):
    """Answer a submenu with `key` the first time and (0) Quit after that.

    A report returns to the menu it was chosen from; answering that menu with
    the same key again would show the report forever.
    """
    pressed = []

    def answer():
        if pressed:
            return "0"
        pressed.append(key)
        return key
    return answer


def prompts(county: str, race: str = "humans", read="Q"):
    """Getting from launch to the county's main menu, joining if new. `read`
    answers the mail reader; Player passes a `reader()`."""
    return [
        (READER, read),
        (r"Do you want ANSI Graphics", "Y"),
        # ── joining ───────────────────────────────────────────────────────
        (r"Select this race\?", "Y"),
        (r"name of your County\?", f"{county}\r"),
        (r"Name Your County .*\?", "Y"),
        (r"Choice>", RACES.get(race.lower(), race), r"^Race Selection$"),
        # (1) is Join Game for a new player and Enter Game for a returning one.
        (r"Choice>", "1", OUTER),
        *_PAGER,
    ]


def turn_prompts(on_take="Y", read="Q"):
    """One month. `on_take` answers "Take your next turn?"; it may be a
    callable, so a count of turns can live in it."""
    return [
        (READER, read),
        (r"Take your next turn\?", on_take),
        # "Give how much silver? (189; 189)": the default pays it all.
        (r"\(\s*[\d,]+;\s*[\d,]+\s*\)\s*$", "\r"),
        *_PAGER,
        (r"\(y/N\)|\(Y/n\)", "\r"),
    ]


class Player(Driver):
    """One interactive FE session, as a player."""

    main_menu = re.compile(r"\[Main Menu\]")
    paused = PAUSED
    # The bottom bar: " TEST PILOT 01   │ A │ Harness County │".
    furniture = (r"│.*│.*│\s*$",)

    def __init__(self, install: Install, county: str, user: str = "TEST PILOT",
                 race: str = "humans", transcript=None, date=None):
        install.write_doorfile(user)
        super().__init__(install.session("FULL", transcript=transcript, date=date))
        self.install, self.county, self.user, self.race = install, county, user, race
        self.turn_text = ""
        self.entry_text = ""       # what start() saw: international mail, news
        self.month = None          # (month played, months per year) after a turn

    def _pager(self):
        return [(READER, reader(lambda: self.screen)), *_PAGER]

    def at_main_menu(self) -> bool:
        return re.match(MAIN, self.menu) is not None and self.prompt.startswith("Choice>")

    def _back_at_main(self, mark):
        """At the main menu, and it has been redrawn since `mark`.

        Without the redraw check a walk that has just pressed a key from the
        main menu sees "Choice> Take Turn" under the main menu's title and
        believes it is already done.
        """
        return lambda p: p.at_main_menu() and "[Main Menu]" in p.session.text_since(mark)

    def start(self, timeout=300.0):
        """Walk from launch to the county's main menu, joining if new."""
        mark = self.session.mark()
        walk = prompts(self.county, self.race, reader(lambda: self.screen))
        if not self.answer_until(self._back_at_main(mark), walk, timeout, label="entry"):
            hint = ""
            if "Duplicate User" in self.screen:
                hint = (f" -- the BBS user name {self.user!r} is already playing on "
                        "another board in this league")
            raise TimeoutError(
                f"never reached FE's main menu{hint}; last prompt was "
                f"{self.prompt!r} in menu {self.menu!r}\n--- screen ---\n{self.screen}"
            )
        self.entry_text = self.session.text_since(mark)
        return self

    def _visit(self, keys, prompts_, timeout, label) -> str:
        """Press `keys` from the main menu, answer `prompts_`, return to the main
        menu, and give back everything printed on the way."""
        mark = self.session.mark()
        for key in keys:
            self.choose(key)
        self.back_to_menu_since(mark, prompts_, timeout, label)
        return self.session.text_since(mark)

    def back_to_menu_since(self, mark, prompts_, timeout, label):
        if not self.answer_until(self._back_at_main(mark), prompts_, timeout, label):
            raise TimeoutError(
                f"{label}: never got back to the main menu; last prompt was "
                f"{self.prompt!r} in menu {self.menu!r}\n--- screen ---\n{self.screen}"
            )

    def status(self, timeout=60.0) -> dict:
        """(C) Council Room, (A) State of the County, parsed."""
        mark = self.session.mark()
        self.choose("C")
        # The Council Room's first-visit help pauses before its menu.
        self.answer_until(lambda p: re.match(r"^Council Room$", p.menu)
                          and p.prompt.startswith("Choice>"), self._pager(), timeout, "status")
        self.choose("A")
        self.back_to_menu_since(mark, [*self._pager(), (r"Choice>", "0")], timeout, "status")
        return parse_status(self.session.text_since(mark))

    def play_turns(self, count: int = 1, timeout=600.0) -> int:
        """Play `count` months, paying every expense in full and doing nothing
        else -- no hiring, building or buying. Returns the number played.

        Everything printed is kept in `turn_text`.
        """
        played, mark = 0, self.session.mark()
        for _ in range(count):
            start = self.session.mark()
            self.choose("-")
            self.back_to_menu_since(start, turn_prompts(read=reader(lambda: self.screen)),
                                    timeout, "turn")
            said = self.session.text_since(start)
            m = re.findall(r"playing month #(\d+) out of (\d+) months", said)
            if not m:
                break
            self.month = tuple(int(x) for x in m[-1])
            played += 1
        self.turn_text = self.session.text_since(mark)
        if played < count:
            raise RuntimeError(
                f"only {played} of {count} months were played -- the county most "
                f"likely has no months left today\n--- last turn ---\n{said[-1500:]}"
            )
        return played

    # (I) International Room, (1) View Rankings opens a menu of reports. As in
    # BRE, individual players appear only under the *Players* reports.
    RANKINGS = {"nations_by_score": "1", "nations_by_worth": "2",
                "nations_by_land": "3", "nations_by_density": "4",
                "players_by_score": "5", "players_by_worth": "6",
                "players_by_land": "7", "players_by_density": "8"}

    def rankings(self, report: str = "players_by_score", timeout=120.0) -> str:
        """(I) International Room, (1) View Rankings, then one report: where
        other boards' counties appear once their packets have been ingested
        *and* `FE.EXE SCORES` has run on this board."""
        key = self.RANKINGS.get(report, report)
        return self._visit(["I"], [
            (r"Choice>", _then_quit("1"), r"^International Operations$"),
            (r"Choice>", _then_quit(key), r"^International Scores$"),
            *self._pager(), (r"Choice>", "0")], timeout, "rankings")

    def read_messages(self, timeout=120.0) -> str:
        """(7) Communications, (1) Read Messages: local mail, and international
        mail that was not deleted on entry."""
        return self._visit(["7"], [
            (r"Choice>", _then_quit("1"), r"^Messages$"),
            *self._pager(), (r"Choice>", "0")], timeout, "messages")

    def send_world_message(self, text: str, timeout=120.0):
        """An international message to every nation: (I) International Room,
        (8) Send Message, (3) World-Wide. (7) Communications on the main menu
        is local to this board.
        """
        mark = self.session.mark()
        self.choose("I")
        if not self.answer_until(lambda p: re.match(r"^International Operations$", p.menu)
                                 and p.prompt.startswith("Choice>"), self._pager(), timeout,
                                 "message"):
            raise TimeoutError(f"International Room never opened\n{self.screen}")
        self.choose("8")
        self.choose("3")
        if not self.session.wait_for(r"(?m)^\s*1>", timeout=30):
            raise RuntimeError(
                f"the message editor never opened; prompt was {self.prompt!r}\n"
                f"--- screen ---\n{self.screen}"
            )
        for line in text.splitlines() or [text]:
            self.session.send(line[:68] + "\r")
            self.session.pump(0.4)
        self.session.send("/S\r")    # /S saves, /A aborts, /C clears
        self.back_to_menu_since(mark, [*self._pager(), (r"Choice>", "0")], timeout, "message")
        self.events.append(f"sent world-wide message: {text!r}")

    def quit(self, timeout=180.0) -> int:
        """Quit the county, then the outer menu, and let outbound run."""
        self.choose("0")
        self.answer_until(lambda p: re.match(OUTER, p.menu) is not None
                          and p.prompt.startswith("Choice>"), self._pager(), 60, "quit")
        rc = self.leave("0", timeout)
        self.install.clear_mutex()
        return rc


# ── parsing ───────────────────────────────────────────────────────────────
# (C) Council Room, (A) State of the County, verbatim from v1.06:
#     State of the County of Harness County founded by Humans in month #0.
#     Housing Land:    100 Acres
#     Total People:    100              Unemployed:    100
#     Approval:         50%
#     Silver:          15,000           Food:              2000
#     Stone Blocks:       200           Weapon Stores:      400
#     Runes:               25
#     Quality Rating: 50%
#     Total Offense: 200 Swords       Total Defense: 200 Shields
#     The county has 20 months of protected status left.
#     There are 8 months per year.
_FIELDS = {
    "land": r"Housing Land:\s*([\d,]+)",
    "people": r"Total People:\s*([\d,]+)",
    "unemployed": r"Unemployed:\s*([\d,]+)",
    "approval": r"Approval:\s*([\d,]+)%",
    "silver": r"Silver:\s*([\d,]+)",
    "food": r"Food:\s*([\d,]+)",
    "stone": r"Stone Blocks:\s*([\d,]+)",
    "weapons": r"Weapon Stores:\s*([\d,]+)",
    "runes": r"Runes:\s*([\d,]+)",
    "quality": r"Quality Rating:\s*([\d,]+)%",
    "offense": r"Total Offense:\s*([\d,]+)",
    "defense": r"Total Defense:\s*([\d,]+)",
    "protection_months": r"([\d,]+) months of protected status",
    "months_per_year": r"There are ([\d,]+) months per year",
}


def parse_status(text: str) -> dict:
    """Pull State of the County out of a transcript or screen.

    Reads the *last* occurrence of each field, as bre.parse_status does. Fields
    not found are left out rather than defaulted: FE's zero-valued lines have
    not been observed yet, and a guessed zero hides a parse failure.
    """
    out = {}
    for name, pattern in _FIELDS.items():
        found = re.findall(pattern, text, re.I)
        if found:
            out[name] = int(found[-1].replace(",", ""))
    county = re.findall(r"State of the County of (.+?) founded by (\w+)", text)
    if county:
        out["county"], out["race"] = county[-1][0].strip(), county[-1][1]
    return out
