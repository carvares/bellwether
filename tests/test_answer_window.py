"""The answer window (Answer.qml) through the real panel, the real backend and its prompt engine, and a client of
made-up screens: what shows in each state, what a click and a key send (one key after a new read, or nothing), the
guard after a new question, the text field, the ways to close. No test starts herdr-core."""
import re
import threading

import pytest
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QWheelEvent
from PySide6.QtTest import QTest

from bellwether import layouts
from bellwether.client import Failure, Screen
from bellwether.prompt_session import MESSAGES
from bellwether.state import Agent
from tests.audit import text_findings
from tests.test_answer_control import LEFT, LETTERS, NONE, Panel, centre
from tests.test_backend_prompt import ASK, BASH, CREATE, FIXTURES, NO_DIALOG, TIP, shown, wait_for
from tests.test_options_look import focused, items, js, key, tab_order, type_text
from tests.test_qml import LAYERSHELL_QMLDIR, click, settle, walk
from tests.test_skins import spoken, wait_jump

pytestmark = pytest.mark.skipif(not LAYERSHELL_QMLDIR.is_file(), reason="org.kde.layershell is not installed")

CODEX_EDIT, CODEX, TALL, EDIT = shown("codex-edit"), shown("codex-command"), shown("claude-create-tall"), shown("claude-edit-diff")
MARKER = "MARKER-private-screen-text"
UNKNOWN = Screen(f"made-up line one\n{MARKER}\n   made-up line three\n\n\n", True)
AGENTS = [
    Agent("t1", "blocked", "rev", "Main", "claude-code"),
    Agent("t7", "blocked", "dev", "api / 1", "codex"),
    Agent("t2", "working", "ana", "api / 1", "codex"),
]
GONE = [Agent("t1", "working", "rev", "Main", "claude-code"), *AGENTS[1:]]


class Desk(Panel):
    """The panel with the answer window open for one agent."""

    def answer_for(self, key="t1", state="ready", quiet=300):
        """Open the window for the agent `key`. `quiet`: the quiet time of the number keys after a new question, short
        here to keep the tests fast (None: the window's own, 1000 ms)."""
        self.open_group("blocked")
        click(self.app, self.root, self.control(key))
        if quiet is not None:
            self.window.setProperty("keyQuietMs", quiet)
        assert wait_for(self.app, lambda: self.state() == state and not self.backend._session.busy), self.state()
        self.window.setProperty("roomHeight", 1080)
        settle(self.app)
        return self.window

    def arm(self):
        """The guard after a new question is over: for the pointer, and for the number keys."""
        assert wait_for(self.app, lambda: self.window.property("armed") is True
                        and self.window.property("keysArmed") is True)
        settle(self.app)

    def until(self, *states):
        assert wait_for(self.app, lambda: self.state() in states and not self.backend._session.busy), self.state()
        settle(self.app)

    def buttons(self):
        return [i for i in items(self.window, "isOptionButton") if i.isVisible()]

    def button(self, key):
        return next(i for i in self.buttons() if i.property("key") == key)

    def texts(self):
        return [i.property("text") for i in walk(self.window.contentItem())
                if i.isVisible() and i.inherits("QQuickText") and i.property("text")]

    def one(self, name):
        found = [i for i in items(self.window, name) if i.isVisible()]
        assert len(found) == 1, (name, len(found))
        return found[0]

    def shows(self, name):
        return any(i.isVisible() for i in items(self.window, name))

    def press(self, item):
        QTest.mouseClick(self.window, LEFT, NONE, centre(item))
        settle(self.app)


@pytest.fixture
def desk(app, tmp_path):
    made = []

    def make(agents=AGENTS, screens=(BASH,), **more):
        one = Desk(app, tmp_path, agents, **more)
        one.client.screens = list(screens)
        made.append(one)
        return one

    yield make
    for one in made:
        warnings = one.warnings()
        one.close()
        assert warnings == []


# ----- ready: the question and one button for each option -----

@pytest.mark.parametrize("letter", LETTERS)
def test_the_window_shows_the_agent_the_question_and_one_button_for_each_option_in_each_layout(app, desk, letter):
    d = desk()
    d.backend.setLayout(letter)
    window = d.answer_for("t1")
    assert d.one("isAgentLabel").property("text") == "rev" and d.one("isAgentAddress").property("text") == "t1"
    assert d.one("isPromptTitle").property("text") == "Bash command"
    assert d.one("isPromptSubtitle").property("text") == TIP + "\nCreate an empty test file"
    assert d.one("isQuestion").property("text") == "Do you want to proceed?"
    assert [i.property("text") for i in items(window, "isScreenLine")] == [" touch made-by-test.txt"]
    d.arm()  # the options that approve are on after the guard: then the detail, all in view, is reported seen
    assert [spoken(b) for b in d.buttons()] == [
        "Option 1, Yes, approves",
        "Option 2, Yes, and always allow access to /home/dev/projects/sample-app from this project, approves, "
        "standing permission",
        "Option 3, Yes, and switch to auto mode · auto mode handles these prompts for you, approves, standing permission",
        "Option 4, No, declines"]
    # The plain "Yes", the options that approve more than this one thing, and "No" have three different looks.
    assert [b.property("look") for b in d.buttons()] == ["accept", "wide", "wide", "decline"]
    assert all(b.property("enabled") for b in d.buttons())
    assert not d.shows("isNote") and not d.shows("isNewMark") and not d.shows("isTextEntry") and not d.shows("isScreen")
    assert d.one("isStateWord").property("text") == "" and d.one("isOpenInHerdr").property("first") is False
    frame = d.one("isFrame")
    assert QColor(frame.property("color")).name(QColor.NameFormat.HexArgb) == d.backend.colors["background"]
    assert text_findings(window) == []
    assert window.height() <= 1000 and window.width() == 600
    assert d.client.pressed == [] and d.client.sent == [] and d.client.focused == []


def test_the_three_kinds_of_options_differ_in_shape_and_not_only_in_colour(app, desk):
    d = desk()
    d.answer_for("t1")
    caps = {b.property("look"): next(i for i in walk(b) if i.property("isKeyCap")) for b in d.buttons()}
    bars = {b.property("look"): next(i for i in walk(b) if i.property("isWideBar")).isVisible() for b in d.buttons()}
    assert caps["accept"].property("full") is True and caps["wide"].property("full") is False
    assert caps["decline"].property("full") is False
    assert bars == {"accept": False, "wide": True, "decline": False}
    assert js(caps["wide"], "border.width") == 2 and js(caps["decline"], "border.width") == 1
    tones = {b.property("look"): QColor(b.property("tone")).name() for b in d.buttons()}
    assert len(set(tones.values())) == 3 and tones["wide"] == d.backend.stateColors["blocked"]


def test_a_click_on_an_option_reads_the_screen_again_and_presses_that_one_key(app, desk):
    d = desk()
    d.answer_for("t1")
    d.arm()
    reads = len(d.client.reads)
    order = []
    d.client.on_press = lambda: order.append(len(d.client.reads))
    d.press(d.button("4"))
    d.until("failed", "sent", "ready")
    assert d.client.pressed == [("t1", ["4"])] and d.client.sent == []
    assert order == [reads + 1]  # one new read came before the key


def test_a_click_when_the_screen_changed_presses_nothing_and_says_so(app, desk):
    d = desk()
    d.answer_for("t1")
    d.arm()
    d.client.screens[:] = [CREATE]
    d.press(d.button("1"))
    d.until("ready")
    assert d.client.pressed == [] and d.one("isNoteText").property("text") == "The question changed. Nothing was sent."
    assert d.one("isPromptTitle").property("text") == "Create file" and d.shows("isNewMark")
    assert text_findings(d.window) == []


# ----- blind: only the options that decline -----

@pytest.mark.parametrize("screen,key_of_no,agent", [(CODEX_EDIT, "3", "t7"), (TALL, "3", "t1")], ids=["codex-edit", "cut"])
def test_a_blind_question_can_only_be_declined_from_the_window(app, desk, screen, key_of_no, agent):
    d = desk(screens=[screen])
    d.answer_for(agent)
    d.arm()
    assert d.one("isNoteText").property("text") == "The full content is not visible here. Open it in Herdr to approve."
    assert d.one("isStateWord").property("text") == "Partly visible" and d.one("isOpenInHerdr").property("first") is True
    assert d.shows("isCutNote") is (screen is TALL)
    enabled = {b.property("key"): b.property("enabled") for b in d.buttons()}
    assert enabled == {"1": False, "2": False, "3": True}
    for accept in ("1", "2"):
        d.press(d.button(accept))
        key(app, d.window, getattr(Qt.Key, f"Key_{accept}"))
    assert d.client.pressed == [] and d.state() == "ready"
    assert "not available" in spoken(d.button("1")) and "not available" not in spoken(d.button(key_of_no))
    d.press(d.button(key_of_no))
    d.until("failed", "sent", "ready")
    assert d.client.pressed == [(agent, [key_of_no])]
    assert text_findings(d.window) == []


# ----- the keyboard -----

def test_a_digit_presses_the_option_with_that_key_and_other_keys_press_nothing(app, desk):
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    for which, modifier in ((Qt.Key.Key_5, NONE), (Qt.Key.Key_0, NONE), (Qt.Key.Key_Y, NONE), (Qt.Key.Key_Return, NONE),
                            (Qt.Key.Key_Enter, NONE), (Qt.Key.Key_Space, NONE),
                            (Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier), (Qt.Key.Key_1, Qt.KeyboardModifier.AltModifier)):
        key(app, window, which, modifier)
    assert d.client.pressed == [] and d.state() == "ready"  # nothing is selected at the start: Enter presses nothing
    key(app, window, Qt.Key.Key_2)
    d.until("failed", "sent", "ready")
    assert d.client.pressed == [("t1", ["2"])]


def test_enter_presses_only_the_option_that_has_the_keyboard(app, desk):
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    assert focused(window) is None
    key(app, window, Qt.Key.Key_Tab)
    key(app, window, Qt.Key.Key_Tab)
    assert focused(window).startswith("Option 2, ")
    key(app, window, Qt.Key.Key_Return)
    d.until("failed", "sent", "ready")
    assert d.client.pressed == [("t1", ["2"])]


def test_the_tab_key_goes_through_the_options_the_field_send_herdr_and_close(app, desk):
    d = desk(screens=[ASK])
    window = d.answer_for("t1")
    key(app, window, Qt.Key.Key_Tab)
    assert tab_order(app, window) == [
        "Option 1, Tea, answers", "Option 2, Coffee, answers", "Option 3, Type something., text", "Send the text",
        "Option 4, Chat about this, declines", "Open the agent in Herdr", "Close"]
    d2 = desk()
    window = d2.answer_for("t1")
    d2.arm()  # the options that approve take the keyboard once they are on
    key(app, window, Qt.Key.Key_Tab)
    assert [name.split(",")[0] for name in tab_order(app, window)] == [
        "Option 1", "Option 2", "Option 3", "Option 4", "Open the agent in Herdr", "Close"]


# ----- the text field -----

def test_a_text_goes_through_the_text_option_and_digits_in_the_field_are_text(app, desk):
    d = desk(screens=[ASK])
    window = d.answer_for("t1")
    d.arm()
    entry = d.one("isTextEntry")
    assert d.one("isEntryHint").property("text") == "Type something." and [b.property("key") for b in d.buttons()] == ["1", "2", "4"]
    key(app, window, Qt.Key.Key_3)  # the digit of the text option: the keyboard goes to the field
    assert focused(window) == "Option 3, Type something., text" and d.client.pressed == []
    type_text(app, window, "12 made-up 2")
    assert entry.property("text") == "12 made-up 2" and d.client.pressed == [] and d.state() == "ready"
    d.client.on_press = lambda: d.client.screens.__setitem__(slice(None), [shown("claude-ask-text-cursor")])
    key(app, window, Qt.Key.Key_Return)
    d.until("failed", "sent", "ready")
    assert d.client.pressed == [("t1", ["3"])] and d.client.sent == [("t1", "12 made-up 2")]


@pytest.mark.parametrize("text,message", [("", "Type a text first."), ("x" * 2001, "The text is too long: at most 2000 characters.")])
def test_a_text_that_is_refused_shows_the_message_at_the_field_and_stays_in_it(app, desk, text, message):
    d = desk(screens=[ASK])
    window = d.answer_for("t1")
    d.arm()
    entry = d.one("isTextEntry")
    entry.setProperty("text", text)
    d.press(d.one("isSend"))
    assert d.state() == "ready" and d.client.pressed == [] and d.client.sent == []
    assert d.one("isFieldNote").property("text") == message and not d.shows("isNote")
    assert d.one("isTextEntry").property("text") == text  # the field keeps what the person typed
    assert text_findings(window) == []


# ----- the guard after a new question -----

def test_a_click_right_after_a_new_question_does_nothing(app, desk):
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    window.setProperty("guardMs", 600000)
    d.client.on_press = lambda: d.client.screens.__setitem__(slice(None), [CREATE])
    d.press(d.button("1"))
    d.until("ready")
    assert d.one("isPromptTitle").property("text") == "Create file" and d.client.pressed == [("t1", ["1"])]
    assert window.property("armed") is False and d.one("isNewMark").property("text") == "New question (no. 2)"
    assert focused(window) is None  # the option of the old question does not keep the keyboard
    d.press(d.button("1"))  # the second click of a double click: on the same place, on the new question
    key(app, window, Qt.Key.Key_1)
    key(app, window, Qt.Key.Key_2)
    settle(app)
    assert d.client.pressed == [("t1", ["1"])] and d.state() == "ready"
    window.setProperty("guardMs", 30)
    d.client.screens[:] = [EDIT]
    d.backend.apply(list(AGENTS))  # a tick shows a third question: the guard starts again, now a short one
    d.until("ready")
    assert d.one("isPromptTitle").property("text") == "Edit file"
    d.arm()
    d.client.on_press = None
    d.press(d.button("3"))
    d.until("failed", "sent", "ready")
    assert d.client.pressed == [("t1", ["1"]), ("t1", ["3"])]


def test_the_guard_is_400_ms_and_applies_to_the_first_question_too(app, desk):
    d = desk()
    d.open_group("blocked")
    click(app, d.root, d.control("t1"))
    assert d.window.property("guardMs") == 400
    d.window.setProperty("guardMs", 600000)
    assert wait_for(app, lambda: d.state() == "ready")
    settle(app)
    assert d.window.property("armed") is False and not d.shows("isNewMark")  # the first question is not "new"
    d.press(d.button("1"))
    assert d.client.pressed == [] and d.state() == "ready"


# ----- after the answer -----

def test_the_window_closes_by_itself_a_moment_after_sent(app, desk):
    d = desk(sent_seconds=0.15, follow=(5.0,))  # the first read after the key comes late: the list is first
    window = d.answer_for("t1")
    d.arm()
    d.press(d.button("1"))
    assert wait_for(app, lambda: d.client.pressed == [("t1", ["1"])] and not d.backend._session.busy)
    d.backend.apply(list(GONE))
    assert wait_for(app, lambda: d.state() == "sent")
    settle(app)
    assert window.isVisible() and d.one("isNoteText").property("text") == "Sent." and d.buttons() == []
    assert d.one("isStateWord").property("text") == "Sent"
    assert wait_for(app, lambda: not window.isVisible()) and d.state() == "closed"
    assert d.client.pressed == [("t1", ["1"])]


def test_a_sent_with_a_note_stays_until_the_person_closes_it(app, desk):
    d = desk(sent_seconds=0.05)
    window = d.answer_for("t1")
    d.arm()
    d.client.keep_key = True
    d.client.press_result = Failure("timeout")
    d.press(d.button("1"))
    assert wait_for(app, lambda: d.state() == "pending")
    d.backend.apply(list(GONE))
    assert wait_for(app, lambda: d.state() == "sent")
    for _ in range(20):
        settle(app)
    assert window.isVisible() and d.one("isNoteText").property("text") == MESSAGES["unconfirmed"]
    assert d.one("isOpenInHerdr").property("enabled") is True


# ----- the other states -----

def test_loading_shows_a_quiet_line_and_the_agent(app, desk):
    d = desk()
    d.client.read_gate = threading.Event()
    d.open_group("blocked")
    click(app, d.root, d.control("t1"))
    try:
        assert d.state() == "loading" and d.window.isVisible()
        assert d.one("isLoadingLine").property("text") == "Reading the screen of the agent…"
        assert d.one("isAgentLabel").property("text") == "rev" and d.one("isStateWord").property("text") == "Reading…"
        assert d.buttons() == [] and not d.shows("isNote")
        assert text_findings(d.window) == []
    finally:
        d.client.read_gate.set()
    d.until("ready")
    assert not d.shows("isLoadingLine") and len(d.buttons()) == 4


def test_answering_keeps_the_question_with_its_buttons_off(app, desk):
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    d.client.press_gate = threading.Event()
    try:
        d.press(d.button("1"))
        assert wait_for(app, lambda: d.state() == "answering")
        settle(app)
        assert d.one("isStateWord").property("text") == "Sending…" and len(d.buttons()) == 4
        assert not any(b.property("enabled") for b in d.buttons())
        d.press(d.button("4"))
        key(app, window, Qt.Key.Key_4)
        assert d.client.pressed == [("t1", ["1"])]
    finally:
        d.client.press_gate.set()
    d.until("failed", "sent", "ready")
    assert d.client.pressed == [("t1", ["1"])]


def test_pending_says_what_to_do_and_offers_herdr_first(app, desk):
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    d.client.keep_key = True
    d.client.press_result = Failure("timeout")
    gate = threading.Event()
    d.client.screens[:] = [BASH, lambda: (gate.wait(5), BASH)[1]]
    try:
        d.press(d.button("1"))
        assert wait_for(app, lambda: d.state() == "pending")
        settle(app)
        assert d.one("isNoteText").property("text") == "Herdr did not confirm the answer. It may still arrive. Check in Herdr."
        assert d.one("isStateWord").property("text") == "Not confirmed" and d.one("isOpenInHerdr").property("first") is True
        assert len(d.buttons()) == 4 and not any(b.property("enabled") for b in d.buttons())
        for digit in (Qt.Key.Key_1, Qt.Key.Key_4):
            key(app, window, digit)
        d.press(d.button("4"))
        assert d.client.pressed == [("t1", ["1"])]
        assert text_findings(window) == []
    finally:
        gate.set()


def test_a_reopen_while_an_earlier_answer_may_arrive_shows_the_question_with_no_button_on(app, desk):
    d = desk(pending_follow=(0.0,))
    window = d.answer_for("t1")
    d.arm()
    d.client.keep_key = True
    d.client.press_result = Failure("timeout")
    d.press(d.button("1"))
    d.until("failed")
    assert d.one("isNoteText").property("text") == MESSAGES["press_timeout"] and d.buttons() == []
    assert d.one("isStateWord").property("text") == "Failed"
    key(app, window, Qt.Key.Key_Escape)
    assert not window.isVisible() and d.state() == "closed"
    d.client.press_result = None
    click(app, d.root, d.control("t1"))
    d.until("pending")
    assert window.isVisible() and d.one("isNoteText").property("text") == MESSAGES["earlier"]
    assert len(d.buttons()) == 4 and not any(b.property("enabled") for b in d.buttons())
    assert not wait_for(app, lambda: window.property("armed"), 0.6)  # no guard ends while nothing can be answered
    d.press(d.button("2"))
    key(app, window, Qt.Key.Key_2)
    assert d.client.pressed == [("t1", ["1"])]
    assert text_findings(window) == []
    d.client.late(None)  # the key command ended: delivered. The question can be answered again.
    d.until("ready")
    d.arm()  # the change into "ready" starts the guard; after it the detail (all in view) is reported seen
    assert wait_for(app, lambda: all(b.property("enabled") for b in d.buttons())) and not d.shows("isNote")


def test_a_failed_answer_says_why_and_has_no_question(app, desk):
    d = desk()
    d.answer_for("t1")
    d.arm()
    d.client.press_result = Failure("exit_1")
    d.press(d.button("1"))
    d.until("failed")
    assert d.one("isNoteText").property("text") == "The answer was not sent, or Herdr did not confirm it."
    assert d.buttons() == [] and not d.shows("isQuestion") and not d.shows("isDetail")
    assert d.one("isOpenInHerdr").property("first") is True and d.window.height() == 220
    assert text_findings(d.window) == []


def test_an_agent_that_is_not_blocked_any_more_is_gone(app, desk):
    d = desk()
    d.answer_for("t1")
    d.backend.apply(list(GONE))
    d.until("gone")
    assert d.one("isNoteText").property("text") == "This agent is not blocked now." and d.buttons() == []
    assert d.one("isStateWord").property("text") == "Not blocked" and d.one("isAgentLabel").property("text") == "rev"
    assert d.window.isVisible()  # it stays until the person closes it


def test_a_screen_that_is_not_known_shows_as_text_and_only_while_unreadable(app, desk):
    d = desk(screens=[UNKNOWN])
    window = d.answer_for("t1", "unreadable")
    assert d.one("isNoteText").property("text") == "Bellwether does not know this screen."
    view = d.one("isScreen")
    lines = [i.property("text") for i in walk(view) if i.property("isScreenLine")]
    assert lines == ["made-up line one", MARKER, "   made-up line three"]  # as lines, with the first spaces
    assert d.buttons() == [] and d.one("isOpenInHerdr").property("first") is True
    assert d.one("isStateWord").property("text") == "Not readable"
    d.client.screens[:] = [BASH]
    d.backend.apply(list(AGENTS))  # a tick: the agent now shows a dialog
    d.until("ready")
    assert not d.shows("isScreen") and len(d.buttons()) == 4

    def holds_the_marker():
        return any(MARKER in str(i.property(name) or "") for i in walk(window.contentItem())
                   for name in ("text", "lines", "name"))

    assert not holds_the_marker()
    assert MARKER not in str(window.property("prompt"))


def test_a_program_with_no_reader_shows_its_screen(app, desk):
    d = desk([Agent("t1", "blocked", "rev", "Main", "gemini"), *AGENTS[1:]], screens=[UNKNOWN])
    d.answer_for("t1", "unreadable")
    assert d.one("isNoteText").property("text") == "Bellwether cannot read the questions of this program."
    assert d.shows("isScreen")


# ----- the ways to close: each closes the prompt, and nothing is read or sent after it -----

def closes(d, act):
    window = d.window
    reads = len(d.client.reads)
    act()
    settle(d.app)
    assert not window.isVisible() and d.state() == "closed" and d.backend.prompt["question"] == ""
    for _ in range(3):
        d.backend.apply(list(AGENTS))
        settle(d.app)
    assert len(d.client.reads) == reads and d.client.pressed == [] and d.client.sent == []


def test_esc_closes_the_window_and_the_prompt(app, desk):
    d = desk()
    window = d.answer_for("t1")
    closes(d, lambda: key(app, window, Qt.Key.Key_Escape))


def test_esc_closes_also_from_the_text_field(app, desk):
    d = desk(screens=[ASK])
    window = d.answer_for("t1")
    key(app, window, Qt.Key.Key_3)
    type_text(app, window, "made-up")
    closes(d, lambda: key(app, window, Qt.Key.Key_Escape))
    click(app, d.root, d.control("t1"))  # the next open starts with an empty field
    d.until("ready")
    assert d.one("isTextEntry").property("text") == ""


def test_the_close_control_closes_with_the_pointer_and_with_the_keyboard(app, desk):
    d = desk()
    window = d.answer_for("t1")
    closes(d, lambda: d.press(d.one("isClose")))
    click(app, d.root, d.control("t1"))
    d.until("ready")
    d.one("isClose").forceActiveFocus()
    assert focused(window) == "Close"
    closes(d, lambda: key(app, window, Qt.Key.Key_Return))


def test_a_close_by_the_compositor_closes_the_prompt(app, desk):
    d = desk()
    window = d.answer_for("t1")
    closes(d, window.close)


def test_open_in_herdr_jumps_to_the_agent_and_closes_the_window(app, desk):
    d = desk()
    window = d.answer_for("t1")
    d.client.focus_gate = threading.Event()
    try:
        d.press(d.one("isOpenInHerdr"))
        assert d.client.focused == ["t1"] and d.backend.opening == "t1"
        assert not window.isVisible() and d.state() == "closed"
    finally:
        d.client.focus_gate.set()
    wait_jump(app, d.backend)
    assert d.client.pressed == []


def test_open_in_herdr_is_off_while_a_jump_runs(app, desk):
    d = desk()
    d.open_group("blocked")
    click(app, d.root, d.control("t1"))
    d.until("ready")
    d.client.focus_gate = threading.Event()
    try:
        d.backend.focus("t7")
        settle(app)
        button = d.one("isOpenInHerdr")
        assert button.property("enabled") is False
        d.press(button)
        assert d.client.focused == ["t7"] and d.window.isVisible() and d.state() == "ready"
    finally:
        d.client.focus_gate.set()
    wait_jump(app, d.backend)


def test_the_window_changes_to_a_different_agent_and_back(app, desk):
    d = desk(screens=[CODEX])
    window = d.answer_for("t7")
    assert d.one("isAgentLabel").property("text") == "dev" and d.one("isPromptTitle").property("text") == "Command approval"
    assert [b.property("look") for b in d.buttons()] == ["accept", "wide", "decline"]
    d.client.screens[:] = [BASH]
    click(app, d.root, d.control("t1"))
    d.until("ready")
    assert d.window is window and window.isVisible()
    assert d.one("isAgentLabel").property("text") == "rev" and len(d.buttons()) == 4
    assert not d.shows("isNewMark")  # a question of a different agent is not "a new question"
    assert d.client.pressed == []


def test_a_second_open_while_the_window_is_behind_does_not_close_the_prompt(app, desk):
    d = desk()
    window = d.answer_for("t1")
    states = []
    d.backend.promptChanged.connect(lambda: states.append(d.state()))
    d.opener.open()  # the program shows the window again to bring it to the front
    settle(app)
    assert window.isVisible() and d.state() == "ready" and "closed" not in states
    assert window.property("raising") is False


# ----- the look follows the layout and the custom look while the window is open -----

@pytest.mark.parametrize("letter", LETTERS)
def test_the_window_follows_a_change_of_the_layout_and_of_the_custom_look(app, desk, letter):
    d = desk(screens=[ASK])
    window = d.answer_for("t1")
    frame = d.one("isFrame")
    d.backend.setLayout(letter)
    settle(app)
    assert QColor(frame.property("color")).name(QColor.NameFormat.HexArgb) == d.backend.colors["background"]
    assert window.property("theme").property("radius") == frame.property("radius")
    assert text_findings(window) == [] and d.state() == "ready"
    assert d.backend.setColor("accent", "#ff00aa") and d.backend.setColor("text", "#102030")
    assert d.backend.setColor("blocked", "#00aa55") and d.backend.setFontScale(1.4)
    settle(app)
    assert QColor(d.one("isQuestion").property("color")).name() == "#102030"
    argb = QColor.NameFormat.HexArgb  # "Chat about this" is dim: the text colour with less opacity
    assert QColor(d.button("4").property("tone")).name(argb) != QColor(d.button("1").property("tone")).name(argb)
    assert text_findings(window) == []
    d.backend.setFontScale(0.8)
    settle(app)
    assert text_findings(window) == [] and len(d.buttons()) == 3 and d.shows("isTextEntry")


def test_the_warning_colour_can_always_be_told_from_the_panel(app, desk):
    d = desk()
    window = d.answer_for("t1")
    panel = d.backend.colors["background"]
    assert d.backend.setColor("blocked", "#" + panel[-6:])  # the status colour is the colour of the panel
    settle(app)
    warn = QColor(window.property("warnColor"))
    assert warn.name() in ("#202124", "#f1f3f4")


# ----- the size -----

def test_a_long_detail_scrolls_inside_its_view_and_the_window_stays_on_a_low_screen(app, desk):
    d = desk(screens=[TALL])
    window = d.answer_for("t1")
    view = d.one("isDetail")
    assert view.property("scrolls") is True and view.height() > 300  # it takes the free height of the window
    assert window.height() == 1000
    window.setProperty("roomHeight", 480)
    settle(app)
    assert window.height() == 400 and d.one("isScroller").property("scrolls") is True
    header, footer = d.one("isHeader"), d.one("isFooter")
    assert header.mapToScene(header.boundingRect().topLeft()).y() == 0
    assert footer.mapToScene(footer.boundingRect().bottomLeft()).y() == window.height()
    key(app, window, Qt.Key.Key_Tab)  # the option that gets the keyboard comes on the screen
    first = d.button("1")
    inside = QRectF(0, header.height(), window.width(), window.height() - header.height() - footer.height())
    assert inside.adjusted(-1, -1, 1, 1).contains(first.mapRectToScene(first.boundingRect()))


# ----- static rules of the answer window -----

ANSWER_FILES = [layouts.UI_PATH / "Answer.qml", *((layouts.UI_PATH / "controls") / name for name in
                                                   ("OptionButton.qml", "TextView.qml", "TextEntry.qml"))]


def test_every_text_of_the_answer_window_is_plain_text_and_nothing_is_logged():
    for file in ANSWER_FILES:
        text = file.read_text()
        assert "console." not in text and "print(" not in text, file.name
        assert len(re.findall(r"^\s*Text \{", text, re.M)) == text.count("textFormat: Text.PlainText"), file.name
        assert "Text.RichText" not in text and "Text.StyledText" not in text and "Text.AutoText" not in text
    window = ANSWER_FILES[0].read_text()
    # The window sends only through these two slots, each from one function that the person starts.
    assert window.count("backend.answer(") == 1 and window.count("backend.answerText(") == 1
    # Two timers: the guard of the pointer and the quiet time of the number keys after a new question.
    assert "backend.openPrompt" not in window and window.count("Timer {") == 2


def test_the_window_has_every_fixed_message_from_the_engine_and_none_of_its_own():
    window = ANSWER_FILES[0].read_text()
    for message in MESSAGES.values():
        assert message not in window


# ----- a long detail: the free height, the note of the lines out of view, and its end before an approval -----

STEPS = [f" echo made-up step {n:02d} of the made-up build && \\" for n in range(1, 41)] + [" rm -rf ~/made-up-home"]
LONG = Screen(BASH.text.replace(" touch made-by-test.txt\n╌", "\n".join(STEPS) + "\n╌", 1), True)
SCROLL_NOTE = "Scroll to the end of the text above to approve."


def answer_spy(d):
    """The calls of `backend.answer` (the slot only forwards to the engine): the keys."""
    calls, real = [], d.backend._session.answer
    d.backend._session.answer = lambda key: calls.append(key) or real(key)
    return calls


def test_a_long_command_takes_the_free_height_and_says_how_many_lines_are_below(app, desk):
    d = desk(screens=[LONG])
    window = d.answer_for("t1")
    d.arm()
    view = d.one("isDetail")
    assert window.height() == 1000 and view.height() > 500 and view.property("scrolls") is True
    note = d.one("isMoreNote")
    assert re.fullmatch(r"\d+ more lines below", note.property("text")), note.property("text")
    below = view.property("below")
    assert 0 < below < 41 and note.property("text") == f"{below} more lines below"
    window.setProperty("roomHeight", 700)  # a low screen: the window is smaller, the view still shows lines
    settle(app)
    assert window.height() == 620 and view.height() >= 110 and view.property("below") > below
    assert text_findings(window) == []


@pytest.mark.parametrize("how", ["end-key", "page-down", "wheel", "detail-focus", "thumb"])
def test_the_options_that_approve_stay_off_until_the_end_of_the_command_was_in_view(app, desk, how):
    d = desk(screens=[LONG])
    window = d.answer_for("t1")
    d.arm()
    calls = answer_spy(d)
    view = d.one("isDetail")
    enabled = {b.property("key"): b.property("enabled") for b in d.buttons()}
    assert enabled == {"1": False, "2": False, "3": False, "4": True} and d.one("isOpenInHerdr").property("enabled")
    assert d.one("isSeenNote").property("text") == SCROLL_NOTE and d.backend.prompt["seen"] is False
    for accept in ("1", "2", "3"):
        d.press(d.button(accept))
        key(app, window, getattr(Qt.Key, f"Key_{accept}"))
    assert calls == [] and d.client.pressed == [] and d.state() == "ready"
    if how == "end-key":
        key(app, window, Qt.Key.Key_End)
    elif how == "page-down":
        for _ in range(30):
            key(app, window, Qt.Key.Key_PageDown)
    elif how == "wheel":
        point = view.mapToScene(QPointF(view.width() / 2, view.height() / 2))
        for _ in range(30):
            QGuiApplication.sendEvent(window, QWheelEvent(point, window.mapToGlobal(point), QPoint(0, 0),
                                                          QPoint(0, -240), Qt.MouseButton.NoButton, NONE,
                                                          Qt.ScrollPhase.NoScrollPhase, False))
        settle(app)
    elif how == "detail-focus":
        key(app, window, Qt.Key.Key_Tab)  # a detail that scrolls takes the keyboard first
        assert focused(window).startswith("What the agent asks for")
        key(app, window, Qt.Key.Key_End)
    else:
        thumb = next(i for i in walk(view) if i.property("isScrollThumb"))
        start = thumb.mapToScene(QPointF(thumb.width() / 2, thumb.height() / 2)).toPoint()
        end = view.mapToScene(QPointF(0, view.height() - 2)).toPoint().y()  # the foot of the view
        QTest.mousePress(window, LEFT, NONE, start)
        for step in range(1, 21):
            QTest.mouseMove(window, QPoint(start.x(), start.y() + (end - start.y()) * step // 20))
        QTest.mouseRelease(window, LEFT, NONE, QPoint(start.x(), end))
        settle(app)
    assert view.property("atEnd") is True and view.property("below") == 0
    assert re.fullmatch(r"\d+ lines above", d.one("isMoreNote").property("text"))
    assert wait_for(app, lambda: d.backend.prompt["seen"] is True)
    settle(app)
    assert all(b.property("enabled") for b in d.buttons()) and not d.shows("isSeenNote")
    key(app, window, Qt.Key.Key_Home)  # back up: what was seen stays seen for this question
    assert d.button("1").property("enabled")
    d.press(d.button("1"))
    d.until("failed", "sent", "ready")
    assert calls == ["1"] and d.client.pressed == [("t1", ["1"])]


def test_a_detail_that_fits_is_reported_seen_after_the_guard_and_not_before(app, desk):
    d = desk()
    d.open_group("blocked")
    click(app, d.root, d.control("t1"))
    d.window.setProperty("guardMs", 600000)
    assert wait_for(app, lambda: d.state() == "ready" and not d.backend._session.busy)
    settle(app)
    assert d.backend.prompt["seen"] is False and not d.button("1").property("enabled")
    assert not d.shows("isSeenNote") and not d.shows("isMoreNote")  # nothing to scroll: no note
    d.press(d.button("1"))
    assert d.client.pressed == []
    d.window.setProperty("guardMs", 20)  # the guard ends: the whole detail is in view, so it is reported seen
    assert wait_for(app, lambda: d.backend.prompt["seen"] is True)
    settle(app)
    assert d.button("1").property("enabled") and d.button("2").property("enabled")


def test_the_window_never_calls_answer_for_an_option_that_is_not_allowed(app, desk):
    d = desk(screens=[CODEX_EDIT])  # blind: only "No" is allowed
    window = d.answer_for("t7")
    d.arm()
    calls = answer_spy(d)
    for accept in ("1", "2"):
        d.press(d.button(accept))
        key(app, window, getattr(Qt.Key, f"Key_{accept}"))
        assert js(window, f"answer.choose('{accept}', 'pointer')") is False
    assert calls == [] and d.client.pressed == []
    d.press(d.button("3"))
    d.until("failed", "sent", "ready")
    assert calls == ["3"]


# ----- the guard and the number keys after a new question -----

def test_the_reviewers_probe_digits_typed_for_the_field_do_not_answer_a_new_question(app, desk):
    d = desk(screens=[ASK])
    window = d.answer_for("t1")
    d.window.setProperty("guardMs", 50)
    d.arm()
    key(app, window, Qt.Key.Key_3)  # the field takes the keyboard
    type_text(app, window, "made-up")
    assert focused(window) == "Option 3, Type something., text"
    d.client.screens[:] = [BASH]
    d.backend.apply(list(AGENTS))  # a tick: the agent now shows a different question
    d.until("ready")
    assert d.one("isPromptTitle").property("text") == "Bash command"
    d.arm()
    type_text(app, window, " a 2")  # the person goes on typing what they meant for the field
    assert not wait_for(app, lambda: d.client.pressed != [], 1.0)
    assert d.client.pressed == [] and d.state() == "ready"
    assert d.one("isDigitsOff").property("text") == "New question — click or press Tab to use the number keys"
    assert window.property("digitsLocked") is True
    assert d.one("isFooterNote").property("text") == "Click or press Tab first. Esc closes."


@pytest.mark.parametrize("unlock", ["click", "tab"])
def test_after_a_change_while_typing_the_digits_stay_off_until_a_click_or_tab(app, desk, unlock):
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    key(app, window, Qt.Key.Key_A)  # a key in the 2 s before the change
    d.client.screens[:] = [EDIT]
    d.backend.apply(list(AGENTS))
    d.until("ready")
    d.arm()
    key(app, window, Qt.Key.Key_3)
    assert d.client.pressed == [] and d.shows("isDigitsOff")
    if unlock == "click":
        title = d.one("isPromptTitle")
        d.press(title)
    else:
        key(app, window, Qt.Key.Key_Tab)
        key(app, window, Qt.Key.Key_Backtab)
    assert window.property("digitsLocked") is False and not d.shows("isDigitsOff")
    d.arm()
    key(app, window, Qt.Key.Key_3)
    d.until("failed", "sent", "ready")
    assert d.client.pressed == [("t1", ["3"])]


def test_normal_fast_use_open_wait_then_a_digit_answers(app, desk):
    d = desk()
    window = d.answer_for("t1", quiet=None)
    assert window.property("guardMs") == 400 and window.property("keyQuietMs") == 1000
    assert window.property("lockMs") == 2000
    assert not window.property("digitsLocked") and not d.shows("isDigitsOff")
    d.arm()
    key(app, window, Qt.Key.Key_4)
    d.until("failed", "sent", "ready")
    assert d.client.pressed == [("t1", ["4"])]


def test_a_key_in_the_quiet_time_answers_nothing_and_starts_it_again(app, desk):
    d = desk()
    window = d.answer_for("t1", quiet=None)
    window.setProperty("guardMs", 600000)
    d.client.screens[:] = [EDIT]
    d.backend.apply(list(AGENTS))  # a new question: both guards start
    d.until("ready")
    window.setProperty("guardMs", 30)
    assert wait_for(app, lambda: window.property("armed") is True)
    for _ in range(4):  # a key each 0.4 s: the quiet time of 1 s never ends
        key(app, window, Qt.Key.Key_3)
        assert window.property("keysArmed") is False
        assert not wait_for(app, lambda: window.property("keysArmed") is True, 0.35)
    assert d.client.pressed == []
    assert wait_for(app, lambda: window.property("keysArmed") is True, 1.5)
    key(app, window, Qt.Key.Key_3)
    d.until("failed", "sent", "ready")
    assert d.client.pressed == [("t1", ["3"])]


def test_a_pointer_press_in_the_guard_starts_it_again(app, desk):
    d = desk()
    window = d.answer_for("t1")
    window.setProperty("guardMs", 300)
    d.client.screens[:] = [EDIT]
    d.backend.apply(list(AGENTS))
    d.until("ready")
    for _ in range(3):  # a press each 0.2 s: the guard of 0.3 s never ends
        d.press(d.one("isPromptTitle"))
        assert not wait_for(app, lambda: window.property("armed") is True, 0.2)
    assert wait_for(app, lambda: window.property("armed") is True, 1.0)


def test_a_change_of_question_is_marked_with_its_number_and_a_highlight(app, desk):
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    assert not d.shows("isNewMark") and d.one("isChangeFlash").property("opacity") == 0
    d.client.screens[:] = [EDIT]
    d.backend.apply(list(AGENTS))
    d.until("ready")
    assert d.one("isNewMark").property("text") == "New question (no. 2)"
    assert wait_for(app, lambda: d.one("isChangeFlash").property("opacity") > 0, 0.5)
    assert wait_for(app, lambda: d.one("isChangeFlash").property("opacity") == 0, 3.0)
    d.client.screens[:] = [CREATE]
    d.backend.apply(list(AGENTS))
    d.until("ready")
    assert d.one("isNewMark").property("text") == "New question (no. 3)"


def test_every_change_into_an_answerable_state_starts_the_guard(app, desk):
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    session, prompt = d.backend._session, d.backend._session.prompt
    window.setProperty("guardMs", 600000)
    session._set("pending", "earlier", prompt=prompt)  # the same question, not answerable
    settle(app)
    assert window.property("armed") is False
    session._set("ready", prompt=prompt)  # the same question is answerable again: the guard runs again
    settle(app)
    assert d.backend.prompt["shown"] == 1 and window.property("armed") is False
    d.press(d.button("4"))
    assert d.client.pressed == []
    window.setProperty("guardMs", 20)
    d.arm()
    d.press(d.button("4"))
    d.until("failed", "sent", "ready")
    assert d.client.pressed == [("t1", ["4"])]


def test_a_wide_option_has_a_tag_in_words_and_the_others_do_not(app, desk):
    d = desk()
    d.answer_for("t1")
    tags = {b.property("key"): [i.property("text") for i in walk(b) if i.property("isWideTag") and i.isVisible()]
            for b in d.buttons()}
    assert tags == {"1": [], "2": ["Standing permission"], "3": ["Standing permission"], "4": []}


def test_on_a_low_screen_the_end_of_the_detail_must_be_in_the_window_too(app, desk):
    """The detail fits in its own view, but the content of a low window scrolls: the view itself is out of the
    window at first, so it is not reported seen until the content scrolls to it."""
    d = desk(screens=[EDIT])
    d.open_group("blocked")
    click(app, d.root, d.control("t1"))
    d.window.setProperty("roomHeight", 300)  # the window is 220 px high
    d.window.setProperty("guardMs", 600000)
    assert wait_for(app, lambda: d.state() == "ready" and not d.backend._session.busy)
    settle(app)
    scroller, view = d.one("isScroller"), d.one("isDetail")
    assert d.window.height() == 220 and scroller.property("scrolls") and view.property("atEnd") is True
    d.window.setProperty("guardMs", 20)
    assert not wait_for(app, lambda: d.backend.prompt["seen"] is True, 0.5)
    assert not d.button("1").property("enabled")
    scroller.setProperty("contentY", scroller.property("contentHeight") - scroller.height())
    assert wait_for(app, lambda: d.backend.prompt["seen"] is True)
