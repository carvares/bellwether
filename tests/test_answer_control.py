"""The "Answer" control of a blocked agent row, in every layout: the real Main.qml, the real backend, a fake client
and real pointer events. A click on it opens the prompt of that agent and asks for the answer window; the rest of
the row still jumps. Screens are the made-up fixtures of the readers."""
import threading

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtTest import QTest

from bellwether import layouts
from bellwether.__main__ import IMPORT_PATH, UI_PATH
from bellwether.answer import Answer
from bellwether.backend import Backend
from bellwether.icons import Icons
from bellwether.state import Agent
from tests.audit import text_findings
from tests.test_backend_prompt import ScreenClient, wait_for
from tests.test_qml import LAYERSHELL_QMLDIR, OFFSCREEN_NOTE, click, rows, settle, use_screens, visible_texts, walk
from tests.test_skins import spoken, wait_jump

pytestmark = pytest.mark.skipif(not LAYERSHELL_QMLDIR.is_file(), reason="org.kde.layershell is not installed")

LETTERS = [letter for letter, _, _ in layouts.LAYOUTS]
LEFT, NONE = Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
AGENTS = [
    Agent("t1", "blocked", "rev", "Main", "claude-code"),
    Agent("t7", "blocked", "a reviewer with a very long name that cannot fit in one row", "api / fix the login", "codex"),
    Agent("box-pane", "blocked", "old", "Main", "claude-code"),  # a key that is not a terminal address: no answer
    Agent("t2", "working", "ana", "api / 1", "codex"),
    Agent("t3", "done", "bob", "", "claude-code"),
    Agent("t4", "idle", "", "docs", "codex"),
]


class Panel:
    """The panel (Main.qml) with a real backend and a client of made-up screens."""

    def __init__(self, app, tmp_path, agents=AGENTS, **more):
        self.app = app
        self.client = ScreenClient()
        self.backend = Backend(self.client, settings_path=tmp_path / "state.json",
                               icons=Icons(tmp_path / "app", tmp_path / "cache"),
                               follow=more.pop("follow", (0.0, 0.0, 0.0)), prompt_floor=0.0, **more)
        self.messages: list[str] = []
        self.asked: list[str] = []
        self.backend.answerRequested.connect(lambda: self.asked.append(self.backend.prompt["key"]))
        self._previous = qInstallMessageHandler(lambda mode, context, text: self.messages.append(text))
        self.engine = QQmlApplicationEngine()
        self.engine.warnings.connect(lambda errors: self.messages.extend(e.toString() for e in errors))
        self.engine.rootContext().setContextProperty("backend", self.backend)
        self.engine.addImportPath(str(IMPORT_PATH))
        self.engine.load(UI_PATH / "Main.qml")
        assert self.engine.rootObjects(), self.messages
        self.root: QQuickWindow = self.engine.rootObjects()[0]
        self.opener = Answer(self.engine, self.backend)  # as the program does it: the answer window
        use_screens(self.root, [("S", 0, 0, 1920, 1080)], "S", 400, 100)
        self.backend.apply(list(agents))
        settle(app)

    @property
    def window(self):
        """The answer window. None before its first open."""
        return self.opener.window

    def close(self):
        self.backend.stop()
        del self.opener
        del self.engine
        self.app.processEvents()
        qInstallMessageHandler(self._previous)

    def warnings(self):
        """The Qt messages without the two notes of the off-screen platform (it is not Wayland, and it has no size
        hints for a window with a fixed size)."""
        return [m for m in self.messages if OFFSCREEN_NOTE not in m and "propagateSizeHints" not in m]

    def open_group(self, state="blocked"):
        if self.root.property("openState") != state:
            click(self.app, self.root, next(i for i in rows(self.root, "status") if i.property("stateName") == state))
        assert self.root.property("openState") == state

    def controls(self):
        return [i for i in walk(self.root.contentItem()) if i.property("hitRole") == "answer" and i.isVisible()]

    def control(self, key):
        return next(i for i in self.controls() if i.property("key") == key)

    def row(self, key):
        return next(i for i in rows(self.root, "agent") if i.property("key") == key)

    def state(self):
        return self.backend.prompt["state"]


@pytest.fixture(params=[(letter, scale) for scale in (1.0, 1.5) for letter in LETTERS], ids=lambda p: f"{p[0]}-{p[1]}")
def panel(request, app, tmp_path):
    letter, scale = request.param
    made = Panel(app, tmp_path)
    made.backend.setLayout(letter)
    assert made.backend.setScale(scale) is True
    settle(app)
    yield made
    warnings = made.warnings()
    made.close()
    assert warnings == []


def centre(item, dx=0.5, dy=0.5):
    return item.mapToScene(QPointF(item.width() * dx, item.height() * dy)).toPoint()


def test_only_the_rows_of_blocked_agents_with_a_terminal_have_the_control(app, panel):
    panel.open_group("blocked")
    assert sorted(i.property("key") for i in panel.controls()) == ["t1", "t7"]
    assert len(rows(panel.root, "agent")) == 3
    assert spoken(panel.control("t1")) == "Answer rev"
    assert "Answer" in {t for t in visible_texts(panel.root)} or "ANSWER" in {t.upper() for t in visible_texts(panel.root)}
    for state in ("working", "done", "idle"):
        panel.open_group(state)
        assert panel.controls() == [] and len(rows(panel.root, "agent")) == 1


def test_a_click_on_the_control_opens_the_prompt_of_that_agent_and_does_not_jump(app, panel):
    panel.open_group("blocked")
    click(app, panel.root, panel.control("t1"))
    assert panel.asked == ["t1"] and panel.backend.prompt["key"] == "t1"
    assert wait_for(app, lambda: panel.state() == "ready") and panel.backend.prompt["title"] == "Bash command"
    window = panel.window
    assert window is not None and window.isVisible() and window.width() == 600
    shown_texts = {i.property("text") for i in walk(window.contentItem()) if i.isVisible() and i.property("text")}
    assert {"rev", "t1", "Bash command", "Do you want to proceed?", "Yes", "No"} <= shown_texts
    assert panel.client.focused == [] and panel.backend.opening == ""
    assert panel.client.pressed == [] and panel.client.sent == []
    click(app, panel.root, panel.control("t7"))  # a different agent: the same window changes to it
    assert panel.asked == ["t1", "t7"] and panel.backend.prompt["key"] == "t7"
    assert panel.window is window and window.isVisible() and panel.state() != "closed"
    assert wait_for(app, lambda: panel.state() == "unreadable")  # the Bash screen is not a dialog of Codex
    assert panel.client.focused == [] and panel.client.pressed == []


def test_a_click_on_the_rest_of_the_row_jumps_and_does_not_open(app, panel):
    panel.open_group("blocked")
    row, control = panel.row("t1"), panel.control("t1")
    left_of_control = control.mapToScene(QPointF(-6, control.height() / 2)).toPoint()
    for point in (centre(row, 0.3), left_of_control):
        QTest.mouseClick(panel.root, LEFT, NONE, point)
        settle(app)
        wait_jump(app, panel.backend)
    assert panel.client.focused == ["t1", "t1"] and panel.asked == [] and panel.state() == "closed"
    assert panel.window is None
    click(app, panel.root, panel.row("box-pane"))  # a blocked row with no control jumps everywhere
    wait_jump(app, panel.backend)
    assert panel.client.focused[-1] == "box-pane" and panel.asked == []


def test_a_drag_from_the_control_moves_the_panel_and_does_nothing_else(app, panel):
    panel.open_group("blocked")
    root = panel.root
    before = (root.property("posX"), root.property("posY"))
    start = centre(panel.control("t1"))
    QTest.mousePress(root, LEFT, NONE, start)
    settle(app)
    for step in (QPoint(-10, 5), QPoint(-20, 12)):
        QTest.mouseMove(root, start + step)
        settle(app)
    QTest.mouseRelease(root, LEFT, NONE, start + QPoint(-20, 12))
    settle(app)
    assert (root.property("posX"), root.property("posY")) == (before[0] - 30, before[1] + 17)
    assert panel.asked == [] and panel.state() == "closed" and panel.client.focused == []
    assert root.property("openState") == "blocked"


def test_the_control_is_inert_while_a_jump_is_in_flight(app, panel):
    panel.open_group("blocked")
    panel.client.focus_gate = threading.Event()
    try:
        click(app, panel.root, panel.row("box-pane"))
        assert panel.backend.opening == "box-pane"
        click(app, panel.root, panel.control("t1"))
        assert panel.asked == [] and panel.state() == "closed" and panel.client.focused == ["box-pane"]
        assert panel.control("t1").property("inert") is True
    finally:
        panel.client.focus_gate.set()
    wait_jump(app, panel.backend)
    click(app, panel.root, panel.control("t1"))
    assert panel.asked == ["t1"] and panel.client.focused == ["box-pane"]


def test_the_pointer_look_is_on_the_control_and_not_on_its_row(app, panel):
    panel.open_group("blocked")
    control, row = panel.control("t1"), panel.row("t1")
    QTest.mouseMove(panel.root, centre(control))
    settle(app)
    assert control.property("hovered") is True and row.property("hovered") is False
    QTest.mouseMove(panel.root, centre(row, 0.3))
    settle(app)
    assert control.property("hovered") is False and row.property("hovered") is True


@pytest.mark.parametrize("font_scale", [0.8, 1.4])
def test_the_control_keeps_its_size_and_the_long_label_gives_way(app, panel, font_scale):
    panel.backend.setFontScale(font_scale)
    settle(app)
    panel.open_group("blocked")
    short, long = panel.control("t1"), panel.control("t7")
    assert (short.width(), short.height()) == (long.width(), long.height()) and short.width() >= 40
    word = next(i for i in walk(long) if i.property("isAnswerWord"))
    assert word.property("contentWidth") <= long.width() - 8 and word.property("truncated") is False
    row = panel.row("t7")
    inside = row.mapRectToScene(row.boundingRect())
    box = long.mapRectToScene(long.boundingRect())
    assert inside.contains(box)
    assert text_findings(panel.root) == []


def test_the_control_has_the_accent_of_the_custom_look(app, panel):
    panel.open_group("blocked")
    control = panel.control("t1")
    word = next(i for i in walk(control) if i.property("isAnswerWord"))
    assert panel.backend.setColor("accent", "#ff00aa") is True
    settle(app)
    assert QColor(word.property("color")).name() == "#ff00aa"
    QTest.mouseMove(panel.root, centre(control))
    settle(app)
    plate = next(i for i in walk(control) if i.property("isAnswerPlate"))
    assert QColor(plate.property("color")).name() == "#ff00aa"
    assert QColor(word.property("color")).name() in ("#202124", "#f1f3f4")  # the ink that can be read on the plate
