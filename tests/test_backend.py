import logging
import threading
import time

import pytest

from herdr_float.backend import Backend
from herdr_float.client import HerdrError, HerdrOffline
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
    assert backend.groups[0]["agents"] == [{"key": "t1", "name": "rev", "workspace": "Main"}]
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
