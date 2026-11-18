import logging
import threading
import time

import pytest

from herdr_float.backend import Backend
from herdr_float.client import HerdrError, HerdrOffline
from herdr_float.icons import Icons
from herdr_float.state import Agent


@pytest.fixture
def backend(app, fake_client, tmp_path):
    return Backend(fake_client, settings_path=tmp_path / "state.json")


def test_starts_offline_with_four_zero_counters(backend):
    assert backend.online is False
    assert [c["state"] for c in backend.counters] == ["blocked", "done", "working", "idle"]
    assert all(c["count"] == 0 for c in backend.counters)
    assert [g["agents"] for g in backend.groups] == [[], [], [], []]


def test_groups_hold_the_four_states_in_order_with_their_agents(backend):
    backend.apply([
        Agent("t1", "blocked", "rev", "Main"),
        Agent("t3", "working", "ana", "api / 1"),
        Agent("t2", "working", "bob", ""),
    ])
    assert [(g["state"], g["label"], g["count"], g["attention"]) for g in backend.groups] == [
        ("blocked", "Blocked", 1, True),
        ("done", "Done", 0, True),
        ("working", "Working", 2, False),
        ("idle", "Idle", 0, False),
    ]
    assert backend.groups[0]["agents"] == [{
        "key": "t1", "icon": "", "label": "rev", "detail": "Main", "address": "", "spoken": "Go to rev in Main",
    }]
    assert [a["key"] for a in backend.groups[2]["agents"]] == ["t3", "t2"]


def test_apply_snapshot_sets_counters_and_groups(backend):
    seen = []
    backend.changed.connect(lambda: seen.append(1))
    backend.apply([Agent("t1", "blocked", "rev", "Main"), Agent("t2", "idle", "dev", "Main")])
    assert backend.online is True
    assert {c["state"]: c["count"] for c in backend.counters} == {
        "blocked": 1, "done": 0, "working": 0, "idle": 1,
    }
    assert [g["count"] for g in backend.groups] == [1, 0, 0, 1]
    assert seen == [1]


def test_attention_flag_is_only_for_blocked_and_done(backend):
    assert {c["state"] for c in backend.counters if c["attention"]} == {"blocked", "done"}


def test_apply_none_goes_offline_and_clears(backend):
    backend.apply([Agent("t1", "working", "a", "Main")])
    backend.apply(None)
    assert backend.online is False
    assert all(g["count"] == 0 and g["agents"] == [] for g in backend.groups)
    assert all(c["count"] == 0 for c in backend.counters)


def test_same_snapshot_twice_emits_changed_one_time(backend):
    seen = []
    backend.changed.connect(lambda: seen.append(1))
    agents = [Agent("t1", "working", "a", "Main")]
    backend.apply(agents)
    backend.apply(list(agents))
    assert seen == [1]


def test_fetch_returns_agents_or_none(backend):
    backend._client.result = [Agent("t1", "done", "claude", "")]
    assert backend.fetch() == [Agent("t1", "done", "claude", "")]
    backend._client.list_error = HerdrOffline("no socket")
    assert backend.fetch() is None


def test_focus_calls_client(backend):
    backend.focus_now("t3")
    assert backend._client.focused == ["t3"]


def test_focus_error_emits_focus_failed(backend):
    failures = []
    backend.focusFailed.connect(lambda key, message: failures.append((key, message)))
    backend._client.focus_error = HerdrError("exit_1", "no agent")
    backend.focus_now("t3")
    assert failures == [("t3", "no agent")]
    backend._client.focus_error = HerdrOffline("gone")
    backend.focus_now("t4")
    assert failures[-1] == ("t4", "Herdr is offline")


def test_opening_names_the_agent_while_the_jump_runs(app, backend):
    seen = []
    backend.openingChanged.connect(lambda: seen.append(backend.opening))
    assert backend.opening == ""
    backend.focus_now("t3")
    assert backend.opening == ""
    gate = backend._client.focus_gate = threading.Event()
    backend.focus("t3")
    assert backend.opening == "t3"
    gate.set()
    assert wait_for(app, lambda: backend.opening == "")
    assert seen == ["t3", ""]


def test_a_click_while_a_jump_runs_is_ignored(app, backend):
    gate = backend._client.focus_gate = threading.Event()
    backend.focus("t1")
    backend.focus("t1")
    backend.focus("t2")
    app.processEvents()
    gate.set()
    assert wait_for(app, lambda: backend.opening == "")
    assert backend._client.focused == ["t1"]
    backend.focus("t2")
    assert wait_for(app, lambda: backend.opening == "")
    assert backend._client.focused == ["t1", "t2"]


def test_opening_ends_after_a_failed_jump(app, backend):
    failures = []
    backend.focusFailed.connect(lambda key, message: failures.append((key, message, backend.opening)))
    backend._client.focus_error = HerdrError("no_raise", "could not raise the window")
    backend.focus("t1")
    assert wait_for(app, lambda: backend.opening == "" and failures)
    assert failures == [("t1", "could not raise the window", "t1")]


def test_an_unexpected_error_in_a_jump_shows_a_fixed_message_and_logs_its_class_only(app, backend, caplog, capsys):
    caplog.set_level(logging.INFO, logger="herdr_float")
    failures = []
    backend.focusFailed.connect(lambda key, message: failures.append((key, message)))
    backend._client.focus_error = RuntimeError("text from a program")
    backend._wake.clear()
    backend.focus("t1")
    assert wait_for(app, lambda: backend.opening == "" and failures)
    assert failures == [("t1", "jump failed")]
    assert backend._wake.is_set()  # the next read starts at once
    assert [r.getMessage() for r in caplog.records] == ["focus failed agent=t1 error=RuntimeError"]
    assert "text from a program" not in caplog.text
    assert capsys.readouterr() == ("", "")  # no traceback on the terminal


def test_position_is_saved_and_loaded(app, fake_client, tmp_path):
    path = tmp_path / "state.json"
    first = Backend(fake_client, settings_path=path)
    assert (first.savedX, first.savedY) == (-1, -1)
    first.savePosition(300, 40)
    second = Backend(fake_client, settings_path=path)
    assert (second.savedX, second.savedY) == (300, 40)


def wait_for(app, condition, timeout=2.0):
    """Deliver Qt events until condition() is true. Return False on timeout."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.005)
    return False


def test_polling_continues_after_an_unexpected_error(app, fake_client, tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="herdr_float")
    backend = Backend(fake_client, interval=0.02, settings_path=tmp_path / "state.json")
    backend.start()
    try:
        assert wait_for(app, lambda: backend.online), "the first snapshot did not arrive"
        fake_client.list_error = RuntimeError("text from the server")
        assert wait_for(app, lambda: not backend.online), "an unexpected error did not set offline"
        time.sleep(0.1)  # several more failed cycles: the warning must stay one record
        assert backend._thread.is_alive()
        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings == ["snapshot failed: RuntimeError"]
        assert "text from the server" not in caplog.text
        fake_client.list_error = None
        assert wait_for(app, lambda: backend.online), "polling did not recover"
    finally:
        backend.stop()
    assert not backend._thread.is_alive()


GLYPH = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M2 2h20v20H2z"/></svg>'


@pytest.fixture
def with_icons(app, fake_client, tmp_path):
    """A backend that reads a made-up app folder with two icons: "pi" and the generic "agent"."""
    home = tmp_path / "app"
    (home / "icons").mkdir(parents=True)
    for name in ("pi", "agent"):
        (home / "icons" / f"{name}.svg").write_text(GLYPH)
    return Backend(fake_client, settings_path=tmp_path / "state.json", icons=Icons(home, tmp_path / "cache"))


def rows_of(backend, state):
    return next(g["agents"] for g in backend.groups if g["state"] == state)


def test_agent_row_with_an_icon_shows_the_name_or_else_the_workspace_and_no_program_word(with_icons):
    with_icons.apply([
        Agent("t1", "idle", "rev", "Main", "pi"),
        Agent("t2", "idle", "", "api / 1", "pi"),
        Agent("t3", "idle", "", "", "pi"),
    ])
    rows = {r["key"]: r for r in rows_of(with_icons, "idle")}
    assert all(r["icon"].startswith("file://") and r["icon"].endswith(".svg") for r in rows.values())
    assert (rows["t1"]["label"], rows["t1"]["detail"]) == ("rev", "Main")
    assert (rows["t2"]["label"], rows["t2"]["detail"]) == ("api / 1", "")
    assert (rows["t3"]["label"], rows["t3"]["detail"]) == ("t3", "")  # no name and no workspace: the address
    assert [r["address"] for r in rows.values()] == ["", "", ""]


def test_spoken_name_says_the_program_in_words(with_icons):
    with_icons.apply([
        Agent("t1", "idle", "rev", "Main", "pi"),
        Agent("t2", "idle", "", "Main", "pi"),
        Agent("t3", "idle", "", "", ""),
    ])
    assert sorted(r["spoken"] for r in rows_of(with_icons, "idle")) == [
        "Go to pi in Main", "Go to rev, pi in Main", "Go to t3",
    ]


def test_rows_that_look_the_same_get_the_address(with_icons):
    with_icons.apply([
        Agent("t1", "working", "", "Main", "pi"),
        Agent("t2", "working", "", "Main", "pi"),
        Agent("t3", "working", "", "Main", "codex"),  # the generic icon: a different picture, so no address
        Agent("t4", "working", "", "docs", "pi"),
        Agent("t5", "idle", "", "Main", "pi"),  # a different group
    ])
    assert {r["key"]: r["address"] for r in rows_of(with_icons, "working")} == {
        "t1": "t1", "t2": "t2", "t3": "", "t4": "",
    }
    assert rows_of(with_icons, "idle")[0]["address"] == ""


def test_a_program_without_an_icon_gets_the_generic_one(with_icons):
    with_icons.apply([Agent("t1", "idle", "", "Main", "codex"), Agent("t2", "idle", "", "Main", "")])
    assert [r["icon"].rsplit("/", 1)[1].split("-")[0] for r in rows_of(with_icons, "idle")] == ["agent", "agent"]


def test_without_icons_the_row_shows_the_text_as_before(backend):
    backend.apply([Agent("t1", "idle", "", "Main", "codex"), Agent("t2", "idle", "", "", "")])
    assert [(r["icon"], r["label"], r["detail"]) for r in rows_of(backend, "idle")] == [
        ("", "codex", "Main"), ("", "t2", ""),
    ]


def test_top_state_follows_the_priority_of_the_user(backend):
    assert backend.topState == "offline"
    backend.apply([])
    assert backend.topState == "none"
    backend.apply([Agent("t1", "idle", "a", ""), Agent("t2", "working", "b", ""), Agent("t3", "working", "c", "")])
    assert backend.topState == "idle"
    backend.apply([Agent("t1", "blocked", "a", ""), Agent("t2", "done", "b", "")])
    assert backend.topState == "blocked"
    backend.apply(None)
    assert backend.topState == "offline"


def test_rows_of_a_group_show_the_named_agents_first_and_then_the_others(with_icons):
    with_icons.apply([
        Agent("t1", "idle", "", "zeta", "pi"),  # no name: shows "zeta"
        Agent("t6", "idle", "zed", "alpha", "pi"),
        Agent("t3", "idle", "", "alpha", "claude-code"),  # no name: shows "alpha"
        Agent("t5", "idle", "", "", "pi"),  # no name: shows "t5"
        Agent("t2", "idle", "Mid", "alpha", "pi"),
        Agent("t4", "idle", "", "Beta", "pi"),  # no name: shows "Beta"
    ])
    assert [(r["key"], r["label"]) for r in rows_of(with_icons, "idle")] == [
        ("t2", "Mid"), ("t6", "zed"), ("t3", "alpha"), ("t4", "Beta"), ("t5", "t5"), ("t1", "zeta"),
    ]


def test_rows_with_the_same_text_are_in_the_natural_order_of_the_address(with_icons):
    with_icons.apply([
        Agent("t10", "idle", "", "api", "pi"),
        Agent("t2", "idle", "", "api", "pi"),
        Agent("t1b", "idle", "", "api", "pi"),
        Agent("t12", "idle", "rev", "api", "pi"),
        Agent("t9", "idle", "Rev", "api", "pi"),
        Agent("t1", "idle", "", "api", "pi"),
    ])
    rows = rows_of(with_icons, "idle")
    assert [r["key"] for r in rows] == ["t9", "t12", "t1", "t1b", "t2", "t10"]
    # The address shows on the rows that look the same, also after the sort.
    assert [r["address"] for r in rows] == ["", "", "t1", "t1b", "t2", "t10"]


def test_a_named_agent_is_first_also_without_icons(backend):
    backend.apply([Agent("t1", "idle", "", "a", "codex"), Agent("t2", "idle", "zoe", "a", "codex")])
    assert [r["label"] for r in rows_of(backend, "idle")] == ["zoe", "codex"]


def test_rows_without_icons_are_in_the_order_of_their_text(backend):
    backend.apply([Agent("t1", "idle", "", "a", "pi"), Agent("t2", "idle", "", "z", "codex"), Agent("t3", "idle", "bob", "", "")])
    assert [r["label"] for r in rows_of(backend, "idle")] == ["bob", "codex", "pi"]
