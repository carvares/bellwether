from herdr_float.state import STATES
from herdr_float.tray import STATE_COLORS, tooltip_text, top_state


def counters(**counts):
    return [{"state": s, "count": counts.get(s, 0), "attention": s in ("blocked", "done")} for s in STATES]


def test_every_state_and_offline_and_none_has_a_colour():
    assert set(STATE_COLORS) == set(STATES) | {"offline", "none"}


def test_top_state_is_offline_when_not_online():
    assert top_state(False, counters(blocked=3)) == "offline"


def test_top_state_is_none_with_no_agents():
    assert top_state(True, counters()) == "none"


def test_top_state_follows_display_order():
    assert top_state(True, counters(idle=5, working=2)) == "working"
    assert top_state(True, counters(idle=5, done=1, working=2)) == "done"
    assert top_state(True, counters(idle=5, done=1, blocked=1)) == "blocked"


def test_tooltip_text():
    assert tooltip_text(False, counters()) == "Herdr Float: offline"
    assert tooltip_text(True, counters(blocked=1, idle=2)) == (
        "Herdr Float: 1 blocked, 0 done, 0 working, 2 idle"
    )
