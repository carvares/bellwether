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


# ----- the font family -----

def families(backend):
    """A proportional and a monospace family of this system that the user can choose, both not the font of a theme."""
    from PySide6.QtGui import QFontDatabase
    listed = backend.fontFamilies
    themes = {"Adwaita Sans", "Inter", "Noto Sans", "DejaVu Sans", "Hack", "JetBrains Mono", "DejaVu Sans Mono"}
    serif = next((f for f in ("DejaVu Serif", "Liberation Serif", "Noto Serif") if f in listed), None) or next(
        f for f in listed if f not in themes and not QFontDatabase.isFixedPitch(f))
    mono = next((f for f in ("Liberation Mono", "Adwaita Mono", "Noto Sans Mono") if f in listed), None) or next(
        f for f in listed if f not in themes and QFontDatabase.isFixedPitch(f))
    return serif, mono


@pytest.mark.parametrize("letter", LETTERS)
def test_the_font_family_of_the_user_reaches_every_text_and_every_text_keeps_its_room(app, window, letter):
    root, backend, messages = window
    backend.setLayout(letter)
    use_screens(root, OFFSET, "B", 0, 0)
    backend.apply(TEAM)
    root.setProperty("openState", "working")
    settle(app)
    design = {i.property("font").family() for i in texts(root)}
    assert len(design) == 1  # each layout has one font
    for family in families(backend):
        assert family not in design and backend.setFontFamily(family) is True
        for scale in (1.0, 1.4):  # also the widest case: a monospace font and the largest text
            backend.setFontScale(scale)
            for scene in scenes(app, root, backend):
                assert {i.property("font").family() for i in texts(root)} == {family}, scene
                assert text_findings(root) == [], (family, scale, scene)
    backend.setLayout("C" if letter != "C" else "A")  # a layout switch keeps the family
    settle(app)
    assert {i.property("font").family() for i in texts(root)} == {families(backend)[1]}
    backend.setLayout(letter)
    backend.resetLook()
    backend.apply(TEAM)
    root.setProperty("openState", "working")
    settle(app)
    assert {i.property("font").family() for i in texts(root)} == design
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


# ----- the colours -----

CUSTOM = {"blocked": "#ff2d95", "done": "#ff9f1c", "working": "#00c2ff", "idle": "#b8f000",
          "background": "#f5f0e6", "text": "#3b1f6b", "frame": "#0f8a5f", "accent": "#d00000"}
# Colours of a skin that are not one of the roles: the dark text on a solid plate of a status colour, the white
# veil under the pointer on such a plate, and the colour of "no agents" and "offline" (the user cannot change it).
FIXED = {"#202124", "#ffffff", "#5f6368"}


def has(item, name):
    return item.metaObject().indexOfProperty(name) >= 0


def value(item, expression):
    """A value of an item that Python cannot read as a property (the border of a Rectangle, a gradient)."""
    from PySide6.QtQml import QQmlExpression, qmlContext
    result = QQmlExpression(qmlContext(item), item, expression).evaluate()
    return result[0] if isinstance(result, tuple) else result


def colours(root):
    """Every colour that a visible item of the panel has: (the kind of item, what it is, "#rrggbb", alpha)."""
    out = []
    for item in walk(root.contentItem()):
        if not item.isVisible():
            continue
        kind = item.metaObject().className().split("_")[0]
        found = [("color", item.property("color"))]
        # A Rectangle with no border has the border values width 1 and black, and draws no line.
        if has(item, "border") and value(item, "border.width") > 0 and value(item, "border.color").name() != "#000000":
            found.append(("border", value(item, "border.color")))
        if has(item, "gradient"):
            found += [("stop", value(item, f"gradient.stops[{n}].color"))
                      for n in range(int(value(item, "gradient ? gradient.stops.length : 0")))]
        if has(item, "tone"):  # the corner brackets of Layout C
            found.append(("tone", item.property("tone")))
        out += [(kind, what, colour.name(), colour.alpha()) for what, colour in found
                if colour is not None and hasattr(colour, "alpha") and colour.isValid() and colour.alpha() > 0]
    return out


def pixels(image, colour):
    """The number of pixels of the image that have exactly this colour."""
    from PySide6.QtGui import QColor
    wanted = QColor(colour).rgb()
    return sum(1 for y in range(image.height()) for x in range(image.width()) if image.pixel(x, y) == wanted)


def custom_look(backend, colors=CUSTOM):
    for role, colour in colors.items():
        assert backend.setColor(role, colour) is True


@pytest.mark.parametrize("letter", LETTERS)
def test_with_eight_custom_colours_no_colour_of_the_design_is_left_in_any_state(app, window, letter):
    root, backend, messages = window
    backend.setLayout(letter)
    use_screens(root, OFFSET, "B", 0, 0)
    custom_look(backend)
    from PySide6.QtGui import QColor
    inset = QColor(CUSTOM["background"]).darker(120).name()  # a card or a footer inside the panel
    allowed = set(CUSTOM.values()) | FIXED | {inset}
    roles_seen = set()
    for scene in scenes(app, root, backend):
        found = colours(root)
        left = sorted({(kind, what, colour) for kind, what, colour, _ in found if colour not in allowed})
        assert left == [], (letter, scene)
        roles_seen |= {role for role, colour in CUSTOM.items() if any(c == colour for _, _, c, _ in found)}
        if scene == "a jump runs":  # "opening…" has the accent
            assert any(kind == "QQuickText" and c == CUSTOM["accent"] for kind, _, c, _ in found)
        if scene == "a jump failed":  # the message has the colour of blocked
            (message,) = [i for i in texts(root) if i.property("text").endswith(MESSAGE)]
            assert message.property("color").name() == CUSTOM["blocked"]
    assert roles_seen == set(CUSTOM)  # each of the eight colours is on the screen in some state
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


@pytest.mark.parametrize("letter", LETTERS)
def test_each_status_colour_is_drawn_and_the_colour_of_the_design_is_gone(app, window, letter):
    root, backend, messages = window
    backend.setLayout(letter)
    backend.apply(many(blocked=1, done=2, working=3, idle=4))
    settle(app)
    from tests.test_skins import STATE_COLORS
    before = root.grabWindow()
    assert all(pixels(before, STATE_COLORS[state]) > 0 for state in CUSTOM if state in STATE_COLORS)
    for state in ("blocked", "done", "working", "idle"):
        assert backend.setColor(state, CUSTOM[state]) is True
        settle(app)
        image = root.grabWindow()
        assert pixels(image, CUSTOM[state]) >= pixels(before, STATE_COLORS[state]) > 0, state
        assert pixels(image, STATE_COLORS[state]) == 0, state
        group = next(g for g in js(root, "root.panel.groups").toVariant() if g["state"] == state)
        assert group["color"] == CUSTOM[state]
    assert js(root, "'' + root.panel.topColor") == CUSTOM["blocked"]  # the border or the brackets: the top status
    backend.resetColor("blocked")
    settle(app)
    assert pixels(root.grabWindow(), STATE_COLORS["blocked"]) == pixels(before, STATE_COLORS["blocked"])
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


@pytest.mark.parametrize("letter", LETTERS)
def test_the_background_keeps_the_opacity_of_the_design_or_takes_its_own(app, window, letter):
    root, backend, messages = window
    backend.setLayout(letter)
    backend.apply(TEAM)
    settle(app)
    plate = max((i for i in walk(root.contentItem()) if i.isVisible() and has(i, "border")
                 and i.width() == root.width()), key=lambda i: i.height())  # the frame of the panel
    design = plate.property("color")
    assert design.name(design.NameFormat.HexArgb) == backend.defaultColors["background"] and 200 < design.alpha() < 255
    backend.setColor("background", "#102030")
    settle(app)
    assert plate.property("color").name() == "#102030" and plate.property("color").alpha() == design.alpha()
    backend.setColor("background", "#80102030")
    settle(app)
    assert plate.property("color").name() == "#102030" and plate.property("color").alpha() == 0x80
    backend.setColor("background", "#ff102030")
    settle(app)
    image = root.grabWindow()
    assert pixels(image, "#102030") > image.width() * image.height() * 0.3  # the panel has this colour
    backend.resetColor("background")
    settle(app)
    assert plate.property("color") == design
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


@pytest.mark.parametrize("letter", LETTERS)
def test_the_frame_colour_shows_with_no_agents_and_the_text_colour_gives_the_dim_and_the_faint_text(app, window, letter):
    root, backend, messages = window
    backend.setLayout(letter)
    backend.apply([])
    backend.setColor("frame", CUSTOM["frame"])
    settle(app)
    image = root.grabWindow()
    assert image.pixelColor(root.width() // 2, 0).name() == CUSTOM["frame"]  # the neutral frame, at its top edge
    if letter == "C":
        assert image.pixelColor(0, 0).name() == CUSTOM["frame"]  # and the corner brackets with no agents
    backend.apply(TEAM)
    root.setProperty("openState", "working")
    settle(app)
    before = [i.property("color") for i in texts(root)]
    greys = {c.name() for c in before if c.red() == c.green() or abs(c.red() - c.blue()) < 24}
    assert len(greys) >= 3  # the text, the dim text and the faint text of the design
    backend.setColor("text", CUSTOM["text"])
    settle(app)
    alphas = set()
    assert len(texts(root)) == len(before)
    for item, old in zip(texts(root), before):
        colour = item.property("color")
        if old.name() in greys and old.name() != "#202124":
            assert colour.name() == CUSTOM["text"], item.property("text")
            alphas.add(colour.alpha())
        else:
            assert colour == old, item.property("text")  # a status colour, or the dark text on a solid plate
    assert 255 in alphas and round(0.62 * 255) in alphas and min(alphas) >= round(0.28 * 255) and len(alphas) >= 3
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


@pytest.mark.parametrize("letter", LETTERS)
def test_reset_gives_the_pixels_of_the_design_again(app, window, letter):
    """Set everything, reset everything, in one run: the panel is the same picture as before, in every state."""
    root, backend, messages = window
    backend.setLayout(letter)
    use_screens(root, OFFSET, "B", 0, 0)
    serif, mono = families(backend)

    def pictures():
        out = {}
        for scene in scenes(app, root, backend):
            root.setProperty("hoverRow", None)
            settle(app)
            out[scene] = root.grabWindow()
        return out

    design = pictures()
    custom_look(backend)
    backend.setScale(1.5), backend.setFontScale(1.4), backend.setFontFamily(serif)
    custom = pictures()
    assert all(custom[scene] != design[scene] for scene in design)
    backend.resetLook()
    again = pictures()
    assert [scene for scene in design if again[scene] != design[scene]] == []
    assert (backend.scale, backend.fontScale, backend.fontFamily, backend.colorOverrides) == (1.0, 1.0, "", {})
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []


# ----- the options window has the custom look too -----

def test_the_options_window_takes_the_family_and_the_colours_and_the_selected_card_has_the_accent(app, real_options):
    window, backend, messages = real_options
    from tests.test_options import cards, named
    frame = named(window, "isFrame")
    design = (frame.property("color"), value(frame, "border.color"))
    serif, mono = families(backend)
    for letter in LETTERS:
        backend.setLayout(letter)
        custom_look(backend)
        backend.setFontFamily(serif)
        settle(app)
        selected = next(c for c in cards(window) if c.property("selected"))
        other = next(c for c in cards(window) if not c.property("selected"))
        assert frame.property("color").name() == CUSTOM["background"]
        assert value(frame, "border.color").name() == CUSTOM["frame"]
        assert value(selected, "border.color").name() == CUSTOM["accent"]
        plate = selected.property("color")
        assert plate.name() == CUSTOM["accent"] and 20 <= plate.alpha() <= 40  # the opacity of the design
        assert value(other, "border.color").name() == CUSTOM["frame"]  # a line
        assert {i.property("font").family() for i in texts(window)} == {serif}
        assert {i.property("color").name() for i in texts(window)} == {CUSTOM["text"], "#0b0e11"}  # the tag: dark
        assert text_findings(window) == []
        backend.resetLook()
        settle(app)
    backend.setLayout("C")
    settle(app)
    assert (frame.property("color"), value(frame, "border.color")) == design
