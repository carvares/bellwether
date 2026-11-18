"""The options window: the real Options.qml through the real Options object, off screen."""
import json
import time
from pathlib import Path

import pytest
import shiboken6
from PySide6.QtCore import QPoint, QPointF, Qt, QUrl, qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from bellwether.backend import Backend
from bellwether import layouts
from bellwether.layouts import built_skins
from bellwether.options import Options

# Layout C of the program, and the test skin in the place of design B: a second layout that can be chosen.
# A, D and E have no skin here: the window must show a design that is not built as "coming next".
SKINS = {"C": built_skins()["C"], "B": Path(__file__).parent / "skins" / "T.qml"}


def walk(item):
    yield item
    for child in item.childItems():
        yield from walk(child)


def settle(app):
    for _ in range(5):
        app.processEvents()
        time.sleep(0.01)


@pytest.fixture
def opened(app, fake_client, tmp_path):
    """Yield (options object, engine, backend, Qt messages). No panel: the options window does not need it."""
    backend = Backend(fake_client, settings_path=tmp_path / "state.json", skins=SKINS)
    messages = []
    previous = qInstallMessageHandler(lambda mode, context, text: messages.append(text))
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda errors: messages.extend(e.toString() for e in errors))
    engine.rootContext().setContextProperty("backend", backend)
    try:
        yield Options(engine), engine, backend, messages
    finally:
        # The engine goes before the backend that its bindings read. Not `del`: the options object of the test
        # holds the engine too.
        shiboken6.delete(engine)
        app.processEvents()
        qInstallMessageHandler(previous)


def cards(window):
    return [i for i in walk(window.contentItem()) if i.property("layoutId")]


def spoken(item):
    attached = next(c for c in item.children() if c.metaObject().className() == "QQuickAccessibleAttached")
    return attached.property("name")


def tags(window):
    return [next((t.property("text") for t in walk(tag) if t.property("text")), "")
            for tag in walk(window.contentItem()) if tag.property("isTag") and tag.isVisible()]


def click(app, window, item):
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint())
    settle(app)


def test_the_window_opens_one_time_and_a_second_open_shows_the_same_window(app, opened):
    options, engine, backend, messages = opened
    assert engine.rootObjects() == []  # not made before the first open
    options.open()
    settle(app)
    (window,) = engine.rootObjects()
    assert isinstance(window, QQuickWindow) and window.isVisible()
    assert window.title() == "Bellwether — Options"
    # A normal window (not a tool tip, not a layer surface) with no title bar of the system: it draws its own.
    assert window.flags() & Qt.WindowType.FramelessWindowHint and window.type() == Qt.WindowType.Window
    assert not window.flags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert window.minimumSize() == window.maximumSize() == window.size() and window.width() > 900
    options.open()
    settle(app)
    assert engine.rootObjects() == [window] and window.isVisible()
    window.close()  # the close button of the title bar
    settle(app)
    assert not window.isVisible()
    options.open()
    settle(app)
    assert engine.rootObjects() == [window] and window.isVisible()
    assert messages == []


def test_the_window_lists_the_five_designs_and_marks_the_selected_and_the_ones_to_come(app, opened):
    options, engine, backend, messages = opened
    options.open()
    settle(app)
    window = engine.rootObjects()[0]
    found = cards(window)
    assert [c.property("layoutId") for c in found] == ["A", "B", "C", "D", "E"]
    assert [spoken(c) for c in found] == [
        "Layout A, Refined list, coming next", "Layout B, Tiles", "Layout C, Techno / HUD, selected",
        "Layout D, Signal strip, coming next", "Layout E, Ring, coming next"]
    assert tags(window) == ["COMING NEXT", "SELECTED", "COMING NEXT", "COMING NEXT"]
    texts = [i.property("text") for i in walk(window.contentItem()) if i.property("text")]
    assert "C — Techno / HUD" in texts and "E — Ring" in texts and "Layout" in texts
    pictures = [i for i in walk(window.contentItem()) if i.property("isPreview")]
    assert len(pictures) == 5 and all(p.property("implicitWidth") == 360 for p in pictures)  # every picture loaded
    assert len({c.height() for c in found}) == 1 and found[-1].x() + found[-1].width() <= window.width()
    assert messages == []


def test_a_click_on_a_built_card_applies_and_saves_the_layout_and_a_card_to_come_does_nothing(app, opened, tmp_path):
    options, engine, backend, messages = opened
    options.open()
    settle(app)
    window = engine.rootObjects()[0]
    a, b, c, d, e = cards(window)
    told = []
    backend.layoutChanged.connect(lambda: told.append(backend.layout))
    click(app, window, a)
    click(app, window, e)
    assert told == [] and backend.layout == "C" and not (tmp_path / "state.json").exists()
    click(app, window, b)
    assert told == ["B"] and json.loads((tmp_path / "state.json").read_text()) == {"layout": "B"}
    assert spoken(b) == "Layout B, Tiles, selected" and spoken(c) == "Layout C, Techno / HUD"
    assert tags(window) == ["COMING NEXT", "SELECTED", "COMING NEXT", "COMING NEXT"]
    click(app, window, b)  # the selected card again: nothing to do
    assert told == ["B"] and window.isVisible()
    assert messages == []


def test_the_keyboard_moves_between_the_built_cards_selects_and_closes(app, opened):
    options, engine, backend, messages = opened
    options.open()
    settle(app)
    window = engine.rootObjects()[0]
    a, b, c, d, e = cards(window)

    def focused():
        return [card.property("layoutId") for card in (a, b, c, d, e) if card.property("activeFocus")]

    def rings():
        return sum(1 for i in walk(window.contentItem()) if i.property("isFocusRing") and i.isVisible())

    assert focused() == ["C"] and rings() == 1  # the selected card has the focus at the open
    QTest.keyClick(window, Qt.Key.Key_Tab)
    settle(app)
    assert focused() == ["B"]  # the cards to come are not in the tab order: after C the first built card
    QTest.keyClick(window, Qt.Key.Key_Space)
    settle(app)
    assert backend.layout == "B"
    QTest.keyClick(window, Qt.Key.Key_Tab)
    settle(app)
    assert focused() == ["C"]
    QTest.keyClick(window, Qt.Key.Key_Return)
    settle(app)
    assert backend.layout == "C"
    QTest.keyClick(window, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
    settle(app)
    assert focused() == ["B"]
    QTest.keyClick(window, Qt.Key.Key_Enter)
    settle(app)
    assert backend.layout == "B"
    QTest.keyClick(window, Qt.Key.Key_Escape)
    settle(app)
    assert not window.isVisible()
    options.open()  # the next open starts on the selected card again
    settle(app)
    assert window.isVisible() and focused() == ["B"]
    assert messages == []


def test_an_options_file_that_does_not_load_gives_one_log_line_and_no_window(app, fake_client, tmp_path, caplog):
    engine = QQmlApplicationEngine()
    previous = qInstallMessageHandler(lambda mode, context, text: None)
    try:
        options = Options(engine, tmp_path / "not-there.qml")
        options.open()
        options.open()
    finally:
        qInstallMessageHandler(previous)
    assert engine.rootObjects() == []
    assert [r.getMessage() for r in caplog.records] == ["the options window did not load"] * 2


# ----- the window in the style of the layout that shows -----

LETTERS = [letter for letter, _, _ in layouts.LAYOUTS]


def load_theme(path):
    """The token object of a theme file, with the engine that keeps it alive, and the errors."""
    engine = QQmlEngine()
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(path)))
    return component.create(), (engine, component), [e.toString() for e in component.errors()]


def missing_tokens(theme):
    names = {theme.metaObject().property(i).name() for i in range(theme.metaObject().propertyCount())}
    return [token for token in layouts.THEME_TOKENS if token not in names]


@pytest.mark.parametrize("letter", LETTERS)
def test_every_skin_has_a_theme_file_with_all_the_tokens(app, letter):
    skin = layouts.built_skins()[letter]
    theme, engine, errors = load_theme(layouts.theme_file(skin))
    assert errors == [] and theme is not None
    assert missing_tokens(theme) == []
    assert theme.property("panelColor").alpha() > 200 and theme.property("fontFamily")
    assert theme.property("frameWidth") >= 1 and 9 <= theme.property("smallSize") <= theme.property("titleSize") <= 16
    assert f"{letter}Theme {{" in skin.read_text()  # the skin uses its own tokens


def test_a_theme_file_that_forgets_a_token_is_found(app, tmp_path):
    text = layouts.theme_file(layouts.built_skins()["A"]).read_text()
    lines = [line for line in text.splitlines() if "hoverColor" not in line and "readonly property int radius" not in line]
    (tmp_path / "ZTheme.qml").write_text("\n".join(lines))
    theme, engine, errors = load_theme(tmp_path / "ZTheme.qml")
    assert errors == [] and missing_tokens(theme) == ["radius", "hoverColor"]


def test_the_theme_of_the_backend_is_the_file_next_to_the_skin_or_the_one_of_the_default_layout(app, fake_client, tmp_path):
    real = built_skins()
    backend = Backend(fake_client, settings_path=tmp_path / "state.json", skins={**real, "T": SKINS["B"]})
    told = []
    backend.layoutChanged.connect(lambda: told.append(backend.themeSource.fileName()))
    assert backend.themeSource == QUrl.fromLocalFile(str(real["C"].with_name("CTheme.qml")))
    for letter in "ABDET":
        backend.setLayout(letter)
    assert told == ["ATheme.qml", "BTheme.qml", "DTheme.qml", "ETheme.qml", "CTheme.qml"]  # T has no theme file
    assert Backend(fake_client, settings_path=tmp_path / "none.json", skins={"C": Path("/skins/C.qml")}).themeSource == QUrl()


@pytest.fixture
def real_options(app, fake_client, tmp_path):
    """Yield (window, backend, Qt messages): the options window with the five real skins. After: no QML warning."""
    backend = Backend(fake_client, settings_path=tmp_path / "state.json", skins=built_skins())
    messages = []
    previous = qInstallMessageHandler(lambda mode, context, text: messages.append(text))
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda errors: messages.extend(e.toString() for e in errors))
    engine.rootContext().setContextProperty("backend", backend)
    try:
        options = Options(engine)
        options.open()
        settle(app)
        yield engine.rootObjects()[0], backend, messages
        assert len(engine.rootObjects()) == 1  # the same window in every step: it is never made again
    finally:
        shiboken6.delete(engine)
        app.processEvents()
        qInstallMessageHandler(previous)
    assert messages == []


def named(window, name):
    return next(i for i in walk(window.contentItem()) if i.property(name))


def look(window):
    """The values of the window that come from the theme tokens."""
    frame, title = named(window, "isFrame"), named(window, "isTitle")
    font = title.property("font")
    return {
        "panel": frame.property("color").name(), "radius": frame.property("radius"),
        "family": font.family(), "size": font.pixelSize(), "upper": font.capitalization() == font.Capitalization.AllUppercase,
        "ink": title.property("color").name(), "card radius": cards(window)[0].property("radius"),
    }


def frame_pixel(window):
    return window.grabWindow().pixelColor(window.width() // 2, 0).name()


@pytest.mark.parametrize("letter", LETTERS)
def test_the_window_has_the_style_of_each_layout_and_all_five_cards_can_be_chosen(app, real_options, letter):
    window, backend, messages = real_options
    backend.setLayout(letter)
    settle(app)
    theme, engine, errors = load_theme(layouts.theme_file(built_skins()[letter]))
    assert window.property("theme").metaObject().className().startswith(f"{letter}Theme")
    assert look(window) == {
        "panel": theme.property("panelColor").name(), "radius": theme.property("radius"),
        "family": theme.property("fontFamily"), "size": theme.property("titleSize"),
        "upper": theme.property("uppercaseTitles"), "ink": theme.property("dimColor").name(),
        "card radius": theme.property("itemRadius"),
    }
    # The frame has the neutral colour of the layout, never the colour of a status.
    assert frame_pixel(window) == theme.property("frameColor").name()
    assert window.color().alpha() == 0  # round corners stay clean
    assert tags(window) == ["SELECTED"]  # no card is "coming next"
    assert [spoken(c) for c in cards(window)] == [
        f"Layout {l}, {name}" + (", selected" if l == letter else "") for l, name, _ in layouts.LAYOUTS]
    assert all(c.property("built") and c.property("activeFocusOnTab") for c in cards(window))
    pictures = [i for i in walk(window.contentItem()) if i.property("isPreview")]
    assert len(pictures) == 5 and all(p.property("implicitWidth") == 360 for p in pictures)
    assert window.width() == 1076 and 300 <= window.height() <= 400
    assert sum(1 for i in walk(window.contentItem()) if i.property("isFocusRing") and i.isVisible()) == 1


def test_the_window_of_layout_c_has_the_corner_brackets_in_the_neutral_colour(app, real_options):
    window, backend, messages = real_options
    image = window.grabWindow()
    right, bottom = image.width() - 1, image.height() - 1
    corners = [(0, 0), (13, 1), (1, 13), (right, 0), (right - 13, 1), (0, bottom), (1, bottom - 13), (right, bottom)]
    assert [image.pixelColor(x, y).name() for x, y in corners] == ["#6b747d"] * 8
    assert image.pixelColor(14, 0).name() == "#2b333b"  # the thin line of the frame between the brackets
    assert named(window, "isTitle").property("text") == "Bellwether — Options"  # shown in capitals by the font
    backend.setLayout("A")  # a layout with no ornament: a round frame
    settle(app)
    image = window.grabWindow()
    assert image.pixelColor(0, 0).alpha() == 0 and image.pixelColor(13, 1).name() != "#6b747d"


def test_a_click_on_a_card_changes_the_style_and_the_cards_stay_where_they_are(app, real_options, tmp_path):
    window, backend, messages = real_options
    place = lambda: [(c.mapToScene(QPointF(0, 0)).x(), c.mapToScene(QPointF(0, 0)).y(), c.width(), c.height()) for c in cards(window)]
    first, size, origin, looks = place(), window.size(), window.position(), {"C": look(window)}
    for letter in "ABDEC":
        card = next(c for c in cards(window) if c.property("layoutId") == letter)
        click(app, window, card)
        assert backend.layout == letter and json.loads((tmp_path / "state.json").read_text()) == {"layout": letter}
        assert place() == first and window.size() == size and window.position() == origin and window.isVisible()
        assert card.property("selected") and card.property("activeFocus")
        looks[letter] = look(window)
        click(app, window, card)  # a second click at the same place: the same card, nothing changes
        assert backend.layout == letter
    assert looks["C"]["upper"] and not looks["A"]["upper"] and looks["C"]["family"] != looks["A"]["family"]
    assert [looks[l]["radius"] for l in "ABCDE"] == [14, 16, 0, 14, 16]
    assert len({(v["panel"], v["radius"], v["card radius"], v["size"]) for v in looks.values()}) == 5  # five looks


def test_the_keyboard_reaches_all_five_cards_and_selects(app, real_options):
    window, backend, messages = real_options
    focused = lambda: [c.property("layoutId") for c in cards(window) if c.property("activeFocus")]
    assert focused() == ["C"]
    seen = []
    for key in (Qt.Key.Key_Return, Qt.Key.Key_Space, Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Space):
        QTest.keyClick(window, Qt.Key.Key_Tab)
        settle(app)
        QTest.keyClick(window, key)
        settle(app)
        seen.append((focused(), backend.layout))
    assert seen == [(["D"], "D"), (["E"], "E"), (["A"], "A"), (["B"], "B"), (["C"], "C")]


def test_a_press_in_the_header_that_moves_6_px_asks_the_compositor_to_move_the_window(app, real_options):
    window, backend, messages = real_options
    asked = []
    window.systemMoveRequested.connect(lambda: asked.append(1))
    left, none = Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    start = QPoint(300, 20)
    QTest.mouseClick(window, left, none, start)  # a click is not a move
    settle(app)
    QTest.mouseMove(window, start + QPoint(40, 0))  # a move with no button is not a move of the window
    QTest.mouseMove(window, start)
    QTest.mousePress(window, left, none, start)
    QTest.mouseMove(window, start + QPoint(3, 2))
    settle(app)
    assert asked == []  # less than 6 px
    QTest.mouseMove(window, start + QPoint(5, 3))
    settle(app)
    assert asked == [1]
    QTest.mouseMove(window, start + QPoint(30, 12))  # one request for one drag
    QTest.mouseRelease(window, left, none, start + QPoint(30, 12))
    settle(app)
    assert asked == [1] and window.isVisible()
    card = cards(window)[1]  # a drag that starts on a card moves nothing
    point = card.mapToScene(QPointF(50, 50)).toPoint()
    QTest.mousePress(window, left, none, point)
    QTest.mouseMove(window, point + QPoint(30, 0))
    QTest.mouseRelease(window, left, none, point + QPoint(30, 0))
    settle(app)
    assert asked == [1]


def test_esc_and_the_close_control_hide_the_window_and_it_opens_again(app, real_options):
    window, backend, messages = real_options
    close = named(window, "isClose")
    assert spoken(close) == "Close" and close.x() + close.width() <= window.width() - 8
    click(app, window, close)
    assert not window.isVisible()
    window.show()
    settle(app)
    assert window.isVisible()
    QTest.keyClick(window, Qt.Key.Key_Escape)
    settle(app)
    assert not window.isVisible()
    window.show()
    settle(app)
    assert window.isVisible() and [c.property("layoutId") for c in cards(window) if c.property("activeFocus")] == ["C"]
