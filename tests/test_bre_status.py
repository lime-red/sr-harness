from pathlib import Path

from sr_harness.bre import parse_status

CAPTURE = (Path(__file__).parent / "captures" / "bre_status.txt").read_text()


def test_fresh_realm():
    fresh = CAPTURE.split("=== (2) See Status")[1].split("=== the same block")[0]
    assert parse_status(fresh) == {
        "turns": 8, "score": 0, "gold": 1000, "bank": 0,
        "population_millions": 100, "tax_rate": 15, "popular_support": 100,
        "food": 1000, "realm_name": "Test Realm",
    }


def test_mid_game_reads_the_bank_line_and_thousands():
    mid = CAPTURE.split("=== the same block mid-game")[1]
    status = parse_status(mid)
    assert status["bank"] == 251_272
    assert status["gold"] == 56_652
    assert status["score"] == 1491


def test_the_last_paint_wins():
    assert parse_status("Turns: 8\nScore: 0\n...\nTurns: 7\nScore: 12\n")["turns"] == 7


def test_absent_gold_is_zero_but_absent_food_is_not_invented():
    status = parse_status("-*R*-\nTurns: 1\n")
    assert status["gold"] == 0 and status["bank"] == 0
    assert "food" not in status


class _Screen:
    """Just enough of a session for the screen-reading properties."""
    def __init__(self, text):
        self.text = text

    def screen_text(self):
        return self.text


def test_the_realm_letter_comes_from_the_status_bar():
    from sr_harness.bre import Player
    p = Player.__new__(Player)
    p.session = _Screen("Choice> Play Game\n"
                        " PLAYER TWO          │ B │ Realm Beta │ ■F2=Extra Information")
    assert p.letter == "B"
    # Before the realm exists the bar says UNKNOWN.
    p.session = _Screen(" PLAYER TWO          │ UNKNOWN │ Who knows! │ ■F2=Extra Information")
    assert p.letter == ""


def test_the_bre_reader_shows_each_message_once_then_quits():
    from sr_harness.driver import mail_reader
    one = "│ Message From: Realm Beta\n│ ONE\n[R] Reply, [D] Delete, [I] Ignore, or [Q] Quit>"
    two = "│ Message From: Realm Gamma\n│ TWO\n[R] Reply, [D] Delete, [I] Ignore, or [Q] Quit>"
    screens = iter([one, two, one])
    answer = mail_reader(lambda: next(screens), "[R]")
    assert [answer(), answer(), answer()] == ["I", "I", "Q"]
