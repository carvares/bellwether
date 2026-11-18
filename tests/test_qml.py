"""Smoke test of the real Main.qml, loaded the same way as herdr_float/__main__.py (off screen)."""
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, Qt, qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from herdr_float.__main__ import IMPORT_PATH, UI_PATH
from herdr_float.backend import Backend
from herdr_float.state import Agent
from herdr_float.tray import STATE_COLORS

LAYERSHELL_QMLDIR = Path("/usr/lib/qt6/qml/org/kde/layershell/qmldir")
# layer-shell-qt says this for every window on a platform that is not Wayland. It is expected off screen.
OFFSCREEN_NOTE = "is not a wayland window"

pytestmark = pytest.mark.skipif(
    not LAYERSHELL_QMLDIR.is_file(),
    reason=f"the system QML module org.kde.layershell is not installed ({LAYERSHELL_QMLDIR} not found)",
)


def walk(item):
    yield item
    for child in item.childItems():
        yield from walk(child)


@pytest.fixture
def window(app, fake_client, tmp_path):
    """Yield (root window, backend, Qt messages). The poll thread is not started."""
    assert app.platformName() == "offscreen"
    backend = Backend(fake_client, settings_path=tmp_path / "state.json")
    messages = []
    previous = qInstallMessageHandler(lambda mode, context, text: messages.append(text))
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda errors: messages.extend(e.toString() for e in errors))
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("stateColors_", STATE_COLORS)
    engine.addImportPath(str(IMPORT_PATH))
    engine.load(UI_PATH / "Main.qml")
    try:
        roots = engine.rootObjects()
        assert roots, f"Main.qml did not load: {messages}"
        assert isinstance(roots[0], QQuickWindow)
        yield roots[0], backend, messages
    finally:
        del engine
        app.processEvents()
        qInstallMessageHandler(previous)
    assert backend._thread is None


def rows(root, kind):
    """The visible rows of one kind ("status" or "agent"), in the order on the screen."""
    return [i for i in walk(root.contentItem()) if i.property("rowKind") == kind and i.isVisible()]


def settle(app):
    """Deliver the events and let the items take their places (the layout runs before a frame)."""
    for _ in range(5):
        app.processEvents()
        time.sleep(0.01)


def click(app, root, item):
    """A real pointer click (press and release) in the middle of a row."""
    center = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
    QTest.mouseClick(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center)
    settle(app)


AGENTS = [
    Agent("t1", "blocked", "rev", "Main"),
    Agent("t2", "working", "ana", "api / 1"),
    Agent("t3", "working", "bob", ""),
]


def test_main_qml_shows_four_status_rows_and_opens_one_group_at_a_time(app, window):
    root, backend, messages = window
    backend.apply(AGENTS)
    settle(app)
    status = rows(root, "status")
    assert [r.property("stateName") for r in status] == ["blocked", "done", "working", "idle"]
    assert (root.width(), root.height()) == (240, 136)
    assert rows(root, "agent") == []

    click(app, root, status[2])
    assert root.property("openState") == "working"
    assert [r.property("key") for r in rows(root, "agent")] == ["t2", "t3"]
    assert root.height() == 136 + 2 * 26

    click(app, root, status[0])  # a second group closes the first
    assert root.property("openState") == "blocked"
    assert [r.property("key") for r in rows(root, "agent")] == ["t1"]

    click(app, root, status[1])  # a group without agents does not open, and the open group stays
    assert root.property("openState") == "blocked"

    click(app, root, status[0])  # a second click closes the group
    assert root.property("openState") == ""
    assert rows(root, "agent") == []
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_a_click_on_an_agent_row_jumps_one_time(app, window):
    root, backend, messages = window
    backend.apply(AGENTS)
    settle(app)
    click(app, root, rows(root, "status")[2])
    click(app, root, rows(root, "agent")[1])
    for _ in range(100):  # the jump runs on its own thread
        settle(app)
        if backend._client.focused and backend.opening == "":
            break
    assert backend._client.focused == ["t3"]
    assert root.property("openState") == "working"
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_the_open_group_closes_when_it_is_empty_or_herdr_is_offline(app, window):
    root, backend, messages = window
    backend.apply(AGENTS)
    settle(app)
    click(app, root, rows(root, "status")[0])
    assert root.property("openState") == "blocked"
    backend.apply(AGENTS[1:])  # the one blocked agent is gone
    settle(app)
    assert root.property("openState") == ""

    click(app, root, rows(root, "status")[2])
    assert root.property("openState") == "working"
    backend.apply(None)
    settle(app)
    assert root.property("openState") == ""
    assert rows(root, "status") == [] and rows(root, "agent") == []
    offline_text = next(i for i in walk(root.contentItem()) if i.property("text") == "offline")
    assert offline_text.isVisible() is True
    assert root.height() == 46
    backend.apply(AGENTS)  # back online: the group does not open by itself
    settle(app)
    assert root.property("openState") == ""
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_a_failed_jump_shows_its_message_where_the_agent_is_now(app, window):
    root, backend, messages = window
    backend.apply(AGENTS)
    settle(app)

    def texts():
        return [i.property("text") for i in walk(root.contentItem()) if i.isVisible() and i.property("text")]

    backend.focusFailed.emit("t2", "could not raise the window")
    settle(app)
    assert root.property("openState") == "working"  # the group of the agent opens
    assert texts().count("could not raise the window") == 1
    backend.apply([Agent("t1", "blocked", "rev", "Main"), Agent("t2", "idle", "ana", "api / 1")])
    settle(app)
    assert root.property("openState") == "idle"  # the agent changed its state: the message follows it
    assert texts().count("could not raise the window") == 1
    backend.apply([Agent("t1", "blocked", "rev", "Main")])  # the agent is gone: the line at the bottom
    settle(app)
    assert root.property("openState") == ""
    assert texts().count("could not raise the window") == 1
    assert root.height() == 136 + 24
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []
