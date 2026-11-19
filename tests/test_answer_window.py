"""The answer window (Answer.qml) through the real panel, the real backend and its prompt engine, and a client of
made-up screens: what shows in each state, what a click and a key send (one key after a new read, or nothing), the
guard after a new question, the text field, the ways to close. No test starts herdr-core."""
import re
import threading

import pytest
from PySide6.QtCore import Q_ARG, QCoreApplication, QEvent, QMetaObject, QPoint, QPointF, QRectF, Qt, qInstallMessageHandler
from PySide6.QtGui import QAccessible, QColor, QGuiApplication, QKeyEvent, QWheelEvent, QWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest

from bellwether import layouts
from bellwether.answer import Answer
from bellwether.backend import Backend
from bellwether.client import Failure, Screen
from bellwether.icons import Icons
from bellwether.prompt_session import MESSAGES
from bellwether.state import Agent
from tests.audit import text_findings
from tests.test_answer_control import LEFT, LETTERS, NONE, Panel, centre
from tests.test_backend_prompt import ASK, BASH, CREATE, FIXTURES, NO_DIALOG, TIP, ScreenClient, shown, wait_for
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
    assert_locked(d, window)


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
    assert not window.property("digitsLocked") and not d.shows("isDigitsOff")
    d.arm()
    key(app, window, Qt.Key.Key_4)
    d.until("failed", "sent", "ready")
    assert d.client.pressed == [("t1", ["4"])]


def test_a_key_in_the_quiet_time_answers_nothing_and_starts_it_again(app, desk):
    d = desk()
    window = d.answer_for("t1", quiet=None)
    d.arm()
    d.client.on_press = lambda: d.client.screens.__setitem__(slice(None), [EDIT])
    window.setProperty("guardMs", 600000)
    key(app, window, Qt.Key.Key_4)  # the next question of this answer: both guards start, the keys stay on
    assert wait_for(app, lambda: d.backend.prompt["title"] == "Edit file" and d.state() == "ready")
    d.client.on_press = None
    settle(app)
    assert window.property("digitsLocked") is False
    window.setProperty("guardMs", 30)
    assert wait_for(app, lambda: window.property("armed") is True)
    for _ in range(4):  # a key each 0.4 s: the quiet time of 1 s never ends
        key(app, window, Qt.Key.Key_3)
        assert window.property("keysArmed") is False
        assert not wait_for(app, lambda: window.property("keysArmed") is True, 0.35)
    assert d.client.pressed == [("t1", ["4"])]
    assert wait_for(app, lambda: window.property("keysArmed") is True, 1.5)
    key(app, window, Qt.Key.Key_3)
    d.until("failed", "sent", "ready")
    assert d.client.pressed == [("t1", ["4"]), ("t1", ["3"])]


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


@pytest.mark.parametrize("letter", LETTERS)
def test_the_room_of_the_detail_has_no_binding_loop_when_the_window_gets_its_screen_height_at_once(app, tmp_path,
                                                                                                    letter):
    """The path of the program at its first open (dfd4d90): a fresh engine with only the answer window, the window
    made and shown, then the height of the screen at once, with a command that scrolls."""
    messages = []
    previous = qInstallMessageHandler(lambda mode, context, text: messages.append(text))
    client = ScreenClient()
    client.screens = [LONG]
    backend = Backend(client, settings_path=tmp_path / "state.json", icons=Icons(None, tmp_path / "cache"),
                      follow=(0.0,), prompt_floor=0.0)
    try:
        backend.setLayout(letter)
        engine = QQmlApplicationEngine()
        engine.warnings.connect(lambda errors: messages.extend(e.toString() for e in errors))
        engine.rootContext().setContextProperty("backend", backend)
        backend.apply([Agent("t1", "blocked", "rev", "Main", "claude-code")])
        opener = Answer(engine, backend)
        backend.showAnswer("t1")
        window = opener.window
        window.setProperty("roomHeight", 1080)
        window.setProperty("guardMs", 1)
        window.setProperty("keyQuietMs", 1)
        assert wait_for(app, lambda: backend.prompt["state"] == "ready" and backend.prompt["seen"] is False)
        settle(app)
        assert window.height() == 1000
        window.close()
        settle(app)
    finally:
        backend.stop()
        app.processEvents()
        qInstallMessageHandler(previous)
    assert [m for m in messages if "Binding loop" in m] == []


# ----- the one rule of the number keys: locked at each change of the question, but for the next question of an
# answer sent from this window, with the window active and no key pressed since -----

def pause(app, ms):
    wait_for(app, lambda: False, ms / 1000)


def to_the_field(d, app, window):
    """The person presses 3: the text field of the question ASK takes the keyboard, and the person types in it."""
    window.setProperty("guardMs", 50)
    d.arm()
    key(app, window, Qt.Key.Key_3)
    type_text(app, window, "made-up")
    assert focused(window) == "Option 3, Type something., text"


def tick_to(d, screen):
    """The next read of the list shows the agent with an other question (not the result of an answer)."""
    d.client.screens[:] = [screen]
    d.backend.apply(list(AGENTS))
    d.until("ready")


def away(app, window):
    """An other window takes the activation (Alt+Tab): Qt takes the keyboard away from every item of the window."""
    other = QWindow()
    other.resize(50, 50)
    other.show()
    other.requestActivate()
    assert wait_for(app, lambda: not window.isActive())
    return other


def back(app, window, other):
    """The person comes back with the keyboard (no click)."""
    window.requestActivate()
    assert wait_for(app, lambda: window.isActive())
    other.destroy()
    settle(app)


LOCK_LINE = "New question — the number keys are off. Click in the window or press Tab to turn them on."
LOCK_FOOTER = "Number keys off: click or press Tab. Esc closes."


def assert_locked(d, window):
    assert window.property("digitsLocked") is True
    assert d.one("isDigitsOff").property("text") == LOCK_LINE
    assert d.one("isFooterNote").property("text") == LOCK_FOOTER


def test_the_reviewers_n1_probe_a_change_while_the_window_is_not_active_locks_the_number_keys(app, desk):
    d = desk(screens=[ASK])
    window = d.answer_for("t1", quiet=None)
    to_the_field(d, app, window)
    other = away(app, window)
    pause(app, 2500)  # more than 2 s after the last key
    tick_to(d, BASH)
    pause(app, 1200)
    back(app, window, other)
    type_text(app, window, " a 2")
    pause(app, 300)
    assert d.client.pressed == []
    assert_locked(d, window)


def test_the_reviewers_n2_probe_a_second_change_keeps_the_lock(app, desk):
    d = desk(screens=[ASK])
    window = d.answer_for("t1", quiet=None)
    to_the_field(d, app, window)
    tick_to(d, BASH)
    assert window.property("digitsLocked") is True
    type_text(app, window, " more")  # the keys go to the frame now
    pause(app, 2200)
    tick_to(d, EDIT)
    pause(app, 1200)
    type_text(app, window, "1")
    pause(app, 300)
    assert d.client.pressed == []
    assert_locked(d, window)


def test_a_change_while_the_window_is_not_active_locks_the_number_keys_with_no_key_before(app, desk):
    d = desk()
    window = d.answer_for("t1", quiet=None)
    d.arm()
    other = away(app, window)
    tick_to(d, EDIT)
    back(app, window, other)
    d.arm()
    key(app, window, Qt.Key.Key_3)
    assert d.client.pressed == []
    assert_locked(d, window)


def test_a_change_after_a_quiet_time_with_the_field_used_before_locks_the_number_keys(app, desk):
    """The person typed in the field, then nothing for 2.5 s: a change of the question locks all the same."""
    d = desk(screens=[ASK])
    window = d.answer_for("t1", quiet=None)
    to_the_field(d, app, window)
    pause(app, 2500)
    tick_to(d, BASH)
    d.arm()
    key(app, window, Qt.Key.Key_2)
    assert d.client.pressed == []
    assert_locked(d, window)


def test_a_change_with_no_key_and_no_field_before_locks_the_number_keys_too(app, desk):
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    pause(app, 2200)
    tick_to(d, EDIT)
    d.arm()
    key(app, window, Qt.Key.Key_3)
    assert d.client.pressed == []
    assert_locked(d, window)


def test_the_lock_stays_through_a_second_and_a_third_change(app, desk):
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    tick_to(d, EDIT)
    assert_locked(d, window)
    for screen in (CREATE, EDIT):
        pause(app, 2200)
        tick_to(d, screen)
        d.arm()
        assert_locked(d, window)
        other = away(app, window)  # a change of the activation does not end the lock either
        back(app, window, other)
        key(app, window, Qt.Key.Key_3)
        assert d.client.pressed == [] and window.property("digitsLocked") is True


@pytest.mark.parametrize("how", ["digit", "pointer"])
def test_the_next_question_of_an_own_answer_keeps_the_number_keys_on(app, desk, how):
    """The fast path: an answer from this window, the next question comes, a number key answers it after the guard."""
    d = desk()
    window = d.answer_for("t1")
    assert window.isActive()
    d.arm()
    d.client.on_press = lambda: d.client.screens.__setitem__(slice(None), [EDIT])
    if how == "digit":
        key(app, window, Qt.Key.Key_4)
    else:
        d.press(d.button("4"))
    assert wait_for(app, lambda: d.backend.prompt["title"] == "Edit file" and d.state() == "ready")
    settle(app)
    assert window.property("digitsLocked") is False and not d.shows("isDigitsOff")
    assert d.one("isNewMark").property("text") == "New question (no. 2)"
    assert d.one("isFooterNote").property("text") == "Press the number of an option. Esc closes."
    d.client.on_press = None
    d.arm()
    key(app, window, Qt.Key.Key_3)
    d.until("failed", "sent", "ready")
    assert d.client.pressed == [("t1", ["4"]), ("t1", ["3"])]


def held_answer(d, app, window, digit=Qt.Key.Key_4):
    """An answer by a number key that herdr-core holds until `release()`; the next question is EDIT."""
    gate = threading.Event()
    d.client.press_gate = gate
    d.client.on_press = lambda: d.client.screens.__setitem__(slice(None), [EDIT])
    key(app, window, digit)
    assert wait_for(app, lambda: d.state() == "answering")

    def release():
        gate.set()
        assert wait_for(app, lambda: d.backend.prompt["title"] == "Edit file" and d.state() == "ready")
        settle(app)
        d.client.press_gate = None
    return release


def test_a_key_after_the_own_answer_locks_the_next_question(app, desk):
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    release = held_answer(d, app, window)
    key(app, window, Qt.Key.Key_A)  # a stray key while the answer is on its way
    release()
    d.arm()
    key(app, window, Qt.Key.Key_3)
    assert d.client.pressed == [("t1", ["4"])]
    assert_locked(d, window)


def test_the_next_question_of_an_own_answer_while_the_window_is_not_active_is_locked(app, desk):
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    release = held_answer(d, app, window)
    other = away(app, window)
    release()
    back(app, window, other)
    d.arm()
    key(app, window, Qt.Key.Key_3)
    assert d.client.pressed == [("t1", ["4"])]
    assert_locked(d, window)


def test_a_question_that_comes_while_nothing_was_sent_is_locked(app, desk):
    """The engine reads the screen again before the key: an other question shows, and the key does not go
    (reason "changed"). That question is not the result of the answer: locked."""
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    d.client.screens[:] = [EDIT]  # the next read, the one before the key, shows an other question
    key(app, window, Qt.Key.Key_4)
    d.until("ready")
    assert d.backend.prompt["reason"] == "changed" and d.client.pressed == []
    d.arm()
    key(app, window, Qt.Key.Key_3)
    assert d.client.pressed == []
    assert_locked(d, window)


@pytest.mark.parametrize("unlock", ["click", "tab", "backtab"])
def test_a_click_or_tab_ends_the_lock_and_the_quiet_time_still_applies(app, desk, unlock):
    d = desk()
    window = d.answer_for("t1", quiet=None)
    d.arm()
    tick_to(d, EDIT)
    d.arm()
    assert_locked(d, window)
    if unlock == "click":
        d.press(d.one("isPromptTitle"))
    else:
        key(app, window, Qt.Key.Key_Tab if unlock == "tab" else Qt.Key.Key_Backtab)
    assert window.property("digitsLocked") is False and not d.shows("isDigitsOff")
    # The quiet time of the number keys (1 s, again at each key) starts again at the end of a lock.
    assert window.property("keysArmed") is False and window.property("armed") is True
    key(app, window, Qt.Key.Key_3)
    pause(app, 600)
    key(app, window, Qt.Key.Key_3)
    assert d.client.pressed == [] and window.property("keysArmed") is False
    d.arm()
    key(app, window, Qt.Key.Key_3)
    d.until("failed", "sent", "ready")
    assert d.client.pressed == [("t1", ["3"])]


def test_typing_in_the_field_keeps_the_quiet_time_of_the_number_keys_running(app, desk):
    """Mutant Q6 of the re-review: each key typed in the field counts as a key press for the quiet time."""
    d = desk(screens=[ASK])
    window = d.answer_for("t1", quiet=None)
    window.setProperty("guardMs", 50)
    assert wait_for(app, lambda: window.property("armed") is True)
    field = next(i for i in walk(window.contentItem()) if i.property("isAnswerField"))
    d.press(field)  # the quiet time starts again with this press
    for letter in "made-up":  # 1.4 s of typing in the field
        QTest.keyClick(window, letter)
        pause(app, 200)
    key(app, window, Qt.Key.Key_Tab)  # out of the field, to "Send"
    assert focused(window) == "Send the text" and window.property("keysArmed") is False
    key(app, window, Qt.Key.Key_1)
    assert d.client.pressed == []


# ----- a new detail shows from its first line; the end of the detail and the reason why accept is off -----

SHORTER = Screen(BASH.text.replace(" touch made-by-test.txt\n╌", "\n".join(
    [" sudo made-up-wipe --all && \\", *STEPS[6:]]) + "\n╌", 1), True)
OTHER_START = Screen(BASH.text.replace(" touch made-by-test.txt\n╌", "\n".join(
    [" sudo made-up-wipe --all && \\", *STEPS[1:]]) + "\n╌", 1), True)


@pytest.mark.parametrize("second", ["shorter", "same-length"])
@pytest.mark.parametrize("room", [1080, 700])
def test_the_reviewers_n3_probe_a_new_long_command_shows_from_its_first_line_and_is_not_seen(app, desk, second, room):
    d = desk(screens=[LONG])
    window = d.answer_for("t1")
    window.setProperty("roomHeight", room)
    settle(app)
    d.arm()
    key(app, window, Qt.Key.Key_End)
    assert wait_for(app, lambda: d.backend.prompt["seen"] is True)
    tick_to(d, SHORTER if second == "shorter" else OTHER_START)
    assert d.backend.prompt["detail"][0] == " sudo made-up-wipe --all && \\" and d.backend.prompt["seen"] is False
    view = d.one("isDetail")
    assert view.property("above") == 0 and view.property("atEnd") is False  # at the top, before the guard ends
    assert d.one("isScroller").property("contentY") == 0
    d.arm()
    pause(app, 300)
    assert d.backend.prompt["seen"] is False and view.property("above") == 0
    assert [b.property("enabled") for b in d.buttons()] == [False, False, False, True]
    assert d.one("isSeenNote").property("text") == SCROLL_NOTE
    key(app, window, Qt.Key.Key_Tab)  # ends the lock of the number keys; the detail takes the keyboard
    key(app, window, Qt.Key.Key_End)
    assert wait_for(app, lambda: d.backend.prompt["seen"] is True)


def test_the_end_of_the_detail_counts_at_its_last_pixel_and_not_before(app, desk):
    """Mutant Q3 of the re-review: the view is at its end only within 1 px of it."""
    d = desk(screens=[LONG])
    d.answer_for("t1")
    d.arm()
    view = d.one("isDetail")
    flick = next(i for i in walk(view) if i.inherits("QQuickFlickable"))
    end = flick.property("contentHeight") - flick.height()
    for short in (40, 30, 2):
        flick.setProperty("contentY", end - short)
        settle(app)
        assert view.property("atEnd") is False, short
        assert not wait_for(app, lambda: d.backend.prompt["seen"] is True, 0.2), short
    assert view.property("below") == 0  # the last line is in view, but not the foot of the view
    flick.setProperty("contentY", end - 1)
    settle(app)
    assert view.property("atEnd") is True
    assert wait_for(app, lambda: d.backend.prompt["seen"] is True)


def test_on_a_low_window_the_reason_why_accept_is_off_is_in_view(app, desk):
    """N5: the detail fits in its own view, but its end is below the window; the footer, which is always in view,
    says why the options that approve are off, and the line below the detail says it too."""
    d = desk(screens=[EDIT])
    d.open_group("blocked")
    click(app, d.root, d.control("t1"))
    d.window.setProperty("roomHeight", 300)
    assert wait_for(app, lambda: d.state() == "ready" and not d.backend._session.busy)
    d.arm()
    scroller, view = d.one("isScroller"), d.one("isDetail")
    assert d.window.height() == 220 and view.property("scrolls") is False and scroller.property("contentY") == 0
    assert d.backend.prompt["seen"] is False and not d.button("1").property("enabled")
    footer = d.one("isFooterNote")
    assert footer.property("text") == f"{SCROLL_NOTE} Esc closes."
    assert footer.property("truncated") is False and d.one("isSeenNote").property("text") == SCROLL_NOTE
    assert footer.mapToScene(QPointF(0, 0)).y() >= d.window.height() - d.one("isFooter").height()  # always in view
    scroller.setProperty("contentY", scroller.property("contentHeight") - scroller.height())
    assert wait_for(app, lambda: d.backend.prompt["seen"] is True)
    settle(app)
    assert footer.property("text") == "Press the number of an option. Esc closes." and not d.shows("isSeenNote")


@pytest.mark.parametrize("letter,size", [("A", 1.0), ("C", 1.0), ("C", 1.4), ("E", 1.4)])
def test_the_footer_says_both_reasons_when_the_keys_are_locked_and_the_end_is_not_seen(app, desk, letter, size):
    d = desk()
    d.backend.setLayout(letter)
    assert d.backend.setFontScale(size)
    d.answer_for("t1")
    d.arm()
    tick_to(d, LONG)
    d.arm()
    footer = d.one("isFooterNote")
    assert footer.property("text") == f"Number keys off: click or press Tab. {SCROLL_NOTE}"
    assert footer.property("truncated") is False and footer.property("lineCount") <= 2
    assert d.one("isDigitsOff").property("text") == LOCK_LINE


def test_a_change_from_failed_to_ready_on_the_same_question_starts_the_guard(app, desk):
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    session, prompt = d.backend._session, d.backend._session.prompt
    window.setProperty("guardMs", 600000)
    session._set("failed", "press_timeout", prompt=prompt)  # the same question, not answerable
    settle(app)
    assert window.property("armed") is False and window.property("digitsLocked") is False
    session._set("ready", prompt=prompt)  # answerable again, with no new question: the guard runs again
    settle(app)
    assert d.backend.prompt["shown"] == 1 and window.property("armed") is False
    d.press(d.button("4"))
    key(app, window, Qt.Key.Key_4)
    assert d.client.pressed == []
    window.setProperty("guardMs", 20)
    d.arm()
    key(app, window, Qt.Key.Key_4)
    d.until("failed", "sent", "ready")
    assert d.client.pressed == [("t1", ["4"])]


def test_the_next_question_after_an_own_answer_that_failed_first_is_locked(app, desk):
    """The answer ends as failed (herdr-core did not confirm the key in time); the key arrives later and the agent
    asks its next question (reason "held"). The answer was over for the window at "Failed": the question is locked."""
    d = desk(pending_follow=(0.0,))
    window = d.answer_for("t1")
    d.arm()
    d.client.keep_key = True
    d.client.press_result = Failure("timeout")
    key(app, window, Qt.Key.Key_4)
    d.until("failed")
    assert d.backend.prompt["reason"] == "press_timeout" and d.client.late is not None
    d.client.press_result = None
    d.client.screens[:] = [EDIT]
    d.client.late(None)  # the key went, late: the agent asks its next question
    assert wait_for(app, lambda: d.backend.prompt["title"] == "Edit file" and d.state() == "ready")
    assert d.backend.prompt["reason"] == "held"
    d.arm()
    key(app, window, Qt.Key.Key_3)
    assert d.client.pressed == [("t1", ["4"])]
    assert_locked(d, window)


# ----- fix round 3: a press from before a change never moves the new detail; the top in view, then the end -----

def flickable(view):
    return next(i for i in walk(view) if i.inherits("QQuickFlickable"))


def repeat(app, window, which, times):
    """A key held down: the presses that the keyboard repeats (no release between them)."""
    for _ in range(times):
        QCoreApplication.sendEvent(window, QKeyEvent(QEvent.Type.KeyPress, which, NONE, "", True))
        settle(app)


def test_a_thumb_drag_held_across_a_change_moves_nothing_of_the_new_command_and_it_is_not_seen(app, desk):
    """I1 of re-review 2: the person drags the thumb of a long command to its end; a different long command comes
    during the drag; the drag goes on. Only a new press of the thumb moves the new command."""
    d = desk(screens=[LONG])
    window = d.answer_for("t1")
    d.arm()
    view = d.one("isDetail")
    start = centre(next(i for i in walk(view) if i.property("isScrollThumb")))
    QTest.mousePress(window, LEFT, NONE, start)
    for dy in range(0, 400, 20):
        QTest.mouseMove(window, start + QPoint(0, dy))
        settle(app)
    assert view.property("atEnd") is True and d.backend.prompt["seen"] is True
    tick_to(d, OTHER_START)
    view = d.one("isDetail")
    assert view.property("above") == 0
    for dy in (401, 200, 420):  # the same press goes on
        QTest.mouseMove(window, start + QPoint(0, dy))
        settle(app)
        assert view.property("above") == 0 and view.property("atEnd") is False, dy
    pause(app, 700)
    QTest.mouseRelease(window, LEFT, NONE, start + QPoint(0, 420))
    settle(app)
    assert d.backend.prompt["seen"] is False and view.property("above") == 0
    start = centre(next(i for i in walk(view) if i.property("isScrollThumb")))
    QTest.mousePress(window, LEFT, NONE, start)  # a new press: it moves the view
    for dy in range(0, 400, 20):
        QTest.mouseMove(window, start + QPoint(0, dy))
        settle(app)
    QTest.mouseRelease(window, LEFT, NONE, start + QPoint(0, 380))
    assert view.property("atEnd") is True and wait_for(app, lambda: d.backend.prompt["seen"] is True)


def test_a_text_drag_held_across_a_change_moves_nothing_of_the_new_command_and_it_is_not_seen(app, desk):
    d = desk(screens=[LONG])
    window = d.answer_for("t1")
    d.arm()
    view = d.one("isDetail")
    flick = flickable(view)
    start = centre(flick)
    QTest.mousePress(window, LEFT, NONE, start)
    for dy in range(0, 160, 20):
        QTest.mouseMove(window, start - QPoint(0, dy))
        settle(app)
    assert flick.property("contentY") > 50
    tick_to(d, OTHER_START)
    view = d.one("isDetail")
    assert flick.property("contentY") == 0
    for dy in range(160, 400, 20):  # the same press goes on, far
        QTest.mouseMove(window, start - QPoint(0, dy))
        settle(app)
        assert flick.property("contentY") == 0 and view.property("above") == 0, dy
    pause(app, 700)
    QTest.mouseRelease(window, LEFT, NONE, start - QPoint(0, 380))
    settle(app)
    assert d.backend.prompt["seen"] is False and flick.property("contentY") == 0


def test_a_flick_that_moves_by_itself_across_a_change_stops_at_the_top_of_the_new_command(app, desk):
    d = desk(screens=[LONG])
    window = d.answer_for("t1")
    d.arm()
    flick = flickable(d.one("isDetail"))
    QMetaObject.invokeMethod(flick, "flick", Q_ARG(float, 0.0), Q_ARG(float, -2500.0))  # a fast flick, let go
    app.processEvents()
    assert flick.property("flicking") is True
    tick_to(d, OTHER_START)
    pause(app, 800)
    assert flick.property("contentY") == 0 and flick.property("flicking") is False
    assert d.backend.prompt["seen"] is False


def test_a_scroll_key_held_across_a_change_moves_nothing_of_the_new_command_until_a_new_press(app, desk):
    d = desk(screens=[LONG])
    window = d.answer_for("t1")
    d.arm()
    view = d.one("isDetail")
    QTest.keyPress(window, Qt.Key.Key_PageDown)
    settle(app)
    repeat(app, window, Qt.Key.Key_PageDown, 30)
    assert view.property("atEnd") is True and wait_for(app, lambda: d.backend.prompt["seen"] is True)
    tick_to(d, OTHER_START)
    view = d.one("isDetail")
    repeat(app, window, Qt.Key.Key_PageDown, 30)  # still held
    QTest.keyRelease(window, Qt.Key.Key_PageDown)
    settle(app)
    assert view.property("above") == 0
    pause(app, 700)
    assert d.backend.prompt["seen"] is False
    key(app, window, Qt.Key.Key_PageDown)  # a new press moves it
    assert view.property("above") > 0


def test_the_end_counts_only_after_the_top_of_the_new_detail_was_in_view_after_the_guard(app, desk):
    """The rule that closes the class of I1: the window reports the end of a detail seen only when, after the reset of
    that question, it observed first the top of the detail in view and then its end. The top counts when it is in
    view at a moment the pointer guard is over (at the end of the guard, or at a later move): a move of the view while
    the guard runs (a press that started before the change, or a program) is not the person's own scroll."""
    d = desk(screens=[LONG])
    window = d.answer_for("t1")
    d.arm()
    window.setProperty("guardMs", 1500)
    tick_to(d, OTHER_START)
    view = d.one("isDetail")
    flick = flickable(view)
    flick.setProperty("contentY", flick.property("contentHeight") - flick.height())  # off the top, by code, at once
    settle(app)
    assert window.property("armed") is False and view.property("atEnd") is True
    window.setProperty("guardMs", 400)
    d.arm()
    pause(app, 300)
    assert d.backend.prompt["seen"] is False  # the end was in view after the guard, the top never
    key(app, window, Qt.Key.Key_Tab)  # the detail takes the keyboard: its arrow keys move it by 40 px
    key(app, window, Qt.Key.Key_Up)
    assert view.property("atTop") is False
    key(app, window, Qt.Key.Key_End)
    assert not wait_for(app, lambda: d.backend.prompt["seen"] is True, 0.3)
    key(app, window, Qt.Key.Key_Home)  # the top in view, after the guard
    assert d.backend.prompt["seen"] is False
    key(app, window, Qt.Key.Key_End)  # then the end
    assert wait_for(app, lambda: d.backend.prompt["seen"] is True)


def test_on_a_low_window_the_top_of_the_detail_must_be_in_the_window_before_its_end_counts(app, desk):
    d = desk(screens=[EDIT])
    d.open_group("blocked")
    click(app, d.root, d.control("t1"))
    d.window.setProperty("roomHeight", 300)
    assert wait_for(app, lambda: d.state() == "ready" and not d.backend._session.busy)
    d.window.setProperty("guardMs", 1500)
    tick_to(d, CREATE)
    scroller = d.one("isScroller")
    scroller.setProperty("contentY", scroller.property("contentHeight") - scroller.height())  # by code, at once
    settle(app)
    assert d.window.property("detailAtEnd") is True and d.window.property("detailAtTop") is False
    d.arm()
    pause(app, 300)
    assert d.backend.prompt["seen"] is False
    scroller.setProperty("contentY", 0)  # the person scrolls the window up: the top of the detail is in view
    settle(app)
    assert d.window.property("detailAtTop") is True and d.backend.prompt["seen"] is False
    scroller.setProperty("contentY", scroller.property("contentHeight") - scroller.height())  # then down to the end
    assert wait_for(app, lambda: d.backend.prompt["seen"] is True)


# ----- fix round 3: the lines of the number-key rule that only rarer transitions reach -----

def screen_reader_press(item):
    """The "Press" action of a screen reader on an item: no pointer press, no key."""
    actions = QAccessible.queryAccessibleInterface(item).actionInterface()
    assert actions is not None and "Press" in actions.actionNames()
    actions.doAction("Press")


def test_a_lock_is_sticky_through_an_answer_by_a_screen_reader(app, desk):
    """m1 (mutant K1): a screen reader presses "No" while the keys are locked (no pointer press, no key in the
    window); the next question of that answer stays locked."""
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    tick_to(d, CREATE)
    d.arm()
    assert_locked(d, window)
    d.client.on_press = lambda: d.client.screens.__setitem__(slice(None), [EDIT])
    screen_reader_press(d.button("3"))
    assert wait_for(app, lambda: d.backend.prompt["title"] == "Edit file" and d.state() == "ready")
    d.client.on_press = None
    settle(app)
    assert d.client.pressed == [("t1", ["3"])]
    d.arm()
    key(app, window, Qt.Key.Key_3)
    pause(app, 300)
    assert d.client.pressed == [("t1", ["3"])]
    assert_locked(d, window)


def test_after_the_next_question_of_an_own_answer_a_second_change_with_no_key_locks(app, desk):
    """m1 (mutant K2): the change of the next question uses up the answer; a tick then brings a third question with
    no key between: it is locked."""
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    d.client.on_press = lambda: d.client.screens.__setitem__(slice(None), [EDIT])
    key(app, window, Qt.Key.Key_4)
    assert wait_for(app, lambda: d.backend.prompt["title"] == "Edit file" and d.state() == "ready")
    d.client.on_press = None
    settle(app)
    assert window.property("digitsLocked") is False and window.property("answerSent") is False
    tick_to(d, CREATE)
    d.arm()
    key(app, window, Qt.Key.Key_3)
    pause(app, 300)
    assert d.client.pressed == [("t1", ["4"])]
    assert_locked(d, window)


def test_on_a_low_window_a_change_puts_the_content_of_the_window_back_at_its_top(app, desk):
    """m1 (mutant K3): the person scrolls the window content to its end (the detail is seen); a new question comes:
    the content of the window goes back to its top, and the new detail is not seen."""
    d = desk(screens=[EDIT])
    d.open_group("blocked")
    click(app, d.root, d.control("t1"))
    d.window.setProperty("roomHeight", 300)
    assert wait_for(app, lambda: d.state() == "ready" and not d.backend._session.busy)
    d.arm()
    scroller = d.one("isScroller")
    scroller.setProperty("contentY", scroller.property("contentHeight") - scroller.height())
    assert wait_for(app, lambda: d.backend.prompt["seen"] is True)
    assert scroller.property("contentY") > 0
    tick_to(d, CREATE)
    assert scroller.property("contentY") == 0
    d.arm()
    pause(app, 300)
    assert d.backend.prompt["seen"] is False


def test_a_next_question_with_a_note_other_than_held_is_locked(app, desk):
    """m2 (mutant K4): a text answer; the key of the text option went, then the screen showed an other question
    (the text did not go: reason "text_key_only"). That is not the plain next question of the answer: locked."""
    d = desk(screens=[ASK])
    window = d.answer_for("t1")
    to_the_field(d, app, window)
    d.client.on_press = lambda: d.client.screens.__setitem__(slice(None), [EDIT])
    key(app, window, Qt.Key.Key_Return)
    assert wait_for(app, lambda: d.backend.prompt["title"] == "Edit file" and d.state() == "ready")
    d.client.on_press = None
    settle(app)
    assert d.backend.prompt["reason"] == "text_key_only" and d.client.sent == []
    d.arm()
    key(app, window, Qt.Key.Key_3)
    pause(app, 300)
    assert d.client.pressed == [("t1", ["3"])]
    assert_locked(d, window)


def edit_prompt():
    from bellwether.prompts import parse
    return parse("claude-code", EDIT.text)


def test_a_new_question_that_shows_while_an_answer_is_on_its_way_is_locked(app, desk):
    """m2 (mutant K5): the rule of the window counts a change as the next question only when the engine is "ready"
    at the change. The engine of today shows a new question during an answer only as "pending" with the reason
    "earlier" (which the reason check refuses too); this test sets the state of the engine itself, as an engine
    that shows a new question while it is still "answering" would."""
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    held_answer(d, app, window)
    session = d.backend._session
    session._end_workers()  # the result of the held key changes nothing now
    session._set("answering", prompt=edit_prompt())
    settle(app)
    assert d.backend.prompt["shown"] == 2 and window.property("digitsLocked") is True
    session._set("ready", prompt=session.prompt)  # the same question: no change
    settle(app)
    d.client.press_gate.set()
    assert wait_for(app, lambda: not session._marks)
    d.client.press_gate = None
    d.arm()
    key(app, window, Qt.Key.Key_3)
    pause(app, 300)
    assert d.client.pressed == [("t1", ["4"])]
    assert_locked(d, window)


def test_an_answer_that_ends_ready_on_the_same_question_does_not_unlock_a_later_change(app, desk):
    """m2 (mutant K6): an answer ends with the same question ready again (no next question came of it); a tick then
    brings a new question with no key between: it is locked. The engine of today ends such an answer as "failed";
    this test sets the state of the engine itself."""
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    held_answer(d, app, window)
    session = d.backend._session
    session._end_workers()
    session._set("ready", prompt=session.prompt)  # the answered question, ready again
    settle(app)
    assert window.property("answerSent") is False
    d.client.press_gate.set()
    assert wait_for(app, lambda: not session._marks)
    d.client.press_gate = None
    d.client.on_press = None
    tick_to(d, CREATE)
    assert window.isActive()
    d.arm()
    key(app, window, Qt.Key.Key_3)
    pause(app, 300)
    assert d.client.pressed == [("t1", ["4"])]
    assert_locked(d, window)


def test_answer_on_an_other_agent_while_the_window_is_open_acts_as_an_open(app, desk):
    """m3: the keys are locked on t1; the person clicks "Answer" of t7 in the panel. That is an open: the lock ends,
    and both guards start."""
    d = desk()
    window = d.answer_for("t1")
    d.arm()
    tick_to(d, EDIT)
    assert window.property("digitsLocked") is True
    d.client.screens[:] = [CODEX]
    click(app, d.root, d.control("t7"))
    d.until("ready")
    assert d.backend.prompt["key"] == "t7" and window.property("digitsLocked") is False
    assert window.property("armed") is False and window.property("keysArmed") is False
    assert not d.shows("isNewMark") and not d.shows("isDigitsOff")
    key(app, window, Qt.Key.Key_3)  # in the guard: nothing
    assert d.client.pressed == []
    d.arm()
    key(app, window, Qt.Key.Key_3)
    d.until("failed", "sent", "ready")
    assert d.client.pressed == [("t7", ["3"])]
