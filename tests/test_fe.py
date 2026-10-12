import re
from pathlib import Path

from sr_harness import fe
from sr_harness.fe import parse_status

CAPTURE = (Path(__file__).parent / "captures" / "fe_state_of_county.txt").read_text()


def test_state_of_the_county():
    assert parse_status(CAPTURE) == {
        "land": 100, "people": 100, "unemployed": 100, "approval": 50,
        "silver": 15_000, "food": 2000, "stone": 200, "weapons": 400, "runes": 25,
        "quality": 50, "offense": 200, "defense": 200,
        "protection_months": 20, "months_per_year": 8,
        "county": "Harness County", "race": "Humans",
    }


class _Screen:
    closed = False

    def __init__(self, text):
        self.text = text

    def screen_text(self):
        return self.text


def _player(text):
    p = fe.Player.__new__(fe.Player)
    p.session, p.events = _Screen(text), []
    return p


MAIN = """──────────────────────────────[Main Menu]───────────────────────────────
(-) Take Turn           (5) Commerce            (I) International Room
────────────────────────────────────────────────────────────────────────
Choice> Labor
 TEST PILOT 01       │ A │ Harness County │"""


def test_the_status_bar_is_furniture_and_the_menu_is_read_from_its_title():
    p = _player(MAIN)
    assert p.prompt == "Choice> Labor"
    assert p.menu == "Main Menu"
    assert p.at_main_menu()


def test_a_submenu_drawn_below_the_main_menu_wins():
    p = _player(MAIN.rsplit("\n", 1)[0] + "\n\n───────[Messages]────────\n(1) Read Messages\n"
                "Choice> Quit\n TEST PILOT 01       │ A │ Harness County │")
    assert p.menu == "Messages"
    assert not p.at_main_menu()


def test_bracketed_text_that_is_not_a_title_is_ignored():
    p = _player("──────[Falcon's Eye]──────\n[R]  Reply, [Q]  Quit>")
    assert p.menu == "Falcon's Eye"


def test_then_quit_answers_once():
    answer = fe._then_quit("5")
    assert [answer(), answer(), answer()] == ["5", "0", "0"]


def test_take_turn_is_answered_yes_even_though_the_default_is_no():
    first = next(p for p in fe.turn_prompts()
                 if re.search(p[0], "Take your next turn? (y/N)", re.I))
    assert first[1] == "Y"


def test_the_reader_shows_each_message_once_then_quits():
    one = "│ Message From: A (B)\n│ ONE\n(Reply, Delete, Ignore, or Quit)"
    two = "│ Message From: C (B)\n│ TWO\n(Reply, Delete, Ignore, or Quit)"
    screens = iter([one, two, one])
    answer = fe.reader(lambda: next(screens))
    # Ignore moves on and the reader wraps round; Quit stops all reading.
    assert [answer(), answer(), answer()] == ["I", "I", "Q"]
