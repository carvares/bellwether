"""Every layout (skin) through the real Main.qml, the real controller and a fake client, with real pointer events:
the same information and the same behaviour in each of them. Then what is special in each skin."""
import json
import re
import shutil
import threading

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest

from bellwether import layouts
from bellwether.__main__ import IMPORT_PATH, UI_PATH
from bellwether.backend import Backend
from bellwether.state import Agent
from bellwether.tray import STATE_COLORS
from tests.test_qml import (  # noqa: F401  (window is a fixture)
    LAYERSHELL_QMLDIR, OFFSCREEN_NOTE, OFFSET, click, js, many, place, rows, settle, use_screens, visible_texts,
    walk, window)

pytestmark = pytest.mark.skipif(not LAYERSHELL_QMLDIR.is_file(), reason="org.kde.layershell is not installed")

LETTERS = [letter for letter, _, _ in layouts.LAYOUTS]
ORDER = ["blocked", "done", "working", "idle"]
MESSAGE = "could not raise the window"
MIXED = [
    Agent("t1", "blocked", "rev", "Main"),
    Agent("t2", "working", "ana", "api / 1"),
    Agent("t3", "working", "bob", ""),
    Agent("t4", "working", "", "docs"),
]


@pytest.fixture(params=LETTERS)
def shown(request, app, window):
    """Yield (letter, root window, backend, Qt messages) with the layout of the parameter. After the test: no
    QML warning in any step."""
    root, backend, messages = window
    if request.param not in layouts.built_skins():
        pytest.skip(f"layout {request.param} is not built")
    backend.setLayout(request.param)
    settle(app)
    assert backend.layout == request.param and root.isVisible()
    yield request.param, root, backend, messages
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def status_items(root):
    """The four status items by state name."""
    found = {i.property("stateName"): i for i in rows(root, "status")}
    return [found[state] for state in ORDER if state in found]


def flickable(root):
    return next(i for i in walk(root.contentItem()) if i.property("hitRole") == "scroll" and i.isVisible())


def hints(root):
    return [i for i in walk(root.contentItem()) if i.property("isScrollHint") and i.isVisible()]


def wheel(app, root, point, angle=-120):
    app.sendEvent(root, QWheelEvent(QPointF(point), QPointF(point), QPoint(0, 0), QPoint(0, angle), Qt.MouseButton.NoButton,
                                    Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False))
    settle(app)


def wait_jump(app, backend):
    for _ in range(100):
        settle(app)
        if backend.opening == "":
            break
    assert backend.opening == "", f"the jump to {backend.opening!r} did not end in 100 settles"


def count_text(root, text):
    return sum(text.lower() in t.lower() for t in visible_texts(root))


def spoken(item):
    attached = next((c for c in item.children() if c.metaObject().className() == "QQuickAccessibleAttached"), None)
    return attached.property("name") if attached else None


# ----- the shared behaviour, for each skin -----

def test_the_four_statuses_show_and_one_group_opens_at_a_time(app, shown):
    letter, root, backend, messages = shown
    backend.apply(MIXED)
    settle(app)
    blocked, done, working, idle = status_items(root)
    assert len(rows(root, "status")) == 4 and rows(root, "agent") == []
    closed = (root.width(), root.height())
    assert closed == (root.property("skin").property("implicitWidth"), root.property("skin").property("implicitHeight"))
    click(app, root, working)
    assert root.property("openState") == "working"
    assert [r.property("key") for r in rows(root, "agent")] == ["t2", "t3", "t4"]  # named agents first
    assert root.height() > closed[1] and root.width() == closed[0]
    texts = visible_texts(root)
    assert "ana" in texts and "bob" in texts and "api / 1" in texts and "docs" in texts
    click(app, root, status_items(root)[0])  # a second status closes the first
    assert root.property("openState") == "blocked"
    assert [r.property("key") for r in rows(root, "agent")] == ["t1"]
    click(app, root, status_items(root)[0])  # a second click closes the group
    assert root.property("openState") == "" and rows(root, "agent") == []
    assert (root.width(), root.height()) == closed


def test_a_status_with_no_agents_and_every_status_while_offline_is_inert(app, shown):
    letter, root, backend, messages = shown
    backend.apply(MIXED)
    settle(app)
    blocked, done, working, idle = status_items(root)
    click(app, root, working)
    for item in (done, idle):
        QTest.mouseMove(root, item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint())
        settle(app)
        assert root.property("hoverRow") is None  # no pointer look
        click(app, root, item)
        assert root.property("openState") == "working"  # and no change
    QTest.mouseMove(root, blocked.mapToScene(QPointF(blocked.width() / 2, blocked.height() / 2)).toPoint())
    settle(app)
    assert root.property("hoverRow") == blocked
    backend.apply(None)  # offline closes the group
    settle(app)
    assert root.property("openState") == "" and rows(root, "agent") == []
    assert count_text(root, "off") >= 1  # the skin says that Herdr is offline ("Offline", "off", "NO LINK")
    for item in rows(root, "status"):  # a skin can show its status items while offline: they do nothing
        click(app, root, item)
        assert root.property("openState") == "" and root.property("hoverRow") is None
    backend.apply(MIXED)  # online again: the group does not open by itself
    settle(app)
    assert root.property("openState") == "" and len(status_items(root)) == 4
    backend.apply([])  # no agents: the four statuses show, and none opens
    settle(app)
    assert len(status_items(root)) == 4
    for item in status_items(root):
        click(app, root, item)
        assert root.property("openState") == ""


def test_a_click_on_an_agent_jumps_one_time_and_clicks_wait_while_a_jump_runs(app, shown):
    letter, root, backend, messages = shown
    backend.apply(MIXED)
    settle(app)
    click(app, root, status_items(root)[2])
    backend._client.focus_gate = threading.Event()
    try:
        first, second, third = rows(root, "agent")
        click(app, root, first)
        assert backend.opening == "t2" and count_text(root, "opening…") == 1
        click(app, root, first)
        click(app, root, second)
        assert backend._client.focused == ["t2"]
    finally:
        backend._client.focus_gate.set()
    wait_jump(app, backend)
    assert count_text(root, "opening…") == 0
    click(app, root, rows(root, "agent")[1])
    wait_jump(app, backend)
    assert backend._client.focused == ["t2", "t3"] and root.property("openState") == "working"


def test_a_group_of_12_shows_8_rows_and_scrolls_and_the_hint_takes_no_click_and_no_wheel_turn(app, shown):
    letter, root, backend, messages = shown
    backend.apply(many(blocked=1, working=8, idle=12))
    settle(app)
    click(app, root, status_items(root)[2])  # 8 rows fit: no hint
    flick = flickable(root)
    row_height = rows(root, "agent")[0].height()
    assert flick.height() == flick.property("contentHeight") == 8 * row_height and hints(root) == []
    short = root.height()
    click(app, root, status_items(root)[3])
    flick = flickable(root)
    assert flick.height() == 8 * row_height and flick.property("contentHeight") == 12 * row_height
    assert len(hints(root)) >= 1
    assert short <= root.height() <= 1080 and root.height() - short <= 40  # only the space of the hint
    # Each scroll hint over the rows (a thumb, a track, a fade): a click on it goes to the row under it, and a wheel
    # turn on it scrolls the list. D has its hint as a footer under the rows, and C has a line of text there.
    view = flick.mapRectToScene(flick.boundingRect())
    over = [h for h in hints(root) + marked(root, "isScrollTick")
            if view.contains(h.mapToScene(QPointF(h.width() / 2, h.height() / 2)))]
    assert over or letter == "D", "no scroll hint over the rows"
    for hint in over:
        flick.setProperty("contentY", 0)
        settle(app)
        point = hint.mapToScene(QPointF(hint.width() / 2, hint.height() / 2)).toPoint()
        (under,) = [r for r in rows(root, "agent") if r.mapRectToScene(r.boundingRect()).contains(QPointF(point))]
        backend._client.focused.clear()
        QTest.mouseClick(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
        wait_jump(app, backend)
        assert backend._client.focused == [under.property("key")], hint
        wheel(app, root, point)
        assert flick.property("contentY") == 2 * row_height, hint
    row = rows(root, "agent")[1]
    for edge in (QPointF(row.width() - 1, row.height() / 2), QPointF(row.width() / 2, row.height() - 1),
                 QPointF(1, 1)):  # the edges of a row
        flick.setProperty("contentY", 0)
        point = row.mapToScene(edge).toPoint()
        wheel(app, root, point)
        assert flick.property("contentY") == 2 * row_height, edge
        backend._client.focused.clear()
        QTest.mouseClick(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
        wait_jump(app, backend)
        assert backend._client.focused == ["i003"], edge  # the row at that place after the scroll of 2 rows
    last = rows(root, "agent")[11]  # the last row on the screen at the end of the list: under a fade or a hint
    for _ in range(3):
        wheel(app, root, flick.mapToScene(QPointF(flick.width() / 2, flick.height() / 2)).toPoint())
    assert flick.property("contentY") == 4 * row_height
    backend._client.focused.clear()
    click(app, root, last)
    wait_jump(app, backend)
    assert backend._client.focused == ["i011"]
    backend.apply(many(blocked=1, working=8, idle=12) + [Agent("x1", "done", "new", "")])  # new data: the place stays
    settle(app)
    assert flick.property("contentY") == 4 * row_height and root.property("openState") == "idle"


def test_a_failed_jump_shows_its_message_in_the_row_or_in_a_line_and_it_ends_after_the_timer(app, shown):
    letter, root, backend, messages = shown
    backend.apply(MIXED)
    settle(app)
    timer = "root.panel.failTimer"
    backend.focusFailed.emit("t3", MESSAGE)
    settle(app)
    assert root.property("openState") == "working" and count_text(root, MESSAGE) == 1  # in the row of the agent
    failed = [r.property("key") for r in rows(root, "agent") if r.property("failed")]
    assert failed == ["t3"] and (js(root, f"{timer}.running"), js(root, f"{timer}.interval")) == (True, 3000)
    with_row = root.height()
    js(root, f"{timer}.triggered()")  # the 3 seconds are over
    settle(app)
    assert count_text(root, MESSAGE) == 0 and root.property("openState") == "working" and root.height() == with_row
    backend.focusFailed.emit("t3", MESSAGE)
    settle(app)
    backend.apply([a for a in MIXED if a.key != "t3"])  # the agent is gone: a line of its own
    settle(app)
    assert count_text(root, MESSAGE) == 1 and root.property("openState") == "working"
    assert root.height() > with_row - rows(root, "agent")[0].height()  # the line has its own space
    backend.apply(None)  # offline: the line stays
    settle(app)
    assert count_text(root, MESSAGE) == 1 and root.property("openState") == ""
    offline_with_line = root.height()
    js(root, f"{timer}.triggered()")
    settle(app)
    assert count_text(root, MESSAGE) == 0 and root.height() < offline_with_line


def test_a_drag_from_a_status_item_and_from_an_agent_row_moves_the_panel_and_does_not_click(app, shown):
    letter, root, backend, messages = shown
    backend.apply(MIXED)
    settle(app)
    click(app, root, status_items(root)[2])
    left, none = Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    for item in (status_items(root)[0], status_items(root)[2], rows(root, "agent")[0]):
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
        assert after == (before[0] - 30, before[1] + 17) and backend.saves == [after]
        assert root.property("openState") == "working" and backend._client.focused == []


def test_the_status_items_and_the_agent_rows_have_names_for_a_screen_reader(app, shown):
    letter, root, backend, messages = shown
    backend.apply(MIXED)
    settle(app)
    click(app, root, status_items(root)[2])
    assert [spoken(i) for i in status_items(root)] == [
        "Blocked, 1 agent", "Done, 0 agents", "Working, 3 agents", "Idle, 0 agents"]
    assert [spoken(i) for i in rows(root, "agent")] == ["Go to ana in api / 1", "Go to bob", "Go to t4 in docs"]


def test_each_count_shows_and_the_size_is_never_0(app, shown):
    letter, root, backend, messages = shown
    for agents in (many(blocked=11, done=22, working=33, idle=44), [], None, MIXED):
        backend.apply(agents)
        settle(app)
        assert root.width() >= 200 and 40 <= root.height() <= 1080
    backend.apply(many(blocked=11, done=22, working=33, idle=44))
    settle(app)
    numerals = {i.property("countFor"): i.property("text") for i in walk(root.contentItem())
                if i.property("countFor") and i.isVisible()}
    assert numerals == {"blocked": "11", "done": "22", "working": "33", "idle": "44"}


# ----- switching -----

def test_switching_between_every_pair_of_layouts_keeps_the_place_the_screen_and_the_open_group(app, window):
    root, backend, messages = window
    built = sorted(layouts.built_skins())
    backend.apply(many(blocked=1, working=3, idle=12))
    settle(app)
    use_screens(root, OFFSET, "B", 700, 200)
    root.setProperty("openState", "idle")
    settle(app)
    sizes = {}
    changes = []
    root.widthChanged.connect(lambda *_: changes.append("w"))
    root.heightChanged.connect(lambda *_: changes.append("h"))
    hidden = []
    root.visibleChanged.connect(lambda *_: hidden.append(root.isVisible()))
    for start in built:
        for to in built:
            if start == to:
                continue
            backend.setLayout(start)
            settle(app)
            changes.clear()
            backend.setLayout(to)
            settle(app)
            assert changes.count("w") <= 1 and changes.count("h") <= 1, (start, to, changes)  # one new size
            assert place(root) == ("B", 700, 200) and root.property("openState") == "idle", (start, to)
            assert len(rows(root, "agent")) == 12 and len(rows(root, "status")) == 4
            skin = root.property("skin")
            assert (root.width(), root.height()) == (skin.property("implicitWidth"), skin.property("implicitHeight"))
            assert sizes.setdefault(to, (root.width(), root.height())) == (root.width(), root.height())
    assert hidden == [] and backend.saves == []
    # At the bottom-right corner of the screen a bigger skin is kept on the screen.
    smallest = min(sizes, key=lambda letter: sizes[letter][1])
    backend.setLayout(smallest)
    settle(app)
    use_screens(root, OFFSET, "B", 1920 - root.width(), 1080 - root.height())
    for to in built:
        backend.setLayout(to)
        settle(app)
        name, x, y = place(root)
        assert name == "B" and 0 <= x <= 1920 - root.width() and 0 <= y <= 1080 - root.height(), to
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


# ----- Layout A: Refined list -----

def frame_colour(root, radius_gap=40):
    """The colour of the frame at the middle of its top edge."""
    return root.grabWindow().pixelColor(root.width() // 2, 0).name()


@pytest.fixture
def layout(request, app, window):
    """The window with the layout that the test names: @pytest.mark.parametrize("layout", ["A"], indirect=True)."""
    root, backend, messages = window
    if request.param not in layouts.built_skins():
        pytest.skip(f"layout {request.param} is not built")
    backend.setLayout(request.param)
    settle(app)
    yield root, backend, messages
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def only(letter):
    return pytest.mark.parametrize("layout", [letter], indirect=True)


@only("A")
def test_layout_a_has_a_filled_badge_for_blocked_and_done_with_agents_and_plain_numerals_for_the_rest(app, layout):
    root, backend, messages = layout
    backend.apply(many(blocked=1, done=0, working=3, idle=12))
    settle(app)
    badges = {i.property("badgeFor"): i for i in walk(root.contentItem()) if i.property("isBadge")}
    assert {state: b.property("filled") for state, b in badges.items()} == {
        "blocked": True, "done": False, "working": False, "idle": False}
    image = root.grabWindow()

    def corner(badge):  # inside the badge, away from its numeral
        return image.pixelColor(badge.mapToScene(QPointF(4, badge.height() / 2)).toPoint()).name()

    assert corner(badges["blocked"]) == STATE_COLORS["blocked"]
    assert corner(badges["done"]) != STATE_COLORS["done"] and corner(badges["working"]) != STATE_COLORS["working"]
    assert badges["idle"].width() > badges["working"].width() == 26  # two digits make the badge wider
    backend.apply(many(done=120))
    settle(app)
    assert badges["done"].property("filled") is True and badges["done"].width() < 60


@only("A")
def test_layout_a_sizes_and_the_frame_in_the_colour_of_the_top_status(app, layout):
    root, backend, messages = layout
    for agents, colour in ((many(blocked=1, done=2, working=3, idle=12), STATE_COLORS["blocked"]),
                           (many(done=1, idle=2), STATE_COLORS["done"]), (many(working=3, idle=1), STATE_COLORS["idle"]),
                           (many(working=2), STATE_COLORS["working"]), ([], "#3c4043")):
        backend.apply(agents)
        settle(app)
        assert (root.width(), root.height()) == (296, 168)
        assert frame_colour(root) == colour
    backend.apply(many(blocked=1, done=2, working=3, idle=12))
    settle(app)
    click(app, root, status_items(root)[2])
    assert root.height() == 168 + 3 * 30 + 6
    click(app, root, status_items(root)[3])
    assert root.height() == 168 + 8 * 30 + 6  # the hint is a thumb and a fade over the rows: no space of its own
    assert sorted(h.property("isScrollThumb") or False for h in hints(root)) == [False, True]  # a fade and a thumb
    wheel(app, root, QPoint(150, 300), -120 * 3)
    assert [bool(h.property("isScrollThumb")) for h in hints(root)] == [True]  # at the end: no fade over the last row
    backend.apply(None)
    settle(app)
    assert (root.width(), root.height()) == (296, 54) and frame_colour(root) == "#3c4043"
    assert visible_texts(root) == ["Herdr is offline"]


# ----- Layout B: Tiles -----

def marked(root, name):
    return [i for i in walk(root.contentItem()) if i.property(name) and i.isVisible()]


@only("B")
def test_layout_b_marks_the_open_tile_and_the_card_names_the_group_and_its_number_of_agents(app, layout):
    root, backend, messages = layout
    backend.apply(many(blocked=1, done=0, working=3, idle=12))
    settle(app)
    assert (root.width(), root.height()) == (304, 176)
    tiles = status_items(root)
    assert [(t.width(), t.height()) for t in tiles] == [(138, 74)] * 4
    assert [(t.x(), t.y()) for t in tiles] == [(0, 0), (146, 0), (0, 82), (146, 82)]  # a grid of 2 × 2
    assert [t.property("solid") for t in tiles] == [True, False, False, False]  # only an attention status with agents
    assert marked(root, "isOpenMark") == [] and marked(root, "isListTitle") == []
    click(app, root, tiles[2])
    assert [t.property("open") for t in tiles] == [False, False, True, False]
    image = root.grabWindow()
    edges = [image.pixelColor(t.mapToScene(QPointF(0, 37)).toPoint()).name() for t in tiles]
    assert edges[0] == STATE_COLORS["blocked"] and edges[1] == "#3c4043"  # a solid tile, and the line of an empty one
    assert edges[2] == STATE_COLORS["working"] and edges[3] not in ("#3c4043", STATE_COLORS["idle"])  # open, tinted
    assert [m.parentItem() for m in marked(root, "isOpenMark")] == [tiles[2]]
    assert [t.property("text") for t in marked(root, "isListTitle") + marked(root, "isListRange")] == ["Working", "3 agents"]
    assert root.height() == 176 + 8 + 30 + 3 * 30 + 6
    click(app, root, tiles[0])
    assert [t.property("text") for t in marked(root, "isListTitle") + marked(root, "isListRange")] == ["Blocked", "1 agent"]
    assert [m.parentItem() for m in marked(root, "isOpenMark")] == [tiles[0]]
    assert marked(root, "isOpenMark")[0].property("color").name() == "#202124"  # dark on the solid tile
    click(app, root, tiles[3])
    assert [t.property("text") for t in marked(root, "isListTitle") + marked(root, "isListRange")] == ["Idle", "1–8 of 12"]
    assert root.height() == 176 + 8 + 30 + 8 * 30 + 6 and len(hints(root)) == 1
    flick = flickable(root)
    wheel(app, root, flick.mapToScene(QPointF(100, 100)).toPoint())
    assert marked(root, "isListRange")[0].property("text") == "3–10 of 12"
    wheel(app, root, flick.mapToScene(QPointF(100, 100)).toPoint())
    assert marked(root, "isListRange")[0].property("text") == "5–12 of 12"


@only("B")
def test_layout_b_frame_colour_and_the_offline_tiles(app, layout):
    root, backend, messages = layout
    for agents, colour in ((many(blocked=1, working=3), STATE_COLORS["blocked"]), (many(done=1, idle=2), STATE_COLORS["done"]),
                           (many(working=3, idle=1), STATE_COLORS["idle"]), (many(working=2), STATE_COLORS["working"]),
                           ([], "#3c4043"), (None, "#3c4043")):
        backend.apply(agents)
        settle(app)
        assert frame_colour(root) == colour
    assert (root.width(), root.height()) == (304, 176 + 8 + 22)  # offline: the four tiles and one line
    numerals = [i.property("text") for i in walk(root.contentItem()) if i.property("countFor") and i.isVisible()]
    assert numerals == ["–"] * 4 and "Herdr is offline" in visible_texts(root)
    assert [t.property("solid") for t in status_items(root)] == [False] * 4


# ----- Layout D: Signal strip -----

def strip(root, width, gap, minimum):
    import json
    return [(round(p["x"], 3), round(p["width"], 3))
            for p in json.loads(js(root, f"JSON.stringify(root.panel.strip({width}, {gap}, {minimum}))"))]


def test_the_parts_of_a_share_strip_are_in_proportion_and_a_state_with_an_agent_has_a_minimum_width(app, window):
    root, backend, messages = window
    backend.apply(many(blocked=1, done=2, working=3, idle=4))
    settle(app)
    assert strip(root, 296, 3, 8) == [(0, 28.7), (31.7, 57.4), (92.1, 86.1), (181.2, 114.8)]  # 287 px for 10 agents
    backend.apply(many(done=1, working=2, idle=2))  # a state with no agents: no width and no gap
    settle(app)
    assert strip(root, 296, 3, 8) == [(0, 0), (0, 58), (61, 116), (180, 116)]
    backend.apply(many(blocked=1, done=1, working=120, idle=90))  # two shares are less than the minimum
    settle(app)
    parts = strip(root, 296, 3, 8)
    assert [w for _, w in parts][:2] == [8, 8]
    assert parts[2][1] / parts[3][1] == pytest.approx(120 / 90, abs=0.001)  # the rest stays in proportion
    assert parts[3][0] + parts[3][1] == pytest.approx(296)  # the strip is full
    assert [x for x, _ in parts] == pytest.approx([0, 11, 22, 22 + parts[2][1] + 3], abs=0.002)
    backend.apply(many(working=7))
    settle(app)
    assert strip(root, 296, 3, 8)[:3] == [(0, 0), (0, 0), (0, 296)] and strip(root, 296, 3, 8)[3][1] == 0
    for agents in ([], None):
        backend.apply(agents)
        settle(app)
        assert [w for _, w in strip(root, 296, 3, 8)] == [0, 0, 0, 0]
    assert js(root, 'root.panel.tint("#f28b82", 0.16)') == "#29f28b82" and js(root, 'root.panel.tint("#000000", 0)') == "#00000000"
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


@only("D")
def test_layout_d_shows_the_total_the_top_badge_the_strip_and_the_four_numerals(app, layout):
    root, backend, messages = layout
    backend.apply(many(blocked=1, done=2, working=3, idle=4))
    settle(app)
    assert (root.width(), root.height()) == (320, 122)
    texts = visible_texts(root)
    assert texts[:3] == ["10", "agents", "1 blocked"] and frame_colour(root) == STATE_COLORS["blocked"]
    numerals = {i.property("countFor"): i.property("text") for i in walk(root.contentItem()) if i.property("countFor")}
    assert numerals == {"blocked": "1", "done": "2", "working": "3", "idle": "4"}
    segments = sorted(marked(root, "isSegment"), key=lambda s: s.x())
    assert [s.property("segmentFor") for s in segments] == ORDER
    assert [s.width() for s in segments] == pytest.approx([28.7, 57.4, 86.1, 114.8])
    assert segments[-1].x() + segments[-1].width() == pytest.approx(296) and marked(root, "isEmptyTrack") == []
    assert len(marked(root, "isLamp")) == 2  # blocked and done have agents
    image = root.grabWindow()
    for s in segments:
        point = s.mapToScene(QPointF(s.width() / 2, 4)).toPoint()
        assert image.pixelColor(point).name() == STATE_COLORS[s.property("segmentFor")]
    click(app, root, status_items(root)[2])  # the other segments go dim
    assert [s.property("opacity") for s in segments] == [0.4, 0.4, 1, 0.4]
    assert root.height() == 122 + 1 + 3 * 30 + 12
    backend.apply(many(blocked=1, done=1, working=120, idle=90))
    settle(app)
    assert visible_texts(root)[:3] == ["212", "agents", "1 blocked"]
    assert [s.width() for s in segments][:2] == [8, 8]  # a share that is very small can still be seen
    backend.apply(many(working=1))
    settle(app)
    assert visible_texts(root)[:3] == ["1", "agent", "1 working"] and marked(root, "isLamp") == []
    assert [s.width() for s in marked(root, "isSegment")] == [296]


@only("D")
def test_layout_d_with_no_agents_and_offline_and_the_footer_of_a_long_list(app, layout):
    root, backend, messages = layout
    backend.apply([])
    settle(app)
    assert visible_texts(root)[:3] == ["0", "agents", "No agents"] and frame_colour(root) == "#3c4043"
    assert marked(root, "isSegment") == [] and len(marked(root, "isEmptyTrack")) == 1  # one neutral track
    backend.apply(None)
    settle(app)
    assert (root.width(), root.height()) == (320, 122)
    assert visible_texts(root) == ["Offline", "–", "Blocked", "–", "Done", "–", "Working", "–", "Idle"]
    assert len(marked(root, "isEmptyTrack")) == 1 and marked(root, "isTopBadge") == []
    backend.apply(many(blocked=1, idle=12))
    settle(app)
    click(app, root, status_items(root)[3])
    assert root.height() == 122 + 1 + 8 * 30 + 34
    (hint,) = hints(root)
    assert hint.property("text") == "4 more  ↓"
    flick = flickable(root)
    wheel(app, root, flick.mapToScene(QPointF(100, 100)).toPoint())
    assert hint.property("text") == "2 more  ↓"
    wheel(app, root, flick.mapToScene(QPointF(100, 100)).toPoint())
    assert hint.property("text") == "4 above  ↑"


# ----- Layout E: Ring -----

def ring(root, gap=0.07, minimum=0.10):
    import json
    return [(p["start"], p["sweep"]) for p in json.loads(js(root, f"JSON.stringify(root.panel.ring({gap}, {minimum}))"))]


def test_the_arcs_of_a_share_ring_fill_the_circle_and_a_state_with_an_agent_has_a_minimum_arc(app, window):
    import math
    root, backend, messages = window
    full = 2 * math.pi
    backend.apply(many(blocked=1, done=2, working=3, idle=4))
    settle(app)
    arcs = ring(root)
    assert [sweep for _, sweep in arcs] == pytest.approx([full * share - 0.07 for share in (0.1, 0.2, 0.3, 0.4)])
    assert [start for start, _ in arcs] == pytest.approx([0.035 + full * before for before in (0, 0.1, 0.3, 0.6)])
    assert sum(sweep for _, sweep in arcs) + 4 * 0.07 == pytest.approx(full)  # the arcs and the gaps: the full circle
    backend.apply(many(blocked=1, done=1, working=300, idle=200))  # two shares are less than the gap
    settle(app)
    arcs = ring(root)
    assert [sweep for _, sweep in arcs][:2] == pytest.approx([0.10, 0.10]) and all(sweep > 0 for _, sweep in arcs)
    assert sum(sweep for _, sweep in arcs) + 4 * 0.07 == pytest.approx(full)
    for (start, sweep), (next_start, _) in zip(arcs, arcs[1:]):
        assert next_start == pytest.approx(start + sweep + 0.07)  # no arc is over the next one
    backend.apply(many(done=1, idle=3))  # states with no agents have no arc and no gap
    settle(app)
    arcs = ring(root)
    assert [sweep for _, sweep in arcs] == pytest.approx([0, full / 4 - 0.07, 0, full * 3 / 4 - 0.07])
    backend.apply(many(working=5))  # one state: the full circle with no gap
    settle(app)
    assert ring(root)[2] == pytest.approx((0, full)) and sum(sweep for _, sweep in ring(root)) == pytest.approx(full)
    for agents in ([], None):
        backend.apply(agents)
        settle(app)
        assert [sweep for _, sweep in ring(root)] == [0, 0, 0, 0]
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


def ring_colours(root, angles):
    """The colour of the ring at each angle in degrees, clockwise from the top."""
    import math
    (canvas,) = marked(root, "isRing")
    image = root.grabWindow()
    out = []
    for angle in angles:
        a = math.radians(angle - 90)
        out.append(image.pixelColor(canvas.mapToScene(QPointF(50 + 40 * math.cos(a), 50 + 40 * math.sin(a))).toPoint()).name())
    return out


@only("E")
def test_layout_e_shows_the_shares_as_a_ring_with_the_total_in_its_centre_and_a_legend(app, layout):
    root, backend, messages = layout
    backend.apply(many(blocked=1, done=2, working=3, idle=4))
    settle(app)
    assert (root.width(), root.height()) == (312, 128) and frame_colour(root) == STATE_COLORS["blocked"]
    (total,) = marked(root, "isTotal")
    assert total.property("text") == "10" and "agents" in visible_texts(root)
    # The middle of each share: 10 %, 20 %, 30 % and 40 % of the circle, clockwise from the top.
    assert ring_colours(root, [18, 72, 162, 288]) == [STATE_COLORS[s] for s in ORDER]
    legend = status_items(root)
    assert [(i.x(), i.width(), i.height()) for i in legend] == [(0, 174, 25)] * 4
    assert [i.y() for i in legend] == [0, 25, 50, 75]
    assert visible_texts(root)[2:] == ["Blocked", "1", "Done", "2", "Working", "3", "Idle", "4"]
    click(app, root, legend[2])
    assert root.height() == 128 + 1 + 3 * 30 + 14
    colours = ring_colours(root, [18, 72, 162, 288])
    assert colours[2] == STATE_COLORS["working"] and STATE_COLORS["blocked"] not in colours  # the others go dim
    click(app, root, legend[2])
    backend.apply(many(working=1))
    settle(app)
    assert total.property("text") == "1" and "agent" in visible_texts(root)
    assert set(ring_colours(root, [0, 90, 180, 270])) == {STATE_COLORS["working"]}  # one state: the full circle
    backend.apply(many(blocked=1, working=3000))
    settle(app)
    assert total.property("text") == "3001" and total.width() < 62  # the numeral stays inside the ring
    assert ring_colours(root, [5])[0] == STATE_COLORS["blocked"]  # 1 of 3001 can still be seen


@only("E")
def test_layout_e_with_no_agents_and_offline(app, layout):
    root, backend, messages = layout
    backend.apply([])
    settle(app)
    assert set(ring_colours(root, [0, 45, 90, 180, 270])) == {"#3c4043"} and frame_colour(root) == "#3c4043"  # one neutral track
    assert marked(root, "isTotal")[0].property("text") == "0"
    backend.apply(None)
    settle(app)
    assert (root.width(), root.height()) == (312, 128)
    assert visible_texts(root) == ["off", "Blocked", "–", "Done", "–", "Working", "–", "Idle", "–"]
    dashes = ring_colours(root, [x * 3.75 for x in range(96)])  # a ring of 24 dashes
    assert 30 <= dashes.count("#3c4043") <= 60 and dashes[1] == "#3c4043" and dashes[3] != "#3c4043"
    backend.apply(many(blocked=1, idle=12))
    settle(app)
    click(app, root, status_items(root)[3])
    assert root.height() == 128 + 1 + 8 * 30 + 14 and len(hints(root)) == 2  # a fade and a thumb, over the rows


def test_the_five_designs_are_built():
    assert sorted(layouts.built_skins()) == LETTERS


# ----- the theme tokens and the skins do not drift apart -----

# Test values for the tokens, each different from every real value, so that a text that has a literal in the place of
# its token keeps the old value and is found.
DRIFT = {"titleSize": 31, "bodySize": 27, "smallSize": 23, "textColor": "#123456", "dimColor": "#654321"}


def font_of(item):
    return item.property("font").pixelSize(), item.property("color").name()


@pytest.mark.parametrize("letter", LETTERS)
def test_the_texts_of_each_layout_take_their_size_and_colour_from_its_theme_tokens(app, fake_client, tmp_path, letter):
    """A copy of the interface with other token values in the theme of the layout: the status title, the agent label
    and the small text follow them. Not by a static search for literals: a text can read the wrong token, and a value
    can be equal to a token by chance (a numeral of 13 px with a body size of 13 px)."""
    ui = tmp_path / "ui"
    shutil.copytree(UI_PATH, ui)
    theme = ui / "skins" / f"{letter}Theme.qml"
    text = theme.read_text()
    for token, value in DRIFT.items():
        text, n = re.subn(rf"(property \w+ {token}: )[^\n]+", lambda m: m.group(1) + json.dumps(value), text)
        assert n == 1, token
    theme.write_text(text)
    backend = Backend(fake_client, settings_path=tmp_path / "state.json",
                      skins={l: ui / "skins" / f"{l}.qml" for l in layouts.built_skins()})
    backend.setLayout(letter)
    messages = []
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda errors: messages.extend(e.toString() for e in errors))
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("stateColors_", STATE_COLORS)
    engine.addImportPath(str(IMPORT_PATH))
    engine.load(ui / "Main.qml")
    try:
        root = engine.rootObjects()[0]
        backend.apply(MIXED)
        settle(app)
        working = status_items(root)[2]
        click(app, root, working)
        texts = [i for i in walk(root.contentItem()) if i.isVisible() and i.property("text")]
        title = next(i for i in walk(working) if (i.property("text") or "").lower() == "working")
        (row,) = [r for r in rows(root, "agent") if r.property("key") == "t2"]
        label = next(i for i in walk(row) if i.property("text") == "ana")
        detail = next(i for i in walk(row) if i.property("text") == "api / 1")
        small = next(i for i in texts if i.property("isTotal")) if letter == "C" else detail
        if letter != "D":  # D's tabs have 11 px labels, a size of that design; its titleSize is for the options window
            assert font_of(title)[0] == DRIFT["titleSize"]
        assert font_of(label) == (DRIFT["bodySize"], DRIFT["textColor"])
        assert font_of(small)[0] == DRIFT["smallSize"]  # C: the header (its detail has 11 px, a size of that design)
        assert font_of(detail)[1] == DRIFT["dimColor"]
    finally:
        del engine
        app.processEvents()
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []
