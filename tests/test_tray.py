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
