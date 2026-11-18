import logging
import time

import pytest

from herdr_float.backend import Backend
from herdr_float.client import HerdrError, HerdrOffline
from herdr_float.state import Agent


@pytest.fixture
def backend(app, fake_client, tmp_path):
    return Backend(fake_client, settings_path=tmp_path / "state.json")


def test_starts_offline_with_five_zero_counters(backend):
    assert backend.online is False
    assert [c["state"] for c in backend.counters] == ["blocked", "done", "working", "idle", "unknown"]
    assert all(c["count"] == 0 for c in backend.counters)
    assert backend.agents == []


def test_apply_snapshot_sets_counters_and_agents(backend):
    seen = []
    backend.changed.connect(lambda: seen.append(1))
    backend.apply([Agent("w1:p1", "blocked", "rev", "w1"), Agent("w1:p2", "idle", "dev", "w1")])
    assert backend.online is True
    assert {c["state"]: c["count"] for c in backend.counters} == {
        "blocked": 1, "done": 0, "working": 0, "idle": 1, "unknown": 0,
    }
    assert backend.agents[0] == {"paneId": "w1:p1", "name": "rev", "status": "blocked", "workspace": "w1"}
    assert seen == [1]


def test_attention_flag_is_only_for_blocked_and_done(backend):
    assert {c["state"] for c in backend.counters if c["attention"]} == {"blocked", "done"}


def test_apply_none_goes_offline_and_clears(backend):
    backend.apply([Agent("w1:p1", "working", "a", "w1")])
    backend.apply(None)
    assert backend.online is False
    assert backend.agents == []
    assert all(c["count"] == 0 for c in backend.counters)


def test_same_snapshot_twice_emits_changed_one_time(backend):
    seen = []
    backend.changed.connect(lambda: seen.append(1))
    agents = [Agent("w1:p1", "working", "a", "w1")]
    backend.apply(agents)
    backend.apply(list(agents))
    assert seen == [1]


def test_fetch_returns_agents_or_none(backend):
    backend._client.result = {"agents": [{"pane_id": "w1:p1", "agent_status": "done", "agent": "claude"}]}
    assert backend.fetch() == [Agent("w1:p1", "done", "claude", "")]
    backend._client.list_error = HerdrOffline("no socket")
    assert backend.fetch() is None


def test_focus_calls_client(backend):
    backend.focus_now("w1:p3")
    assert backend._client.focused == ["w1:p3"]


def test_focus_error_emits_focus_failed(backend):
    failures = []
    backend.focusFailed.connect(lambda pane_id, message: failures.append((pane_id, message)))
    backend._client.focus_error = HerdrError("agent_not_found", "no agent")
    backend.focus_now("w1:p3")
    assert failures == [("w1:p3", "no agent")]
    backend._client.focus_error = HerdrOffline("gone")
    backend.focus_now("w1:p4")
    assert failures[-1] == ("w1:p4", "Herdr is offline")


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
