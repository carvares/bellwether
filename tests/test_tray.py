from herdr_float.state import STATES
from herdr_float.tray import STATE_COLORS, tooltip_text


def counters(**counts):
    return [{"state": s, "count": counts.get(s, 0), "attention": s in ("blocked", "done")} for s in STATES]


def test_every_state_and_offline_and_none_has_a_colour():
    assert set(STATE_COLORS) == set(STATES) | {"offline", "none"}


def test_tooltip_lists_the_counts_in_the_priority_order():
    assert tooltip_text(False, counters()) == "Herdr Float: offline"
    assert tooltip_text(True, counters(blocked=1, idle=2, working=3)) == (
        "Herdr Float: 1 blocked, 0 done, 2 idle, 3 working"
    )


class FakeIcon:
    def setIcon(self, icon):
        pass

    def setToolTip(self, text):
        self.tooltip = text


def test_the_tray_dot_has_the_colour_of_the_top_state_of_the_backend(app, fake_client, tmp_path, monkeypatch):
    from herdr_float import tray
    from herdr_float.backend import Backend
    from herdr_float.state import Agent

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
    assert item._icon.tooltip == "Herdr Float: 1 blocked, 1 done, 0 idle, 0 working"


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

    from herdr_float import tray
    from herdr_float.backend import Backend
    from herdr_float.state import Agent

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
    assert item._icon.tooltips[-1] == "Herdr Float: 0 blocked, 1 done, 0 idle, 1 working"


def test_a_tray_loads_the_app_icon_one_time(app, fake_client, tmp_path, monkeypatch):
    from PySide6.QtGui import QWindow

    from herdr_float import appicon, tray
    from herdr_float.backend import Backend
    from herdr_float.state import Agent

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
