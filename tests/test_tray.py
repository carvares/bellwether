from bellwether.state import STATES
from bellwether.tray import STATE_COLORS, tooltip_text


def counters(**counts):
    return [{"state": s, "count": counts.get(s, 0), "attention": s in ("blocked", "done")} for s in STATES]


def test_every_state_and_offline_and_none_has_a_colour():
    assert set(STATE_COLORS) == set(STATES) | {"offline", "none"}


def test_tooltip_lists_the_counts_in_the_priority_order():
    assert tooltip_text(False, counters()) == "Bellwether: offline"
    assert tooltip_text(True, counters(blocked=1, idle=2, working=3)) == (
        "Bellwether: 1 blocked, 0 done, 2 idle, 3 working"
    )


class FakeIcon:
    def setIcon(self, icon):
        pass

    def setToolTip(self, text):
        self.tooltip = text


def test_the_tray_dot_has_the_colour_of_the_top_state_of_the_backend(app, fake_client, tmp_path, monkeypatch):
    from bellwether import tray
    from bellwether.backend import Backend
    from bellwether.state import Agent

    backend = Backend(fake_client, settings_path=tmp_path / "state.json")
    made = []
    monkeypatch.setattr(tray, "make_icon", lambda color: made.append(color))
    item = tray.Tray.__new__(tray.Tray)  # no real tray item: only refresh() runs
    item._backend, item._shown_state, item._icon = backend, None, FakeIcon()
    item._icons = tray.TrayIcons(None)  # no Herdr app icon: the circle
    item.refresh()
    backend.apply([Agent("t1", "idle", "a", ""), Agent("t2", "working", "b", ""), Agent("t3", "working", "c", "")])
    item.refresh()
    backend.apply([Agent("t1", "blocked", "a", ""), Agent("t2", "done", "b", "")])
    item.refresh()
    assert made == [STATE_COLORS["offline"], STATE_COLORS["idle"], STATE_COLORS["blocked"]]
    assert item._icon.tooltip == "Bellwether: 1 blocked, 1 done, 0 idle, 0 working"


class CountingIcon:
    def __init__(self):
        self.icons, self.tooltips = [], []

    def setIcon(self, icon):
        self.icons.append(icon)

    def setToolTip(self, text):
        self.tooltips.append(text)


def test_refresh_with_a_real_icon_sets_the_icon_only_when_the_top_state_changes(app, fake_client, tmp_path):
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QImage, QPainter

    from bellwether import tray
    from bellwether.backend import Backend
    from bellwether.state import Agent

    source = QImage(64, 64, QImage.Format.Format_ARGB32)
    source.fill(Qt.GlobalColor.transparent)
    painter = QPainter(source)
    painter.fillRect(QRect(16, 16, 32, 32), QColor("#303438"))
    painter.end()
    backend = Backend(fake_client, settings_path=tmp_path / "state.json")
    item = tray.Tray.__new__(tray.Tray)
    item._backend, item._shown_state, item._icon = backend, None, CountingIcon()
    item._icons = tray.TrayIcons(source)
    item.refresh()  # offline
    item.refresh()
    backend.apply([Agent("t1", "working", "a", "")])
    item.refresh()
    backend.apply([Agent("t1", "working", "a", ""), Agent("t2", "working", "b", "")])  # the top state stays
    item.refresh()
    backend.apply([Agent("t1", "working", "a", ""), Agent("t2", "done", "b", "")])
    item.refresh()
    colours = [icon.pixmap(22).toImage().pixelColor(11, 11).name() for icon in item._icon.icons]
    assert colours == [STATE_COLORS["offline"], STATE_COLORS["working"], STATE_COLORS["done"]]
    assert len(item._icon.tooltips) == 5  # the text follows every change
    assert item._icon.tooltips[-1] == "Bellwether: 0 blocked, 1 done, 0 idle, 1 working"


def test_a_tray_loads_the_app_icon_one_time(app, fake_client, tmp_path, monkeypatch):
    from PySide6.QtGui import QWindow

    from bellwether import appicon, tray
    from bellwether.backend import Backend
    from bellwether.state import Agent

    calls = []
    monkeypatch.setattr(appicon, "load_app_icon", lambda *args: calls.append(args))  # no icon: the circle
    monkeypatch.setattr(tray.QSystemTrayIcon, "show", lambda self: None)  # no item in a real tray
    backend = Backend(fake_client, settings_path=tmp_path / "state.json")
    window = QWindow()
    item = tray.Tray(backend, window, app)
    backend.apply([Agent("t1", "working", "a", "")])
    backend.apply([Agent("t1", "blocked", "a", "")])
    backend.apply(None)
    item.refresh()
    assert len(calls) == 1
    backend.changed.disconnect(item.refresh)


def test_a_colour_that_cannot_be_drawn_gives_the_circle_and_one_log_line(app, monkeypatch, caplog):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    from bellwether import tray

    source = QImage(64, 64, QImage.Format.Format_ARGB32)
    source.fill(Qt.GlobalColor.transparent)
    for x in range(16, 48):
        for y in range(16, 48):
            source.setPixelColor(x, y, Qt.GlobalColor.black)
    icons = tray.TrayIcons(source)
    assert icons._shapes is not None

    def broken(shape, color):
        raise RuntimeError("text with /a/path")

    monkeypatch.setattr(tray, "tint", broken)
    circles = []
    monkeypatch.setattr(tray, "make_icon", lambda color: circles.append(color) or f"circle {color}")
    with caplog.at_level("INFO", logger="bellwether"):
        assert icons.icon("#f28b82") == "circle #f28b82"  # the start does not stop
        assert icons.icon("#81c995") == "circle #81c995"
        assert icons.icon("#f28b82") == "circle #f28b82"
    assert circles == ["#f28b82", "#81c995"]  # made one time for each colour
    assert [r.getMessage() for r in caplog.records] == [
        "the Herdr app icon cannot be used (RuntimeError): the tray icon is a circle"
    ]
    assert "/a/path" not in caplog.text


def make_tray(backend, window, tray_app, monkeypatch, options=None):
    from bellwether import appicon, tray

    monkeypatch.setattr(appicon, "load_app_icon", lambda *args: None)  # no icon: the circle
    monkeypatch.setattr(tray.QSystemTrayIcon, "show", lambda self: None)  # no item in a real tray
    return tray.Tray(backend, window, tray_app, options)


def test_the_menu_has_move_to_next_screen_only_with_more_than_one_screen(app, fake_client, tmp_path, monkeypatch):
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtGui import QWindow

    from bellwether.backend import Backend

    class FakeApp(QObject):
        screenAdded = Signal(object)
        screenRemoved = Signal(object)

        def __init__(self, count):
            super().__init__()
            self.count = count

        def screens(self):
            return [object()] * self.count

        def quit(self):
            pass

    def move_entries(item):
        return [a.text() for a in item._menu.actions() if a.isVisible() and a.text() == "Move to next screen"]

    backend = Backend(fake_client, settings_path=tmp_path / "state.json")
    fake_app = FakeApp(1)
    item = make_tray(backend, QWindow(), fake_app, monkeypatch)
    assert move_entries(item) == []
    assert [a.text() for a in item._menu.actions() if a.isVisible() and a.text()] == ["Show widget", "Quit"]  # the plain test window is not visible
    fake_app.count = 2
    fake_app.screenAdded.emit(None)  # a monitor is connected
    assert move_entries(item) == ["Move to next screen"]
    assert [a.text() for a in item._menu.actions() if a.isVisible() and a.text()] == [
        "Show widget", "Move to next screen", "Quit"]
    fake_app.count = 1
    fake_app.screenRemoved.emit(None)
    assert move_entries(item) == []
    backend.changed.disconnect(item.refresh)
    two = make_tray(backend, QWindow(), FakeApp(2), monkeypatch)
    assert move_entries(two) == ["Move to next screen"]
    backend.changed.disconnect(two.refresh)


def test_move_to_next_screen_asks_the_panel_to_move(app, fake_client, tmp_path, monkeypatch):
    from PySide6.QtCore import QObject, Signal, Slot

    from bellwether.backend import Backend

    class Panel(QObject):
        visibleChanged = Signal(bool)

        def __init__(self):
            super().__init__()
            self.moves = 0

        def isVisible(self):
            return True

        @Slot()
        def moveToNextScreen(self):
            self.moves += 1

    backend = Backend(fake_client, settings_path=tmp_path / "state.json")
    panel = Panel()
    item = make_tray(backend, panel, app, monkeypatch)
    item._move_action.trigger()
    assert panel.moves == 1
    backend.changed.disconnect(item.refresh)


def test_the_menu_has_options_above_hide_and_each_click_opens_the_options(app, fake_client, tmp_path, monkeypatch):
    from PySide6.QtGui import QWindow

    from bellwether.backend import Backend

    backend = Backend(fake_client, settings_path=tmp_path / "state.json")
    opens = []
    item = make_tray(backend, QWindow(), app, monkeypatch, lambda: opens.append(1))
    entries = [a.text() for a in item._menu.actions() if a.isVisible() and a.text()]
    assert entries[:2] == ["Options…", "Show widget"] and entries[-1] == "Quit"
    assert [e for e in entries[2:-1]] in ([], ["Move to next screen"])  # with the screens of the test session
    options = item._menu.actions()[0]
    options.trigger()
    options.trigger()
    assert opens == [1, 1]
    backend.changed.disconnect(item.refresh)
