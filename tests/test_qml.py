"""Smoke test of the real Main.qml, loaded the same way as herdr_float/__main__.py (off screen)."""
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt, qInstallMessageHandler
from PySide6.QtGui import QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from herdr_float.__main__ import IMPORT_PATH, UI_PATH
from herdr_float.backend import Backend
from herdr_float.icons import Icons
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
    # The icons folder is a made-up one in tmp_path. It does not exist until a test makes it.
    icons = Icons(tmp_path / "app", tmp_path / "cache")
    backend = Backend(fake_client, settings_path=tmp_path / "state.json", icons=icons)
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


def test_a_failure_message_opens_its_group_one_time_and_then_follows_only_a_state_change(app, window):
    root, backend, messages = window
    backend.apply(AGENTS)
    settle(app)
    backend.focusFailed.emit("t2", "could not raise the window")
    settle(app)
    assert root.property("openState") == "working"
    click(app, root, rows(root, "status")[2])  # the person closes the group
    assert root.property("openState") == ""
    backend.apply(AGENTS + [Agent("t4", "idle", "cy", "")])  # new data, the failed agent did not move
    settle(app)
    assert root.property("openState") == ""
    click(app, root, rows(root, "status")[0])  # the person opens a different group
    backend.apply(AGENTS)
    settle(app)
    assert root.property("openState") == "blocked"
    backend.apply([AGENTS[0], Agent("t2", "idle", "ana", "api / 1"), AGENTS[2]])  # the failed agent moved
    settle(app)
    assert root.property("openState") == "idle"
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_the_scroll_indicator_does_not_take_clicks_or_the_wheel(app, window):
    root, backend, messages = window
    backend.apply([Agent(f"i{n:02d}", "idle", f"helper {n:02d}", "pool") for n in range(12)])
    settle(app)
    click(app, root, rows(root, "status")[3])
    row = rows(root, "agent")[1]
    edge = row.mapToScene(QPointF(row.width() - 1, row.height() / 2))  # on the 3 px of the indicator
    flick = next(i for i in walk(root.contentItem()) if i.property("scrolls"))
    wheel = QWheelEvent(edge, edge, QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    app.sendEvent(root, wheel)
    settle(app)
    assert flick.property("contentY") == 52
    QTest.mouseClick(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, edge.toPoint())
    for _ in range(100):
        settle(app)
        if backend._client.focused and backend.opening == "":
            break
    assert backend._client.focused == ["i03"]  # the row that is at that place after the scroll of 2 rows
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


@pytest.mark.parametrize(
    "states, colour",
    [
        (["blocked", "done", "idle", "working"], STATE_COLORS["blocked"]),
        (["done", "idle", "working"], STATE_COLORS["done"]),
        (["idle", "working", "working", "working"], STATE_COLORS["idle"]),  # idle is above working
        (["working"], STATE_COLORS["working"]),
        ([], "#3c4043"),
        (None, "#3c4043"),  # offline
    ],
)
def test_the_border_has_the_colour_of_the_top_state_and_the_panel_keeps_its_size(app, window, states, colour):
    root, backend, messages = window
    backend.apply(None if states is None else [Agent(f"t{n}", s, "a", "") for n, s in enumerate(states)])
    settle(app)
    image = root.grabWindow()
    assert (image.width(), image.height()) == ((240, 46) if states is None else (240, 136))
    middle = image.width() // 2
    assert [image.pixelColor(middle, y).name() for y in (0, 1)] == [colour, colour]  # 2 px, inside the panel
    assert image.pixelColor(middle, 2).name() != colour
    assert image.pixelColor(middle, image.height() - 1).name() == colour
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_agent_rows_show_the_icon_of_the_program_and_no_program_word(app, window, tmp_path):
    root, backend, messages = window
    folder = tmp_path / "app" / "icons"
    folder.mkdir(parents=True)
    square = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path %sd="M2 2h20v20H2z"/></svg>'
    (folder / "pi.svg").write_text(square % "")  # a black glyph: it must show in the text colour
    (folder / "claude.svg").write_text(square % 'fill="#d97757" ')  # a picture: it shows as it is
    backend.apply([
        Agent("t1", "working", "rev", "Main", "pi"),
        Agent("t2", "working", "", "Main", "claude-code"),
        Agent("t3", "working", "", "Main", "claude-code"),
    ])
    settle(app)
    click(app, root, rows(root, "status")[2])
    root.setProperty("hoverRow", None)
    settle(app)
    assert [r.property("key") for r in rows(root, "agent")] == ["t2", "t3", "t1"]
    icons = [i for i in walk(root.contentItem()) if i.property("isProgramIcon") and i.isVisible()]
    assert [(i.width(), i.height()) for i in icons] == [(16, 16)] * 3
    image = root.grabWindow()
    centres = [i.mapToScene(QPointF(8, 8)).toPoint() for i in icons]
    assert [image.pixelColor(c).name() for c in centres] == ["#d97757", "#d97757", "#e8eaed"]
    texts = [i.property("text") for i in walk(root.contentItem()) if i.isVisible() and i.property("text")]
    assert [t for t in texts if t in ("rev", "Main", "t1", "t2", "t3")] == ["Main", "t2", "Main", "t3", "rev", "Main"]
    assert "claude-code" not in texts and "pi" not in texts
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_agent_rows_show_the_program_word_when_the_app_has_no_icons(app, window):
    root, backend, messages = window
    backend.apply([Agent("t2", "working", "", "Main", "claude-code")])
    settle(app)
    click(app, root, rows(root, "status")[2])
    assert [i for i in walk(root.contentItem()) if i.property("isProgramIcon") and i.isVisible()] == []
    texts = [i.property("text") for i in walk(root.contentItem()) if i.isVisible() and i.property("text")]
    assert "claude-code" in texts and "Main" in texts
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def shown_icons(root):
    return [i for i in walk(root.contentItem()) if i.property("isProgramIcon") and i.isVisible()]


def test_an_icon_copy_that_was_deleted_shows_again_with_no_warning(app, window, tmp_path):
    root, backend, messages = window
    folder = tmp_path / "app" / "icons"
    folder.mkdir(parents=True)
    (folder / "pi.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M2 2h20v20H2z"/></svg>')
    backend.apply([Agent("t1", "working", "", "Main", "pi")])
    settle(app)
    click(app, root, rows(root, "status")[2])
    for copy in (tmp_path / "cache").iterdir():
        copy.unlink()  # the person deleted the cache while the widget runs
    backend.apply([Agent("t1", "working", "", "Main", "pi"), Agent("t2", "working", "", "docs", "pi")])
    settle(app)
    root.setProperty("hoverRow", None)
    settle(app)
    icons = shown_icons(root)
    assert len(icons) == 2
    image = root.grabWindow()
    assert [image.pixelColor(i.mapToScene(QPointF(8, 8)).toPoint()).name() for i in icons] == ["#e8eaed"] * 2
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_an_icon_that_does_not_load_gives_the_row_the_layout_without_an_icon(app, window, tmp_path):
    root, backend, messages = window
    folder = tmp_path / "app" / "icons"
    folder.mkdir(parents=True)
    (folder / "pi.svg").write_bytes(b"\x00\x01 this is not a picture")  # not text: given to QML as it is
    backend.apply([Agent("t1", "working", "rev", "Main", "pi")])
    settle(app)
    click(app, root, rows(root, "status")[2])
    assert shown_icons(root) == []
    label = next(i for i in walk(root.contentItem()) if i.isVisible() and i.property("text") == "rev")
    assert label.x() == 24  # the place of the text of a row without an icon: no gap
