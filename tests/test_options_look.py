"""The controls of the custom look in the options window: the real Options.qml with the real backend on a scratch
state file, and pointer and key events as a person makes them. Off screen."""
import json
import re
import time
from types import SimpleNamespace

import pytest
import shiboken6
from PySide6.QtCore import QPoint, QPointF, Qt, qInstallMessageHandler
from PySide6.QtGui import QAccessible, QColor, QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression, qmlContext
from PySide6.QtTest import QTest

from bellwether import layouts
from bellwether.__main__ import UI_PATH
from bellwether.platform.linux import IMPORT_PATH
from bellwether.backend import Backend
from bellwether.layouts import built_skins
from bellwether.state import Agent
from tests.audit import text_findings, walk
from tests.conftest import wide_options
from tests.test_options import LETTERS, SIZE_HINTS_NOTE, cards, settle, spoken
from tests.test_qml import LAYER_QML, LAYERSHELL_QMLDIR, OFFSCREEN_NOTE

FAMILIES = ["Made Up Mono", "Made Up Sans", "Other Mono Wide", "Plain Serif"]
ROLES = ["blocked", "done", "working", "idle", "background", "text", "frame", "accent"]
NAMES = dict(zip(ROLES, ["Blocked", "Done", "Working", "Idle", "Background", "Text", "Frame", "Accent"]))
CUSTOM = {"blocked": "#ff5555", "done": "#f1fa8c", "working": "#8be9fd", "idle": "#50fa7b",
          "background": "#e6282a36", "text": "#f8f8f2", "frame": "#6272a4", "accent": "#bd93f9"}
LOOK_KEYS = {"scale", "fontScale", "fontFamily", "colors"}
LEFT, NONE = Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
HINT = "Use a colour like #8ab4f8"


def hold_the_save(backend):
    """The save of the look comes 0.4 s after the last change (tests/test_look.py checks that). Here a test says
    when that time is over (`fire`), so a slow machine cannot write the file in the middle of a test."""
    assert backend._look_timer.interval() == 400
    backend._look_timer.setInterval(600_000)


def make(app, fake_client, path, families=FAMILIES, room=1080):
    """(window, backend, messages, engine): the options window on a screen of `room` pixels of height."""
    backend = Backend(fake_client, settings_path=path, skins=built_skins(), families=families)
    hold_the_save(backend)
    messages = []
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda errors: messages.extend(e.toString() for e in errors))
    engine.rootContext().setContextProperty("backend", backend)
    options = wide_options(engine)
    options.open()
    settle(app)
    window = engine.rootObjects()[0]
    window.setProperty("roomHeight", room)
    settle(app)
    return window, backend, messages, engine


@pytest.fixture
def state_path(tmp_path):
    return tmp_path / "state.json"


@pytest.fixture
def shown(app, fake_client, state_path):
    """Yield (window, backend, Qt messages). After: no QML warning in any step."""
    messages = []
    previous = qInstallMessageHandler(lambda mode, context, text: messages.append(text))
    engines = []
    try:
        window, backend, warnings, engine = make(app, fake_client, state_path)
        engines.append(engine)
        yield window, backend, messages
        backend._look_timer.stop()
        messages.extend(warnings)
    finally:
        for engine in engines:
            shiboken6.delete(engine)
        app.processEvents()
        qInstallMessageHandler(previous)
    assert [m for m in messages if SIZE_HINTS_NOTE not in m] == []


def items(window, name, value=True):
    return [i for i in walk(window.contentItem()) if i.property(name) == value]


def find(window, name, value=True):
    (item,) = items(window, name, value)
    return item


def centre(item):
    return item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()


def click(app, window, item):
    QTest.mouseClick(window, LEFT, NONE, centre(item))
    settle(app)


def key(app, window, which, modifier=NONE):
    QTest.keyClick(window, which, modifier)
    settle(app)


def type_text(app, window, text):
    for letter in text:
        QTest.keyClick(window, letter)
    settle(app)


def replace_text(app, window, text):
    """Select all of the field that has the keyboard, and type."""
    QTest.keyClick(window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    type_text(app, window, text)


def js(item, text):
    expression = QQmlExpression(qmlContext(item), item, text)
    value = expression.evaluate()
    assert not expression.hasError(), expression.error().toString()
    return value[0] if isinstance(value, tuple) else value


def fire(backend):
    """The 0.4 s after the last change of the look are over."""
    timer = backend._look_timer
    assert timer.isActive()
    timer.stop()
    timer.timeout.emit()


def saved(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def focused(window):
    """The accessible name of the item that has the keyboard."""
    item = window.activeFocusItem()
    while item is not None:
        attached = [c for c in item.children() if c.metaObject().className() == "QQuickAccessibleAttached"]
        if attached and attached[0].property("name"):
            return attached[0].property("name")
        item = item.parentItem()
    return None


def tab_order(app, window, limit=60):
    """The names of the controls in the order of the Tab key, from the control that has the keyboard, one round."""
    first = focused(window)
    order = [first]
    for _ in range(limit):
        key(app, window, Qt.Key.Key_Tab)
        if focused(window) == first:
            return order
        order.append(focused(window))
    raise AssertionError(f"the Tab key does not come back: {order}")


def point_for(slider, value):
    """The place on a slider for a value."""
    low, high, handle = slider.property("from"), slider.property("to"), slider.property("handleSize")
    x = handle / 2 + (value - low) / (high - low) * (slider.width() - handle)
    return slider.mapToScene(QPointF(x, slider.height() / 2)).toPoint()


def in_window(window, item):
    box = item.mapRectToScene(item.boundingRect())
    return box.top() >= 0 and box.bottom() <= window.height() and box.left() >= 0 and box.right() <= window.width()


# ----- the two sliders -----

SLIDERS = [("scale", "Panel size", 0.75, 2.0, "setScale"), ("fontScale", "Text size", 0.8, 1.4, "setFontScale")]


@pytest.mark.parametrize("name, label, low, high, setter", SLIDERS)
def test_a_slider_follows_the_pointer_live_and_the_file_gets_the_last_value_one_time(
        app, shown, state_path, name, label, low, high, setter):
    window, backend, messages = shown
    slider = find(window, "sliderFor", name)
    value = lambda: getattr(backend, name)
    shown_value = lambda: find(window, "valueFor", name).property("text")
    assert (slider.property("from"), slider.property("to"), slider.property("step")) == (low, high, 0.05)
    assert value() == 1.0 and shown_value() == "100 %" and spoken(slider) == f"{label}, 100 percent"
    told = []
    getattr(backend, name + "Changed").connect(lambda: told.append(value()))
    target = round(low + 0.05 * 3, 2)
    QTest.mousePress(window, LEFT, NONE, point_for(slider, target))  # a press on the track: the value of that place
    settle(app)
    assert value() == target and slider.property("activeFocus")
    steps = [round(low + 0.05 * n, 2) for n in range(4, 9)]
    for step in steps:  # the drag: each step applies at once
        QTest.mouseMove(window, point_for(slider, step))
        settle(app)
        assert value() == step
    assert told == [target, *steps] and not state_path.exists()  # live, and no write while the slider moves
    QTest.mouseMove(window, point_for(slider, high) + QPoint(120, 40))  # far out at the right: the largest value
    settle(app)
    assert value() == high
    QTest.mouseMove(window, point_for(slider, low) - QPoint(100, 0))
    settle(app)
    assert value() == low
    QTest.mouseMove(window, point_for(slider, 1.25))
    QTest.mouseRelease(window, LEFT, NONE, point_for(slider, 1.25))
    settle(app)
    assert value() == 1.25 and shown_value() == "125 %" and spoken(slider) == f"{label}, 125 percent"
    QTest.mouseMove(window, point_for(slider, 1.3))  # a move with no button does nothing
    settle(app)
    assert value() == 1.25
    fire(backend)
    assert saved(state_path) == {name: 1.25}


@pytest.mark.parametrize("name, label, low, high, setter", SLIDERS)
def test_the_arrow_keys_move_a_slider_by_one_step_and_stop_at_its_ends(app, shown, name, label, low, high, setter):
    window, backend, messages = shown
    slider = find(window, "sliderFor", name)
    value = lambda: getattr(backend, name)
    slider.forceActiveFocus()
    seen = []
    for which in (Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Left, Qt.Key.Key_Down, Qt.Key.Key_Down,
                  Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
        key(app, window, which)
        seen.append(value())
    assert seen == [1.05, 1.1, 1.05, 1.0, 0.95, 1.15, 0.95]
    key(app, window, Qt.Key.Key_End)
    assert value() == high
    key(app, window, Qt.Key.Key_Right)
    assert value() == high
    key(app, window, Qt.Key.Key_Home)
    assert value() == low
    key(app, window, Qt.Key.Key_Left)
    assert value() == low and window.isVisible()
    key(app, window, Qt.Key.Key_Right)
    assert value() == round(low + 0.05, 2) and spoken(slider) == f"{label}, {round((low + 0.05) * 100)} percent"
    getattr(backend, setter)(1.23)  # a value of the file between two steps: the next step above or below it
    key(app, window, Qt.Key.Key_Right)
    assert value() == 1.25
    getattr(backend, setter)(1.23)
    key(app, window, Qt.Key.Key_Left)
    assert value() == 1.2
    getattr(backend, setter)(1.21)  # near a step: still the next one, not that one
    key(app, window, Qt.Key.Key_Right)
    assert value() == 1.25
    getattr(backend, setter)(1.24)
    key(app, window, Qt.Key.Key_PageDown)  # Page Down: the next step below, and three more
    assert value() == 1.05


@pytest.mark.parametrize("name, label, low, high, setter", SLIDERS)
def test_a_slider_goes_back_to_100_percent_in_one_action(app, shown, name, label, low, high, setter):
    window, backend, messages = shown
    slider = find(window, "sliderFor", name)
    reset = find(window, "resetFor", name)
    value = lambda: getattr(backend, name)
    assert not reset.isVisible() and not reset.property("activeFocusOnTab") or not reset.isEnabled()
    getattr(backend, setter)(1.3)
    settle(app)
    assert reset.isVisible() and spoken(reset) == f"Reset the {label.lower()} to 100 percent"
    click(app, window, reset)  # the mark next to the value
    assert value() == 1.0 and not reset.isVisible()
    getattr(backend, setter)(low)
    settle(app)
    QTest.mouseDClick(window, LEFT, NONE, point_for(slider, low))  # a double click on the handle of the slider
    settle(app)
    assert value() == 1.0
    getattr(backend, setter)(high)
    slider.forceActiveFocus()
    settle(app)
    key(app, window, Qt.Key.Key_Tab)  # by keyboard: the next stop is the mark
    assert focused(window) == spoken(reset)
    key(app, window, Qt.Key.Key_Space)
    assert value() == 1.0 and focused(window) == f"{label}, 100 percent"  # the keyboard is on the slider again
    mark = next(i for i in walk(slider) if i.property("isDefaultMark"))
    handle = next(i for i in walk(slider) if i.property("isSliderHandle"))
    assert abs(centre(mark).x() - centre(handle).x()) <= 1  # the mark of the default is where the handle is now


def test_a_fast_run_of_a_slider_writes_the_file_one_time(app, shown, state_path, monkeypatch):
    window, backend, messages = shown
    writes = []
    real = Backend._save_look
    monkeypatch.setattr(Backend, "_save_look", lambda self: (writes.append(1), real(self)))
    slider = find(window, "sliderFor", "scale")
    QTest.mousePress(window, LEFT, NONE, point_for(slider, 0.75))
    for step in range(200):  # to and fro, with no pause
        QTest.mouseMove(window, point_for(slider, 0.75 + (step % 26) * 0.05))
    QTest.mouseRelease(window, LEFT, NONE, point_for(slider, 1.6))
    settle(app)
    assert backend.scale == 1.6 and writes == []
    fire(backend)
    assert writes == [1] and saved(state_path) == {"scale": 1.6}


# ----- the font -----

def font_rows(window):
    return [r.property("fontRowFor") for r in sorted(
        (i for i in walk(find(window, "isFontList")) if i.property("fontRowFor") and i.isVisible()), key=lambda i: i.y())]


def test_the_font_chooser_filters_while_the_user_types_and_enter_chooses(app, shown, state_path):
    window, backend, messages = shown
    button, chooser = find(window, "isFontButton"), find(window, "isFontChooser")
    name = lambda: find(window, "isFontName").property("text")
    assert name() == "Layout default" and spoken(button) == "Font, Layout default" and not chooser.property("open")
    height = window.height()
    click(app, window, button)
    assert chooser.property("open") and window.height() > height  # the list is inside the window, which grows
    assert font_rows(window) == ["Layout default", *FAMILIES]
    field = find(window, "isFontFilter")
    assert field.property("activeFocus") and spoken(field) == "Filter the fonts, 4 of 4"
    type_text(app, window, "mono ")  # a space is text here, not a press of a control
    assert field.property("text") == "mono " and font_rows(window) == ["Layout default", "Made Up Mono", "Other Mono Wide"]
    assert find(window, "isFontCount").property("text") == "2 fonts" and backend.fontFamily == ""
    key(app, window, Qt.Key.Key_Down)
    key(app, window, Qt.Key.Key_Return)  # the second family that matches
    assert backend.fontFamily == "Other Mono Wide" and not chooser.property("open") and window.height() == height
    assert name() == "Other Mono Wide" and focused(window) == "Font, Other Mono Wide" and window.isVisible()
    assert find(window, "isTitle").property("font").family() == "Other Mono Wide"  # the window follows at once
    fire(backend)
    assert saved(state_path) == {"fontFamily": "Other Mono Wide"}
    key(app, window, Qt.Key.Key_Space)  # the button opens the list again: the family in effect is marked
    marks = [m.parentItem().property("fontRowFor") for m in items(window, "isCurrentFontMark") if m.isVisible()]
    assert marks == ["Other Mono Wide"] and field.property("text") == ""
    assert [spoken(r) for r in walk(find(window, "isFontList")) if r.property("fontRowFor") == "Other Mono Wide"] == [
        "Other Mono Wide, selected"]
    type_text(app, window, "zz")
    assert font_rows(window) == ["Layout default"] and find(window, "isFontCount").property("text") == "No match"
    key(app, window, Qt.Key.Key_Return)  # nothing matches: Enter chooses nothing
    assert backend.fontFamily == "Other Mono Wide" and chooser.property("open")
    replace_text(app, window, "SANS")  # capitals do not matter
    assert font_rows(window) == ["Layout default", "Made Up Sans"]
    key(app, window, Qt.Key.Key_Up)  # from the first match up to "Layout default"
    key(app, window, Qt.Key.Key_Enter)
    assert backend.fontFamily == "" and name() == "Layout default" and not chooser.property("open")
    fire(backend)
    assert saved(state_path) == {}


def test_a_click_on_a_row_chooses_the_font_and_esc_closes_the_list_before_the_window(app, shown):
    window, backend, messages = shown
    button, chooser = find(window, "isFontButton"), find(window, "isFontChooser")
    click(app, window, button)
    row = next(i for i in walk(find(window, "isFontList")) if i.property("fontRowFor") == "Plain Serif")
    click(app, window, row)
    assert backend.fontFamily == "Plain Serif" and not chooser.property("open")
    click(app, window, button)
    type_text(app, window, "made")
    key(app, window, Qt.Key.Key_Escape)  # the list closes, nothing is chosen, the window stays
    assert not chooser.property("open") and window.isVisible() and backend.fontFamily == "Plain Serif"
    assert focused(window) == "Font, Plain Serif"
    click(app, window, button)
    click(app, window, button)  # the button closes the list too
    assert not chooser.property("open")
    key(app, window, Qt.Key.Key_Escape)
    assert not window.isVisible()


def test_the_font_list_makes_only_the_rows_on_the_screen_for_hundreds_of_fonts(app, fake_client, state_path):
    many = [f"Made Up Family {n:03d}" for n in range(600)]
    window, backend, messages, engine = make(app, fake_client, state_path, families=many)
    try:
        began = time.monotonic()
        click(app, window, find(window, "isFontButton"))
        made = [i for i in walk(find(window, "isFontList")) if i.property("fontRowFor")]
        assert len(made) <= 10 and find(window, "isFontCount").property("text") == "600 fonts"
        type_text(app, window, "59")
        assert font_rows(window)[:3] == ["Layout default", "Made Up Family 059", "Made Up Family 159"]
        for _ in range(12):
            key(app, window, Qt.Key.Key_Down)
        key(app, window, Qt.Key.Key_PageDown)
        key(app, window, Qt.Key.Key_Return)
        # 16 families match: 059, 159, ..., 559, then 590 to 599. From the first, 12 and 6 rows down: the last.
        assert backend.fontFamily == "Made Up Family 599"
        assert time.monotonic() - began < 5 and messages == []
    finally:
        backend._look_timer.stop()
        shiboken6.delete(engine)
        app.processEvents()


# ----- the colours -----

def swatch(window, role):
    return find(window, "swatchFor", role)


def editor(window):
    return find(window, "isColourEditor")


def preset(window, colour):
    return find(window, "presetColour", colour)


def default_name(backend, role):
    colour = backend.defaultColors[role]
    opacity = f", {round(int(colour[1:3], 16) / 2.55)} percent opacity" if len(colour) == 9 else ""
    return f"{NAMES[role]} colour, default, #{colour[-6:]}{opacity}"


def test_the_eight_colours_show_in_two_groups_with_the_colour_in_effect(app, shown):
    window, backend, messages = shown
    titles = [t.property("text") for t in walk(window.contentItem()) if t.property("isSectionTitle")]
    assert titles == ["Layout", "Size", "Text", "Colours"]
    found = sorted((i for i in walk(window.contentItem()) if i.property("swatchFor")), key=lambda i: centre(i).x())
    assert [s.property("swatchFor") for s in found] == ROLES == backend.colorRoles
    assert len({centre(s).y() for s in found}) == 1  # one row
    gaps = [found[n + 1].mapToScene(QPointF(0, 0)).x() - found[n].mapToScene(QPointF(0, 0)).x() for n in range(7)]
    assert gaps[3] > gaps[0] == gaps[1] == gaps[2] == gaps[4]  # two groups
    texts = [t.property("text") for t in walk(window.contentItem()) if t.inherits("QQuickText")]
    assert "Status" in texts and "Panel" in texts
    assert [spoken(s) for s in found] == [default_name(backend, role) for role in ROLES]
    assert spoken(found[0]) == "Blocked colour, default, #f28b82"
    assert spoken(found[4]) == "Background colour, default, #0b0e11, 94 percent opacity"
    for item in found:
        chip = next(i for i in walk(item) if i.property("isChip"))
        assert chip.property("color").name() == "#" + backend.colors[item.property("swatchFor")][-6:]
        assert [r for r in walk(item) if r.property("isColourReset") and r.isVisible()] == []  # no reset: not custom
    assert not editor(window).isVisible()


@pytest.mark.parametrize("role", ROLES)
def test_a_colour_changes_through_the_palette_and_the_hex_field_and_goes_back(app, shown, state_path, role):
    window, backend, messages = shown
    item, name = swatch(window, role), NAMES[role]
    reset = next(i for i in walk(item) if i.property("isColourReset"))
    default = backend.colors[role]
    click(app, window, item)
    panel = editor(window)
    assert panel.isVisible() and item.property("editing") and window.property("editingRole") == role
    assert find(window, "isEditorTitle").property("text") == f"{name} colour"
    assert find(window, "isOpacitySlider").isVisible() == (role == "background")
    assert focused(window).startswith(f"Presets for the {name} colour, ")  # the keyboard is in the editor
    told = []
    backend.colorsChanged.connect(lambda: told.append(backend.colorOverrides.get(role)))
    # The palette.
    click(app, window, preset(window, "#bd93f9"))
    assert told == ["#bd93f9"] and backend.colorOverrides == {role: "#bd93f9"}
    assert backend.colors[role][-6:] == "bd93f9" and preset(window, "#bd93f9").property("inEffect")
    assert spoken(item).startswith(f"{name} colour, custom, #bd93f9") and reset.isVisible()
    assert spoken(reset) == f"Reset {name} colour"
    key(app, window, Qt.Key.Key_Right)  # the keyboard in the palette: the next preset
    key(app, window, Qt.Key.Key_Space)
    assert backend.colorOverrides == {role: "#ff79c6"}
    # The hex field.
    field, message = find(window, "isHexField"), find(window, "isHexMessage")
    assert field.property("text") == "#ff79c6"
    click(app, window, field)
    replace_text(app, window, "#12AB34")
    assert backend.colorOverrides == {role: "#12ab34"} and not message.isVisible()  # applies while the user types
    replace_text(app, window, "0a0b0c")  # also with no "#"
    assert backend.colorOverrides == {role: "#0a0b0c"}
    replace_text(app, window, "#12")  # not a colour yet: nothing changes, and nothing is wrong yet
    assert backend.colorOverrides == {role: "#0a0b0c"} and not message.isVisible()
    key(app, window, Qt.Key.Key_Return)  # the user says "this is it": it is not a colour
    assert message.isVisible() and message.property("text") == HINT and backend.colorOverrides == {role: "#0a0b0c"}
    before = len(told)
    for wrong in ("red", "#12345g", "#12 3456", "12 34 56", "#ffg"):
        replace_text(app, window, wrong)
        assert message.isVisible() and message.property("text") == HINT, wrong
    assert len(told) == before and backend.colorOverrides == {role: "#0a0b0c"} and window.isVisible()
    replace_text(app, window, "#445566")
    assert not message.isVisible() and backend.colorOverrides == {role: "#445566"}
    fire(backend)
    assert saved(state_path) == {"colors": {role: "#445566"}}
    # Back to the colour of the layout.
    replace_text(app, window, "nope")
    click(app, window, reset)
    assert backend.colorOverrides == {} and backend.colors[role] == default and not reset.isVisible()
    assert spoken(item) == default_name(backend, role)
    assert field.property("text") == "#" + default[-6:] and not message.isVisible()  # the field shows the colour again
    assert panel.isVisible()  # the editor stays open for this colour
    fire(backend)
    assert saved(state_path) == {}
    click(app, window, item)  # the swatch of the open editor closes it
    assert not panel.isVisible() and window.property("editingRole") == ""


def test_the_editor_moves_to_a_different_colour_and_done_closes_it(app, shown):
    window, backend, messages = shown
    click(app, window, swatch(window, "done"))
    click(app, window, preset(window, "#50fa7b"))
    click(app, window, swatch(window, "frame"))  # a second swatch: the same editor, for that colour
    assert window.property("editingRole") == "frame" and find(window, "isEditorTitle").property("text") == "Frame colour"
    assert find(window, "isHexField").property("text") == "#2b333b"
    assert [s.property("swatchFor") for s in items(window, "editing")] == ["frame"]
    click(app, window, preset(window, "#9aa0a6"))
    assert backend.colorOverrides == {"done": "#50fa7b", "frame": "#9aa0a6"}
    click(app, window, find(window, "isEditorClose"))
    assert not editor(window).isVisible() and focused(window).startswith("Frame colour, custom, #9aa0a6")


def test_the_opacity_of_the_background_is_a_slider_and_gives_a_colour_with_alpha(app, shown, state_path):
    window, backend, messages = shown
    click(app, window, swatch(window, "background"))
    slider, shown_value = find(window, "isOpacitySlider"), find(window, "isOpacityValue")
    assert spoken(slider) == "Background opacity, 94 percent" and shown_value.property("text") == "94 %"
    limits = (backend.opacityMin, backend.opacityMax, backend.opacityStep)
    assert (slider.property("from"), slider.property("to"), slider.property("step")) == limits == (0.1, 1, 0.05)
    # A colour with no choice of the opacity is saved as "#rrggbb": it keeps the opacity of each layout.
    click(app, window, preset(window, "#1f2023"))
    assert backend.colorOverrides == {"background": "#1f2023"} and backend.colors["background"] == "#f01f2023"
    slider.forceActiveFocus()
    key(app, window, Qt.Key.Key_Right)  # from 94 % to the next step above, not one step further
    assert backend.colorOverrides == {"background": "#f21f2023"} and shown_value.property("text") == "95 %"
    key(app, window, Qt.Key.Key_Left)
    assert backend.colorOverrides == {"background": "#e61f2023"} and shown_value.property("text") == "90 %"
    QTest.mousePress(window, LEFT, NONE, point_for(slider, 0.5))
    QTest.mouseRelease(window, LEFT, NONE, point_for(slider, 0.5))
    settle(app)
    assert backend.colorOverrides == {"background": "#801f2023"} and spoken(slider) == "Background opacity, 50 percent"
    assert spoken(swatch(window, "background")) == "Background colour, custom, #1f2023, 50 percent opacity"
    click(app, window, preset(window, "#3c4043"))  # a new colour keeps the opacity that the user chose
    assert backend.colorOverrides == {"background": "#803c4043"}
    click(app, window, find(window, "isHexField"))
    replace_text(app, window, "#102030")
    assert backend.colorOverrides == {"background": "#80102030"} and find(window, "isHexField").property("text") == "#102030"
    slider.forceActiveFocus()
    key(app, window, Qt.Key.Key_Home)
    assert backend.colorOverrides == {"background": "#1a102030"} and window.isVisible()  # 10 %: the least
    key(app, window, Qt.Key.Key_End)
    assert backend.colorOverrides == {"background": "#ff102030"}
    fire(backend)
    assert saved(state_path) == {"colors": {"background": "#ff102030"}}
    frame = find(window, "isFrame")
    assert frame.property("color").name(frame.property("color").NameFormat.HexArgb) == "#ff102030"  # this window too


# ----- reset to defaults -----

def test_reset_to_defaults_is_off_with_nothing_custom_and_needs_two_clicks(app, shown, state_path):
    window, backend, messages = shown
    button = find(window, "isResetAll")
    label = lambda: next(t.property("text") for t in walk(button) if t.inherits("QQuickText"))
    assert not button.isEnabled() and label() == "Reset to defaults" and in_window(window, button)
    click(app, window, button)  # nothing custom: nothing to do
    assert label() == "Reset to defaults" and not window.property("resetArmed")
    backend.setScale(1.5), backend.setFontScale(1.2), backend.setFontFamily("Made Up Mono")
    for role, colour in CUSTOM.items():
        backend.setColor(role, colour)
    settle(app)
    fire(backend)
    assert set(saved(state_path)) == LOOK_KEYS and button.isEnabled()
    click(app, window, swatch(window, "text"))  # the editor is open
    click(app, window, button)  # the first click only arms
    assert label() == "Click again to reset" and spoken(button) == "Reset to defaults, press again to reset"
    assert backend.scale == 1.5 and backend.colorOverrides == CUSTOM and window.property("resetArmed")
    click(app, window, button)
    assert (backend.scale, backend.fontScale, backend.fontFamily, backend.colorOverrides) == (1.0, 1.0, "", {})
    assert not button.isEnabled() and label() == "Reset to defaults" and not editor(window).isVisible()
    fire(backend)
    assert saved(state_path) == {}  # the file has none of the look keys
    assert [i for i in walk(window.contentItem()) if (i.property("isColourReset") or i.property("resetFor"))
            and i.isVisible()] == []


def test_a_first_click_on_reset_to_defaults_is_forgotten_after_3_seconds_and_when_the_keyboard_leaves(app, shown):
    window, backend, messages = shown
    backend.setScale(1.5)
    settle(app)
    button = find(window, "isResetAll")
    button.forceActiveFocus()
    key(app, window, Qt.Key.Key_Return)
    assert window.property("resetArmed") and focused(window) == "Reset to defaults, press again to reset"
    key(app, window, Qt.Key.Key_Tab)  # the keyboard leaves: not armed any more
    assert not window.property("resetArmed") and backend.scale == 1.5
    key(app, window, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
    key(app, window, Qt.Key.Key_Space)
    assert window.property("resetArmed")
    timer = next(t for t in button.parent().children() if t.metaObject().className() == "QQmlTimer")
    assert timer.property("interval") == 3000 and timer.property("running")
    QTest.qWait(3150)
    settle(app)
    assert not window.property("resetArmed") and backend.scale == 1.5
    key(app, window, Qt.Key.Key_Space)
    key(app, window, Qt.Key.Key_Space)  # two presses by keyboard reset
    assert backend.scale == 1.0 and not backend.lookIsCustom


# ----- the keyboard -----

def test_esc_closes_the_colour_editor_first_and_the_window_second(app, shown):
    window, backend, messages = shown
    click(app, window, swatch(window, "idle"))
    click(app, window, find(window, "isHexField"))
    replace_text(app, window, "#aa")
    key(app, window, Qt.Key.Key_Space)  # a space in the field is text: no control is pressed
    assert editor(window).isVisible() and backend.colorOverrides == {} and window.isVisible()
    key(app, window, Qt.Key.Key_Escape)
    assert not editor(window).isVisible() and window.isVisible() and backend.colorOverrides == {}
    assert focused(window) == "Idle colour, default, #81c995"  # the keyboard is on the swatch again
    key(app, window, Qt.Key.Key_Return)  # Enter opens the editor from the swatch
    assert editor(window).isVisible() and window.property("editingRole") == "idle"
    key(app, window, Qt.Key.Key_Escape)
    key(app, window, Qt.Key.Key_Escape)
    assert not window.isVisible()
    window.show()
    settle(app)
    assert not editor(window).isVisible() and focused(window) == "Layout C, Techno / HUD, selected"


DEFAULT_ORDER = [
    "Layout C, Techno / HUD, selected", "Layout D, Signal strip", "Layout E, Ring",
    "Panel size, 100 percent", "Text size, 100 percent", "Font, Layout default",
    "Blocked colour, default, #f28b82", "Done colour, default, #fdd663", "Working colour, default, #8ab4f8",
    "Idle colour, default, #81c995", "Background colour, default, #0b0e11, 94 percent opacity",
    "Text colour, default, #e3e9ee", "Frame colour, default, #2b333b", "Accent colour, default, #8ab4f8",
    "Close", "Show model and session time", "Layout A, Refined list", "Layout B, Tiles"]


def test_the_tab_key_reaches_every_control_in_the_order_of_the_window(app, shown):
    window, backend, messages = shown
    assert tab_order(app, window) == DEFAULT_ORDER  # "Reset to defaults" is off: nothing is custom
    key(app, window, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
    assert focused(window) == "Layout B, Tiles"


def test_the_tab_key_reaches_every_control_with_every_value_custom_and_the_editor_and_the_list_open(app, shown):
    window, backend, messages = shown
    backend.setScale(1.25), backend.setFontScale(1.1), backend.setFontFamily("Made Up Sans")
    for role, colour in CUSTOM.items():
        backend.setColor(role, colour)
    settle(app)
    click(app, window, swatch(window, "background"))
    cards(window)[2].forceActiveFocus()
    settle(app)
    colours = []
    for role in ROLES:
        opacity = ", 90 percent opacity" if role == "background" else ""
        colours += [f"{NAMES[role]} colour, custom, #{CUSTOM[role][-6:]}{opacity}", f"Reset {NAMES[role]} colour"]
    assert tab_order(app, window) == [
        "Layout C, Techno / HUD, selected", "Layout D, Signal strip", "Layout E, Ring",
        "Panel size, 125 percent", "Reset the panel size to 100 percent",
        "Text size, 110 percent", "Reset the text size to 100 percent", "Font, Made Up Sans",
        *colours,
        "Presets for the Background colour, #f28b82", "Background colour as hex, #282a36",
        "Background opacity, 90 percent", "Close the colour editor",
        "Reset to defaults", "Close", "Show model and session time", "Layout A, Refined list", "Layout B, Tiles"]
    find(window, "isFontButton").forceActiveFocus()
    key(app, window, Qt.Key.Key_Return)  # the list of fonts opens (and the editor closes): its field is the next stop
    assert focused(window) == "Filter the fonts, 4 of 4" and not editor(window).isVisible()
    key(app, window, Qt.Key.Key_Tab)
    assert focused(window) == colours[0]
    key(app, window, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
    key(app, window, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
    assert focused(window) == "Font, Made Up Sans"


def test_the_close_control_works_with_the_keyboard(app, shown):
    window, backend, messages = shown
    close = find(window, "isClose")
    close.forceActiveFocus()
    settle(app)
    assert focused(window) == "Close" and sum(1 for r in items(window, "isFocusRing") if r.isVisible()) == 1
    key(app, window, Qt.Key.Key_Space)
    assert not window.isVisible()


# ----- a low screen -----

def test_on_a_screen_of_768_pixels_the_sections_scroll_and_the_header_and_the_footer_stay(app, fake_client, state_path):
    messages = []
    previous = qInstallMessageHandler(lambda mode, context, text: messages.append(text))
    window, backend, warnings, engine = make(app, fake_client, state_path, room=768)
    try:
        scroller, thumb = find(window, "isScroller"), find(window, "isScrollThumb")
        assert window.height() <= 768 - 80 and window.minimumHeight() == window.maximumHeight() == window.height()
        assert not scroller.property("scrolls") and not thumb.isVisible()  # the closed sections fit
        click(app, window, find(window, "isFontButton"))
        assert window.height() == 768 - 80 and scroller.property("scrolls") and thumb.isVisible()
        assert in_window(window, find(window, "isFontList"))  # what opened is on the screen
        key(app, window, Qt.Key.Key_Escape)
        backend.setFontScale(1.4)
        settle(app)
        click(app, window, swatch(window, "background"))
        assert window.height() == 768 - 80 and scroller.property("scrolls")
        top = scroller.mapToScene(QPointF(0, 0)).y()
        visible = lambda item: (item.mapRectToScene(item.boundingRect()).top() >= top - 0.5
                                and item.mapRectToScene(item.boundingRect()).bottom() <= top + scroller.height() + 0.5)
        assert visible(editor(window)) and scroller.property("contentY") > 0
        # The header, the close control and the footer with "Reset to defaults" do not scroll.
        for name in ("isHeader", "isClose", "isFooter", "isResetAll", "isTitle"):
            assert in_window(window, find(window, name)), name
        assert find(window, "isHeader").mapToScene(QPointF(0, 0)).y() == 0
        assert find(window, "isFooter").mapRectToScene(find(window, "isFooter").boundingRect()).bottom() == window.height()
        # The Tab key brings each control on the screen.
        cards(window)[2].forceActiveFocus()
        settle(app)
        assert visible(cards(window)[2]) and scroller.property("contentY") < 60
        seen = [focused(window)]
        for _ in range(40):
            key(app, window, Qt.Key.Key_Tab)
            item = window.activeFocusItem()
            inside = scroller in [p for p in parents(item)]
            assert not inside or visible(item), focused(window)
            assert in_window(window, item), focused(window)
            seen.append(focused(window))
            if focused(window) == "Close":
                break
        assert "Close the colour editor" in seen and seen[-1] == "Close"
        # The wheel scrolls the sections: one step of a mouse wheel is 60 pixels.
        def turn(angle):
            place = QPointF(centre(find(window, "sliderFor", "scale")))
            app.sendEvent(window, QWheelEvent(place, place, QPoint(0, 0), QPoint(0, angle), Qt.MouseButton.NoButton,
                                              NONE, Qt.ScrollPhase.NoScrollPhase, False))
            settle(app)

        assert scroller.property("contentY") > 0
        for _ in range(30):
            turn(120)
        assert scroller.property("contentY") == 0
        turn(-120)
        assert scroller.property("contentY") == 60 and thumb.y() > scroller.y() + 3
        for _ in range(30):
            turn(-120)
        assert scroller.property("contentY") == scroller.property("contentHeight") - scroller.height()
        assert text_findings(window) == []
        backend._look_timer.stop()
    finally:
        shiboken6.delete(engine)
        app.processEvents()
        qInstallMessageHandler(previous)
    assert [m for m in messages + warnings if SIZE_HINTS_NOTE not in m] == []


def drag(app, window, start, end, steps=10, release=True):
    """A pointer with its button down from `start` to `end`, in small steps."""
    QTest.mousePress(window, LEFT, NONE, start)
    settle(app)
    for n in range(1, steps + 1):
        QTest.mouseMove(window, start + (end - start) * n / steps)
        settle(app)
    if release:
        QTest.mouseRelease(window, LEFT, NONE, end)
        settle(app)


def test_on_a_low_screen_a_pointer_or_a_finger_scrolls_the_sections_and_a_slider_does_not(
        app, fake_client, state_path):
    messages = []
    previous = qInstallMessageHandler(lambda mode, context, text: messages.append(text))
    window, backend, warnings, engine = make(app, fake_client, state_path, room=768)
    try:
        backend.setFontScale(1.4)
        settle(app)
        click(app, window, swatch(window, "background"))  # the editor with its opacity slider: a long column
        scroller, thumb, grip = find(window, "isScroller"), find(window, "isScrollThumb"), find(window, "isScrollGrip")
        scroller.setProperty("contentY", 0)
        settle(app)
        lowest = scroller.property("contentHeight") - scroller.height()
        assert scroller.property("scrolls") and thumb.isVisible() and lowest > 150
        contentY = lambda: scroller.property("contentY")
        # The thumb stays thin; the place that takes the pointer is wider.
        assert thumb.width() == 3 and grip.width() >= 16 and grip.height() >= thumb.height()
        # A drag on the thumb, a little at the left of its line: the sections follow the thumb.
        top = thumb.y()
        start = thumb.mapToScene(QPointF(-5, thumb.height() / 2)).toPoint()
        drag(app, window, start, start + QPoint(0, 40))
        assert abs(thumb.y() - (top + 40)) <= 1 and contentY() > 0
        drag(app, window, start + QPoint(0, 40), QPoint(start.x(), window.height() - 2))  # past the end: no further
        assert contentY() == lowest
        # A drag of the sections themselves (the empty room at their left), as a pen or a mouse with no wheel.
        # Measured while the button is down: the release starts a flick, an animation of the clock, so a measure
        # after the release depends on the speed of the computer.
        place = scroller.mapToScene(QPointF(window.property("pad") / 2, scroller.height() / 2)).toPoint()
        moved = []
        QTest.mousePress(window, LEFT, NONE, place)
        settle(app)
        for n in range(1, 11):
            QTest.mouseMove(window, place + QPoint(0, 12 * n))
            settle(app)
            moved.append(lowest - contentY())
        # The drag starts within two steps (the drag distance of the system), then the sections follow the pointer.
        assert [round(b - a, 3) for a, b in zip(moved[2:], moved[3:])] == [12] * 7 and moved[-1] >= 120 - 24
        QTest.mouseRelease(window, LEFT, NONE, place + QPoint(0, 120))
        settle(app)
        assert contentY() <= lowest - moved[-1]  # the release does not take the sections back
        # A finger that moves up: the sections move with it.
        scroller.setProperty("contentY", 0)
        settle(app)
        finger = QTest.createTouchDevice()
        QTest.touchEvent(window, finger).press(0, place, window).commit()
        settle(app)
        for n in range(1, 13):
            QTest.touchEvent(window, finger).move(0, place - QPoint(0, 10 * n), window).commit()
            settle(app)
        QTest.touchEvent(window, finger).release(0, place - QPoint(0, 120), window).commit()
        settle(app)
        assert contentY() >= 80  # 120 px less the distance before a touch becomes a drag
        # A slider drag that goes a little down too moves the slider and does not scroll.
        scroller.setProperty("contentY", 40)
        settle(app)
        slider = find(window, "sliderFor", "scale")
        drag(app, window, point_for(slider, 1.0), point_for(slider, 1.5) + QPoint(0, 30))
        assert backend.scale == 1.5 and contentY() == 40
        assert text_findings(window) == []
        backend._look_timer.stop()
    finally:
        shiboken6.delete(engine)
        app.processEvents()
        qInstallMessageHandler(previous)
    assert [m for m in messages + warnings if SIZE_HINTS_NOTE not in m] == []


def parents(item):
    while item is not None:
        yield item
        item = item.parentItem()


# ----- every layout as the style of the window -----

def open_everything(app, window, backend):
    click(app, window, swatch(window, "background"))
    backend.setColor("background", "#cc1f2a44")
    settle(app)


@pytest.mark.parametrize("scale", [0.8, 1.0, 1.4])
@pytest.mark.parametrize("letter", LETTERS)
def test_the_controls_load_in_the_style_of_each_layout_and_every_text_has_its_room(app, shown, letter, scale):
    window, backend, messages = shown
    backend.setLayout(letter)
    backend.setFontScale(scale)
    settle(app)
    assert window.property("theme").metaObject().className().startswith(f"{letter}Theme")
    assert len(items(window, "isSlider")) == 3 and len([i for i in walk(window.contentItem()) if i.property("swatchFor")]) == 8
    assert window.width() == 1076 and window.height() <= 1000 and text_findings(window) == []
    theme = window.property("theme")
    fill = next(i for i in walk(find(window, "sliderFor", "scale")) if i.property("isSliderFill"))
    assert fill.property("color") == theme.property("accentColor")
    assert swatch(window, "text").property("radius") == theme.property("itemRadius")
    families = {t.property("font").family() for t in walk(window.contentItem()) if t.inherits("QQuickText") and t.isVisible()}
    assert families == {theme.property("fontFamily")}
    # With the editor open (the background, with its opacity), and with a message in it.
    open_everything(app, window, backend)
    assert editor(window).isVisible() and text_findings(window) == []
    click(app, window, find(window, "isHexField"))
    replace_text(app, window, "nothing")
    assert find(window, "isHexMessage").isVisible() and text_findings(window) == []
    # With the list of fonts open, a filter, and "Reset to defaults" armed (its longest label).
    click(app, window, find(window, "isFontButton"))
    type_text(app, window, "m")
    assert len(font_rows(window)) == 4 and text_findings(window) == []
    click(app, window, find(window, "isResetAll"))
    assert window.property("resetArmed") and text_findings(window) == []
    assert window.height() <= 1000


@pytest.mark.parametrize("letter", LETTERS)
def test_the_controls_follow_the_custom_look_at_once(app, shown, letter):
    window, backend, messages = shown
    backend.setLayout(letter)
    settle(app)
    slider = find(window, "sliderFor", "fontScale")
    fill = next(i for i in walk(slider) if i.property("isSliderFill"))
    handle = next(i for i in walk(slider) if i.property("isSliderHandle"))
    label = next(t for t in walk(swatch(window, "accent")) if t.inherits("QQuickText"))
    before = label.property("font").pixelSize()
    backend.setColor("accent", "#ff00ff"), backend.setColor("text", "#00ffff"), backend.setColor("frame", "#ffff00")
    backend.setFontScale(1.4), backend.setFontFamily("Made Up Sans")
    settle(app)
    assert fill.property("color").name() == "#ff00ff" and handle.property("color").name() == "#00ffff"
    assert label.property("color").name() == "#00ffff" and label.property("font").family() == "Made Up Sans"
    assert label.property("font").pixelSize() == round(before * 1.4 + 0.001)
    assert str(js(swatch(window, "accent"), "border.color.toString()")) == "#ffff00"
    image = window.grabWindow()
    assert image.pixelColor(centre(fill)).name() == "#ff00ff"
    assert text_findings(window) == []


# ----- a look that cannot be read: two controls stay usable -----

def luminance(colour):
    parts = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
             for c in (colour.redF(), colour.greenF(), colour.blueF())]
    return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]


def contrast(one, other):
    a, b = luminance(one), luminance(other)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


@pytest.mark.parametrize("colour", ["#202124", "#ffffff", "#808080", "#ff0000"])
@pytest.mark.parametrize("letter", LETTERS)
def test_with_the_text_in_the_colour_of_the_panel_the_close_control_and_reset_can_still_be_read(
        app, shown, letter, colour):
    window, backend, messages = shown
    backend.setLayout(letter)
    for role in ("background", "text", "frame", "accent"):
        backend.setColor(role, colour)
    backend.setColor("background", "#1a" + colour[1:])  # and almost no opacity
    settle(app)
    image = window.grabWindow()
    reset, close = find(window, "isResetAll"), find(window, "isClose")
    assert reset.isEnabled() and in_window(window, reset) and in_window(window, close)
    for control in (reset, close):
        box = control.mapRectToScene(control.boundingRect()).toRect()
        plate = image.pixelColor(box.left() + 3, box.top() + box.height() // 2)
        assert plate.alpha() == 255 and plate.name() == colour  # a solid plate: what is behind the window does not matter
        inked = sum(1 for x in range(box.left() + 2, box.right() - 1) for y in range(box.top() + 2, box.bottom() - 1)
                    if contrast(image.pixelColor(x, y), plate) >= 3)
        assert inked >= 12, (control.property("isClose"), inked)
    # The two controls work: one look that can be read again is two clicks away.
    click(app, window, reset)
    click(app, window, reset)
    assert not backend.lookIsCustom
    click(app, window, close)
    assert not window.isVisible()


@pytest.mark.parametrize("letter", LETTERS)
def test_the_close_control_has_a_plate_only_when_its_marks_need_one(app, shown, letter):
    window, backend, messages = shown
    backend.setLayout(letter)
    settle(app)
    close = find(window, "isClose")

    def plate_and_header():
        """The colour inside the close control at its left, and the colour of the header just at its left."""
        image = window.grabWindow()
        box = close.mapRectToScene(close.boundingRect()).toRect()
        middle = box.top() + box.height() // 2
        argb = QColor.NameFormat.HexArgb
        return image.pixelColor(box.left() + 3, middle).name(argb), image.pixelColor(box.left() - 4, middle).name(argb)

    inside, outside = plate_and_header()
    assert inside == outside  # the designs: the header of before
    assert close.property("plated") is False
    backend.setColor("text", "#ffffff"), backend.setColor("background", "#808080")  # only the dim mark needs it
    settle(app)
    inside, outside = plate_and_header()
    assert close.property("plated") and inside == "#ff808080" != outside
    backend.setColor("background", "#1a000000")  # white can be read on black, but the panel shows the desktop
    settle(app)
    assert close.property("plated")
    backend.resetLook()
    settle(app)
    assert not close.property("plated")


def test_the_ink_of_the_two_controls_is_the_text_colour_while_it_can_be_read(app, shown):
    window, backend, messages = shown
    theme = window.property("theme")
    assert window.property("safeInk") == theme.property("textColor")  # the design: nothing changes
    marks = items(window, "isCloseMark")
    assert len(marks) == 2 and {m.property("color").name() for m in marks} == {theme.property("dimColor").name()}
    backend.setColor("text", "#101010")  # dark on the dark panel
    settle(app)
    assert window.property("safeInk").name() == "#f1f3f4" and {m.property("color").name() for m in marks} == {"#f1f3f4"}
    backend.setColor("background", "#fafafa")  # dark on light can be read: the colour of the user
    settle(app)
    assert window.property("safeInk").name() == "#101010"
    backend.setColor("text", "#ffffff"), backend.setColor("background", "#808080")
    settle(app)
    # White can be read on grey (3.95:1), the dim mark (white at 62 %) cannot: the idle mark has the ink.
    assert window.property("safeInk").name() == "#ffffff"
    assert {m.property("color").name() for m in marks} == {"#202124"}


# ----- the options window and the panel in one program -----

needs_layershell = pytest.mark.skipif(not LAYERSHELL_QMLDIR.is_file(), reason="org.kde.layershell is not installed")


@pytest.fixture
def both(app, fake_client, state_path):
    """Yield (options window, panel window, backend): the two windows in one engine, as in the program."""
    backend = Backend(fake_client, settings_path=state_path, skins=built_skins(), families=FAMILIES)
    hold_the_save(backend)
    messages = []
    previous = qInstallMessageHandler(lambda mode, context, text: messages.append(text))
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda errors: messages.extend(e.toString() for e in errors))
    engine.rootContext().setContextProperty("backend", backend)
    engine.addImportPath(str(IMPORT_PATH))
    engine.load(LAYER_QML)
    try:
        (panel,) = engine.rootObjects()
        backend.apply([Agent("t1", "blocked", "rev", "Main"), Agent("t2", "working", "ana", "api / 1")])
        options = wide_options(engine)
        options.open()
        settle(app)
        window = engine.rootObjects()[1]
        window.setProperty("roomHeight", 1080)
        settle(app)
        yield window, panel, backend
        backend._look_timer.stop()
    finally:
        shiboken6.delete(engine)
        app.processEvents()
        qInstallMessageHandler(previous)
    assert [m for m in messages if SIZE_HINTS_NOTE not in m and OFFSCREEN_NOTE not in m] == []


@needs_layershell
def test_the_size_slider_changes_the_surface_of_the_panel_and_not_the_options_window(app, both):
    window, panel, backend = both
    slider = find(window, "sliderFor", "scale")
    size, own = (panel.width(), panel.height()), (window.width(), window.height())
    sizes = []
    panel.widthChanged.connect(lambda *_: sizes.append(panel.width()))
    QTest.mousePress(window, LEFT, NONE, point_for(slider, 1.5))
    settle(app)
    assert (panel.width(), panel.height()) == (size[0] * 1.5, size[1] * 1.5)  # while the button is down
    QTest.mouseMove(window, point_for(slider, 2.0))
    settle(app)
    QTest.mouseRelease(window, LEFT, NONE, point_for(slider, 2.0))
    settle(app)
    assert (panel.width(), panel.height()) == (size[0] * 2, size[1] * 2) and sizes == [size[0] * 1.5, size[0] * 2]
    assert (window.width(), window.height()) == own
    slider.forceActiveFocus()
    key(app, window, Qt.Key.Key_Home)
    assert panel.width() == size[0] * 0.75
    click(app, window, find(window, "resetFor", "scale"))
    assert (panel.width(), panel.height()) == size


@needs_layershell
def test_a_colour_of_the_editor_changes_the_panel_and_reset_gives_its_pixels_back(app, both, state_path):
    window, panel, backend = both
    before = panel.grabWindow()
    frame = next(i for i in walk(panel.contentItem()) if i.property("color") == window.property("theme").property("panelColor")
                 and i.width() == panel.width())
    click(app, window, swatch(window, "background"))
    click(app, window, preset(window, "#3c4043"))
    assert frame.property("color").name() == "#3c4043"
    assert panel.grabWindow().pixelColor(panel.width() // 2, panel.height() - 6).name() == "#3c4043"
    click(app, window, swatch(window, "blocked"))
    click(app, window, find(window, "isHexField"))
    replace_text(app, window, "#ff00ff")
    assert panel.property("panel").property("stateColors")["blocked"] == "#ff00ff"
    click(app, window, find(window, "sliderFor", "fontScale"))
    find(window, "sliderFor", "fontScale").forceActiveFocus()
    key(app, window, Qt.Key.Key_End)
    find(window, "sliderFor", "scale").forceActiveFocus()
    key(app, window, Qt.Key.Key_End)
    click(app, window, find(window, "isFontButton"))
    type_text(app, window, "serif")
    key(app, window, Qt.Key.Key_Return)
    for _ in range(4):
        settle(app)
    assert backend.fontFamily == "Plain Serif" and panel.width() > before.width() * 1.9
    assert panel.grabWindow() != before
    click(app, window, find(window, "isResetAll"))
    click(app, window, find(window, "isResetAll"))
    for _ in range(6):
        settle(app)
    assert panel.grabWindow() == before  # the panel of the design, pixel for pixel
    fire(backend)
    assert saved(state_path) is None  # nothing was saved on the way, and a reset to nothing makes no file


# ----- what the window must take without a problem -----

def test_the_window_opens_with_every_value_custom_a_font_that_is_gone_and_a_role_of_a_later_version(
        app, fake_client, state_path, caplog):
    start = {"layout": "B", "scale": 1.75, "fontScale": 1.3, "fontFamily": "A Font That Is Gone",
             "colors": {**CUSTOM, "sparkle": "#123456"}}
    state_path.write_text(json.dumps(start), encoding="utf-8")
    messages = []
    previous = qInstallMessageHandler(lambda mode, context, text: messages.append(text))
    window, backend, warnings, engine = make(app, fake_client, state_path)
    try:
        assert [r.getMessage() for r in caplog.records] == [
            "the saved custom look has values that cannot be used: colors, fontFamily"]
        assert find(window, "isFontName").property("text") == "Layout default"  # the font is gone: the default shows
        assert find(window, "valueFor", "scale").property("text") == "175 %"
        assert find(window, "valueFor", "fontScale").property("text") == "130 %"
        found = [i for i in walk(window.contentItem()) if i.property("swatchFor")]
        assert len(found) == 8 and all(s.property("custom") for s in found)  # no swatch for the unknown role
        assert find(window, "isResetAll").isEnabled() and text_findings(window) == []
        click(app, window, find(window, "isFontButton"))
        assert "A Font That Is Gone" not in font_rows(window)
        key(app, window, Qt.Key.Key_Escape)
        click(app, window, swatch(window, "idle"))
        click(app, window, preset(window, "#81c995"))
        fire(backend)
        # The change of one colour keeps what this version cannot use.
        assert saved(state_path) == {**start, "colors": {**CUSTOM, "sparkle": "#123456", "idle": "#81c995"}}
    finally:
        backend._look_timer.stop()
        shiboken6.delete(engine)
        app.processEvents()
        qInstallMessageHandler(previous)
    assert [m for m in messages + warnings if SIZE_HINTS_NOTE not in m] == []


def test_a_change_of_the_layout_keeps_the_editor_open_with_the_colour_of_the_new_layout(app, shown):
    window, backend, messages = shown
    click(app, window, swatch(window, "text"))
    field = find(window, "isHexField")
    assert field.property("text") == "#e3e9ee"  # the text colour of Layout C
    place = centre(swatch(window, "text"))
    click(app, window, cards(window)[0])  # Layout A, with the editor open
    assert backend.layout == "A" and editor(window).isVisible() and window.property("editingRole") == "text"
    assert field.property("text") == "#e8eaed" and centre(swatch(window, "text")) == place
    assert spoken(swatch(window, "text")) == "Text colour, default, #e8eaed"
    click(app, window, preset(window, "#fdd663"))
    click(app, window, cards(window)[4])
    assert backend.layout == "E" and field.property("text") == "#fdd663" and backend.colorOverrides == {"text": "#fdd663"}
    assert window.property("theme").metaObject().className().startswith("ETheme") and text_findings(window) == []


# The components of the two windows, the options window, the answer window, and the "Answer" control of an agent row
# (it is drawn in the panel, with the theme of a skin as `tokens`).
CONTROL_FILES = sorted((layouts.UI_PATH / "controls").glob("*.qml")) + [
    layouts.UI_PATH / "Options.qml", layouts.UI_PATH / "Answer.qml", layouts.UI_PATH / "AnswerControl.qml"]
# What a text size of a control may be made of, after the rule of the skins (tests/test_look_qml.py): a theme token
# (`theme.bodySize`), or a size of the design through the font scale (`theme.size(10)`). Two forms on top of it:
# a token one pixel larger (`theme.smallSize + 1`: it keeps the font scale of the token), and the smaller of two
# such sizes (`Math.min(a, b)`), or one of two by a flag of the control (`button.small ? a : b`).
SIZE = r"(?:\w+\.)?(?:theme|tokens)\.(?:\w+Size(?:\s*\+\s*1)?|size\(\d+\))"
SIZE_FORMS = [rf"{SIZE}", rf"Math\.min\({SIZE},\s*{SIZE}\)", rf"\w+\.\w+\s*\?\s*{SIZE}\s*:\s*{SIZE}"]


def test_no_control_file_has_a_text_size_or_a_look_of_qt_quick_controls():
    assert len(CONTROL_FILES) == 16
    for file in CONTROL_FILES:
        text = file.read_text(encoding="utf-8")
        assert "QtQuick.Controls" not in text, file.name
        uses = re.findall(r"\bpixelSize\b\s*(:?)\s*([^\n;}]*)", text)
        for colon, value in uses:
            assert colon == ":", f"{file.name}: pixelSize is set in a different way: {value!r}"
            assert any(re.fullmatch(form, value.strip()) for form in SIZE_FORMS), f"{file.name}: pixelSize: {value}"
        assert "pointSize" not in text, file.name
    # The limits and the steps of the three sliders are those of the backend, not numbers of the window.
    text = (layouts.UI_PATH / "Options.qml").read_text(encoding="utf-8")
    for member in ("scaleMin", "scaleMax", "scaleStep", "scaleDefault", "fontScaleMin", "fontScaleMax",
                   "fontScaleStep", "fontScaleDefault", "opacityMin", "opacityMax", "opacityStep", "fontFamilies",
                   "colorRoles", "lookIsCustom"):
        assert f"backend.{member}" in text, member
    for file in CONTROL_FILES:
        assert not re.search(r"^\s*(from|to|step|defaultValue):\s*[\d.]", file.read_text(encoding="utf-8"), re.M), file.name


# The colours that a control file may state, each with its reason. Every other colour comes from the theme.
COLOUR_LITERALS = {
    "ColorEditor.qml": {"#000000": "the value of `colour` before the caller binds it",
                        "#8ab4f8": "the example in the text of the hint (\"Use a colour like #8ab4f8\")"},
    "ColorSwatch.qml": {"#000000": "the value of `colour` before the caller binds it"},
    "LayoutCard.qml": {"#0b0e11": "`tagInk`: the dark ink of the tag on the accent (inkOn picks light on a dark accent)",
                       "#05070a": "the plate under the preview picture (the pictures are drawn for it)"},
    "Options.qml": {"#000000": "a colour for a swatch and the editor while backend.colors has no value for a role"},
}


def test_no_control_file_has_a_colour_of_its_own_except_the_presets_and_the_documented_ones():
    for file in CONTROL_FILES:
        text = file.read_text(encoding="utf-8")
        if file.name == "ColorEditor.qml":  # the palette: 16 presets, its purpose
            (palette,) = re.findall(r"presets: \[([^\]]*)\]", text)
            assert len(re.findall(r'"#[0-9a-f]{6}"', palette)) == 16
            text = text.replace(palette, "")
        found = re.findall(r"#[0-9a-fA-F]{3,8}\b", text)
        assert sorted(set(found)) == sorted(COLOUR_LITERALS.get(file.name, {})), file.name
        assert len(found) == (2 if file.name == "Options.qml" else len(set(found))), (file.name, found)
        named = {word for word in re.findall(r'"([A-Za-z]+)"', text) if QColor.isValidColorName(word)}
        assert named <= {"transparent"}, (file.name, named)  # a name of a colour ("white") is a colour too
        for red, green, blue in re.findall(r"Qt\.rgba\(([^,]+),([^,]+),([^,]+),", text):  # a token with an opacity
            assert [red.strip()[-2:], green.strip()[-2:], blue.strip()[-2:]] == [".r", ".g", ".b"], (file.name, red)
        assert not re.search(r"Qt\.(hsla|hsva|hsl|hsv)\(", text), file.name


# ----- task 26: the setting "Show model and session time" -----

def meta_row(window):
    return find(window, "isCheckRow")


def check_state(item):
    """What a screen reader gets of a check row: (role, name, checked, the actions)."""
    interface = QAccessible.queryAccessibleInterface(item)
    return (interface.role(), interface.text(QAccessible.Text.Name), bool(interface.state().checked),
            bool(interface.state().checkable), bool(interface.state().focusable))


def test_the_setting_of_the_model_line_is_in_the_layout_section_and_a_click_changes_and_saves_it(app, shown, state_path):
    window, backend, messages = shown
    row = meta_row(window)
    title = next(i for i in walk(window.contentItem()) if i.property("text") == "Layout" and i.isVisible())
    assert row.isVisible() and row.property("name") == "showMeta" and row.property("checked") is True
    middle = row.mapToScene(QPointF(0, row.height() / 2)).y()
    assert abs(middle - title.mapToScene(QPointF(0, title.height() / 2)).y()) <= 1  # in the line of the title
    assert check_state(row) == (QAccessible.Role.CheckBox, "Show model and session time", True, True, True)
    assert text_findings(window) == []
    click(app, window, row)
    assert backend.showMeta is False and row.property("checked") is False
    assert check_state(row)[2] is False and focused(window) == "Show model and session time"
    assert json.loads(state_path.read_text(encoding="utf-8")).get("showMeta") is False
    for which in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):  # the keys change it too
        before = backend.showMeta
        key(app, window, which)
        assert backend.showMeta is (not before) and row.property("checked") is backend.showMeta
    assert backend.showMeta is True and "showMeta" not in json.loads(state_path.read_text(encoding="utf-8"))
    actions = QAccessible.queryAccessibleInterface(row).actionInterface()
    assert "Toggle" in actions.actionNames()
    actions.doAction("Toggle")  # a screen reader changes it
    settle(app)
    assert backend.showMeta is False and json.loads(state_path.read_text(encoding="utf-8"))["showMeta"] is False


def test_the_setting_of_the_model_line_shows_the_saved_value_when_the_window_opens(app, shown):
    window, backend, messages = shown
    backend.setShowMeta(False)
    settle(app)
    assert meta_row(window).property("checked") is False and check_state(meta_row(window))[2] is False
    backend.setShowMeta(True)
    settle(app)
    assert meta_row(window).property("checked") is True


@pytest.mark.parametrize("letter", LETTERS)
@pytest.mark.parametrize("scale", [0.8, 1.4])
def test_the_setting_of_the_model_line_has_its_room_in_each_theme_and_text_size(app, shown, letter, scale):
    window, backend, messages = shown
    backend.setLayout(letter)
    backend.setFontScale(scale)
    settle(app)
    row = meta_row(window)
    assert text_findings(window) == []
    right = row.mapToScene(QPointF(row.width(), 0)).x()
    assert right <= window.width() - 20 and row.mapToScene(QPointF(0, 0)).y() >= 44  # below the header
    box = next(i for i in walk(row) if i.property("isCheckBox"))
    assert box.width() == box.height() >= 16


# ----- a narrow screen: the window fits, the cards wrap, the sections are one below the other -----

# The free width → the cards in a row, and Size | Text side by side (None: by the text size: they need room for
# their labels and values, which grow with the text).
NARROW = {1024: (4, None), 800: (3, False), 640: (2, False)}


def right_edges_inside(window):
    """Each visible item of the window ends inside it (no part is cut at the right)."""
    found = []
    for item in walk(window.contentItem()):
        if not item.isVisible() or item.width() <= 0 or item.property("isScroller") or item.property("isFrame"):
            continue
        if item.property("layoutId") or item.property("swatchFor") or item.property("sliderFor") \
                or item.property("isFontButton") or item.property("isResetAll") or item.property("isColourEditor") \
                or item.property("isEditorClose") or item.property("isHexField") or item.property("isOpacitySlider"):
            box = item.mapRectToScene(item.boundingRect())
            if box.left() < -0.5 or box.right() > window.width() + 0.5:
                found.append(f"{item.metaObject().className()} {box.left():.0f}..{box.right():.0f}")
    return found


def rows_of_cards(window):
    rows = {}
    for card in cards(window):
        rows.setdefault(round(card.mapToScene(QPointF(0, 0)).y()), []).append(card.property("layoutId"))
    return [rows[y] for y in sorted(rows)]


@pytest.mark.parametrize("scale", [0.8, 1.4])
@pytest.mark.parametrize("room", NARROW)
@pytest.mark.parametrize("letter", LETTERS)
def test_on_a_narrow_screen_the_window_fits_its_cards_wrap_and_every_text_has_its_room(app, shown, letter, room, scale):
    window, backend, messages = shown
    window.setProperty("roomWidth", room)
    window.setProperty("roomHeight", 3000)  # all of it in the window: each control can be clicked (the scroll of a
    backend.setLayout(letter)               # low screen has tests of its own)
    backend.setFontScale(scale)
    settle(app)
    per_row, two_columns = NARROW[room]
    assert window.width() == room - 32 and not find(window, "isScroller").property("scrolls")
    assert [len(row) for row in rows_of_cards(window)] == {4: [4, 1], 3: [3, 2], 2: [2, 2, 1]}[per_row]
    assert [card for row in rows_of_cards(window) for card in row] == list("ABCDE")
    size, text = find(window, "sliderFor", "scale"), find(window, "sliderFor", "fontScale")
    side_by_side = abs(size.mapToScene(QPointF(0, 0)).y() - text.mapToScene(QPointF(0, 0)).y()) < 1
    assert side_by_side is window.property("twoColumns") is (two_columns if two_columns is not None else scale < 1.4)
    assert right_edges_inside(window) == [] and text_findings(window) == []
    # The colour editor of the background (with its opacity), with a message, then the list of fonts.
    open_everything(app, window, backend)
    assert editor(window).isVisible() and right_edges_inside(window) == [] and text_findings(window) == []
    click(app, window, find(window, "isHexField"))
    replace_text(app, window, "nothing")
    assert find(window, "isHexMessage").isVisible() and text_findings(window) == []
    click(app, window, find(window, "isFontButton"))
    type_text(app, window, "m")
    assert len(font_rows(window)) == 4 and right_edges_inside(window) == [] and text_findings(window) == []
    click(app, window, find(window, "isResetAll"))
    assert window.property("resetArmed") and right_edges_inside(window) == [] and text_findings(window) == []


def test_on_a_narrow_screen_the_tab_key_goes_through_the_cards_in_the_order_that_they_show(app, shown):
    window, backend, messages = shown
    window.setProperty("roomWidth", 640)
    settle(app)
    order = []
    cards(window)[0].forceActiveFocus()
    settle(app)
    for _ in range(5):
        focused = window.activeFocusItem()
        order.append((focused.property("layoutId"), focused.mapToScene(QPointF(0, 0))))
        key(app, window, Qt.Key.Key_Tab)
    assert [name for name, _ in order] == list("ABCDE")
    places = [(round(point.y()), point.x()) for _, point in order]
    assert places == sorted(places)  # row by row, and from the left in a row


def test_a_screen_with_room_gives_the_window_of_five_cards_in_one_row(app, shown):
    window, backend, messages = shown
    for room in (1920, 1108):
        window.setProperty("roomWidth", room)
        settle(app)
        assert window.width() == 1076 and [len(row) for row in rows_of_cards(window)] == [5]
    window.setProperty("roomWidth", 1107)
    settle(app)
    assert window.width() == 1075 and [len(row) for row in rows_of_cards(window)] == [4, 1]


def test_the_window_takes_the_free_width_of_its_screen_before_it_shows_and_stays_inside_it(app, fake_client, state_path):
    """The program (options.py), not a test: the free part of the screen of the test is 800 px wide."""
    from bellwether.options import Options
    backend = Backend(fake_client, settings_path=state_path, skins=built_skins())
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    previous = qInstallMessageHandler(lambda mode, context, text: None)
    try:
        Options(engine).open()
        settle(app)
        window = engine.rootObjects()[0]
        free = window.screen().availableGeometry()
        assert window.property("roomWidth") == free.width() == 800 and window.width() == 768
        assert free.contains(window.frameGeometry())
    finally:
        shiboken6.delete(engine)
        app.processEvents()
        qInstallMessageHandler(previous)


def test_a_window_that_the_system_put_partly_outside_its_screen_comes_inside_it(app):
    from PySide6.QtGui import QWindow
    from bellwether.options import keep_on_screen
    window = QWindow()
    window.setGeometry(500, 600, 600, 300)  # the screen of the test is 800 × 800
    keep_on_screen(window)
    assert (window.x(), window.y()) == (200, 500)
    window.setGeometry(10, 20, 600, 300)
    keep_on_screen(window)
    assert (window.x(), window.y()) == (10, 20)  # inside: no move
    window.setGeometry(0, 0, 1000, 300)
    keep_on_screen(window)
    assert (window.x(), window.y()) == (0, 0)  # wider than the screen: its left edge stays on it


# ----- the first open on a narrow screen starts at the top (review of P4, I1) -----

def fitted_options(engine, width, height):
    """The options object of the program on a screen whose free part is `width` × `height` (given before each
    show, as options.py gives the room of the real screen)."""
    from bellwether.options import Options

    class Fitted(Options):
        def fit_screen(self):
            self._window.setProperty("roomWidth", width)
            self._window.setProperty("roomHeight", height)
            return self._window.screen()

    return Fitted(engine)


def first_title_shows(window):
    scroller = find(window, "isScroller")
    title = next(i for i in walk(window.contentItem()) if i.property("isSectionTitle"))
    top = title.mapToItem(scroller, QPointF(0, 0)).y()
    return scroller.property("contentY") == 0 and 0 <= top and top + title.height() <= scroller.height()


@pytest.mark.parametrize("width, height", [(1024, 768), (800, 720), (640, 720)])
def test_the_first_and_a_later_open_on_a_narrow_low_screen_start_at_the_top(app, fake_client, state_path, width, height):
    backend = Backend(fake_client, settings_path=state_path, skins=built_skins())
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    previous = qInstallMessageHandler(lambda mode, context, text: None)
    try:
        options = fitted_options(engine, width, height)
        options.open()
        settle(app)
        window = engine.rootObjects()[0]
        assert window.width() == width - 32 and find(window, "isScroller").property("scrolls")
        assert first_title_shows(window)
        window.hide()
        settle(app)
        options.open()
        settle(app)
        assert first_title_shows(window)
    finally:
        shiboken6.delete(engine)
        app.processEvents()
        qInstallMessageHandler(previous)


# ----- the options and the answer window: clear of the panel when the screen has room (review of P4, m8) -----

@pytest.mark.parametrize("frame, free, avoid, lower, wanted", [
    ((300, 0, 400, 300), (0, 0, 800, 800), None, None, (300, 0, 300)),  # no panel: only inside the free area
    ((500, 600, 400, 300), (0, 0, 800, 800), None, None, (400, 500, 300)),
    ((300, 0, 400, 300), (0, 0, 800, 800), (480, 16, 300, 192), None, (64, 0, 300)),  # left of the panel
    ((100, 0, 600, 300), (0, 0, 800, 800), (480, 16, 300, 192), None, (100, 224, 300)),  # no room at its left: below
    ((0, 0, 992, 680), (0, 0, 1024, 720), (688, 16, 320, 192), None, (0, 0, 680)),  # a 1024 px screen: no side
    ((0, 0, 992, 680), (0, 0, 1024, 720), (688, 16, 320, 192), 240, (0, 224, 496)),  # …lower, below the panel
    ((0, 0, 992, 680), (0, 0, 1024, 400), (688, 16, 320, 192), 240, (0, 0, 680)),  # no room below for 240 either
    ((20, 20, 300, 200), (0, 0, 1024, 720), (688, 16, 320, 192), None, (20, 20, 200)),  # clear already: no move
    ((2700, 0, 400, 300), (1920, 0, 1280, 720), (2864, 16, 320, 192), None, (2448, 0, 300)),  # a screen not at 0
    ((900, 0, 400, 300), (1920, 0, 1280, 720), (2864, 16, 320, 192), None, (1920, 0, 300)),  # onto it: clear
])
def test_a_window_goes_inside_its_screen_and_clear_of_the_panel_when_there_is_room(frame, free, avoid, lower, wanted):
    from bellwether.options import clear_place
    assert clear_place(frame, free, avoid, min_height=lower) == wanted


class ScreenDouble:
    """A screen of made-up size for the placement (the screen of the off-screen platform is 800 × 800)."""

    def __init__(self, width, height, free_height):
        from PySide6.QtCore import QRect
        self._whole, self._free = QRect(0, 0, width, height), QRect(0, 0, width, free_height)

    def geometry(self):
        return self._whole

    def availableGeometry(self):
        return self._free


class PanelDouble:
    def __init__(self, screen, box=(688, 16, 320, 192)):
        from PySide6.QtCore import QRect
        self._screen, self._box = screen, QRect(*box)

    def isVisible(self):
        return True

    def screen(self):
        return self._screen

    def frameGeometry(self):
        return self._box


def test_on_a_1024_px_screen_the_options_window_goes_below_the_panel_and_its_close_control_is_clear(
        app, fake_client, state_path):
    """The runner's screen of 1024 × 768 (free 1024 × 720) with the panel at its default corner: the real
    keep_on_screen of the program on the real options window."""
    from bellwether import options as options_module
    screen = ScreenDouble(1024, 768, 720)
    backend = Backend(fake_client, settings_path=state_path, skins=built_skins())
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    previous = qInstallMessageHandler(lambda mode, context, text: None)
    try:
        options = fitted_options(engine, 1024, 768)
        options.open()
        settle(app)
        window = engine.rootObjects()[0]
        window.setPosition(0, 0)
        settle(app)
        window.screen = lambda: screen  # this window is on the made-up screen
        options_module.keep_on_screen(window, PanelDouble(screen), lower=True)
        settle(app)
        assert window.frameGeometry().height() == 496 and window.frameGeometry().y() == 224
        corner = find(window, "isClose").mapToScene(QPointF(0, 0))
        assert window.y() + corner.y() > 16 + 192  # the close control is below the panel
        assert first_title_shows(window) and find(window, "isScroller").property("scrolls")
        options_module.keep_on_screen(window, PanelDouble(screen), lower=False)  # the answer window: never lower
        settle(app)
        assert window.frameGeometry().height() == 496
    finally:
        shiboken6.delete(engine)
        app.processEvents()
        qInstallMessageHandler(previous)


class WindowDouble:
    """A window of the program for the glue of options.py and answer.py: it records each call."""

    def __init__(self, screen):
        self.calls, self.properties, self.visible, self._screen = [], {}, False, screen
        self.visibleChanged = SimpleNamespace(connect=lambda slot: None)
        self.screen_slots = []
        self.screenChanged = SimpleNamespace(connect=self.screen_slots.append)

    def __getattr__(self, name):
        if name in ("show", "hide", "requestActivate", "raise_", "installEventFilter"):
            return lambda *args: self.calls.append((name, *args)) or (setattr(self, "visible", name == "show")
                                                                       if name in ("show", "hide") else None)
        raise AttributeError(name)

    def setScreen(self, screen):
        self.calls.append(("setScreen", screen))
        self._screen = screen

    def screen(self):
        return self._screen

    def setProperty(self, name, value):
        self.calls.append(("setProperty", name, value))
        self.properties[name] = value

    def property(self, name):
        return self.properties.get(name)

    def isVisible(self):
        return self.visible

    def isActive(self):
        return False

    def frameGeometry(self):
        from PySide6.QtCore import QRect
        return QRect(0, 0, 100, 100)

    def x(self):
        return 0

    def y(self):
        return 0

    def height(self):
        return 100

    def setPosition(self, x, y):
        self.calls.append(("setPosition", x, y))


class EngineDouble:
    """An engine whose `load` adds the window double after the panel."""

    def __init__(self, panel, window):
        self._roots, self._window = [panel], window

    def rootObjects(self):
        return list(self._roots)

    def load(self, source):
        self._roots.append(self._window)


def panel_double(screen):
    panel = PanelDouble(screen)
    panel.property = lambda name: {"posX": 10, "screenName": "B"}.get(name)
    return panel


def test_the_options_window_opens_on_the_screen_of_the_panel_with_the_room_of_that_screen(app):
    """Mutations M7 (no reset of roomHeight) and M8 (no setScreen) of the final review fail here."""
    from bellwether.options import Options
    first, second = ScreenDouble(800, 600, 560), ScreenDouble(1920, 1080, 1040)
    window = WindowDouble(first)
    options = Options(EngineDouble(panel_double(second), window))
    options.open()
    names = [call[0] for call in window.calls]
    assert names.index("setScreen") < names.index("show") and ("setScreen", second) in window.calls
    assert window.properties["roomWidth"] == 1920 and window.properties["roomHeight"] == 1080
    window.properties["roomHeight"] = 400  # lowered below the panel at the last show
    window.calls.clear()
    options.open()
    assert ("setProperty", "roomHeight", 1080) in window.calls  # given back before the next show
    assert names.count("setScreen") == 1 and [c[0] for c in window.calls].count("setScreen") == 0  # first show only


def test_on_wayland_the_window_takes_the_room_of_the_screen_that_the_compositor_tells_after_the_show(app, monkeypatch):
    """Review F2: before the show Qt knows only the primary screen (or the last one)."""
    from bellwether import options as options_module
    from bellwether.options import Options
    monkeypatch.setattr(options_module, "can_place_windows", lambda: False)
    primary, wide = ScreenDouble(1024, 768, 768), ScreenDouble(2560, 1440, 1440)
    window = WindowDouble(primary)
    Options(EngineDouble(panel_double(wide), window)).open()
    assert window.properties["roomWidth"] == 1024
    window._screen = wide  # the compositor puts it on the wide monitor and Qt tells it
    for slot in window.screen_slots:
        slot(wide)
    assert window.properties["roomWidth"] == 2560 and window.properties["roomHeight"] == 1440
    window.hide()
    for slot in window.screen_slots:
        slot(primary)  # a hidden window: nothing
    assert window.properties["roomWidth"] == 2560


def test_the_place_and_the_lower_height_come_before_the_show(app):
    """Review F6: on a small screen the first frame is already lower, below the panel (no full height first)."""
    from bellwether.options import Options
    small = ScreenDouble(1024, 768, 720)
    window = WindowDouble(small)
    window.frameGeometry = lambda: __import__("PySide6.QtCore", fromlist=["QRect"]).QRect(0, 0, 992, 688)
    window.height = lambda: 688
    Options(EngineDouble(panel_double(small), window)).open()
    names = [call[0] if call[0] != "setProperty" else f"setProperty {call[1]}" for call in window.calls]
    show = names.index("show")
    assert "setPosition" in names[:show]
    lowered = [call for call in window.calls[:show] if call[:2] == ("setProperty", "roomHeight")]
    assert lowered[-1][2] == 496 + 80  # 720 - (16 + 192 + 16) = 496 px high, given before the show


def test_the_answer_window_opens_on_the_screen_of_the_panel(app, monkeypatch):
    from bellwether.answer import Answer
    second = ScreenDouble(1920, 1080, 1040)
    window = WindowDouble(ScreenDouble(800, 600, 560))
    backend = SimpleNamespace(answerRequested=SimpleNamespace(connect=lambda slot: None))
    Answer(EngineDouble(panel_double(second), window), backend).open()
    names = [call[0] for call in window.calls]
    assert ("setScreen", second) in window.calls and names.index("setScreen") < names.index("show")


def test_where_the_compositor_places_windows_the_dialogs_get_no_screen_and_no_move(app, monkeypatch):
    from bellwether import options as options_module
    from bellwether.options import Options
    monkeypatch.setattr(options_module, "can_place_windows", lambda: False)
    window = WindowDouble(ScreenDouble(800, 600, 560))
    Options(EngineDouble(panel_double(ScreenDouble(1920, 1080, 1040)), window)).open()
    assert not [call for call in window.calls if call[0] in ("setScreen", "setPosition")]
    assert window.properties["roomWidth"] == 800  # the room of the screen that Qt knows


def test_the_rule_moves_a_real_window_and_leaves_it_where_the_window_system_places_windows(app, monkeypatch):
    from PySide6.QtGui import QWindow
    from bellwether import options as options_module
    panel, window = QWindow(), QWindow()
    panel.setGeometry(480, 16, 300, 192)
    panel.show()
    window.setGeometry(300, 0, 400, 300)
    try:
        options_module.keep_on_screen(window, panel)
        frame = window.frameGeometry()
        assert frame.x() + frame.width() + 16 == panel.frameGeometry().x() and frame.y() == 0  # 16 px left of it
        window.setGeometry(300, 0, 400, 300)
        monkeypatch.setattr(options_module, "can_place_windows", lambda: False)  # Wayland: the compositor places
        options_module.keep_on_screen(window, panel)
        assert (window.x(), window.y()) == (300, 0)
    finally:
        panel.destroy()
        window.destroy()


def test_the_panel_of_an_engine_is_its_window_with_a_place():
    from types import SimpleNamespace
    from bellwether.options import panel_of
    options = SimpleNamespace(property=lambda name: None)
    panel = SimpleNamespace(property=lambda name: {"posX": 5, "screenName": "A"}.get(name))
    assert panel_of(SimpleNamespace(rootObjects=lambda: [options, panel])) is panel
    assert panel_of(SimpleNamespace(rootObjects=lambda: [options])) is None
