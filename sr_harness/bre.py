"""Drive Barren Realms Elite as a *player*.

Unattended maintenance (`BRE.EXE PLANETARY`) needs nothing answered and runs
through `Install.run`. `BRE.EXE FULL` is the player path, and headless it blocks
forever on "Do you want ANSI Graphics? (Y/n)"; this module answers it.

The walks were derived by observation against a real v0.988 install, not from the
docs; `prompts()` below is a transcript of what the game actually asks.
"""
import re
import time

from sr_harness.driver import Driver
from sr_harness.install import Install

PAUSED = r">Paused<"


def prompts(realm: str, on_continue="N"):
    """(regex, keys) pairs, matched in order against the *live prompt only*.

    Order is significant twice over:
      * "Do you wish to continue?" must precede the generic "Continue?", whose
        pattern also matches it -- and that prompt is how BRE advances to the
        next turn, so answering it wrongly either stops after one turn or plays
        every turn the realm has. `on_continue` may be a callable so the count
        can live in the answer.
      * the generic yes/no fallback must come last, or it eats the specific ones.

    `<CR>` on a yes/no prompt takes whichever answer the game capitalised, which
    is what "play a turn without doing anything" means -- the defaults are the
    do-nothing path, and BRE offers them everywhere.
    """
    return [
        # ── getting in, and creating the realm on first play ──────────────
        (r"Do you want ANSI Graphics",   "Y"),
        (r"IBM Characters",              "Y"),
        (r"Name your Realm",             f"{realm}\r"),
        (r"Name Your Empire",            "Y"),
        (r"Would you like Instructions", "N"),
        # ── the daily turn sequence ───────────────────────────────────────
        # Y plays another turn, N ends play and returns to the main menu.
        (r"Do you wish to continue",     on_continue),
        (r"Do you wish to send a message", "\r"),
        (r"Do you wish to visit the Bank", "\r"),
        # "How much will you give? (40; 40)" / "Buy how many Jets? (0; 120)"
        (r"\(\s*[\d,]+;\s*[\d,]+\s*\)\s*$", "\r"),
        # Interplanetary mail is shown at the START OF PLAY, after any local
        # messages -- never under (6) Read Messages -- and each one waits on its
        # own reader prompt, which looks nothing like a menu:
        #     [R]  Reply, [D]  Delete, [I]  Ignore, or [Q]  Quit>
        # Q leaves the mail alone and closes the reader. The text has already
        # been captured by then (see play_turns), so nothing is lost by not
        # paging through the rest.
        (r"\[R\]\s+Reply|\[Q\]\s+Quit>", "Q"),
        (PAUSED,                         "\r"),
        (r"Continue\?",                  "Y"),
        (r"\[Hit a key\]|any key",       "\r"),
        # Quit out of every submenu: Diplomacy, Food Hall, Covert Ops, Bank,
        # Spending, Attacks, Trading.
        (r"Choice>",                     "0"),
        (r"\(y/N\)|\(Y/n\)",             "\r"),
    ]


# Paging through a read-only screen and back out to the main menu.
_READER = [(PAUSED, "\r"), (r"Continue\?", "Y"), (r"\[Hit a key\]|any key", "\r"),
           (r"Choice>", "0")]


class Player(Driver):
    """One interactive BRE session, as a player."""

    # The banner, not "Choice>": see Driver.main_menu.
    main_menu = re.compile(r"\(2\) See Status")
    paused = PAUSED
    furniture = ("F2=Extra Information",)

    def __init__(self, install: Install, realm: str, user: str = "TEST PILOT",
                 transcript=None, date=None):
        install.write_doorfile(user)
        super().__init__(install.session("FULL", transcript=transcript, date=date))
        self.install, self.realm, self.user = install, realm, user
        self.turn_text = ""

    def start(self, timeout=300.0):
        """Walk from launch to the main menu, creating the realm if new."""
        ok = self.answer_until(lambda p: p.at_main_menu(), prompts(self.realm),
                               timeout, label="entry")
        if not ok:
            hint = ""
            if "Duplicate User" in self.screen:
                hint = (f" -- the BBS user name {self.user!r} is already playing on "
                        "another board in this league, and BRE refuses the join")
            raise TimeoutError(
                f"never reached BRE's main menu{hint}; last prompt was "
                f"{self.prompt!r}\n--- screen ---\n{self.screen}"
            )
        return self

    def status(self, timeout=60.0) -> dict:
        """Read (2) See Status and parse it."""
        mark = self.session.mark()
        self.choose("2")
        self.answer_until(lambda p: p.at_main_menu(), [(PAUSED, "\r")], timeout,
                          label="status")
        return parse_status(self.session.text_since(mark))

    def read_screens(self, *keys, timeout=180.0, label="read") -> str:
        """Press `keys` from the main menu, page through whatever comes back, and
        return the text produced -- then end up back at the main menu.

        For the read-only screens (IPScores, Read Messages, news), where what
        matters is what the game says, not a state change.
        """
        mark = self.session.mark()
        for key in keys:
            self.choose(key)
        self.answer_until(lambda p: p.at_main_menu(), _READER, timeout, label=label)
        return self.session.text_since(mark)

    # (9) InterPlanetary Ops, (1) View IPScores opens a menu of reports, not a
    # listing. Individual realms appear only under the *Players* reports; the
    # Planets ones are per-board totals and never name a realm.
    IP_SCORE_REPORTS = {"planets_by_score": "1", "planets_by_worth": "2",
                        "planets_by_land": "3", "planets_by_density": "4",
                        "players_by_score": "5", "players_by_worth": "6",
                        "players_by_land": "7", "players_by_density": "8"}

    def ip_scores(self, report: str = "players_by_score", timeout=180.0) -> str:
        """(9) InterPlanetary Ops, (1) View IPScores, then one report.

        This is where another planet's realms appear once their packet has been
        ingested.
        """
        key = self.IP_SCORE_REPORTS.get(report, report)
        return self.read_screens("9", "1", key, timeout=timeout, label="ipscores")

    def read_messages(self, timeout=180.0) -> str:
        """(6) Read Messages -- local mail only; see play_turns for IP mail."""
        return self.read_screens("6", timeout=timeout, label="messages")

    def play_turns(self, count: int = 1, timeout=900.0) -> int:
        """Play `count` turns, taking every default -- the do-nothing path.

        One press of (1) plays a turn and then asks "Do you wish to continue?";
        Y runs straight into the next one. So this is a single trip through Play
        Game, with the answer to that prompt counting down.

        Even a do-nothing turn moves the score: production runs and taxes are
        collected.

        Everything the turn printed is kept in `turn_text`. Interplanetary mail
        is only readable here -- BRE shows it at the start of play, after any
        local messages, and never under (6) Read Messages.
        """
        remaining = {"turns": count}
        mark = self.session.mark()

        def on_continue():
            remaining["turns"] -= 1
            return "Y" if remaining["turns"] > 0 else "N"

        self.choose("1")
        ok = self.answer_until(lambda p: p.at_main_menu(),
                               prompts(self.realm, on_continue), timeout, label="turn")
        if not ok:
            raise TimeoutError(
                f"play did not end back at the main menu; last prompt was "
                f"{self.prompt!r}\n--- screen ---\n{self.screen}"
            )
        self.turn_text = self.session.text_since(mark)
        played = count - max(remaining["turns"], 0)
        if played < count:
            raise RuntimeError(
                f"only {played} of {count} turns were played -- the realm most "
                f"likely ran out of turns for today"
            )
        return played

    def send_ip_message(self, text: str, timeout=180.0):
        """Send an interplanetary message to every planet.

        (7) Send Messages on the main menu is *local*: it asks "(A-Y,Z=All)
        Send to:" and only reaches realms on this board. Interplanetary mail --
        the kind that becomes a packet -- is (9) InterPlanetary Ops, (7) Send
        Message, and then a scope. (3) All Planets needs no planet number.
        """
        self.choose("9")            # InterPlanetary Operations
        self.choose("7")            # Send Message
        self.choose("3")            # All Planets
        if not self.session.wait_for(r"(?m)^\s*1>", timeout=30):
            raise RuntimeError(
                f"the message editor never opened; prompt was {self.prompt!r}\n"
                f"--- screen ---\n{self.screen}"
            )
        for line in text.splitlines() or [text]:
            self.session.send(line[:68] + "\r")
            time.sleep(0.4)
        self.session.send("/S\r")   # /S saves, /A aborts, /C clears
        self.back_to_menu(prompts(self.realm), timeout, label="message")
        self.events.append(f"sent IP message: {text!r}")

    def quit(self, timeout=180.0) -> int:
        rc = self.leave("0", timeout)
        self.install.clear_mutex()
        return rc


# ── parsing ───────────────────────────────────────────────────────────────
# The See Status block, verbatim from a running v0.988 game:
#     -*Test Realm*-
#     Turns: 8
#     Score: 0
#     Gold: 1000
#     Bank: 251,272           <- absent when zero
#     Population: 100 Million (Tax Rate: 15%)
#     Popular Support: 100%
#     Food: 1000
_FIELDS = {
    "turns": r"Turns:\s*([\d,]+)",
    "score": r"Score:\s*([\d,]+)",
    "gold": r"Gold:\s*([\d,]+)",
    "bank": r"Bank:\s*([\d,]+)",
    "population_millions": r"Population:\s*([\d,]+)\s*Million",
    "tax_rate": r"Tax Rate:\s*([\d,]+)%",
    "popular_support": r"Popular Support:\s*([\d,]+)%",
    "food": r"Food:\s*([\d,]+)",
}

# BRE omits a line entirely rather than printing a zero, so a realm holding no
# cash has no "Gold:" line at all and one with an empty account has no "Bank:".
# Absent therefore means zero for these two, and only these two -- defaulting the
# rest would turn a parse failure into a plausible-looking number. BRE never
# produces negative gold or food either; the only debt is a bank loan.
_ZERO_WHEN_ABSENT = ("gold", "bank")


def parse_status(text: str) -> dict:
    """Pull the status block out of a transcript.

    Reads the *last* occurrence of each field: the screen is repainted, and on a
    VGA terminal an earlier paint of the same block is still in the history.
    """
    out = {}
    for name, pattern in _FIELDS.items():
        found = re.findall(pattern, text, re.I)
        if found:
            out[name] = int(found[-1].replace(",", ""))
        elif name in _ZERO_WHEN_ABSENT:
            out[name] = 0
    realm = re.findall(r"-\*(.+?)\*-", text)
    if realm:
        out["realm_name"] = realm[-1].strip()
    return out


__all__ = ["Player", "parse_status", "prompts", "PAUSED"]
