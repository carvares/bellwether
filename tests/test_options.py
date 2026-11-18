"""The options window: the real Options.qml through the real Options object, off screen."""
import json
import time
from pathlib import Path

import pytest
import shiboken6
from PySide6.QtCore import QPointF, Qt, qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from bellwether.backend import Backend
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
    assert not window.flags() & Qt.WindowType.FramelessWindowHint  # a normal window with a title bar
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
    pictures = [i for i in walk(window.contentItem()) if i.property("source")]
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
