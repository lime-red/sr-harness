"""answer_until's rules, against a fake session that scripts what the screen shows."""
import re

from sr_harness import driver
from sr_harness.driver import Driver


class FakeSession:
    """Each key sent advances to the screen `script` maps it to."""

    def __init__(self, first, script):
        self.current, self.script, self.sent, self.closed = first, script, [], False

    def pump(self, timeout=0):
        pass

    def screen_text(self):
        return self.current

    def send(self, keys):
        self.sent.append(keys)
        self.current = self.script.get((self.current, keys), self.current)


class Game(Driver):
    main_menu = re.compile(r"\(2\) See Status")
    furniture = ("F2=Extra Information",)


def _no_sleep(monkeypatch):
    monkeypatch.setattr(driver.time, "sleep", lambda s: None)


def test_matches_the_live_prompt_not_furniture(monkeypatch):
    _no_sleep(monkeypatch)
    g = Game(FakeSession("Do you want ANSI Graphics? (Y/n)\n\nF2=Extra Information", {}))
    assert g.prompt == "Do you want ANSI Graphics? (Y/n)"


def test_a_prompt_already_answered_is_not_hammered(monkeypatch):
    _no_sleep(monkeypatch)
    # The screen never changes after the first Y: answer once, then wait.
    s = FakeSession("Continue? (Y/n)", {})
    g = Game(s)
    assert not g.answer_until(lambda p: False, [(r"Continue\?", "Y")], timeout=0.05)
    assert s.sent == ["Y"]


def test_specific_before_generic_and_reaches_the_menu(monkeypatch):
    _no_sleep(monkeypatch)
    menu = "(2) See Status\nChoice>"
    s = FakeSession("Do you wish to continue? (Y/n)", {
        ("Do you wish to continue? (Y/n)", "N"): "page 1\nContinue? (Y/n)",
        ("page 1\nContinue? (Y/n)", "Y"): menu,
    })
    g = Game(s)
    ok = g.answer_until(lambda p: p.at_main_menu(),
                        [(r"Do you wish to continue", "N"), (r"Continue\?", "Y")],
                        timeout=1)
    assert ok and s.sent == ["N", "Y"]


def test_callable_answers_are_evaluated_when_they_fire(monkeypatch):
    _no_sleep(monkeypatch)
    calls = []
    s = FakeSession("Do you wish to continue?", {("Do you wish to continue?", "N"): "x"})
    Game(s).answer_until(lambda p: p.screen == "x",
                         [(r"continue", lambda: calls.append(1) or "N")], timeout=1)
    assert calls == [1]
