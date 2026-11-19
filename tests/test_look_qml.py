"""The custom look on the screen: the real Main.qml and the real Options.qml with the five real skins, a fake client,
and a font scale, a font family and colours of the user."""
import math
import re

import pytest
from PySide6.QtCore import QPointF

from bellwether import layouts
from bellwether.state import Agent
from tests.audit import text_findings, walk
from tests.test_qml import (  # noqa: F401  (window is a fixture)
    LAYERSHELL_QMLDIR, OFFSCREEN_NOTE, OFFSET, js, many, rows, settle, use_screens, window)
from tests.test_options import real_options  # noqa: F401  (a fixture)
from tests.test_skins import LETTERS, MESSAGE, status_items

pytestmark = pytest.mark.skipif(not LAYERSHELL_QMLDIR.is_file(), reason="org.kde.layershell is not installed")

SKIN_FILES = sorted(layouts.SKINS_PATH.glob("[A-Z].qml"))
# Two rows that look the same get their address; a long name must give its room to the detail.
TEAM = [
    Agent("t1", "blocked", "rev", "Main"),
    Agent("t2", "working", "ana", "api / 1"),
    Agent("t3", "working", "a name that is much too long for one row of a panel", "a long workspace name / a branch"),
    Agent("t4", "working", "", "docs"),
    Agent("t5", "working", "", "docs"),
]


def js_round(value):
    """Math.round of JavaScript: a half goes up."""
    return math.floor(value + 0.5)


def texts(root):
    return [i for i in walk(root.contentItem()) if i.isVisible() and i.metaObject().className().startswith("QQuickText")
            and i.property("text")]


def pixel_sizes(root):
    return [(i.property("text"), i.property("font").pixelSize()) for i in texts(root)]


def scenes(app, root, backend):
    """Show the states of a panel one after the other. Yields the name of each when it is on the screen."""
    def show(agents, open_state=""):
        backend.apply(agents)
        settle(app)
        root.setProperty("openState", open_state)
        settle(app)

    show(TEAM)
    yield "closed"
    show(TEAM, "working")
    yield "a group of 4"
    backend._set_opening("t2")
    settle(app)
    yield "a jump runs"
    backend._set_opening("")
    backend.focusFailed.emit("t4", MESSAGE)
    settle(app)
    yield "a jump failed"
    backend.focusFailed.emit("gone", MESSAGE)
    root.setProperty("openState", "")
    settle(app)
    yield "a jump failed and its agent has no row"
    js(root, "root.panel.failTimer.triggered()")  # the 3 seconds of the message are over
    show(many(blocked=1, working=3, idle=12), "idle")
    yield "a group of 12"
    show(many(blocked=11, done=22, working=1333, idle=444), "done")
    yield "large counts"
    show(many(working=2))
    yield "one status"
    show([])
    yield "no agents"
    show(None)
    yield "offline"


# ----- the font scale -----

@pytest.mark.parametrize("skin", SKIN_FILES, ids=lambda path: path.stem)
def test_no_skin_has_a_text_size_of_its_own(skin):
    """Every text size of a skin is a theme token (or a value of the skin that picks one of several tokens), so the
    font scale of the custom look reaches every text. A number after `pixelSize:` fails here."""
    text = skin.read_text()
    uses = re.findall(r"\bpixelSize\b\s*(:?)\s*([^\n;}]*)", text)
    assert uses, "the skin has no text?"
    names = set()
    for colon, value in uses:
        value = value.strip()
        assert colon == ":", f"pixelSize is set in a different way: {value!r}"
        assert not re.search(r"\d", value), f"a text size that is not a theme token: pixelSize: {value}"
        found = re.findall(r"\b(theme|skin)\.(\w+)", value)
        assert found and all(name.endswith("Size") for _, name in found if name != "panel"), f"pixelSize: {value}"
        names |= {name for owner, name in found if owner == "skin" and name != "panel"}
    for name in names:  # a value of the skin that picks a token: it has only tokens too
        (definition,) = re.findall(rf"readonly property int {name}: ((?:[^\n]*\n\s+[:?])*[^\n]*)", text)
        sizes = re.findall(r"[?:]\s*([\w.]+)\s*(?=$|\n|:|\?)", definition)
        assert sizes and all(size.startswith("theme.") and size.endswith("Size") for size in sizes), definition
    assert "pointSize" not in text


@pytest.mark.parametrize("letter", LETTERS)
def test_every_text_of_a_skin_has_the_size_of_its_design_times_the_font_scale(app, window, letter):
    root, backend, messages = window
    backend.setLayout(letter)
    use_screens(root, OFFSET, "B", 0, 0)
    backend.apply(TEAM)
    root.setProperty("openState", "working")
    backend.focusFailed.emit("gone", MESSAGE)
    settle(app)
    design = pixel_sizes(root)
    assert len(design) >= 12 and all(size >= 9 for _, size in design)
    by_text = dict(design)
    title = next(size for text, size in design if text.lower() == "working")
    assert (by_text["ana"], by_text["api / 1"]) != (title, title) or letter in "BD"  # there are several sizes to scale
    for scale in (0.8, 1.25, 1.4, 1.0):
        assert backend.setFontScale(scale) is True
        settle(app)
        assert pixel_sizes(root) == [(text, js_round(size * scale)) for text, size in design], scale
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


@pytest.mark.parametrize("scale", [0.8, 1.0, 1.4])
@pytest.mark.parametrize("letter", LETTERS)
def test_every_text_has_its_room_at_each_font_scale(app, window, letter, scale):
    """No text is outside the panel, cut, or over a different text, in every state of the panel."""
    root, backend, messages = window
    backend.setLayout(letter)
    backend.setFontScale(scale)
    use_screens(root, OFFSET, "B", 0, 0)
    seen = []
    for scene in scenes(app, root, backend):
        assert text_findings(root) == [], (letter, scale, scene)
        skin = root.property("skin")
        assert (root.width(), root.height()) == (skin.property("implicitWidth"), skin.property("implicitHeight")), scene
        assert root.height() <= 1080
        seen.append(scene)
    assert len(seen) == 10
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


@pytest.mark.parametrize("letter", LETTERS)
def test_the_boxes_grow_with_a_larger_font_and_stay_with_a_smaller_one(app, window, letter):
    root, backend, messages = window
    backend.setLayout(letter)
    use_screens(root, OFFSET, "B", 0, 0)

    def sizes():
        out = {}
        for scene in scenes(app, root, backend):
            out[scene] = (root.width(), root.height())
        return out

    design = sizes()
    backend.setFontScale(0.8)
    assert sizes() == design  # the proportions of the design, with more air
    backend.setFontScale(1.4)
    large = sizes()
    assert all(large[scene][0] == design[scene][0] for scene in design)  # the width of the panel stays
    assert all(design[scene][1] < large[scene][1] <= math.ceil(design[scene][1] * 1.4) for scene in design)
    backend.setLayout("C" if letter != "C" else "A")  # a layout switch keeps the font scale
    backend.setLayout(letter)
    settle(app)
    assert backend.fontScale == 1.4 and sizes() == large
    backend.resetLook()
    assert sizes() == design
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


@pytest.mark.parametrize("letter", LETTERS)
def test_a_long_group_stays_on_a_screen_of_1080_pixels_at_the_largest_scale_and_font(app, window, letter):
    root, backend, messages = window
    backend.setLayout(letter)
    backend.apply(many(blocked=1, working=3, idle=12))
    use_screens(root, OFFSET, "B", 0, 0)
    root.setProperty("openState", "idle")
    backend.setScale(2.0)
    backend.setFontScale(1.4)
    for _ in range(10):
        settle(app)
    cap = root.property("panel").property("maxAgentRows")
    row = rows(root, "agent")[0].height()
    assert root.height() <= 1080 and 3 <= cap <= 8 and text_findings(root) == []
    assert root.height() + 2 * row * 2.0 > 1080 or cap == 8  # and not fewer rows than necessary
    backend.resetLook()
    for _ in range(10):
        settle(app)
    assert root.property("panel").property("maxAgentRows") == 8
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


# ----- the options window follows the font scale too -----

@pytest.mark.parametrize("letter", LETTERS)
def test_the_texts_of_the_options_window_follow_the_font_scale_and_keep_their_room(app, real_options, letter):
    window, backend, messages = real_options
    backend.setLayout(letter)
    settle(app)
    design = pixel_sizes(window)
    assert (window.width(), window.height()) == (1076, 344) and len(design) >= 13 and text_findings(window) == []
    for scale in (0.8, 1.4):
        backend.setFontScale(scale)
        settle(app)
        sizes = pixel_sizes(window)
        assert [text for text, _ in sizes] == [text for text, _ in design]
        for (text, size), (_, base) in zip(sizes, design):
            assert abs(size - base * scale) <= 1.5 and (size < base if scale < 1 else size > base), (scale, text)
        assert text_findings(window) == [], scale
        # The window has one size in every theme: it grows only with a larger font.
        assert window.width() == 1076 and (window.height() == 344 if scale < 1 else 344 < window.height() < 344 * 1.4)
        assert (window.minimumHeight(), window.maximumHeight()) == (window.height(), window.height())
    backend.resetLook()
    settle(app)
    assert pixel_sizes(window) == design and (window.width(), window.height()) == (1076, 344)
