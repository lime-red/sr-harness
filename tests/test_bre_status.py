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
