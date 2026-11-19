"""The state machine of the backend for the answer to one blocked agent, with a fake client and a fake clock.
No test starts herdr-core. MARKER stands for the private text of a screen."""
import logging
import threading
import time
from pathlib import Path

import pytest

from bellwether.backend import Backend
from bellwether.client import Failure, Screen
from bellwether.icons import Icons
from bellwether.prompts import parse
from bellwether.state import Agent

from .conftest import FakeClient

FIXTURES = Path(__file__).parent / "fixtures" / "prompts"
MARKER = "MARKER-private-screen-text"
FOLLOW = (0.0, 0.0, 0.0)  # three reads after a key, with no wait


def text_of(name: str) -> str:
    return (FIXTURES / f"{name}.txt").read_text()


def shown(name: str) -> Screen:
    return Screen(text_of(name), True)


BASH, ASK, ASK_CURSOR, CREATE = shown("claude-bash"), shown("claude-ask-2"), shown("claude-ask-text-cursor"), shown("claude-create")
NO_DIALOG, CODEX = shown("claude-no-dialog"), shown("codex-command")
BLOCKED = [Agent("t1", "blocked", "rev", "Main", "claude-code"), Agent("t2", "working", "dev", "Main", "codex")]
WORKING = [Agent("t1", "working", "rev", "Main", "claude-code"), Agent("t2", "working", "dev", "Main", "codex")]


class ScreenClient(FakeClient):
    """`screens` is what the next reads give, in sequence; the last one stays. An item that is a function is called."""

    def __init__(self):
        super().__init__()
        self.screens: list = [BASH]
        self.reads: list[str] = []
        self.pressed: list[tuple[str, list[str]]] = []
        self.sent: list[tuple[str, str]] = []
        self.press_result = None
        self.send_result = None
        self.read_gate: threading.Event | None = None
        self.on_press = None  # called after a key or a text went to the terminal

    def read_screen(self, terminal):
        self.reads.append(terminal)
        if self.read_gate is not None:
            self.read_gate.wait(5)
        item = self.screens.pop(0) if len(self.screens) > 1 else self.screens[0]
        return item() if callable(item) else item

    def press(self, terminal, keys):
        self.pressed.append((terminal, list(keys)))
        if self.press_result is None and self.on_press:
            self.on_press()
        return self.press_result

    def send_text(self, terminal, text):
        self.sent.append((terminal, text))
        if self.send_result is None and self.on_press:
            self.on_press()
        return self.send_result


def wait_for(app, condition, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.002)
    return False


class Bench:
    """One backend with its fake client, its clock, and the states that the prompt went through."""

    def __init__(self, app, tmp_path, agents=BLOCKED, **more):
        self.app = app
        self.client = ScreenClient()
        self.now = [100.0]
        self.backend = Backend(
            self.client, settings_path=tmp_path / "config" / "state.json", clock=lambda: self.now[0],
            wait=lambda event, seconds: event.is_set(), follow=more.pop("follow", FOLLOW),
            sent_seconds=more.pop("sent_seconds", 0.0), **more)
        self.states: list[str] = []
        self.backend.promptChanged.connect(lambda: self.states.append(self.backend.prompt["state"]))
        self.backend.apply(list(agents))

    @property
    def prompt(self) -> dict:
        return self.backend.prompt

    def state(self) -> str:
        return self.backend.prompt["state"]

    def until(self, *states: str) -> bool:
        return wait_for(self.app, lambda: self.state() in states and not self.backend._prompt_busy)

    def open(self, key="t1", state="ready"):
        self.backend.openPrompt(key)
        assert self.until(state), self.state()
        return self


@pytest.fixture
def bench(app, tmp_path):
    made = []

    def make(**more):
        made.append(Bench(app, tmp_path, **more))
        return made[-1]

    yield make
    for one in made:
        one.backend.stop()


def labels(prompt: dict) -> list[str]:
    return [option["label"] for option in prompt["options"]]


# ----- the value for QML -----

CLOSED = {
    "state": "closed", "key": "", "label": "", "program": "", "icon": "", "address": "", "kind": "", "title": "",
    "subtitle": "", "question": "", "detail": [], "cut": False, "options": [], "cursor": "", "freeText": False,
    "screen": "", "reason": "", "message": "", "changed": False,
}


def test_the_prompt_starts_closed_with_every_key(bench):
    b = bench()
    assert b.prompt == CLOSED
    assert b.backend.answering is False
    assert b.client.reads == []


def test_open_reads_the_screen_off_the_ui_thread_and_shows_the_prompt(bench):
    b = bench()
    b.client.read_gate = threading.Event()
    b.backend.openPrompt("t1")
    assert b.state() == "loading" and b.prompt["key"] == "t1" and b.prompt["label"] == "rev"
    assert b.prompt["program"] == "claude-code" and b.prompt["address"] == "t1" and b.prompt["options"] == []
    b.client.read_gate.set()
    assert b.until("ready")
    assert b.states == ["loading", "ready"] and b.client.reads == ["t1"]
    assert b.prompt == {
        **CLOSED, "state": "ready", "key": "t1", "label": "rev", "program": "claude-code", "address": "t1",
        "kind": "permission", "title": "Bash command", "subtitle": "Create an empty test file",
        "question": "Do you want to proceed?", "detail": [" touch made-by-test.txt"], "cursor": "1",
        "options": [
            {"key": "1", "label": "Yes", "description": "", "kind": "choice"},
            {"key": "2", "label": "Yes, and always allow access to /home/dev/projects/sample-app from this project",
             "description": "", "kind": "choice"},
            {"key": "3", "label": "Yes, and switch to auto mode · auto mode handles these prompts for you",
             "description": "", "kind": "choice"},
            {"key": "4", "label": "No", "description": "", "kind": "choice"}],
    }


def test_a_question_has_descriptions_kinds_and_the_free_text_flag(bench):
    b = bench()
    b.client.screens = [ASK]
    b.open()
    assert b.prompt["freeText"] is True and b.prompt["kind"] == "question" and b.prompt["title"] == "Drink"
    assert b.prompt["options"] == [
        {"key": "1", "label": "Tea", "description": "Choose tea.", "kind": "choice"},
        {"key": "2", "label": "Coffee", "description": "Choose coffee.", "kind": "choice"},
        {"key": "3", "label": "Type something.", "description": "", "kind": "text"},
        {"key": "4", "label": "Chat about this", "description": "", "kind": "other"}]


def test_the_prompt_has_the_icon_of_the_row(app, tmp_path):
    folder = tmp_path / "app" / "icons"
    folder.mkdir(parents=True)
    (folder / "claude-code.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><path fill="#123456" d="M0 0h1v1z"/></svg>')
    client = ScreenClient()
    backend = Backend(client, settings_path=tmp_path / "state.json", icons=Icons(tmp_path / "app", tmp_path / "cache"), follow=FOLLOW)
    backend.apply(list(BLOCKED))
    backend.openPrompt("t1")
    assert wait_for(app, lambda: backend.prompt["state"] == "ready")
    row = backend.groups[0]["agents"][0]
    assert backend.prompt["icon"] == row["icon"] != ""
    backend.stop()


# ----- open -----

def test_open_of_a_key_that_is_not_in_the_list_does_nothing(bench):
    b = bench()
    for key in ("t9", "", "rev", "t1; rm", MARKER):
        b.backend.openPrompt(key)
    assert b.prompt == CLOSED and b.states == [] and b.client.reads == []


def test_open_of_an_agent_that_is_not_blocked_says_gone_and_reads_nothing(bench):
    b = bench()
    b.backend.openPrompt("t2")
    assert b.state() == "gone" and b.prompt["key"] == "t2" and b.prompt["label"] == "dev"
    assert b.prompt["reason"] == "not_blocked" and b.prompt["message"] == "This agent is not blocked now."
    assert b.client.reads == []


def test_a_program_with_no_reader_shows_the_screen(bench):
    b = bench(agents=[Agent("t1", "blocked", "x", "Main", "gemini")])
    b.client.screens = [Screen("some screen\nof gemini", True)]
    b.open(state="unreadable")
    assert b.prompt["reason"] == "no_reader" and b.prompt["screen"] == "some screen\nof gemini"
    assert b.prompt["message"] == "Bellwether cannot read the questions of this program."
    assert b.prompt["options"] == [] and b.prompt["question"] == "" and b.client.reads == ["t1"]


def test_a_screen_that_the_reader_does_not_know_shows_the_screen(bench):
    b = bench()
    b.client.screens = [NO_DIALOG]
    b.open(state="unreadable")
    assert b.prompt["reason"] == "not_recognised" and b.prompt["screen"] == NO_DIALOG.text
    assert b.prompt["message"] == "Bellwether does not know this screen."


def test_a_screen_that_is_not_complete_is_not_read(bench):
    b = bench()
    b.client.screens = [Screen(BASH.text, False)]
    b.open(state="unreadable")
    assert b.prompt["reason"] == "incomplete" and b.prompt["options"] == []
    assert b.prompt["message"] == "Herdr could not read the whole screen."


def test_a_read_that_fails_at_open_is_failed_with_a_short_message(bench):
    b = bench()
    b.client.screens = [Failure("timeout")]
    b.open(state="failed")
    assert b.prompt["reason"] == "read_timeout" and b.prompt["message"] == "The screen of the agent could not be read."
    assert b.prompt["screen"] == "" and b.prompt["options"] == []


@pytest.mark.parametrize("code", ["herdr_not_found", "herdr_finished", "unknown_terminal"])
def test_a_terminal_that_herdr_does_not_have_is_gone(bench, code):
    b = bench()
    b.client.screens = [Failure(code)]
    b.open(state="gone")
    assert b.prompt["reason"] == code


def test_open_of_a_second_agent_takes_the_place_of_the_first(bench):
    b = bench(agents=[*BLOCKED, Agent("t3", "blocked", "cod", "Main", "codex")])
    b.open()
    b.client.screens = [CODEX]
    b.open("t3")
    assert b.prompt["key"] == "t3" and b.prompt["program"] == "codex" and b.prompt["kind"] == "command"
    assert b.prompt["title"] == "Command approval" and b.states == ["loading", "ready", "loading", "ready"]


def test_a_late_result_of_an_older_open_is_ignored(bench):
    b = bench(agents=[*BLOCKED, Agent("t3", "blocked", "cod", "Main", "codex")])
    gate = threading.Event()

    def slow():
        gate.wait(5)
        return BASH

    b.client.screens = [slow, CODEX]
    b.backend.openPrompt("t1")
    assert wait_for(b.app, lambda: b.client.reads == ["t1"])
    b.open("t3")
    gate.set()
    time.sleep(0.05)
    b.app.processEvents()
    assert b.prompt["key"] == "t3" and b.prompt["kind"] == "command"


# ----- answer -----

def test_an_answer_reads_again_and_presses_one_key_on_the_same_fingerprint(bench):
    b = bench()
    b.open()
    b.client.on_press = lambda: (b.client.screens.__setitem__(slice(None), [NO_DIALOG]), b.backend._snapshot.emit(WORKING))
    assert b.backend.answer("4") is True
    assert b.state() == "answering" and b.backend.answering is True and labels(b.prompt)[3] == "No"
    assert b.until("closed")
    assert b.client.pressed == [("t1", ["4"])] and b.client.sent == []
    assert b.states == ["loading", "ready", "answering", "sent", "closed"]
    assert b.client.reads[:2] == ["t1", "t1"]  # the open, and the read before the key
    assert b.prompt == CLOSED


def test_the_sent_state_shows_before_the_window_closes(bench):
    b = bench(sent_seconds=30.0)
    b.open()
    b.client.on_press = lambda: b.backend._snapshot.emit(WORKING)
    b.backend.answer("1")
    assert b.until("sent")
    assert b.prompt["message"] == "Sent." and b.prompt["options"] == [] and b.prompt["key"] == "t1"
    b.backend._sent_timer.timeout.emit()
    assert b.state() == "closed"


def test_an_answer_on_a_changed_screen_presses_nothing_and_shows_the_new_question(bench):
    b = bench()
    b.open()
    b.client.screens = [CREATE]
    assert b.backend.answer("4") is True
    assert b.until("ready")
    assert b.client.pressed == [] and b.client.sent == []
    assert b.prompt["changed"] is True and b.prompt["reason"] == "changed"
    assert b.prompt["message"] == "The question changed. Nothing was sent."
    assert b.prompt["title"] == "Create file" and labels(b.prompt)[-1] == "No" and len(b.prompt["options"]) == 3
    assert b.states == ["loading", "ready", "answering", "ready"]
    # The next answer is for the new question, and the note goes away.
    b.client.on_press = lambda: b.backend._snapshot.emit(WORKING)
    assert b.backend.answer("3") is True
    assert b.until("closed") and b.client.pressed == [("t1", ["3"])]


def test_an_answer_on_a_screen_with_no_dialog_now_presses_nothing_and_shows_the_screen(bench):
    b = bench()
    b.open()
    b.client.screens = [NO_DIALOG]
    b.backend.answer("1")
    assert b.until("unreadable")
    assert b.client.pressed == [] and b.prompt["changed"] is True and b.prompt["screen"] == NO_DIALOG.text


def test_an_answer_when_the_same_question_has_one_more_option_presses_nothing(bench):
    b = bench()
    b.open()
    b.client.screens = [Screen(BASH.text.replace("   4. No", "   4. Yes, always\n   5. No"), True)]
    b.backend.answer("4")
    assert b.until("ready")
    assert b.client.pressed == [] and b.prompt["changed"] is True and labels(b.prompt)[3:] == ["Yes, always", "No"]


def test_an_answer_when_the_read_fails_presses_nothing(bench):
    b = bench()
    b.open()
    b.client.screens = [Failure("timeout")]
    b.backend.answer("1")
    assert b.until("failed")
    assert b.client.pressed == [] and b.prompt["reason"] == "read_timeout"


def test_a_second_answer_while_one_is_in_flight_is_ignored(bench):
    b = bench()
    b.open()
    b.client.read_gate = threading.Event()
    assert b.backend.answer("1") is True
    assert b.backend.answer("4") is False and b.backend.answerText("text") is False
    b.client.on_press = lambda: b.backend._snapshot.emit(WORKING)
    b.client.read_gate.set()
    assert b.until("closed")
    assert b.client.pressed == [("t1", ["1"])]


@pytest.mark.parametrize("key", ["5", "0", "", "enter", "y", "1 ", "11", MARKER])
def test_a_key_that_the_prompt_does_not_have_is_refused(bench, key):
    b = bench()
    b.open()
    assert b.backend.answer(key) is False
    assert b.state() == "ready" and b.client.pressed == [] and b.client.reads == ["t1"]


def test_the_key_of_the_text_entry_is_not_an_answer(bench):
    b = bench()
    b.client.screens = [ASK]
    b.open()
    assert b.backend.answer("3") is False and b.client.pressed == []
    b.client.on_press = lambda: b.backend._snapshot.emit(WORKING)
    assert b.backend.answer("4") is True  # "Chat about this" ends the question: its key can be pressed
    assert b.until("closed") and b.client.pressed == [("t1", ["4"])]


@pytest.mark.parametrize("state,screens", [
    ("closed", None), ("unreadable", [NO_DIALOG]), ("failed", [Failure("timeout")])])
def test_an_answer_with_no_prompt_ready_is_refused(bench, state, screens):
    b = bench()
    if screens:
        b.client.screens = screens
        b.open(state=state)
    reads = len(b.client.reads)
    assert b.backend.answer("1") is False and b.backend.answerText("text") is False
    assert b.client.pressed == [] and b.client.sent == [] and len(b.client.reads) == reads


def test_a_key_that_herdr_does_not_take_is_failed(bench):
    b = bench()
    b.open()
    b.client.press_result = Failure("timeout")
    b.backend.answer("1")
    assert b.until("failed")
    assert b.prompt["reason"] == "press_timeout" and b.client.pressed == [("t1", ["1"])]
    assert b.prompt["message"] == "The answer was not sent, or Herdr did not confirm it."
    assert len(b.client.reads) == 2  # no more reads after the failure


def test_after_a_key_a_new_question_shows(bench):
    b = bench()
    b.open()
    b.client.on_press = lambda: b.client.screens.__setitem__(slice(None), [NO_DIALOG, CREATE])
    b.backend.answer("1")
    assert b.until("ready")
    assert b.prompt["title"] == "Create file" and b.prompt["changed"] is False
    assert b.states == ["loading", "ready", "answering", "ready"] and b.client.pressed == [("t1", ["1"])]


def test_after_a_key_the_reads_are_bounded_when_the_question_stays(bench):
    b = bench()
    b.open()
    b.backend.answer("1")
    assert b.until("failed")
    assert b.prompt["reason"] == "no_effect"
    assert b.prompt["message"] == "The answer was sent, but the question did not change."
    assert b.client.pressed == [("t1", ["1"])]
    assert len(b.client.reads) == 2 + len(FOLLOW)  # open, before the key, and the bounded reads after it


def test_after_a_key_a_screen_with_no_dialog_and_an_agent_still_blocked_shows_the_screen(bench):
    b = bench()
    b.open()
    b.client.on_press = lambda: b.client.screens.__setitem__(slice(None), [NO_DIALOG])
    b.backend.answer("1")
    assert b.until("unreadable")
    assert b.prompt["reason"] == "not_recognised" and b.prompt["changed"] is False
    assert len(b.client.reads) == 2 + len(FOLLOW)


def test_after_a_key_reads_that_fail_end_in_failed(bench):
    b = bench()
    b.open()
    b.client.on_press = lambda: b.client.screens.__setitem__(slice(None), [Failure("timeout")])
    b.backend.answer("1")
    assert b.until("failed")
    assert b.prompt["reason"] == "read_timeout" and len(b.client.reads) == 2 + len(FOLLOW)


def test_the_agent_that_is_not_blocked_after_a_key_ends_the_reads_at_once(bench):
    b = bench(follow=(30.0, 30.0))
    b.open()
    b.backend.answer("1")
    assert wait_for(b.app, lambda: b.client.pressed and not b.backend._prompt_busy)
    assert b.state() == "answering"
    b.backend.apply(list(WORKING))
    assert b.until("closed") and b.states[-2:] == ["sent", "closed"]
    assert len(b.client.reads) == 2


# ----- free text -----

def test_a_text_answer_opens_the_entry_checks_the_cursor_and_sends_the_text(bench):
    b = bench()
    b.client.screens = [ASK]
    b.open()
    events = []

    def after():
        events.append(len(b.client.pressed) + len(b.client.sent))
        if b.client.sent:
            b.client.screens[:] = [NO_DIALOG]
            b.backend._snapshot.emit(WORKING)
        else:
            b.client.screens[:] = [ASK_CURSOR]

    b.client.on_press = after
    assert b.backend.answerText("yerba mate, 2 é?") is True
    assert b.state() == "answering"
    assert b.until("closed")
    assert b.client.pressed == [("t1", ["3"])] and b.client.sent == [("t1", "yerba mate, 2 é?")]
    assert b.states == ["loading", "ready", "answering", "sent", "closed"]


def test_a_text_answer_is_not_typed_when_the_entry_does_not_open(bench):
    b = bench()
    b.client.screens = [ASK]
    b.open()
    assert b.backend.answerText("made-up text") is True
    assert b.until("failed")
    assert b.client.pressed == [("t1", ["3"])] and b.client.sent == []
    assert b.prompt["reason"] == "text_not_ready"
    assert b.prompt["message"] == "The text entry did not open. Nothing was typed."


def test_a_text_answer_on_a_changed_screen_presses_and_types_nothing(bench):
    b = bench()
    b.client.screens = [ASK]
    b.open()
    b.client.screens = [BASH]
    b.backend.answerText("made-up text")
    assert b.until("ready")
    assert b.client.pressed == [] and b.client.sent == [] and b.prompt["changed"] is True
    assert b.prompt["freeText"] is False


def test_a_text_answer_is_not_typed_when_the_question_changes_after_the_key(bench):
    b = bench()
    b.client.screens = [ASK]
    b.open()
    b.client.on_press = lambda: b.client.screens.__setitem__(slice(None), [CREATE])
    b.backend.answerText("made-up text")
    assert b.until("ready")
    assert b.client.pressed == [("t1", ["3"])] and b.client.sent == [] and b.prompt["changed"] is True
    assert b.prompt["title"] == "Create file"


@pytest.mark.parametrize("text", ["", "   ", "two\nlines", "esc\x1b[2J", "x" * 2001], ids=range(5))
def test_a_text_that_is_not_valid_is_refused(bench, text):
    b = bench()
    b.client.screens = [ASK]
    b.open()
    assert b.backend.answerText(text) is False
    assert b.state() == "ready" and b.client.pressed == [] and b.client.sent == [] and b.client.reads == ["t1"]


def test_a_text_answer_to_a_dialog_with_no_text_entry_is_refused(bench):
    b = bench()
    b.open()
    assert b.prompt["freeText"] is False and b.backend.answerText("made-up text") is False
    assert b.client.pressed == [] and b.client.sent == []


def test_a_text_that_herdr_does_not_take_is_failed(bench):
    b = bench()
    b.client.screens = [ASK]
    b.open()
    b.client.on_press = lambda: b.client.screens.__setitem__(slice(None), [ASK_CURSOR])
    b.client.send_result = Failure("herdr_blocked")
    b.backend.answerText("made-up text")
    assert b.until("failed")
    assert b.prompt["reason"] == "send_herdr_blocked" and b.client.sent == [("t1", "made-up text")]


# ----- gone -----

@pytest.mark.parametrize("agents", [None, [], WORKING, [Agent("t1", "done", "rev", "Main", "claude-code")]],
                         ids=["offline", "not-in-the-list", "working", "done"])
def test_an_agent_that_is_not_blocked_any_more_is_gone(bench, agents):
    b = bench()
    b.open()
    b.backend.apply(agents)
    assert b.state() == "gone" and b.prompt["options"] == [] and b.prompt["question"] == ""
    assert b.prompt["label"] == "rev" and b.prompt["message"] == "This agent is not blocked now."
    assert b.backend._prompt is None
    reads = len(b.client.reads)
    b.now[0] += 10
    b.backend.apply(list(BLOCKED))
    b.backend.apply(agents)
    assert len(b.client.reads) == reads and b.state() == "gone"  # no reads for a prompt that is gone
    assert b.backend.answer("1") is False


def test_an_unreadable_screen_goes_away_when_the_agent_is_not_blocked(bench):
    b = bench()
    b.client.screens = [Screen(MARKER, True)]
    b.open(state="unreadable")
    assert b.prompt["screen"] == MARKER
    b.backend.apply(list(WORKING))
    assert b.state() == "gone" and b.prompt["screen"] == "" and b.backend._screen_text == ""


# ----- refresh while open -----

def test_the_ticks_read_the_screen_again_at_most_two_times_each_second(bench):
    b = bench()
    b.open()
    assert len(b.client.reads) == 1
    for step in range(40):  # four seconds of ticks, ten each second
        b.now[0] += 0.1
        b.backend.apply(list(BLOCKED))
        assert wait_for(b.app, lambda: not b.backend._prompt_busy)
    assert 6 <= len(b.client.reads) - 1 <= 8
    assert b.states == ["loading", "ready"]  # the same screen: no change for QML


def test_a_tick_shows_a_new_question_and_a_screen_that_is_not_known(bench):
    b = bench()
    b.open()
    b.client.screens = [CREATE]
    b.now[0] += 1
    b.backend.apply(list(BLOCKED))
    assert wait_for(b.app, lambda: b.prompt["title"] == "Create file")
    assert b.prompt["changed"] is False and b.state() == "ready"
    b.client.screens = [Screen(MARKER, True)]
    b.now[0] += 1
    b.backend.apply(list(BLOCKED))
    assert b.until("unreadable") and b.prompt["screen"] == MARKER and b.backend._prompt is None
    b.client.screens = [BASH]
    b.now[0] += 1
    b.backend.apply(list(BLOCKED))
    assert b.until("ready")
    assert b.prompt["screen"] == "" and b.backend._screen_text == ""  # the text is dropped with the state


def test_a_status_change_of_the_agent_reads_the_screen_again(bench):
    b = bench()
    b.open()
    b.now[0] += 1
    b.backend.apply([Agent("t1", "blocked", "rev", "Other", "claude-code"), BLOCKED[1]])
    assert wait_for(b.app, lambda: len(b.client.reads) == 2)


def test_a_tick_read_that_fails_keeps_the_prompt(bench):
    b = bench()
    b.open()
    b.client.screens = [Failure("timeout")]
    b.now[0] += 1
    b.backend.apply(list(BLOCKED))
    assert wait_for(b.app, lambda: len(b.client.reads) == 2 and not b.backend._prompt_busy)
    assert b.state() == "ready" and b.prompt["title"] == "Bash command"


def test_a_cursor_that_moves_is_a_change_for_qml_and_not_a_new_question(bench):
    b = bench()
    b.client.screens = [ASK]
    b.open()
    b.client.screens = [ASK_CURSOR]
    b.now[0] += 1
    b.backend.apply(list(BLOCKED))
    assert wait_for(b.app, lambda: b.prompt["cursor"] == "3")
    assert b.state() == "ready" and b.prompt["changed"] is False


def test_no_reads_when_no_prompt_is_open(bench):
    b = bench()
    for step in range(5):
        b.now[0] += 1
        b.backend.apply(list(WORKING if step % 2 else BLOCKED))
    b.open()
    b.backend.closePrompt()
    reads = len(b.client.reads)
    for step in range(5):
        b.now[0] += 1
        b.backend.apply(list(WORKING if step % 2 else BLOCKED))
    b.app.processEvents()
    assert len(b.client.reads) == reads == 1


# ----- close, stop, memory -----

def test_close_drops_the_prompt_and_the_screen_text(bench):
    b = bench()
    b.client.screens = [Screen(MARKER, True)]
    b.open(state="unreadable")
    b.backend.closePrompt()
    assert b.prompt == CLOSED and b.backend._prompt is None and b.backend._screen_text == ""
    assert MARKER not in repr(vars(b.backend))
    b.backend.closePrompt()  # a second close changes nothing
    assert b.states == ["loading", "unreadable", "closed"]


def test_stop_drops_the_prompt_and_the_screen_text(bench):
    b = bench()
    b.client.screens = [Screen(MARKER, True)]
    b.open(state="unreadable")
    b.backend.stop()
    assert b.prompt == CLOSED and MARKER not in repr(vars(b.backend))
    b.backend.openPrompt("t1")
    assert b.prompt == CLOSED  # nothing opens after the stop


def test_a_close_before_the_key_presses_nothing(bench):
    b = bench()
    b.open()
    b.client.read_gate = threading.Event()
    b.backend.answer("1")
    assert wait_for(b.app, lambda: len(b.client.reads) == 2)
    b.backend.closePrompt()
    b.client.read_gate.set()
    time.sleep(0.05)
    b.app.processEvents()
    assert b.client.pressed == [] and b.prompt == CLOSED


def test_a_close_while_the_reads_after_a_key_run_stops_them(bench):
    b = bench(follow=(30.0, 30.0))
    b.open()
    b.backend.answer("1")
    assert wait_for(b.app, lambda: b.client.pressed and not b.backend._prompt_busy)
    b.backend.closePrompt()
    assert b.prompt == CLOSED and not b.backend._follow_timer.isActive()


def test_an_error_in_the_worker_is_failed_and_logs_the_class_only(bench, caplog):
    b = bench()

    def broken():
        raise RuntimeError(MARKER)

    b.client.screens = [broken]
    with caplog.at_level(logging.DEBUG, logger="bellwether"):
        b.open(state="failed")
    assert b.prompt["reason"] == "error" and b.prompt["message"] == "Bellwether had an error. Open the agent in Herdr."
    assert all(MARKER not in record.getMessage() and record.exc_info is None for record in caplog.records)
    assert any("error=RuntimeError" in record.getMessage() for record in caplog.records)


def test_qml_reads_the_prompt_and_calls_the_slots(bench):
    """The interface for the answer window: QML sees the map and its lists, the flag, the signal and the slots."""
    import shiboken6
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    b = bench()
    b.client.screens = [ASK]
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("backend", b.backend)
    component = QQmlComponent(engine)
    component.setData(b"""
        import QtQml
        QtObject {
            property string state: backend.prompt.state
            property string firstLabel: backend.prompt.options.length ? backend.prompt.options[0].label : ""
            property string lastKind: backend.prompt.options.length ? backend.prompt.options[3].kind : ""
            property int details: backend.prompt.detail.length
            property bool freeText: backend.prompt.freeText
            property bool answering: backend.answering
            property int changes: 0
            property var refused
            property var accepted
            property var connection: Connections {
                target: backend
                function onPromptChanged() { changes += 1 }
            }
            function open() { backend.openPrompt("t1") }
            function refuse() { refused = [backend.answer("9"), backend.answerText("")] }
            function accept() { accepted = backend.answer("2") }
            function close() { backend.closePrompt() }
        }""", QUrl())
    item = component.create()
    assert isinstance(item, QObject), component.errorString()
    item.open()
    assert b.until("ready")
    assert (item.property("state"), item.property("firstLabel"), item.property("lastKind")) == ("ready", "Tea", "other")
    assert item.property("details") == 0 and item.property("freeText") is True and item.property("changes") == 2
    item.refuse()
    assert item.property("refused").toVariant() == [False, False]
    b.client.read_gate = threading.Event()
    item.accept()
    assert item.property("accepted") is True and item.property("answering") is True
    item.close()
    b.client.read_gate.set()
    assert item.property("state") == "closed" and item.property("answering") is False
    shiboken6.delete(item)  # before the engine: its bindings read `backend`
    shiboken6.delete(component)
    shiboken6.delete(engine)


# ----- the rows -----

def test_the_rows_of_blocked_agents_can_be_answered(bench):
    b = bench(agents=[
        Agent("t1", "blocked", "rev", "Main", "claude-code"), Agent("t2", "blocked", "x", "Main", "gemini"),
        Agent("box/t7", "blocked", "far", "Main", "codex"), Agent("t3", "working", "dev", "Main", "codex"),
        Agent("t4", "done", "d", "Main", "codex"), Agent("t5", "idle", "i", "Main", "codex"),
        Agent("reviewer", "blocked", "odd", "Main", "codex")])
    flags = {row["key"]: row["canAnswer"] for group in b.backend.groups for row in group["agents"]}
    assert flags == {"t1": True, "t2": True, "box/t7": True, "t3": False, "t4": False, "t5": False,
                     "reviewer": False}  # a key that is not an address cannot be read


# ----- privacy -----

def test_no_text_of_a_screen_is_in_a_log_record_or_in_a_file(app, tmp_path, caplog, monkeypatch):
    """Run the whole state machine over screens that hold MARKER: in the detail of a dialog, in a question, in a
    label, in a screen that is not known, and in errors. No log record and no file has it."""
    homes = {name: tmp_path / name for name in ("config", "state", "cache")}
    for name, home in homes.items():
        home.mkdir()
        monkeypatch.setenv(f"XDG_{name.upper()}_HOME", str(home))
    caplog.set_level(logging.DEBUG)
    marked = [
        Screen(BASH.text.replace("touch made-by-test.txt", f"echo {MARKER}"), True),
        Screen(ASK.text.replace("Which drink do you want: tea or coffee?", f"Which {MARKER}?"), True),
        Screen(ASK.text.replace("Coffee", MARKER), True),
        Screen(CODEX.text.replace("touch made-by-test.txt", MARKER), True),
        Screen(NO_DIALOG.text + "\n" + MARKER, True),
        Screen(MARKER, False),
    ]
    b = Bench(app, tmp_path, agents=[*BLOCKED, Agent("t3", "blocked", "cod", "Main", "codex"),
                                     Agent("t4", "blocked", "gem", "Main", "gemini")])
    try:
        for place, first in enumerate(marked):
            key = "t3" if "Codex" in first.text or place == 3 else "t1"
            assert parse("codex" if key == "t3" else "claude-code", first.text, first.complete) or place >= 4
            # Open, refresh, a refused key, an answer on the same screen with no effect, and a close.
            b.client.screens = [first]
            b.open(key, state="ready" if place < 4 else "unreadable")
            assert MARKER in repr(b.prompt)  # the test is real: the text is in the value for QML
            b.now[0] += 1
            b.backend.apply(list(b.backend._agents))
            assert wait_for(app, lambda: not b.backend._prompt_busy)
            b.backend.answer(MARKER)
            b.backend.answerText(MARKER + "\n")
            if place < 4:
                b.backend.answer("1")
                assert b.until("failed")
                # A changed screen, and a text answer that does not go.
                b.client.screens = [first]
                b.open(key)
                b.client.screens = [marked[(place + 1) % 4]]
                b.backend.answer("1")
                assert b.until("ready", "unreadable")
                if b.prompt["freeText"]:
                    b.backend.answerText(f"text {MARKER}")
                    assert b.until("failed", "ready", "unreadable")
            b.backend.closePrompt()
        # Errors with the text in them, and a program with no reader.
        def broken():
            raise RuntimeError(MARKER)

        b.client.screens = [broken]
        b.open("t1", state="failed")
        b.client.screens = [Screen(MARKER, True)]
        b.open("t4", state="unreadable")
        b.backend.apply(None)
        assert b.state() == "gone"
    finally:
        b.backend.stop()
    assert b.client.pressed and len(caplog.records) > 20
    for record in caplog.records:
        assert MARKER not in record.getMessage() and MARKER not in repr(record.args) and record.exc_info is None
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert MARKER.encode() not in path.read_bytes(), path.name
    assert MARKER not in repr(vars(b.backend))
