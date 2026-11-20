"""Smoke test of the real panel (the layer shell), loaded the same way as bellwether/__main__.py (off screen)."""
import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import shiboken6
from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl, Signal, Slot, qInstallMessageHandler
from PySide6.QtGui import QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlExpression, qmlContext, qmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from bellwether.__main__ import UI_PATH, follow_refresh_rate
from bellwether.platform.linux import IMPORT_PATH
from bellwether.backend import Backend
from bellwether.icons import Icons
from bellwether.layouts import built_skins
from bellwether.state import STATE_COLORS, Agent

LAYERSHELL_QMLDIR = Path("/usr/lib/qt6/qml/org/kde/layershell/qmldir")
# The panel in each window shell: the layer shell, as the program loads it on KDE Wayland, and the plain shell.
LAYER_QML = UI_PATH / "shells" / "Layer.qml"
SHELLS = {"layer": LAYER_QML, "plain": UI_PATH / "shells" / "Plain.qml"}
# layer-shell-qt says this for every window on a platform that is not Wayland. It is expected off screen.
OFFSCREEN_NOTE = "is not a wayland window"
# The sizes of Layout C (design/layouts/c-hud.qml): the panel, a closed panel, an agent row, the space under a list.
WIDTH, CLOSED, OFFLINE, AGENT_ROW, LIST_END = 320, 192, 108, 28, 4
NEUTRAL, FRAME = "#6b747d", "#2b333b"

# The skins of the program, a second skin that only the tests have, and a skin file that does not load.
SKINS = {**built_skins(), "T": Path(__file__).parent / "skins" / "T.qml", "X": Path(__file__).parent / "skins" / "Broken.qml"}
T_WIDTH, T_ROW = 240, 20  # the test skin: four status rows and the list of the open group below them

pytestmark = pytest.mark.skipif(
    not LAYERSHELL_QMLDIR.is_file(),
    reason=f"the system QML module org.kde.layershell is not installed ({LAYERSHELL_QMLDIR} not found)",
)


def walk(item):
    yield item
    for child in item.childItems():
        yield from walk(child)


class RecordingBackend(Backend):
    """The real backend. It also records the positions that the QML saves."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.saves = []
        self.screens = []  # the screen name of each save

    @Slot(int, int, str)
    def savePosition(self, x, y, screen=""):
        self.saves.append((x, y))
        self.screens.append(screen)
        super().savePosition(x, y, screen)

    @Slot(str)
    def saveScreen(self, screen):
        self.screens.append(screen)  # a screen with no place
        super().saveScreen(screen)


@pytest.fixture
def window(app, fake_client, tmp_path, shell):
    """Yield (root window, backend, Qt messages) of the panel in the shell of the test (the layer shell unless the
    test gives one). The poll thread is not started."""
    assert app.platformName() == "offscreen"
    # The icons folder is a made-up one in tmp_path. It does not exist until a test makes it.
    icons = Icons(tmp_path / "app", tmp_path / "cache")
    backend = RecordingBackend(fake_client, settings_path=tmp_path / "state.json", icons=icons, skins=SKINS)
    messages = []
    previous = qInstallMessageHandler(lambda mode, context, text: messages.append(text))
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda errors: messages.extend(e.toString() for e in errors))
    engine.rootContext().setContextProperty("backend", backend)
    engine.addImportPath(str(IMPORT_PATH))
    engine.load(SHELLS[shell])
    try:
        roots = engine.rootObjects()
        assert roots, f"the panel did not load: {messages}"
        assert isinstance(roots[0], QQuickWindow)
        yield roots[0], backend, messages
    finally:
        del engine
        app.processEvents()
        qInstallMessageHandler(previous)
    assert backend._thread is None


def rows(root, kind):
    """The visible rows of one kind ("status" or "agent"), in the order on the screen."""
    return [i for i in walk(root.contentItem()) if i.property("hitRole") == kind and i.isVisible()]


def visible_texts(root):
    """Every text on the screen, in the order of the items."""
    return [i.property("text") for i in walk(root.contentItem()) if i.isVisible() and i.property("text")]


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
    assert (root.width(), root.height()) == (WIDTH, CLOSED)
    assert rows(root, "agent") == []

    click(app, root, status[2])
    assert root.property("openState") == "working"
    assert [r.property("key") for r in rows(root, "agent")] == ["t2", "t3"]
    assert root.height() == CLOSED + 2 * AGENT_ROW + LIST_END

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
    assert visible_texts(root) == ["BELLWETHER", "NO LINK", "OFFLINE", "OFFLINE"]  # the header, the tag and the plate
    assert root.height() == OFFLINE
    backend.apply(AGENTS)  # back online: the group does not open by itself
    settle(app)
    assert root.property("openState") == ""
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_a_failed_jump_shows_its_message_where_the_agent_is_now(app, window):
    root, backend, messages = window
    backend.apply(AGENTS)
    settle(app)

    def texts():
        return visible_texts(root)

    backend.focusFailed.emit("t2", "could not raise the window")
    settle(app)
    assert root.property("openState") == "working"  # the group of the agent opens
    assert texts().count("! could not raise the window") == 1
    backend.apply([Agent("t1", "blocked", "rev", "Main"), Agent("t2", "idle", "ana", "api / 1")])
    settle(app)
    assert root.property("openState") == "idle"  # the agent changed its state: the message follows it
    assert texts().count("! could not raise the window") == 1
    backend.apply([Agent("t1", "blocked", "rev", "Main")])  # the agent is gone: the line at the bottom
    settle(app)
    assert root.property("openState") == ""
    assert texts().count("! could not raise the window") == 1
    assert root.height() == CLOSED + 24
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
    flick = next(i for i in walk(root.contentItem()) if i.property("hitRole") == "scroll" and i.isVisible())
    wheel = QWheelEvent(edge, edge, QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    app.sendEvent(root, wheel)
    settle(app)
    assert flick.property("contentY") == 2 * AGENT_ROW
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
        ([], NEUTRAL),
        (None, NEUTRAL),  # offline
    ],
)
def test_the_brackets_and_the_tag_have_the_colour_of_the_top_state_and_the_panel_keeps_its_size(
    app, window, states, colour
):
    root, backend, messages = window
    backend.apply(None if states is None else [Agent(f"t{n}", s, "a", "") for n, s in enumerate(states)])
    settle(app)
    image = root.grabWindow()
    assert (image.width(), image.height()) == ((WIDTH, OFFLINE) if states is None else (WIDTH, CLOSED))
    right, bottom = image.width() - 1, image.height() - 1
    # The four corner brackets: 14 px long and 2 px thick, inside the panel.
    corners = [(0, 0), (13, 1), (1, 13), (right, 0), (right - 13, 1), (0, bottom), (1, bottom - 13), (right, bottom)]
    assert [image.pixelColor(x, y).name() for x, y in corners] == [colour] * len(corners)
    # Between the brackets the frame is the neutral line: the status does not change the size of anything.
    assert [image.pixelColor(x, y).name() for x, y in ((14, 0), (0, 14), (right // 2, 0), (right // 2, bottom))] == [FRAME] * 4
    assert image.pixelColor(2, 2).name() not in (colour, FRAME)
    tag = next(i for i in walk(root.contentItem()) if i.property("isTopTag"))
    word = "OFFLINE" if states is None else "NO AGENTS" if not states else states[0].upper()
    assert (tag.property("text"), tag.property("color").name()) == (word, colour)
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
    assert [r.property("key") for r in rows(root, "agent")] == ["t1", "t2", "t3"]  # the agent with a name is first
    icons = [i for i in walk(root.contentItem()) if i.property("isProgramIcon") and i.isVisible()]
    assert [(i.width(), i.height()) for i in icons] == [(16, 16)] * 3
    image = root.grabWindow()
    centres = [i.mapToScene(QPointF(8, 8)).toPoint() for i in icons]
    assert [image.pixelColor(c).name() for c in centres] == ["#e8eaed", "#d97757", "#d97757"]
    texts = visible_texts(root)
    assert [t for t in texts if t in ("rev", "Main") or "t" in t] == ["rev", "Main", "Main", "[t2]", "Main", "[t3]"]
    assert "claude-code" not in texts and "pi" not in texts
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_agent_rows_show_the_program_word_when_the_app_has_no_icons(app, window):
    root, backend, messages = window
    backend.apply([Agent("t2", "working", "", "Main", "claude-code")])
    settle(app)
    click(app, root, rows(root, "status")[2])
    assert [i for i in walk(root.contentItem()) if i.property("isProgramIcon") and i.isVisible()] == []
    texts = visible_texts(root)
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
    assert label.x() == 20  # the place of the text of a row without an icon: no gap


def many(**counts):
    return [Agent(f"{state[0]}{n:03d}", state, f"agent {n:03d}", "pool") for state, c in counts.items() for n in range(c)]


def test_the_header_total_is_the_sum_of_the_counts_and_the_counts_have_two_digits(app, window):
    root, backend, messages = window
    backend.apply(many(blocked=1, done=0, working=3, idle=12))
    settle(app)
    total = next(i for i in walk(root.contentItem()) if i.property("isTotal"))
    assert total.property("text") == "AGENTS 16"
    assert root.property("panel").property("total") == sum(g["count"] for g in backend.groups) == 16
    numerals = {}
    for item in walk(root.contentItem()):
        if item.property("countFor"):
            row = item.parentItem()  # the zero at the front and the count
            numerals[item.property("countFor")] = "".join(t.property("text") for t in row.childItems() if t.isVisible())
    assert numerals == {"blocked": "01", "done": "00", "working": "03", "idle": "12"}
    backend.apply(many(working=7))
    settle(app)
    assert total.property("text") == "AGENTS 07"
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_the_header_parts_do_not_touch_in_the_widest_case(app, window):
    """The name, a three-digit total and the longest top tag with its lamp: in this order, a gap between each."""
    root, backend, messages = window
    backend.apply(many(blocked=1, working=120))
    settle(app)
    header = next(i for i in walk(root.contentItem()) if i.property("isTotal")).parentItem()
    name, total, tag, lamp = header.childItems()
    assert (name.property("text"), total.property("text"), tag.property("text")) == ("BELLWETHER", "AGENTS 121", "BLOCKED")
    spans = [(i.x(), i.x() + i.property("contentWidth" if i is not lamp else "width")) for i in (name, total, lamp, tag)]
    assert spans[0][0] == 0 and spans[-1][1] <= header.width()
    assert all(left[1] + 4 <= right[0] for left, right in zip(spans, spans[1:])), spans
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def cells(root):
    """The cells of the bar under the header, from left to right: (state or "", x, width)."""
    found = [i for i in walk(root.contentItem()) if i.property("isCell") and i.isVisible()]
    return sorted(((i.property("cellState"), i.x(), i.width()) for i in found), key=lambda cell: cell[1])


@pytest.mark.parametrize(
    "counts, lit",
    [
        ({"blocked": 1, "done": 2, "working": 3, "idle": 4}, [1, 2, 3, 4]),  # one cell for each agent
        ({"working": 2}, [0, 0, 2, 0]),  # 2 cells fill the bar: no empty cells
        ({"idle": 1}, [0, 0, 0, 1]),
        ({"blocked": 1, "done": 1, "idle": 1}, [1, 1, 0, 1]),
        ({"done": 20, "working": 39}, [0, 20, 39, 0]),
        ({"done": 20, "working": 40}, [0, 20, 40, 0]),
        ({"blocked": 1, "done": 2, "working": 3, "idle": 12}, [1, 2, 3, 12]),
        ({"blocked": 1, "idle": 299}, [1, 0, 0, 59]),  # more agents than cells: a state with an agent keeps a cell
        ({"blocked": 100, "done": 1, "working": 100, "idle": 1}, [29, 1, 29, 1]),
        ({"working": 61}, [0, 0, 60, 0]),  # one agent more than the cells
        ({"done": 1, "working": 60}, [0, 1, 59, 0]),
        # The shares are too many (62): the biggest state gives the extra cells back.
        ({"blocked": 1, "done": 1, "working": 1, "idle": 500}, [1, 1, 1, 57]),
        # The shares are too few (57): the biggest state gets the cells that are left.
        ({"blocked": 7, "done": 7, "working": 7, "idle": 41}, [6, 6, 6, 42]),
    ],
)
def test_the_bar_shows_the_share_of_each_state_and_a_state_with_an_agent_is_never_invisible(app, window, counts, lit):
    root, backend, messages = window
    backend.apply(many(**counts))
    settle(app)
    bar = cells(root)
    states = [state for state, _, _ in bar if state]
    assert [states.count(s) for s in ("blocked", "done", "working", "idle")] == lit
    assert states == sorted(states, key=("blocked", "done", "working", "idle").index)  # the row order
    assert len(bar) == len(states) == min(sum(counts.values()), 60)  # one cell for each agent, and every cell is lit
    assert empty_tracks(root) == []
    widths = {round(width, 3) for _, _, width in bar}
    assert len(widths) == 1 and min(widths) >= 3  # equal cells, so the width of a state is its share
    gap = 1 if len(bar) > 24 else 2
    assert sum(width for _, _, width in bar) + gap * (len(bar) - 1) == pytest.approx(WIDTH - 2 * 14)
    assert bar[0][1] == 0 and bar[-1][1] + bar[-1][2] == pytest.approx(WIDTH - 2 * 14)  # the last cell ends at the edge
    for (_, x, width), (_, next_x, _) in zip(bar, bar[1:]):
        assert next_x - (x + width) == pytest.approx(gap)
    image = root.grabWindow()
    for state, x, width in bar:  # each lit cell shows in the colour of its state
        if state:
            assert image.pixelColor(int(14 + x + width / 2), 11 + 22 + 9).name() == STATE_COLORS[state]
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def empty_tracks(root):
    return [i for i in walk(root.contentItem()) if i.property("isEmptyTrack") and i.isVisible()]


@pytest.mark.parametrize("agents", [[], None])  # no agents, and offline
def test_with_no_agents_the_bar_is_one_empty_track(app, window, agents):
    root, backend, messages = window
    backend.apply(many(working=3))
    settle(app)
    backend.apply(agents)
    settle(app)
    assert cells(root) == []
    (track,) = empty_tracks(root)
    assert (track.x(), track.width(), track.height()) == (0, WIDTH - 2 * 14, 8)
    image = root.grabWindow()
    y = 11 + 22 + 5
    assert [image.pixelColor(x, y).name() for x in (14, 100, 160, WIDTH - 15)] == [FRAME] * 4  # the outline
    inside = {image.pixelColor(x, y + 4).name() for x in range(15, WIDTH - 15)}
    assert len(inside) == 1 and FRAME not in inside  # one bar: no lines between cells, nothing lit
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_a_drag_from_a_row_moves_the_widget_and_does_not_click(app, window):
    root, backend, messages = window
    backend.apply(AGENTS)
    settle(app)
    click(app, root, rows(root, "status")[2])
    left, none = Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    for item in (rows(root, "status")[0], rows(root, "status")[2], rows(root, "agent")[0]):
        before = (root.property("posX"), root.property("posY"))
        backend.saves.clear()
        start = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
        QTest.mousePress(root, left, none, start)
        settle(app)
        for step in (QPoint(-10, 5), QPoint(-20, 12)):  # each move is from the start: the window stays off screen
            QTest.mouseMove(root, start + step)
            settle(app)
        QTest.mouseRelease(root, left, none, start + QPoint(-20, 12))
        settle(app)
        after = (root.property("posX"), root.property("posY"))
        assert after == (before[0] - 30, before[1] + 17)
        assert backend.saves == [after]  # saved one time, at the release
        assert root.property("openState") == "working" and backend._client.focused == []
    assert root.property("atDefault") is False
    start = rows(root, "status")[2].mapToScene(QPointF(40, 16)).toPoint()  # less than 6 px is a click
    backend.saves.clear()
    QTest.mousePress(root, left, none, start)
    QTest.mouseMove(root, start + QPoint(3, 2))
    QTest.mouseRelease(root, left, none, start + QPoint(3, 2))
    settle(app)
    assert root.property("openState") == "" and backend.saves == []
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_clicks_are_ignored_while_a_jump_is_in_flight_and_the_row_shows_opening(app, window):
    root, backend, messages = window
    backend.apply(AGENTS)
    settle(app)
    click(app, root, rows(root, "status")[2])
    backend._client.focus_gate = threading.Event()
    try:
        first, second = rows(root, "agent")
        click(app, root, first)
        assert backend.opening == "t2" and "> opening…" in visible_texts(root)
        click(app, root, first)
        click(app, root, second)
        assert backend._client.focused == ["t2"]
    finally:
        backend._client.focus_gate.set()
    for _ in range(100):
        settle(app)
        if backend.opening == "":
            break
    assert "> opening…" not in visible_texts(root)
    click(app, root, second)
    for _ in range(100):
        settle(app)
        if backend.opening == "":
            break
    assert backend._client.focused == ["t2", "t3"]
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_a_long_group_shows_8_rows_with_a_scroll_hint_and_keeps_its_place_with_new_data(app, window):
    root, backend, messages = window
    backend.apply(many(idle=12))
    settle(app)
    click(app, root, rows(root, "status")[3])
    assert root.height() == CLOSED + 8 * AGENT_ROW + 20  # 8 rows and the line of the hint
    flick = next(i for i in walk(root.contentItem()) if i.property("hitRole") == "scroll" and i.isVisible())
    assert flick.height() == 8 * AGENT_ROW and flick.property("contentHeight") == 12 * AGENT_ROW
    hint = next(i for i in walk(root.contentItem()) if i.property("isScrollHint") and i.isVisible())
    assert hint.isVisible() and hint.property("text") == "ROWS 01–08 / 12  ▼ SCROLL"
    ticks = [i for i in walk(root.contentItem()) if i.property("isScrollTick")]
    assert [t.property("lit") for t in ticks] == [True] * 8 + [False] * 4  # one tick for each agent
    row = rows(root, "agent")[2]
    point = row.mapToScene(QPointF(row.width() / 2, row.height() / 2))
    for _ in range(3):  # 3 turns of 2 rows: the list stops at its end
        app.sendEvent(root, QWheelEvent(point, point, QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton,
                                        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False))
        settle(app)
    assert flick.property("contentY") == 4 * AGENT_ROW
    assert hint.property("text") == "ROWS 05–12 / 12  ▲ SCROLL"
    assert [t.property("lit") for t in ticks] == [False] * 4 + [True] * 8
    backend.apply(many(idle=12) + [Agent("t1", "working", "ana", "")])  # new data: the list keeps its place
    settle(app)
    assert flick.property("contentY") == 4 * AGENT_ROW and root.property("openState") == "idle"
    backend.apply(many(idle=10))  # a shorter list: the place is inside the new list
    settle(app)
    assert flick.property("contentY") == 2 * AGENT_ROW
    backend.apply(many(idle=8))  # 8 rows fit: no hint and no space for it
    settle(app)
    assert not hint.isVisible() and root.height() == CLOSED + 8 * AGENT_ROW + LIST_END
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_a_very_long_group_has_one_scroll_bar_and_not_a_tick_for_each_agent(app, window):
    root, backend, messages = window
    backend.apply(many(idle=90))
    settle(app)
    click(app, root, rows(root, "status")[3])
    assert [i for i in walk(root.contentItem()) if i.property("isScrollTick")] == []
    hint = next(i for i in walk(root.contentItem()) if i.property("isScrollHint") and i.isVisible())
    assert hint.property("text") == "ROWS 01–08 / 90  ▼ SCROLL"
    assert root.height() == CLOSED + 8 * AGENT_ROW + 20
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_the_rows_have_names_for_a_screen_reader(app, window):
    root, backend, messages = window
    backend.apply(AGENTS)
    settle(app)
    click(app, root, rows(root, "status")[2])
    names = []
    for item in rows(root, "status") + rows(root, "agent"):
        attached = next((c for c in item.children() if c.metaObject().className() == "QQuickAccessibleAttached"), None)
        assert attached is not None
        names.append(attached.property("name"))
    assert names == ["Blocked, 1 agent", "Done, 0 agents", "Working, 2 agents", "Idle, 0 agents",
                            "Go to ana in api / 1", "Go to bob"]


def test_the_step_of_a_drag_is_two_frames_of_the_screen(app, window):
    root, backend, messages = window
    assert root.property("refreshRate") == 0 and root.property("minMoveMs") == 16  # not known yet
    follow_refresh_rate(root)  # as the program does at start
    assert root.property("refreshRate") == root.screen().refreshRate() > 0
    assert root.property("minMoveMs") == pytest.approx(min(20, 2000 / root.screen().refreshRate()))
    for rate, step in ((240, 8.333), (144, 13.889), (120, 16.667), (60, 20), (0, 16), (-1, 16), (1000, 4), (30, 20)):
        root.setProperty("refreshRate", rate)
        assert root.property("minMoveMs") == pytest.approx(step, abs=0.001)
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


class FakeScreen(QObject):
    refreshRateChanged = Signal(float)

    def __init__(self, rate):
        super().__init__()
        self.rate = rate

    def refreshRate(self):
        return self.rate


class FakeWindow(QObject):
    screenChanged = Signal(QObject)

    def __init__(self, screen):
        super().__init__()
        self.now = screen
        self.sets = 0

    def setProperty(self, name, value):
        self.sets += 1  # one for each time the program gives the rate to the window
        return super().setProperty(name, value)

    def screen(self):
        return self.now

    def move_to(self, screen):
        self.now = screen
        self.screenChanged.emit(screen)


def test_the_refresh_rate_follows_the_screen_of_the_window_and_a_change_of_that_screen(app):
    slow, fast = FakeScreen(144.0), FakeScreen(240.0)
    panel = FakeWindow(slow)
    follow_refresh_rate(panel)
    assert panel.property("refreshRate") == 144.0
    slow.rate = 60.0
    slow.refreshRateChanged.emit(60.0)  # the same screen changes its mode
    assert panel.property("refreshRate") == 60.0
    panel.move_to(fast)
    assert panel.property("refreshRate") == 240.0
    slow.rate = 75.0
    sets = panel.sets
    slow.refreshRateChanged.emit(75.0)  # the old screen is not followed any more
    assert panel.property("refreshRate") == 240.0 and panel.sets == sets
    fast.rate = 120.0
    fast.refreshRateChanged.emit(120.0)
    assert panel.property("refreshRate") == 120.0
    panel.move_to(None)  # no screen: the rate is not known
    assert panel.property("refreshRate") == 0.0
    fast.rate = 165.0
    sets = panel.sets
    fast.refreshRateChanged.emit(165.0)  # not followed after the window left it
    assert panel.property("refreshRate") == 0.0 and panel.sets == sets
    panel.move_to(slow)
    assert panel.property("refreshRate") == 75.0


def test_a_screen_that_goes_away_leaves_no_reference_to_it(app):
    import gc
    import weakref

    gone, stays = FakeScreen(144.0), FakeScreen(60.0)
    panel = FakeWindow(gone)
    follow_refresh_rate(panel)
    watch = weakref.ref(gone)
    panel.now = stays
    del gone  # the monitor is unplugged: Qt deletes the screen and then tells the window
    gc.collect()
    assert watch() is None
    panel.screenChanged.emit(stays)
    assert panel.property("refreshRate") == 60.0


def pointer_area(root):
    return next(i for i in walk(root.contentItem()) if i.property("lastMoveMs") is not None)


def test_a_move_counts_only_when_one_step_passed_after_the_last_move(app, window):
    root, backend, messages = window
    backend.apply(AGENTS)
    settle(app)
    root.setProperty("refreshRate", 100)  # a step of 20 ms
    assert root.property("minMoveMs") == 20
    area = pointer_area(root)
    left, none = Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    start = QPoint(160, 100)
    before = (root.property("posX"), root.property("posY"))
    area.setProperty("lastMoveMs", time.time() * 1000 + 60_000)  # a clock that went back must not block the drag
    QTest.mousePress(root, left, none, start)
    assert area.property("lastMoveMs") == 0
    pressed_at = time.time() * 1000
    QTest.mouseMove(root, start + QPoint(-10, 0), 0)  # the first move after a press always counts
    assert root.property("posX") == before[0] - 10
    assert pressed_at - 1 <= area.property("lastMoveMs") <= time.time() * 1000 + 1  # the time of this move
    # The time of the last move is set here, so the test does not depend on the speed of the computer.
    area.setProperty("lastMoveMs", time.time() * 1000 + 60_000)  # the last move was less than one step ago
    QTest.mouseMove(root, start + QPoint(-12, 0), 0)  # the compositor did not move the window yet: no move
    assert root.property("posX") == before[0] - 10
    area.setProperty("lastMoveMs", time.time() * 1000 - 21)  # one step passed
    QTest.mouseMove(root, start + QPoint(-11, 0), 0)
    assert root.property("posX") == before[0] - 21
    QTest.mouseRelease(root, left, none, start + QPoint(-11, 0))
    settle(app)
    assert backend.saves == [(before[0] - 21, before[1])]
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


# ----- more than one screen -----

PANEL = (WIDTH, CLOSED)
# Two screens of different sizes, as {name, virtualX, virtualY, width, height}. OFFSET: the small one is at the
# right of the big one and starts 360 px lower.
OFFSET = [("A", 0, 0, 2560, 1440), ("B", 2560, 360, 1920, 1080)]
SIDE = [("L", 0, 0, 1920, 1080), ("R", 1920, 0, 1920, 1080)]
STACKED = [("T", 0, 0, 1920, 1080), ("U", 0, 1080, 1920, 1080)]


def js(root, text):
    """The value of a JavaScript expression in the panel."""
    expression = QQmlExpression(qmlContext(root), root, text)
    value = expression.evaluate()
    assert not expression.hasError(), expression.error().toString()
    return value[0] if isinstance(value, tuple) else value


def screen_list(screens):
    return json.dumps([dict(zip(("name", "virtualX", "virtualY", "width", "height"), s)) for s in screens])


def use_screens(root, screens, name, x, y):
    """Give the panel made-up screens and put it on one of them. The real window stays where it is."""
    js(root, f"root.screenSource = {screen_list(screens)}")
    root.setProperty("screenName", name)
    root.setProperty("atDefault", False)
    root.setProperty("posX", x)
    root.setProperty("posY", y)


def place(root):
    return root.property("screenName"), root.property("posX"), root.property("posY")


@pytest.mark.parametrize(
    "screens, wanted, result",
    [
        # Two screens side by side: across the edge that they share, and a stop at each outer edge.
        (SIDE, (1800, 100), (1800, 100)),
        (SIDE, (3700, 100), (3520, 100)),
        (SIDE, (-50, 100), (0, 100)),
        (SIDE, (1800, -30), (1800, 0)),
        (SIDE, (1800, 1000), (1800, 888)),
        (SIDE, (4000, 2000), (3520, 888)),
        # One screen above the other.
        (STACKED, (100, 1000), (100, 1000)),
        (STACKED, (1700, 1000), (1600, 1000)),
        (STACKED, (100, 2100), (100, 1968)),
        (STACKED, (-5, -5), (0, 0)),
        # The offset pair. Across where the two screens touch.
        (OFFSET, (2400, 560), (2400, 560)),
        (OFFSET, (2660, 560), (2660, 560)),
        # Above the small screen is no screen: the panel stops at the edge of the big one.
        (OFFSET, (2400, 100), (2240, 100)),
        (OFFSET, (2300, 100), (2240, 100)),
        # Near the corner the panel goes down a little and then across.
        (OFFSET, (2400, 300), (2400, 360)),
        (OFFSET, (2400, 1300), (2400, 1248)),
        (OFFSET, (3000, 300), (3000, 360)),
        (OFFSET, (4300, 700), (4160, 700)),
        (OFFSET, (-10, 700), (0, 700)),
        # One screen: the same as a clamp to that screen.
        (SIDE[:1], (1800, -30), (1600, 0)),
        (SIDE[:1], (500, 500), (500, 500)),
    ],
)
def test_a_drag_goes_across_an_edge_that_two_screens_share_and_stops_at_an_outer_edge(app, window, screens, wanted, result):
    root, backend, messages = window
    listed = screen_list(screens).replace("virtualX", "x").replace("virtualY", "y")
    found = json.loads(js(root, f"JSON.stringify(root.dragPlace({listed}, {wanted[0]}, {wanted[1]}, {PANEL[0]}, {PANEL[1]}))"))
    assert (found["x"], found["y"]) == result


def test_the_panel_is_kept_on_the_screen_that_holds_it(app, window):
    root, backend, messages = window
    assert root.property("screenName") == root.screen().name()  # at start: the screen of the window
    backend.apply([])
    settle(app)
    use_screens(root, OFFSET, "B", 5000, 5000)
    js(root, "root.clampPosition()")
    assert place(root) == ("B", 1920 - WIDTH, 1080 - CLOSED)  # the size of B, not of A and not of the real screen
    root.setProperty("screenName", "A")
    root.setProperty("posX", 5000)
    root.setProperty("posY", 5000)
    js(root, "root.clampPosition()")
    assert place(root) == ("A", 2560 - WIDTH, 1440 - CLOSED)
    root.setProperty("atDefault", True)
    js(root, "root.clampPosition()")
    assert place(root) == ("A", 2560 - WIDTH - 16, 16)  # the default corner, 16 px from the edges
    root.setProperty("screenName", "B")
    settle(app)
    assert place(root) == ("B", 1920 - WIDTH - 16, 16)  # a new screen moves the default corner by itself
    # A group that opens at the bottom edge of B pushes the panel up.
    backend.apply(AGENTS)
    root.setProperty("atDefault", False)
    root.setProperty("posY", 1080 - CLOSED)
    click(app, root, rows(root, "status")[2])
    assert root.height() == CLOSED + 2 * AGENT_ROW + LIST_END
    assert place(root) == ("B", 1920 - WIDTH - 16, 1080 - root.height())
    assert backend.saves == []
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_move_to_next_screen_keeps_the_distance_to_the_nearer_edges(app, window):
    root, backend, messages = window
    use_screens(root, OFFSET, "A", 2200, 40)  # 40 px from the right edge of A and 40 px from its top
    js(root, "root.moveToNextScreen()")
    assert place(root) == ("B", 1920 - WIDTH - 40, 40)
    assert (backend.saves, backend.screens) == ([(1560, 40)], ["B"])
    js(root, "root.moveToNextScreen()")  # the last screen: the next one is the first
    assert place(root) == ("A", 2200, 40)
    root.setProperty("posX", 30)
    root.setProperty("posY", 1440 - CLOSED - 20)  # at the left, 20 px above the bottom edge
    js(root, "root.moveToNextScreen()")
    assert place(root) == ("B", 30, 1080 - CLOSED - 20)
    # A place that does not exist on the smaller screen: the middle of the big one stays at the left and top
    # distance, and the clamp keeps the panel on the screen.
    root.setProperty("screenName", "A")
    root.setProperty("posX", 1100)
    root.setProperty("posY", 600)
    js(root, "root.moveToNextScreen()")
    assert place(root) == ("B", 1100, 600)
    assert backend.screens == ["B", "A", "B", "B"]
    # With one screen there is nothing to do.
    saves = len(backend.saves)
    use_screens(root, OFFSET[:1], "A", 100, 100)
    js(root, "root.moveToNextScreen()")
    assert place(root) == ("A", 100, 100) and len(backend.saves) == saves
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_move_to_next_screen_keeps_the_default_corner_and_saves_only_the_screen(app, window, tmp_path):
    root, backend, messages = window
    (tmp_path / "state.json").write_text('{"x": 9, "y": 9, "screen": "A", "layout": "C"}')
    use_screens(root, OFFSET, "A", 0, 0)
    root.setProperty("atDefault", True)
    js(root, "root.clampPosition()")
    js(root, "root.moveToNextScreen()")
    assert place(root) == ("B", 1920 - WIDTH - 16, 16) and root.property("atDefault") is True
    # No place in the file: at the next start the panel is at the default corner again, and it follows the
    # width of the screen and of the layout.
    assert (backend.saves, backend.screens) == ([], ["B"])
    assert json.loads((tmp_path / "state.json").read_text()) == {"screen": "B", "layout": "C"}
    root.setProperty("atDefault", False)  # a panel that the person moved saves its place
    js(root, "root.moveToNextScreen()")
    assert backend.screens == ["B", "A"] and len(backend.saves) == 1
    assert json.loads((tmp_path / "state.json").read_text())["x"] == backend.saves[0][0]
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def drag_by(app, root, steps):
    """Press in the middle of the header and move to each step from there. The window stays off screen, so the
    steps add up. Return the function that releases the button."""
    left, none = Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    start = QPoint(160, 20)
    QTest.mouseMove(root, start)  # the pointer is there before the press
    settle(app)
    QTest.mousePress(root, left, none, start)
    settle(app)
    for step in steps:
        QTest.mouseMove(root, start + step)
        settle(app)
    return lambda: (QTest.mouseRelease(root, left, none, start + steps[-1]), settle(app))


def test_a_drag_to_the_other_screen_leaves_the_panel_there(app, window):
    root, backend, messages = window
    use_screens(root, OFFSET, "A", 2100, 600)
    release = drag_by(app, root, [QPoint(90, 0), QPoint(110, 0)])
    assert place(root) == ("A", 2300, 600)  # on the two screens: past the edge of A (2240), still a panel of A
    release()
    assert place(root) == ("A", 2240, 600)  # its centre is on A: it stays on A, all of it
    assert (backend.saves, backend.screens) == ([(2240, 600)], ["A"])
    release = drag_by(app, root, [QPoint(90, 10), QPoint(100, 9), QPoint(110, 11)])
    assert place(root) == ("A", 2540, 630)
    release()
    assert place(root) == ("B", 0, 270)  # its centre is on B: the same place of the desktop, all of it on B
    assert (backend.saves[-1], backend.screens[-1]) == ((0, 270), "B")
    release = drag_by(app, root, [QPoint(-190, 0), QPoint(-210, 0)])  # and back, to the left
    assert place(root) == ("B", -400, 270)
    release()
    assert place(root) == ("A", 2160, 630)
    assert (backend.saves[-1], backend.screens[-1]) == ((2160, 630), "A")
    assert root.property("atDefault") is False and root.property("openState") == ""
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_a_drag_stops_at_an_edge_with_no_screen_behind_it(app, window):
    root, backend, messages = window
    use_screens(root, OFFSET, "A", 2100, 50)  # at this height nothing is at the right of A
    release = drag_by(app, root, [QPoint(90, 0), QPoint(100, 0), QPoint(110, 0)])
    assert place(root) == ("A", 2240, 50)
    release()
    assert place(root) == ("A", 2240, 50)
    assert (backend.saves, backend.screens) == ([(2240, 50)], ["A"])
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_a_group_that_changes_size_does_not_pull_a_drag_back_to_its_screen(app, window):
    root, backend, messages = window
    backend.apply(AGENTS)
    settle(app)
    use_screens(root, OFFSET, "A", 2150, 600)
    release = drag_by(app, root, [QPoint(100, 0), QPoint(150, 0)])
    assert place(root) == ("A", 2400, 600)
    root.setProperty("openState", "working")  # the panel changes its height during the drag
    settle(app)
    assert place(root) == ("A", 2400, 600)
    release()
    assert place(root)[0] == "B"
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def wait_until(app, condition, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end and not condition():
        app.processEvents()
        time.sleep(0.01)
    return condition()


def test_a_monitor_that_goes_away_leaves_the_panel_on_a_screen_that_stays(app, window):
    root, backend, messages = window
    backend.apply([])
    use_screens(root, OFFSET, "B", 1500, 800)
    settle(app)
    js(root, f"root.screenSource = {screen_list(OFFSET + [('C', 4480, 0, 1280, 720)])}")  # a monitor is added
    time.sleep(0.3)
    settle(app)
    assert place(root) == ("B", 1500, 800)  # nothing moves
    js(root, f"root.screenSource = {screen_list([OFFSET[0], ('C', 4480, 0, 1280, 720)])}")  # B goes away
    assert wait_until(app, lambda: root.property("screenName") != "B")
    assert place(root) == ("A", 1500, 800) and root.isVisible()
    js(root, f"root.screenSource = {screen_list([('C', 4480, 0, 1280, 720)])}")  # and A: only the small one stays
    assert wait_until(app, lambda: root.property("screenName") == "C")
    assert place(root) == ("C", 1280 - WIDTH, 720 - CLOSED)  # kept on the screen
    assert backend.saves == []  # the saved place stays: the panel is on its monitor again at a later start
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_a_panel_that_the_compositor_closes_shows_again_and_a_hidden_panel_stays_hidden(app, window):
    root, backend, messages = window
    settle(app)
    assert root.isVisible()
    root.close()  # what layer-shell-qt does when the compositor closes the surface (its monitor went away)
    assert not root.isVisible()
    assert wait_until(app, root.isVisible)
    assert root.property("closedByCompositor") is False
    root.setVisible(False)  # the tray entry "Hide widget"
    js(root, f"root.screenSource = {screen_list(OFFSET)}")  # the screens change while the panel is hidden
    time.sleep(0.4)
    settle(app)
    assert not root.isVisible()
    root.setVisible(True)
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


@pytest.mark.parametrize(
    "saved, at_default, x, y",
    [
        ('{"x": 120, "y": 48, "screen": "%s"}', False, 120, 48),  # the saved screen is there
        ('{"x": 120, "y": 48}', False, 120, 48),  # a file of an older version: the screen of the window
        ('{"x": 120, "y": 48, "screen": "NOT-THERE"}', True, None, 16),  # the monitor is not connected: the default corner
        ('{"x": 9000, "y": 48, "screen": "%s"}', True, None, 16),  # a place that is not on the screen
        ('{"screen": "%s", "layout": "C"}', True, None, 16),  # only the screen: the default corner of that screen
    ],
)
def test_the_start_uses_the_saved_screen_and_place(app, tmp_path, request, saved, at_default, x, y):
    name = app.primaryScreen().name()
    (tmp_path / "state.json").write_text(saved % name if "%s" in saved else saved)
    root, backend, messages = request.getfixturevalue("window")
    settle(app)
    default_x = root.screen().size().width() - WIDTH - 16
    assert root.property("atDefault") is at_default
    assert place(root) == (name, default_x if x is None else x, y)
    assert root.property("surfaceScreen") == name and root.isVisible()
    assert backend.saves == []
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


# ----- layouts: the skin changes, the window and its state stay -----

def test_a_different_layout_shows_in_the_same_window_and_keeps_the_place_the_screen_and_the_open_group(app, window, tmp_path):
    root, backend, messages = window
    backend.apply(many(blocked=1, working=2, idle=12))
    settle(app)
    use_screens(root, OFFSET, "B", 700, 300)
    click(app, root, rows(root, "status")[3])
    assert root.property("openState") == "idle" and root.height() == CLOSED + 8 * AGENT_ROW + 20
    sizes = []
    root.widthChanged.connect(lambda *_: sizes.append(("width", root.width())))
    root.heightChanged.connect(lambda *_: sizes.append(("height", root.height())))
    shown = []
    root.visibleChanged.connect(lambda *_: shown.append(root.isVisible()))

    backend.setLayout("T")
    settle(app)
    assert (root.width(), root.height()) == (T_WIDTH, 4 * T_ROW + 8 * T_ROW)  # the size of the new skin, 8 rows of 12
    assert sizes == [("width", T_WIDTH), ("height", 12 * T_ROW)]  # one change of each: never the size 0
    assert shown == [] and root.isVisible()  # the same window: it was not hidden
    assert place(root) == ("B", 700, 300) and root.property("openState") == "idle"
    assert [r.property("stateName") for r in rows(root, "status")] == ["blocked", "done", "working", "idle"]
    assert len(rows(root, "agent")) == 12
    assert json.loads((tmp_path / "state.json").read_text()) == {"layout": "T"}
    assert backend.saves == []  # the place did not change: it is not saved again

    backend.setLayout("C")
    settle(app)
    assert (root.width(), root.height()) == (WIDTH, CLOSED + 8 * AGENT_ROW + 20)
    assert place(root) == ("B", 700, 300) and root.property("openState") == "idle"
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_the_window_finds_the_rows_of_a_second_skin_by_their_role(app, window):
    """The test skin has no pointer code: the click, the jump, the wheel and the rules come from the shared parts."""
    root, backend, messages = window
    backend.setLayout("T")
    backend.apply(many(blocked=1, working=10, idle=12))
    settle(app)
    status = rows(root, "status")
    click(app, root, status[2])
    assert root.property("openState") == "working" and root.height() == 4 * T_ROW + 8 * T_ROW
    click(app, root, status[1])  # a group without agents does not open
    assert root.property("openState") == "working"
    click(app, root, status[3])  # one list for the open group: it shows the new group from its first row
    assert root.property("openState") == "idle"
    flick = next(i for i in walk(root.contentItem()) if i.property("hitRole") == "scroll" and i.isVisible())
    assert flick.height() == 8 * T_ROW and flick.property("contentHeight") == 12 * T_ROW
    row = rows(root, "agent")[2]
    point = row.mapToScene(QPointF(row.width() / 2, row.height() / 2))
    app.sendEvent(root, QWheelEvent(point, point, QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton,
                                    Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False))
    settle(app)
    assert flick.property("contentY") == 2 * T_ROW
    QTest.mouseClick(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point.toPoint())
    for _ in range(100):
        settle(app)
        if backend._client.focused and backend.opening == "":
            break
    assert backend._client.focused == ["i004"]  # the row at that place after the scroll of 2 rows
    click(app, root, status[2])  # a different long group in the same list starts at its first row
    assert flick.property("contentY") == 0 and flick.property("contentHeight") == 10 * T_ROW
    assert [r.property("key") for r in rows(root, "agent")][:2] == ["w000", "w001"]
    backend.focusFailed.emit("i003", "could not raise the window")  # the failure rule opens the group of the agent
    settle(app)
    assert root.property("openState") == "idle"
    backend.apply(None)  # the offline rule closes it
    settle(app)
    assert root.property("openState") == "" and root.height() == 4 * T_ROW
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_a_bigger_skin_is_kept_on_the_screen_and_the_default_corner_follows_the_width(app, window):
    root, backend, messages = window
    backend.setLayout("T")
    backend.apply(AGENTS)
    settle(app)
    use_screens(root, OFFSET, "B", 1920 - T_WIDTH, 1080 - 4 * T_ROW)  # in the bottom-right corner of B
    backend.setLayout("C")  # wider and higher
    settle(app)
    assert place(root) == ("B", 1920 - WIDTH, 1080 - CLOSED)
    root.setProperty("atDefault", True)
    js(root, "root.clampPosition()")
    assert place(root) == ("B", 1920 - WIDTH - 16, 16)
    backend.setLayout("T")
    settle(app)
    assert place(root) == ("B", 1920 - T_WIDTH - 16, 16) and root.property("atDefault") is True
    assert backend.saves == []
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_a_start_shows_the_saved_layout(app, tmp_path, request):
    (tmp_path / "state.json").write_text('{"x": 120, "y": 48, "layout": "T"}')
    root, backend, messages = request.getfixturevalue("window")
    backend.apply(AGENTS)
    settle(app)
    assert backend.layout == "T" and (root.width(), root.height()) == (T_WIDTH, 4 * T_ROW)
    assert place(root)[1:] == (120, 48) and root.isVisible()
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_a_skin_that_does_not_load_gives_the_default_layout(app, window, tmp_path):
    root, backend, messages = window
    backend.apply(AGENTS)
    settle(app)
    click(app, root, rows(root, "status")[2])
    backend.setLayout("X")
    settle(app)
    assert backend.layout == "C" and (root.width(), root.height()) == (WIDTH, CLOSED + 2 * AGENT_ROW + LIST_END)
    assert root.isVisible() and root.property("openState") == "working"
    assert json.loads((tmp_path / "state.json").read_text()) == {"layout": "X"}  # only in memory: the file stays
    assert any("Broken.qml" in m for m in messages)  # Qt says why the file did not load


def test_a_start_with_a_saved_skin_that_does_not_load_shows_the_default_layout(app, tmp_path, request):
    (tmp_path / "state.json").write_text('{"layout": "X"}')
    root, backend, messages = request.getfixturevalue("window")
    assert not root.isVisible()  # no window without a skin: a layer surface must have a size
    settle(app)
    assert backend.layout == "C" and (root.width(), root.height()) == (WIDTH, OFFLINE)
    assert root.isVisible() and root.property("started") is True
    assert json.loads((tmp_path / "state.json").read_text()) == {"layout": "X"}


def test_a_skin_that_reports_the_size_0_does_not_change_the_size_of_the_window(app, window):
    """A layer surface must never get the size 0."""
    root, backend, messages = window
    backend.setLayout("T")
    backend.apply(AGENTS)
    settle(app)
    assert (root.width(), root.height()) == (T_WIDTH, 4 * T_ROW)
    skin = root.property("skin")
    for name, value in (("implicitWidth", 0), ("implicitHeight", 0), ("implicitHeight", -5)):
        skin.setProperty(name, value)
        settle(app)
        assert (root.width(), root.height()) == (T_WIDTH, 4 * T_ROW), (name, value)
    skin.setProperty("implicitHeight", 4 * T_ROW)
    skin.setProperty("implicitWidth", 200)  # the two values are good again: the window takes them
    settle(app)
    assert (root.width(), root.height()) == (200, 4 * T_ROW)
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_a_status_without_agents_gets_no_pointer_look_and_the_controller_says_what_can_open(app, window):
    root, backend, messages = window
    backend.apply(AGENTS)
    settle(app)
    panel = root.property("panel")
    status = rows(root, "status")

    def hover(item):
        QTest.mouseMove(root, item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint())
        settle(app)
        return root.property("hoverRow")

    assert [js(root, f'root.panel.canOpen("{s}")') for s in ("blocked", "done", "working", "idle", "", "x")] == [
        True, False, True, False, False, False]
    assert hover(status[0]) == status[0]
    assert hover(status[1]) is None and hover(status[3]) is None  # no agents: not a target for the pointer
    assert hover(status[2]) == status[2]
    backend.apply(AGENTS[:1])  # the last working agent goes away under the pointer
    settle(app)
    assert root.property("hoverRow") is None
    backend.apply(AGENTS)
    settle(app)
    assert hover(status[0]) == status[0] and hover(status[2]) == status[2]  # at the next move of the pointer
    click(app, root, status[2])
    agent = rows(root, "agent")[0]
    assert hover(agent) == agent  # an agent row is always a target
    backend.apply(None)
    settle(app)
    assert js(root, 'root.panel.canOpen("blocked")') is False and panel.property("openState") == ""
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_each_group_has_its_share_and_the_sum_of_the_shares_before_it(app, window):
    root, backend, messages = window

    def shares():
        return json.loads(js(root, "JSON.stringify(root.panel.groups.map(g => [g.state, g.share, g.start]))"))

    backend.apply(many(blocked=1, done=2, working=3, idle=4))
    settle(app)
    assert shares() == [["blocked", 0.1, 0], ["done", 0.2, 0.1], ["working", 0.3, pytest.approx(0.3)],
                        ["idle", 0.4, pytest.approx(0.6)]]
    last = shares()[-1]
    assert last[1] + last[2] == pytest.approx(1)  # the shares fill the ring or the strip
    backend.apply(many(working=2))
    settle(app)
    assert [(share, start) for _, share, start in shares()] == [(0, 0), (0, 0), (1, 0), (0, 1)]
    for agents in ([], None):  # no agents, and offline
        backend.apply(agents)
        settle(app)
        assert [(share, start) for _, share, start in shares()] == [(0, 0)] * 4
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_the_cap_of_8_rows_has_one_source(app, window):
    root, backend, messages = window
    backend.apply(many(working=3, idle=12))
    settle(app)
    assert [js(root, f"root.panel.rowsFor({n})") for n in (0, 3, 8, 9, 90)] == [0, 3, 8, 8, 8]
    click(app, root, rows(root, "status")[3])
    lists = [i.parentItem() for i in walk(root.contentItem()) if i.property("hitRole") == "scroll"]
    open_list = next(l for l in lists if l.property("open"))
    assert (open_list.property("shown"), open_list.property("longer")) == (8, True)
    assert (root.property("panel").property("shown"), root.property("panel").property("scrolls")) == (8, True)
    panel = root.property("panel")
    assert panel.setProperty("maxAgentRows", 5) is False and panel.property("maxAgentRows") == 8  # a skin cannot
    # A second controller that a test makes with a different cap (an initial property): a list and the controller
    # both follow that one number.
    engine = qmlEngine(root)
    types = [QQmlComponent(engine, QUrl.fromLocalFile(str(UI_PATH / name))) 
             for name in ("PanelModel.qml", "AgentList.qml")]
    other = types[0].createWithInitialProperties({"maxAgentRows": 5, "openState": "idle"})
    agent_list = types[1].createWithInitialProperties({"panel": other})
    try:
        settle(app)
        assert (agent_list.property("shown"), agent_list.property("longer"), other.property("shown")) == (5, True, 5)
    finally:
        shiboken6.delete(agent_list)
        shiboken6.delete(other)
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_the_note_of_a_row_is_the_failure_then_opening_then_the_detail(app, window):
    root, backend, messages = window
    backend.apply(AGENTS)
    settle(app)
    click(app, root, rows(root, "status")[2])

    def notes():
        return {r.property("key"): (r.property("note"), r.property("noteText")) for r in rows(root, "agent")}

    assert notes() == {"t2": ("", "api / 1"), "t3": ("", "")}
    backend._set_opening("t2")
    settle(app)
    assert notes() == {"t2": ("opening", "opening…"), "t3": ("", "")}
    backend.focusFailed.emit("t2", "could not raise the window")  # a failure comes before "opening"
    settle(app)
    assert notes() == {"t2": ("failed", "could not raise the window"), "t3": ("", "")}
    panel = root.property("panel")
    assert (panel.property("failedColor").name(), panel.property("openingColor").name()) == ("#f28b82", "#8ab4f8")
    backend._set_opening("")
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_a_group_that_opens_again_starts_at_its_first_row(app, window):
    root, backend, messages = window
    backend.apply(many(working=10, idle=12))
    settle(app)
    for layout in ("C", "T"):  # one list in each group, and one list for the open group
        backend.setLayout(layout)
        settle(app)
        root.setProperty("openState", "")
        settle(app)
        click(app, root, rows(root, "status")[3])
        flick = next(i for i in walk(root.contentItem()) if i.property("hitRole") == "scroll" and i.isVisible())
        row = rows(root, "agent")[2]
        point = row.mapToScene(QPointF(row.width() / 2, row.height() / 2))
        app.sendEvent(root, QWheelEvent(point, point, QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton,
                                        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False))
        settle(app)
        assert flick.property("contentY") > 0
        click(app, root, rows(root, "status")[3])  # close
        click(app, root, rows(root, "status")[3])  # and open again
        flick = next(i for i in walk(root.contentItem()) if i.property("hitRole") == "scroll" and i.isVisible())
        assert flick.property("contentY") == 0, layout
        assert [r.property("key") for r in rows(root, "agent")][:1] == ["i000"]
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


# ----- the plain shell: a frameless window above the others, for the systems with no layer shell -----

plain_only = pytest.mark.parametrize("shell", ["plain"], indirect=True)
TYPE_MASK = Qt.WindowType.WindowType_Mask


@plain_only
def test_the_plain_shell_is_a_frameless_tool_window_above_the_others_with_a_clear_background(app, window):
    root, backend, messages = window
    settle(app)
    flags = root.flags()
    assert flags & TYPE_MASK == Qt.WindowType.Tool  # no entry in a taskbar
    for flag in (Qt.WindowType.FramelessWindowHint, Qt.WindowType.WindowStaysOnTopHint,
                 Qt.WindowType.WindowDoesNotAcceptFocus, Qt.WindowType.NoDropShadowWindowHint):
        assert flags & flag == flag, flag
    assert root.color().alpha() == 0 and root.isVisible()
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


@pytest.mark.parametrize("name", ["Layer.qml", "Plain.qml", "../PanelShell.qml"])
def test_no_shell_asks_for_the_focus(name):
    """The panel never takes the keyboard: no QML of the panel window asks for the focus or for the front. (The
    off-screen platform makes every window that shows the active one, so a test of the active window proves
    nothing here: the flag WindowDoesNotAcceptFocus and this rule are the test; the real runs show the rest.)"""
    text = (UI_PATH / "shells" / name).read_text()
    assert [word for word in ("requestActivate", "forceActiveFocus", "raise()", "focus: true") if word in text] == []


@plain_only
def test_the_plain_window_is_at_the_place_of_the_panel_and_a_new_size_keeps_its_top_left_corner(app, window):
    root, backend, messages = window
    settle(app)
    real = root.screen().geometry()
    assert root.property("atDefault") is True
    assert (root.x(), root.y()) == (real.x() + real.width() - WIDTH - 16, real.y() + 16)  # the default corner
    use_screens(root, OFFSET, "B", 100, 200)
    assert (root.x(), root.y()) == (2560 + 100, 360 + 200)  # the screen of the panel and the place on it
    backend.apply(AGENTS)
    settle(app)
    size = (root.width(), root.height())
    click(app, root, rows(root, "status")[2])  # a group opens: the window is taller
    assert root.height() > size[1] and root.width() == size[0]
    assert (root.x(), root.y()) == (2660, 560) and place(root) == ("B", 100, 200)
    click(app, root, rows(root, "status")[2])  # and closes
    assert (root.width(), root.height()) == size and (root.x(), root.y()) == (2660, 560)
    js(root, "root.moveToNextScreen()")  # from B, the last screen, to A
    assert place(root) == ("A", 100, 200) and (root.x(), root.y()) == (100, 200)
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def test_the_plain_window_goes_to_the_screen_of_the_panel_and_qt_follows_it_during_a_drag(tmp_path):
    """Two real screens (off screen, in a process of their own): the window is on the screen of the panel; during a
    drag Qt gives it the screen that holds its centre; at the release the panel belongs to that screen."""
    config = tmp_path / "screens.json"
    config.write_text(json.dumps({"screens": [
        {"name": "LEFT", "x": 0, "y": 0, "width": 1920, "height": 1080, "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1},
        {"name": "RIGHT", "x": 1920, "y": 0, "width": 1280, "height": 720, "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1},
    ]}))
    done = subprocess.run(
        [sys.executable, "-m", "tests.plain_screens", str(tmp_path / "state.json")], capture_output=True, text=True,
        timeout=60, cwd=Path(__file__).parent.parent, env={**os.environ, "QT_QPA_PLATFORM": f"offscreen:configfile={config}"})
    assert done.returncode == 0, done.stderr[-2000:]
    steps = {s.pop("step"): s for s in map(json.loads, done.stdout.splitlines())}
    assert steps["start"]["screens"] == ["LEFT", "RIGHT"]
    view = {name: (s["place"], s["window"][:2], s["qtScreen"], s["surfaceScreen"]) for name, s in steps.items()}
    assert view == {
        "start": (["LEFT", 1920 - WIDTH - 16, 16], [1920 - WIDTH - 16, 16], "LEFT", "LEFT"),
        "next screen": (["RIGHT", 1280 - WIDTH - 16, 16], [1920 + 1280 - WIDTH - 16, 16], "RIGHT", "RIGHT"),
        "next screen again": (["LEFT", 1920 - WIDTH - 16, 16], [1920 - WIDTH - 16, 16], "LEFT", "LEFT"),
        "placed": (["LEFT", 1500, 300], [1500, 300], "LEFT", "LEFT"),
        # The panel follows the pointer 1:1; it is a panel of LEFT until the release.
        "drag 100": (["LEFT", 1600, 300], [1600, 300], "LEFT", "LEFT"),
        "drag 250": (["LEFT", 1750, 300], [1750, 300], "LEFT", "LEFT"),
        "drag 300": (["LEFT", 1800, 300], [1800, 300], "RIGHT", "LEFT"),  # its centre is on RIGHT: Qt moves it
        # The centre is on RIGHT: the panel goes there, all of it.
        "released": (["RIGHT", 0, 300], [1920, 300], "RIGHT", "RIGHT"),
    }
    assert all(s["visible"] for s in steps.values())


@pytest.mark.parametrize("variable, chosen", [(None, "plain"), ("plain", "plain"), ("layer", "layer")])
def test_the_program_loads_the_panel_in_the_shell_of_the_rule_and_writes_the_shell_in_the_log(
        app, fake_client, tmp_path, caplog, monkeypatch, variable, chosen):
    """As bellwether/__main__.py does it. Off screen the platform is not Wayland: the rule gives the plain shell."""
    from bellwether.__main__ import load_panel
    if variable is None:
        monkeypatch.delenv("BELLWETHER_SHELL", raising=False)
    else:
        monkeypatch.setenv("BELLWETHER_SHELL", variable)
    caplog.set_level(logging.INFO, logger="bellwether")
    backend = Backend(fake_client, settings_path=tmp_path / "state.json", icons=Icons(tmp_path / "app", tmp_path / "cache"))
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    try:
        assert load_panel(engine) == chosen
        (root,) = engine.rootObjects()
        assert bool(root.flags() & Qt.WindowType.WindowStaysOnTopHint) is (chosen == "plain")
        assert root.property("posX") is not None and root.property("openState") == ""
        assert [r.getMessage() for r in caplog.records if r.getMessage().startswith("shell:")] == [f"shell: {chosen}"]
    finally:
        del engine
        app.processEvents()
