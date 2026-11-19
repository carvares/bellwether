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
from bellwether import prompts
from bellwether.prompts import ACCEPT, DECLINE, TEXT, Option, Prompt, parse
from tests.test_prompts import TIP
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
EDIT_DIFF = shown("claude-edit-diff")
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
        self.press_gate: threading.Event | None = None  # a key waits for it: herdr-core holds the key
        # A `keys` command that did not end before its deadline runs on, and the client tells how it ended through
        # `late`. False: the process is lost at once (the settle rule of the mark applies). True: the test ends it.
        self.keep_key = False
        self.late = None

    def read_screen(self, terminal):
        self.reads.append(terminal)
        if self.read_gate is not None:
            self.read_gate.wait(5)
        item = self.screens.pop(0) if len(self.screens) > 1 else self.screens[0]
        return item() if callable(item) else item

    def press(self, terminal, keys, late=None):
        self.pressed.append((terminal, list(keys)))
        if self.press_gate is not None:
            self.press_gate.wait(5)
        if self.press_result is None and self.on_press:
            self.on_press()
        if self.press_result == Failure("timeout") and late is not None:
            self.late = late
            if not self.keep_key:
                late(Failure("lost"))
        return self.press_result

    def send_text(self, terminal, text, cancel=None):
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
    """One backend with its fake client, its clock, and the states that the prompt went through. `sees`: like an
    answer window that shows the whole detail of each question, the bench reports it seen (`detailSeen`) as soon as
    a question shows; with False, a test reports it itself."""

    def __init__(self, app, tmp_path, agents=BLOCKED, sees=True, **more):
        self.app = app
        self.client = ScreenClient()
        self.now = [100.0]
        self.backend = Backend(
            self.client, settings_path=tmp_path / "config" / "state.json", clock=lambda: self.now[0],
            wait=lambda event, seconds: event.is_set(), follow=more.pop("follow", FOLLOW),
            sent_seconds=more.pop("sent_seconds", 0.0), **more)
        self.states: list[str] = []
        self._last: dict = {}
        self.backend.promptChanged.connect(self._record)
        if sees:
            self.backend.promptChanged.connect(lambda: self.backend.detailSeen(self.backend.prompt["shown"]))
        self.backend.apply(list(agents))

    def _record(self) -> None:
        """The state at each change of the prompt. A change of only `seen` and of the options it allows (the report
        of the bench) is not one."""
        value = {**self.backend.prompt, "seen": None}
        value["options"] = [{**option, "allowed": None} for option in value["options"]]
        if value != self._last:
            self.states.append(value["state"])
        self._last = value

    @property
    def prompt(self) -> dict:
        return self.backend.prompt

    def state(self) -> str:
        return self.backend.prompt["state"]

    def until(self, *states: str) -> bool:
        return wait_for(self.app, lambda: self.state() in states and not self.backend._session.busy)

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
    "screen": "", "reason": "", "message": "", "changed": False, "blind": False, "shown": 0, "seen": False,
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
        **CLOSED, "state": "ready", "shown": 1, "seen": True, "key": "t1", "label": "rev", "program": "claude-code", "address": "t1",
        "kind": "permission", "title": "Bash command", "subtitle": TIP + "\nCreate an empty test file",
        "question": "Do you want to proceed?", "detail": [" touch made-by-test.txt"], "cursor": "1",
        "options": [
            {"key": "1", "label": "Yes", "description": "", "kind": "choice", "effect": "accept", "wide": False,
             "allowed": True},
            {"key": "2", "label": "Yes, and always allow access to /home/dev/projects/sample-app from this project",
             "description": "", "kind": "choice", "effect": "accept", "wide": True, "allowed": True},
            {"key": "3", "label": "Yes, and switch to auto mode · auto mode handles these prompts for you",
             "description": "", "kind": "choice", "effect": "accept", "wide": True, "allowed": True},
            {"key": "4", "label": "No", "description": "", "kind": "choice", "effect": "decline", "wide": False,
             "allowed": True}],
    }


def test_a_question_has_descriptions_kinds_and_the_free_text_flag(bench):
    b = bench()
    b.client.screens = [ASK]
    b.open()
    assert b.prompt["freeText"] is True and b.prompt["kind"] == "question" and b.prompt["title"] == "Drink"
    assert b.prompt["options"] == [
        {"key": "1", "label": "Tea", "description": "Choose tea.", "kind": "choice", "effect": "other", "wide": False,
         "allowed": True},
        {"key": "2", "label": "Coffee", "description": "Choose coffee.", "kind": "choice", "effect": "other",
         "wide": False, "allowed": True},
        {"key": "3", "label": "Type something.", "description": "", "kind": "text", "effect": "other", "wide": False,
         "allowed": True},
        {"key": "4", "label": "Chat about this", "description": "", "kind": "other", "effect": "decline",
         "wide": False, "allowed": True}]


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
    b.backend._session._sent_timer.timeout.emit()
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
    b.client.press_result = Failure("herdr_unavailable")
    b.backend.answer("1")
    assert b.until("failed")
    assert b.prompt["reason"] == "press_herdr_unavailable" and b.client.pressed == [("t1", ["1"])]
    assert b.prompt["message"] == "The answer was not sent, or Herdr did not confirm it."
    assert len(b.client.reads) == 2  # no more reads after the failure


# ----- a key or a text that Herdr did not confirm: it may still arrive -----

MAY_ARRIVE = "Herdr did not confirm the answer. It may still arrive. Check in Herdr."


def test_a_key_that_herdr_does_not_confirm_may_still_arrive_and_the_reads_go_on(bench):
    """herdr-core holds a key while a person types in that terminal, and a killed `keys` still delivers it. A
    timeout is therefore not "failed": the window says that the key may still arrive and reads on, bounded."""
    b = bench(pending_follow=(0.0, 0.0, 0.0, 0.0))
    b.open()
    gate = threading.Event()
    b.client.press_result = Failure("timeout")
    b.client.screens = [BASH, lambda: (gate.wait(5), BASH)[1]]
    b.backend.answer("1")
    assert b.until("pending")
    assert b.prompt["reason"] == "press_timeout" and b.prompt["message"] == MAY_ARRIVE
    assert b.backend.answering is True and b.prompt["question"] == "Do you want to proceed?"
    assert b.backend.answer("1") is False and b.backend.answerText("x") is False
    b.backend.openPrompt("t1")  # does nothing while the key may still arrive
    assert b.state() == "pending"
    gate.set()
    assert b.until("failed")  # the same question at the end of the reads: the key did not arrive (yet)
    assert b.prompt["reason"] == "press_timeout" and b.prompt["message"] == MAY_ARRIVE
    assert len(b.client.reads) == 2 + 4 and b.client.pressed == [("t1", ["1"])]


def test_an_agent_that_goes_on_after_an_unconfirmed_key_is_sent_with_a_note_and_stays(bench):
    b = bench(pending_follow=(0.0, 0.0))
    b.open()
    b.client.press_result = Failure("timeout")
    b.backend.answer("1")
    assert b.until("pending")
    b.backend._snapshot.emit(WORKING)
    assert b.until("sent")
    assert b.prompt["reason"] == "unconfirmed"
    assert b.prompt["message"] == ("The agent went on, but Herdr did not confirm the answer. Check in Herdr that it "
                                   "got yours.")
    assert not b.backend._session._sent_timer.isActive()  # the person reads it and closes the window


def test_a_different_screen_after_an_unconfirmed_key_shows_no_buttons(bench):
    """A new question can be the effect of the key, or of a person in Herdr while the key is still on its way."""
    b = bench(pending_follow=(0.0, 0.0))
    b.open()
    b.client.press_result = Failure("timeout")
    b.client.screens = [BASH, BASH, CREATE]  # before the key, the first read after it, then a new question
    b.backend.answer("1")
    assert b.until("failed")
    assert b.client.reads == ["t1"] * 4 and b.client.pressed == [("t1", ["1"])]
    assert b.states[-2:] == ["pending", "failed"] and b.prompt["reason"] == "press_timeout"
    assert b.prompt["options"] == [] and b.prompt["message"] == MAY_ARRIVE


def test_a_text_that_herdr_does_not_confirm_may_still_arrive(bench):
    b = bench(pending_follow=(0.0,))
    b.client.screens = [ASK]
    b.open()
    b.client.on_press = lambda: b.client.screens.__setitem__(slice(None), [ASK_CURSOR])
    b.client.send_result = Failure("timeout")
    b.backend.answerText("made-up text")
    assert b.until("pending")
    assert b.prompt["reason"] == "send_timeout" and b.prompt["message"] == MAY_ARRIVE
    assert b.until("failed") and b.prompt["reason"] == "send_timeout"


# ----- a key that herdr-core held: a person typed in that terminal just before -----

HELD = "Herdr held the key while someone typed in this terminal. Check in Herdr that it answered the question you saw."


def test_a_held_key_that_answered_says_so_and_the_window_stays(bench):
    b = bench()
    b.open()

    def held():
        b.now[0] += 3.0  # herdr-core gave the key 3 s after the command started
        b.backend._snapshot.emit(WORKING)

    b.client.on_press = held
    b.backend.answer("1")
    assert b.until("sent")
    assert b.prompt["reason"] == "held" and b.prompt["message"] == HELD
    assert not b.backend._session._sent_timer.isActive()


def test_a_held_key_before_a_new_question_says_so(bench):
    b = bench()
    b.open()

    def held():
        b.now[0] += 3.0
        b.client.screens[:] = [CREATE]

    b.client.on_press = held
    b.backend.answer("1")
    assert b.until("ready") and b.prompt["title"] == "Create file"
    assert b.prompt["reason"] == "held" and b.prompt["message"] == HELD and b.prompt["changed"] is False


def test_a_key_that_went_at_once_is_not_held(bench):
    b = bench()
    b.open()

    def quick():
        b.now[0] += 0.05
        b.backend._snapshot.emit(WORKING)

    b.client.on_press = quick
    b.backend.answer("1")
    assert b.until("sent") and b.prompt["reason"] == "" and b.prompt["message"] == "Sent."


# ----- a blind prompt: what it approves is not all on the screen -----

TALL, CODEX_EDIT = shown("claude-create-tall"), shown("codex-edit")
BLIND = "The full content is not visible here. Open it in Herdr to approve."


@pytest.mark.parametrize("screen,agents", [(TALL, BLOCKED), (CODEX_EDIT, [Agent("t1", "blocked", "x", "Main", "codex")])],
                         ids=["cut", "codex-edit"])
def test_a_blind_prompt_allows_only_the_options_that_decline(bench, screen, agents):
    b = bench(agents=agents)
    b.client.screens = [screen]
    b.open()
    assert b.prompt["blind"] is True and b.prompt["message"] == BLIND
    assert [(o["key"], o["effect"], o["allowed"]) for o in b.prompt["options"]] == [
        ("1", "accept", False), ("2", "accept", False), ("3", "decline", True)]
    assert b.backend.answer("1") is False and b.backend.answer("2") is False
    assert b.client.pressed == [] and b.state() == "ready"
    b.client.on_press = lambda: b.backend._snapshot.emit([Agent("t1", "working", "x", "Main", agents[0].app)])
    assert b.backend.answer("3") is True
    assert b.until("sent") and b.client.pressed == [("t1", ["3"])]


def test_a_prompt_that_is_not_blind_has_no_blind_message_and_allows_every_option(bench):
    b = bench()
    b.open()
    assert b.prompt["blind"] is False and b.prompt["message"] == ""
    assert all(option["allowed"] for option in b.prompt["options"])


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
    assert wait_for(b.app, lambda: b.client.pressed and not b.backend._session.busy)
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
    assert b.prompt["message"] == ("The text option was selected but its entry did not open. The text was not sent. "
                                   "Check in Herdr.")


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
    """The key of the text option went: the message must not say that nothing was sent."""
    b = bench()
    b.client.screens = [ASK]
    b.open()
    b.client.on_press = lambda: b.client.screens.__setitem__(slice(None), [CREATE])
    b.backend.answerText("made-up text")
    assert b.until("ready")
    assert b.client.pressed == [("t1", ["3"])] and b.client.sent == [] and b.prompt["changed"] is False
    assert b.prompt["title"] == "Create file" and b.prompt["reason"] == "text_key_only"
    assert b.prompt["message"] == "The text option was selected but the text was not sent. Check in Herdr."
    # The reads go on: the note stays while the same question shows, and goes with the next one.
    b.now[0] += 1.0
    b.backend.apply(list(BLOCKED))
    assert wait_for(b.app, lambda: len(b.client.reads) == 4 and not b.backend._session.busy)
    assert b.prompt["reason"] == "text_key_only"
    b.client.screens = [BASH]
    b.now[0] += 1.0
    b.backend.apply(list(BLOCKED))
    assert wait_for(b.app, lambda: b.prompt["title"] == "Bash command" and not b.backend._session.busy)
    assert b.prompt["reason"] == "" and b.prompt["message"] == ""


def test_a_text_answer_whose_key_went_before_a_screen_with_no_dialog_says_so(bench):
    b = bench()
    b.client.screens = [ASK]
    b.open()
    b.client.on_press = lambda: b.client.screens.__setitem__(slice(None), [NO_DIALOG])
    b.backend.answerText("made-up text")
    assert b.until("unreadable")
    assert b.prompt["reason"] == "text_key_only" and b.client.sent == []


@pytest.mark.parametrize("text,reason,message", [
    ("", "text_empty", "Type a text first."), ("   ", "text_empty", "Type a text first."),
    ("two\nlines", "text_lines", "The text must be one line."),
    ("esc\x1b[2J", "text_control",
     "The text has characters that cannot be sent (control, direction or invisible characters)."),
    ("x" * 2001, "text_long", "The text is too long: at most 2000 characters.")], ids=range(5))
def test_a_text_that_is_not_valid_is_refused_with_a_reason(bench, text, reason, message):
    """The window learns why from the prompt: `reason` and `message`. The question stays ready."""
    b = bench()
    b.client.screens = [ASK]
    b.open()
    assert b.backend.answerText(text) is False
    assert b.state() == "ready" and b.client.pressed == [] and b.client.sent == [] and b.client.reads == ["t1"]
    assert b.prompt["reason"] == reason and b.prompt["message"] == message and b.prompt["freeText"] is True
    b.client.on_press = lambda: b.client.screens.__setitem__(slice(None), [ASK_CURSOR])
    assert b.backend.answerText("a coder \U0001F469\u200D\U0001F4BB") is True  # an emoji sequence is fine
    assert wait_for(b.app, lambda: b.client.sent == [("t1", "a coder \U0001F469\u200D\U0001F4BB")])


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
    assert b.backend._session.prompt is None
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
    assert b.state() == "gone" and b.prompt["screen"] == "" and b.backend._session._screen_text == ""


# ----- refresh while open -----

def test_the_ticks_read_the_screen_again_at_most_two_times_each_second(bench):
    b = bench()
    b.open()
    assert len(b.client.reads) == 1
    for step in range(40):  # four seconds of ticks, ten each second
        b.now[0] += 0.1
        b.backend.apply(list(BLOCKED))
        assert wait_for(b.app, lambda: not b.backend._session.busy)
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
    assert b.until("unreadable") and b.prompt["screen"] == MARKER and b.backend._session.prompt is None
    b.client.screens = [BASH]
    b.now[0] += 1
    b.backend.apply(list(BLOCKED))
    assert b.until("ready")
    assert b.prompt["screen"] == "" and b.backend._session._screen_text == ""  # the text is dropped with the state


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
    assert wait_for(b.app, lambda: len(b.client.reads) == 2 and not b.backend._session.busy)
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
    assert b.prompt == CLOSED and b.backend._session.prompt is None and b.backend._session._screen_text == ""
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
    assert wait_for(b.app, lambda: b.client.pressed and not b.backend._session.busy)
    b.backend.closePrompt()
    assert b.prompt == CLOSED and not b.backend._session._follow_timer.isActive()


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
            assert wait_for(app, lambda: not b.backend._session.busy)
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


# ----- the mark: an earlier answer to a terminal may still arrive, also after a close -----

# The mark ends when the `keys` command ends (it is watched), or by the settle rule: true for both.
EARLIER = ("An earlier answer to this agent may still arrive. Nothing more can be sent until it has arrived or can no "
           "longer arrive. Check in Herdr.")
BOTH_BLOCKED = [Agent("t1", "blocked", "rev", "Main", "claude-code"), Agent("t2", "blocked", "dev", "Main", "codex")]


def unconfirmed_key(b, when="failed"):
    """Answer "1" on BASH; herdr-core does not confirm the key (a killed `keys` still delivers it). The reads after
    it see the same question. `when`: "failed" (the reads ended), or "pending" (a read after the key waits)."""
    b.open()
    gate = threading.Event()
    b.client.press_result = Failure("timeout")
    b.client.screens = [BASH, lambda: (gate.wait(5), BASH)[1]] if when == "pending" else [BASH]
    b.backend.answer("1")
    assert wait_for(b.app, lambda: b.state() == when)
    b.client.press_result = None
    return gate


def nothing_can_be_clicked(prompt: dict) -> bool:
    return all(option["allowed"] is False for option in prompt["options"]) and prompt["freeText"] is False


@pytest.mark.parametrize("when", ["pending", "failed"])
def test_a_close_and_a_reopen_after_an_unconfirmed_key_press_no_second_key(bench, when):
    """The probe of the re-review: Esc, a reopen and a click pressed a second key while the first could still
    arrive. The mark of the terminal stays after the close."""
    b = bench(pending_follow=(0.0, 0.0))
    gate = unconfirmed_key(b, when)
    b.backend.closePrompt()
    gate.set()
    b.backend.openPrompt("t1")
    assert b.until("pending")
    assert b.prompt["reason"] == "earlier" and b.prompt["message"] == EARLIER and b.backend.answering is True
    assert b.prompt["question"] == "Do you want to proceed?" and nothing_can_be_clicked(b.prompt)
    for key in ("1", "2", "3"):
        assert b.backend.answer(key) is False
    assert b.backend.answerText("made-up text") is False
    b.backend.closePrompt()
    b.backend.openPrompt("t1")  # again, and again: the same
    assert b.until("pending") and b.backend.answer("2") is False
    assert b.client.pressed == [("t1", ["1"])] and b.client.sent == []


def test_after_pending_and_failed_an_answer_presses_nothing(bench):
    b = bench(pending_follow=(0.0,))
    unconfirmed_key(b)
    assert b.backend.answer("1") is False and b.backend.answer("2") is False
    b.backend.closePrompt()
    b.backend.openPrompt("t1")
    assert b.until("pending") and b.backend.answer("2") is False
    assert b.client.pressed == [("t1", ["1"])]


def test_the_same_question_never_ends_the_mark_by_time_alone(bench):
    b = bench(pending_follow=(0.0,))
    unconfirmed_key(b)
    b.backend.closePrompt()
    b.backend.openPrompt("t1")
    assert b.until("pending")
    for _ in range(3):
        b.now[0] += 1000.0
        reads = len(b.client.reads)
        b.backend.apply(list(BLOCKED))
        assert wait_for(b.app, lambda: len(b.client.reads) == reads + 1 and not b.backend._session.busy)
        assert b.state() == "pending" and b.prompt["reason"] == "earlier"
    assert b.backend.answer("2") is False and b.client.pressed == [("t1", ["1"])]


def test_a_different_question_ends_the_mark_after_the_settle_time(bench):
    b = bench(pending_follow=(0.0,))
    unconfirmed_key(b)
    b.backend.closePrompt()
    b.client.screens = [CREATE]
    b.backend.openPrompt("t1")
    assert b.until("pending")
    assert b.prompt["title"] == "Create file" and nothing_can_be_clicked(b.prompt)  # the new question, no option
    b.now[0] += 3.9  # herdr-core gives a held key 3.0 s after the last key of a person
    b.backend.apply(list(BLOCKED))
    assert wait_for(b.app, lambda: not b.backend._session.busy) and b.state() == "pending"
    b.now[0] += 0.2
    b.backend.apply(list(BLOCKED))
    assert b.until("ready")
    assert b.prompt["title"] == "Create file" and b.prompt["reason"] == "" and b.prompt["options"][0]["allowed"]
    b.client.on_press = lambda: b.backend._snapshot.emit(WORKING)
    assert b.backend.answer("1") is True
    assert b.until("closed") and b.client.pressed == [("t1", ["1"]), ("t1", ["1"])]


def test_the_answered_question_that_comes_back_starts_the_settle_time_again(bench):
    b = bench(pending_follow=(0.0,))
    unconfirmed_key(b)
    b.backend.closePrompt()
    b.client.screens = [CREATE, BASH, BASH]
    b.backend.openPrompt("t1")
    assert b.until("pending")
    b.now[0] += 3.0
    b.backend.apply(list(BLOCKED))  # BASH again: the key may still come to it
    assert wait_for(b.app, lambda: len(b.client.reads) == 5 and not b.backend._session.busy)
    b.now[0] += 3.0
    b.backend.apply(list(BLOCKED))
    assert wait_for(b.app, lambda: len(b.client.reads) == 6 and not b.backend._session.busy)
    assert b.state() == "pending" and b.backend.answer("1") is False


def test_an_agent_that_is_not_blocked_ends_the_mark_after_the_settle_time_also_with_no_prompt_open(bench):
    b = bench(pending_follow=(0.0,))
    unconfirmed_key(b)
    b.backend.closePrompt()
    reads = len(b.client.reads)
    b.backend.apply(list(WORKING))  # the agent went on: the list shows it, no screen is read
    b.now[0] += 2.0
    b.backend.apply(list(BLOCKED))  # a new question, 2 s later
    b.client.screens = [CREATE]
    b.backend.openPrompt("t1")
    assert b.until("pending")  # not yet: a key that a person's typing holds lands 3 s after their last key
    b.now[0] += 2.5
    b.backend.apply(list(BLOCKED))
    assert b.until("ready") and b.prompt["title"] == "Create file"
    assert len(b.client.reads) == reads + 2


def test_offline_is_not_a_proof_that_the_agent_went_on(bench):
    b = bench(pending_follow=(0.0,))
    unconfirmed_key(b)
    b.backend.closePrompt()
    b.backend.apply(None)  # Herdr is offline: the list is empty
    b.now[0] += 100.0
    b.backend.apply(None)
    b.backend.apply(list(BLOCKED))
    b.backend.openPrompt("t1")
    assert b.until("pending") and b.backend.answer("2") is False


def test_a_pending_prompt_of_an_earlier_answer_is_gone_when_the_agent_goes_on(bench):
    b = bench(pending_follow=(0.0,))
    unconfirmed_key(b)
    b.backend.closePrompt()
    b.backend.openPrompt("t1")
    assert b.until("pending")
    b.backend.apply(list(WORKING))
    assert b.until("gone")


def test_a_key_that_herdr_core_holds_at_the_close_marks_the_terminal_until_it_returns(bench):
    b = bench()
    b.open()
    b.client.press_gate = threading.Event()
    b.backend.answer("1")
    assert wait_for(b.app, lambda: b.client.pressed == [("t1", ["1"])])
    b.backend.closePrompt()
    b.backend.openPrompt("t1")
    assert b.until("pending") and b.prompt["reason"] == "earlier" and b.backend.answer("2") is False
    b.client.press_gate.set()  # herdr-core typed the key: nothing more can arrive
    assert b.until("ready") and b.prompt["reason"] == ""
    assert b.client.pressed == [("t1", ["1"])]


def test_a_held_key_that_is_not_confirmed_after_a_close_keeps_the_mark(bench):
    b = bench()
    b.open()
    b.client.press_gate = threading.Event()
    b.client.press_result = Failure("timeout")
    b.backend.answer("1")
    assert wait_for(b.app, lambda: b.client.pressed == [("t1", ["1"])])
    b.backend.closePrompt()
    b.client.press_gate.set()
    assert wait_for(b.app, lambda: not b.backend._session._marks["t1"].running)
    b.backend.openPrompt("t1")
    assert b.until("pending") and b.backend.answer("2") is False


def held_text(b):
    """A text answer whose `send` herdr-core holds until the cancel of the call is set (then it is killed)."""
    b.client.screens = [ASK]
    b.open()
    b.client.on_press = lambda: b.client.screens.__setitem__(slice(None), [ASK_CURSOR])
    started, returned = threading.Event(), threading.Event()

    def send_text(terminal, text, cancel=None):
        b.client.sent.append((terminal, text))
        started.set()
        killed = cancel.wait(5)
        returned.set()
        return Failure("cancelled") if killed else None

    b.client.send_text = send_text
    assert b.backend.answerText("made-up text") is True
    assert started.wait(3)
    return returned


def test_a_close_during_a_held_text_kills_it_and_ends_the_mark(bench):
    b = bench()
    returned = held_text(b)
    b.backend.closePrompt()
    assert returned.wait(3)
    b.client.screens = [ASK]
    b.backend.openPrompt("t1")
    assert b.until("ready") and b.prompt["reason"] == ""
    assert b.client.sent == [("t1", "made-up text")] and b.client.pressed == [("t1", ["3"])]


def test_the_stop_kills_a_held_text_before_it_returns(bench):
    b = bench()
    returned = held_text(b)
    b.backend.stop()
    assert returned.is_set()


def test_the_marks_of_two_terminals_are_apart(bench):
    b = bench(agents=BOTH_BLOCKED, pending_follow=(0.0,))
    unconfirmed_key(b)
    b.backend.closePrompt()
    b.client.screens = [CODEX]
    b.backend.openPrompt("t2")
    assert b.until("ready") and b.prompt["key"] == "t2" and b.prompt["options"][0]["allowed"]
    b.client.on_press = lambda: b.backend._snapshot.emit([BOTH_BLOCKED[0], WORKING[1]])
    assert b.backend.answer("1") is True
    assert b.until("closed")
    b.client.screens = [BASH]
    b.backend.openPrompt("t1")
    assert b.until("pending") and b.backend.answer("2") is False
    assert b.client.pressed == [("t1", ["1"]), ("t2", ["1"])]


def test_a_key_that_went_or_an_answer_that_sent_nothing_leaves_no_mark(bench):
    b = bench()
    b.open()
    b.client.screens = [CREATE]  # the question changed: nothing goes
    b.backend.answer("1")
    assert b.until("ready") and b.client.pressed == []
    b.client.on_press = lambda: b.client.screens.__setitem__(slice(None), [BASH])
    b.backend.answer("1")  # the key went; the next question is the same as before: the reads end with no_effect
    assert b.until("failed", "ready")
    b.backend.closePrompt()
    b.backend.openPrompt("t1")
    assert b.until("ready") and b.backend._session._marks == {}


def test_an_answer_refused_by_a_mark_says_so(bench):
    """The engine refuses also when the window shows a ready prompt of a terminal with a mark."""
    from bellwether.prompt_session import Mark

    b = bench()
    b.client.screens = [ASK]
    b.open()
    mark = Mark("t1", "a fingerprint")
    mark.running = False
    b.backend._session._marks["t1"] = mark
    assert b.backend.answer("1") is False
    assert b.state() == "pending" and b.prompt["reason"] == "earlier" and b.client.pressed == []
    b.backend._session._set("ready", prompt=b.backend._session.prompt)
    assert b.backend.answerText("made-up text") is False and b.prompt["reason"] == "earlier"


# ----- nothing can be clicked while an answer is on its way -----

def test_no_option_can_be_clicked_while_an_answer_is_on_its_way(bench):
    b = bench(pending_follow=(0.0,))
    b.client.screens = [ASK]
    b.open()
    assert b.prompt["freeText"] is True and all(option["allowed"] for option in b.prompt["options"])
    b.client.read_gate = threading.Event()
    b.backend.answer("1")
    assert b.state() == "answering" and nothing_can_be_clicked(b.prompt) and b.prompt["options"]
    b.client.press_result = Failure("timeout")
    b.client.read_gate.set()
    assert wait_for(b.app, lambda: b.state() == "pending")
    assert nothing_can_be_clicked(b.prompt) and b.prompt["options"]


# ----- a failed check of the address: nothing was sent -----

def test_a_check_that_fails_before_the_key_is_a_plain_failure_that_sent_nothing(bench):
    b = bench()
    b.open()
    b.client.press_result = Failure("check_timeout")
    b.backend.answer("1")
    assert b.until("failed")
    assert b.prompt["reason"] == "check_timeout" and b.states[-2:] == ["answering", "failed"]
    assert b.prompt["message"] == "Herdr did not answer the check of the terminal. Nothing was sent."
    b.client.press_result = Failure("check_failed")
    b.backend.closePrompt()
    b.backend.openPrompt("t1")
    assert b.until("ready")  # no mark: nothing can arrive
    b.backend.answer("1")
    assert b.until("failed") and b.prompt["message"] == "Herdr could not check the terminal. Nothing was sent."


def test_a_check_that_fails_before_the_text_says_that_the_text_did_not_go(bench):
    b = bench()
    b.client.screens = [ASK]
    b.open()
    b.client.on_press = lambda: b.client.screens.__setitem__(slice(None), [ASK_CURSOR])
    b.client.send_result = Failure("check_timeout")
    b.backend.answerText("made-up text")
    assert b.until("failed")
    assert b.prompt["reason"] == "text_check" and "The text was not sent." in b.prompt["message"]


# ----- the engine refusals that no reader reaches today -----

def test_a_blind_prompt_whose_text_option_accepts_refuses_the_text(bench, monkeypatch):
    """No reader gives this prompt: built here, it shows that `answerText` asks `allows` of the text option."""
    blind = Prompt("claude-code", "plan", "", "Made-up question?", (
        Option("1", "No", effect=DECLINE), Option("2", "Made-up text entry", kind=TEXT, effect=ACCEPT)), "1",
        cut=True, blind=True)
    monkeypatch.setattr(prompts, "parse", lambda app, text, complete=True: blind)
    b = bench()
    b.open()
    assert b.prompt["freeText"] is False and [o["allowed"] for o in b.prompt["options"]] == [True, False]
    assert b.backend.answerText("made-up text") is False
    assert b.state() == "ready" and b.client.pressed == [] and b.client.sent == [] and b.client.reads == ["t1"]


def test_a_new_question_while_pending_fails_at_once_and_reads_no_more(bench):
    """The read that shows a different question ends the reads: it does not wait for the end of PENDING_FOLLOW."""
    b = bench(pending_follow=(0.0,) * 8)
    b.open()
    b.client.press_result = Failure("timeout")
    b.client.screens = [BASH, BASH, CREATE]  # before the key, the first read after it, then a new question
    b.backend.answer("1")
    assert b.until("failed")
    assert b.states[-2:] == ["pending", "failed"] and b.prompt["reason"] == "press_timeout"
    assert not b.backend._session._follow_timer.isActive() and b.backend._session._follow_left == ()
    wait_for(b.app, lambda: False, timeout=0.2)
    assert b.client.reads == ["t1"] * 4


def test_a_text_killed_at_its_deadline_keeps_the_mark_for_the_settle_time(bench):
    """A killed `send` is not typed (measured), but herdr-core may have been typing it at the kill: a short bound."""
    b = bench(pending_follow=(0.0,))
    b.client.screens = [ASK]
    b.open()
    b.client.on_press = lambda: b.client.screens.__setitem__(slice(None), [ASK_CURSOR])
    b.client.send_result = Failure("timeout")
    b.backend.answerText("made-up text")
    assert b.until("failed") and b.prompt["reason"] == "send_timeout"
    b.client.send_result = None
    b.backend.closePrompt()
    b.backend.openPrompt("t1")
    assert b.until("pending") and b.prompt["reason"] == "earlier" and b.backend.answerText("other text") is False
    b.now[0] += 4.0
    b.backend.apply(list(BLOCKED))
    assert b.until("ready") and b.client.sent == [("t1", "made-up text")]


def test_a_second_text_is_refused_while_the_first_is_pending_also_after_its_mark_ended(bench):
    """The state check of `answerText`: the mark of a text that was killed at its deadline ends 4 s later while the
    prompt is still pending (the reads go on). A second text must not go then."""
    b = bench(pending_follow=(0.0,))
    b.client.screens = [ASK]
    b.open()
    gate = threading.Event()
    b.client.on_press = lambda: b.client.screens.__setitem__(slice(None), [ASK_CURSOR])
    b.client.send_result = Failure("timeout")
    b.backend.answerText("made-up text")
    b.client.screens[:] = [ASK_CURSOR, lambda: (gate.wait(5), ASK_CURSOR)[1]]
    assert wait_for(b.app, lambda: b.state() == "pending") and b.prompt["reason"] == "send_timeout"
    b.client.send_result = None
    b.now[0] += 5.0  # the mark of the killed text has ended
    assert b.backend.answerText("other text") is False and b.backend.answer("1") is False
    assert b.state() == "pending" and b.client.sent == [("t1", "made-up text")]
    gate.set()


# ----- a `keys` command that does not end before its deadline runs on: its end says what happened -----

def running_key(b, pending_follow=(0.0,)):
    """Answer "1" on BASH; the `keys` command does not end before its deadline and runs on. The reads after it see
    the same question, so the prompt ends as failed (press_timeout) while the command still runs."""
    b.client.keep_key = True
    unconfirmed_key(b)
    assert b.client.late is not None
    return b.client.late


def test_a_key_command_that_ends_well_after_its_deadline_is_delivered_and_the_state_follows_the_screen(bench):
    b = bench(pending_follow=(0.0,))
    late = running_key(b)
    assert b.state() == "failed" and b.prompt["reason"] == "press_timeout"
    b.client.screens = [CREATE]  # the key answered the question: the agent asks its next one
    late(None)
    assert b.until("ready") and b.prompt["title"] == "Create file"
    assert b.prompt["reason"] == "held" and b.prompt["message"] == HELD
    assert b.client.pressed == [("t1", ["1"])]
    assert b.backend.answer("2") is True  # no mark is left: the new question can be answered
    assert b.until("failed", "sent", "ready") and b.client.pressed == [("t1", ["1"]), ("t1", ["2"])]


def test_a_key_command_that_ends_well_while_pending_and_the_agent_goes_on_is_sent_with_the_held_note(bench):
    b = bench(pending_follow=(0.0,))
    b.client.keep_key = True
    gate = unconfirmed_key(b, "pending")
    b.client.result = list(WORKING)
    b.client.late(None)
    gate.set()
    b.backend.apply(list(WORKING))
    assert b.until("sent") and b.prompt["reason"] == "held" and b.prompt["message"] == HELD


def test_a_key_command_that_runs_on_keeps_the_mark_however_long_the_agent_is_away(bench):
    """No settle time while the command runs: herdr-core holds the key with no limit while a person types."""
    b = bench(pending_follow=(0.0,))
    late = running_key(b)
    b.backend.closePrompt()
    b.backend.apply(list(WORKING))
    b.now[0] += 500.0
    b.backend.apply(list(WORKING))
    b.backend.apply(list(BLOCKED))
    b.client.screens = [CREATE]
    b.backend.openPrompt("t1")
    assert b.until("pending") and b.prompt["reason"] == "earlier" and b.backend.answer("1") is False
    late(None)  # the command ended: the key is delivered, the mark ends at once
    assert b.until("ready") and b.prompt["title"] == "Create file" and b.backend.answer("1") is True
    assert b.until("failed", "sent", "ready")


def test_a_key_command_that_ends_with_an_error_after_its_deadline_sent_nothing(bench):
    b = bench(pending_follow=(0.0,))
    late = running_key(b)
    late(Failure("herdr_not_blocked"))
    assert b.until("failed") and b.prompt["reason"] == "press_herdr_not_blocked"
    assert b.prompt["message"] == "The answer was not sent, or Herdr did not confirm it."
    b.backend.closePrompt()
    b.backend.openPrompt("t1")
    assert b.until("ready")  # no mark


def test_a_key_command_that_is_lost_keeps_the_settle_rule(bench):
    b = bench(pending_follow=(0.0,))
    late = running_key(b)
    late(Failure("lost"))
    b.backend.closePrompt()
    b.backend.openPrompt("t1")
    assert b.until("pending") and b.prompt["reason"] == "earlier"
    b.backend.apply(list(WORKING))
    assert b.until("gone")
    b.now[0] += 4.0
    b.backend.apply(list(BLOCKED))
    b.backend.openPrompt("t1")
    assert b.until("ready")


def test_the_end_of_a_key_command_after_the_stop_does_nothing(bench):
    b = bench(pending_follow=(0.0,))
    late = running_key(b)
    b.backend.stop()
    late(None)
    b.app.processEvents()
    assert b.state() == "closed" and b.client.pressed == [("t1", ["1"])]


# ----- for the answer window: the options that approve more than one thing, and the number of the question -----

def test_only_the_plain_yes_is_not_wide_in_every_dialog_of_the_fixtures():
    from bellwether.prompt_session import wide
    seen = {}
    for path in sorted(FIXTURES.glob("*.txt")) + sorted((FIXTURES / "narrow").glob("*.txt")):
        prompt = parse("codex" if "codex" in path.name else "claude-code", path.read_text())
        for option in (prompt.options if prompt else ()):
            if option.effect == ACCEPT:
                seen[option.label] = wide(option)
    plain = {label for label, is_wide in seen.items() if not is_wide}
    assert plain == {"Yes", "Yes, proceed (y)", "Yes, manually approve edits", "Submit answers"}
    wide_ones = {label for label, is_wide in seen.items() if is_wide}
    assert len(wide_ones) >= 6 and all(label.startswith("Yes, ") for label in wide_ones)
    for word in ("always allow", "auto mode", "don't ask again", "accept edits", "allow all edits"):
        assert any(word in label for label in wide_ones) or word == "allow all edits", word
    assert wide(Option("1", "Yes, and something new", effect=ACCEPT)) is True  # not known: wide
    assert wide(Option("1", "No", effect=DECLINE)) is False and wide(Option("1", "Yes", effect="other")) is False


def test_the_map_says_which_options_are_wide(bench):
    b = bench()
    b.open()
    assert [(o["label"][:8], o["wide"]) for o in b.prompt["options"]] == [
        ("Yes", False), ("Yes, and", True), ("Yes, and", True), ("No", False)]


def test_each_different_question_has_its_own_number_and_the_same_question_keeps_it(bench):
    b = bench()
    assert b.prompt["shown"] == 0
    b.open()
    first = b.prompt["shown"]
    assert first > 0
    b.backend.apply(list(BLOCKED))  # a tick reads the same question again
    b.now[0] += 1.0
    b.backend.apply(list(BLOCKED))
    assert b.until("ready") and b.prompt["shown"] == first
    b.client.on_press = lambda: b.client.screens.__setitem__(slice(None), [CREATE])
    assert b.backend.answer("1") is True
    assert b.prompt["shown"] == first  # while the answer is on its way the question is the same
    assert b.until("ready") and b.prompt["title"] == "Create file" and b.prompt["shown"] == first + 1
    b.backend.closePrompt()
    assert b.prompt["shown"] == 0
    b.open()
    assert b.prompt["shown"] == first + 2


# ----- the end of the detail must have been seen before an option that approves -----

LONG = Screen(text_of("claude-bash").replace(" touch made-by-test.txt",
                                             "\n".join(f" made-up line {n}" for n in range(40))), True)


def test_an_option_that_approves_needs_the_end_of_the_detail_seen_and_the_others_do_not(bench):
    b = bench(sees=False)
    b.client.screens = [LONG]
    b.open()
    assert len(b.prompt["detail"]) == 40 and b.prompt["seen"] is False
    assert {o["key"]: o["allowed"] for o in b.prompt["options"]} == {"1": False, "2": False, "3": False, "4": True}
    for accept in ("1", "2", "3"):
        assert b.backend.answer(accept) is False
    assert b.state() == "ready" and b.client.pressed == [] and b.prompt["reason"] == ""
    b.backend.detailSeen(b.prompt["shown"] + 1)  # a number of no question that shows: nothing changes
    b.backend.detailSeen(0)
    assert b.prompt["seen"] is False and b.backend.answer("1") is False
    b.backend.detailSeen(b.prompt["shown"])
    assert b.prompt["seen"] is True and all(o["allowed"] for o in b.prompt["options"])
    assert b.backend.answer("1") is True
    assert b.until("sent", "ready", "failed") and b.client.pressed == [("t1", ["1"])]


def test_a_decline_needs_nothing_seen(bench):
    b = bench(sees=False)
    b.client.screens = [LONG]
    b.open()
    assert b.backend.answer("4") is True
    assert b.until("sent", "ready", "failed") and b.client.pressed == [("t1", ["4"])]


def test_a_new_question_must_be_seen_again_and_an_old_number_does_not_count(bench):
    b = bench(sees=False)
    b.client.screens = [LONG]
    b.open()
    first = b.prompt["shown"]
    b.backend.detailSeen(first)
    assert b.prompt["seen"] is True
    b.client.screens[:] = [EDIT_DIFF]
    b.now[0] += 1
    b.backend.apply(list(BLOCKED))  # a tick reads a different question
    assert wait_for(b.app, lambda: b.prompt["title"] == "Edit file" and not b.backend._session.busy)
    assert b.prompt["shown"] == first + 1 and b.prompt["seen"] is False and b.backend.answer("1") is False
    b.backend.detailSeen(first)  # a late report for the question before: it does not count for this one
    assert b.prompt["seen"] is False
    b.client.screens[:] = [LONG]  # the first question comes back: a new number, and it must be seen again
    b.now[0] += 1
    b.backend.apply(list(BLOCKED))
    assert wait_for(b.app, lambda: b.prompt["title"] == "Bash command" and not b.backend._session.busy)
    assert b.prompt["shown"] == first + 2 and b.prompt["seen"] is False and b.backend.answer("1") is False
    assert b.client.pressed == []


def test_a_question_with_no_detail_needs_nothing_seen(bench):
    b = bench(sees=False)
    b.client.screens = [ASK]
    b.open()
    assert b.prompt["detail"] == [] and b.prompt["seen"] is True and all(o["allowed"] for o in b.prompt["options"])


def test_the_refusal_of_an_unseen_approval_is_logged_with_no_screen_text(bench, caplog):
    b = bench(sees=False)
    b.client.screens = [LONG]
    b.open()
    with caplog.at_level(logging.INFO, logger="bellwether"):
        assert b.backend.answer("2") is False
    assert "result=refused reason=unseen" in caplog.text and "made-up line" not in caplog.text
