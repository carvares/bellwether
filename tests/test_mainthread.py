"""A call on the main thread of Qt from a worker thread (bellwether/platform/mainthread.py)."""
import threading
import time

import pytest

from bellwether.platform.mainthread import on_main_thread


def run_in_worker(app, function, seconds=5.0):
    """Run `function` on a worker thread while this (main) thread handles the events of Qt. Return its result or
    error."""
    out = {}

    def worker():
        try:
            out["value"] = function()
        except Exception as error:
            out["error"] = error

    thread = threading.Thread(target=worker)
    thread.start()
    end = time.monotonic() + seconds
    while thread.is_alive() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)
    thread.join(1)
    return out


def test_a_call_from_a_worker_runs_on_the_main_thread_and_gives_its_result(app):
    out = run_in_worker(app, lambda: on_main_thread(lambda: threading.current_thread() is threading.main_thread()))
    assert out == {"value": True}


def test_the_error_of_the_call_goes_to_the_worker(app):
    def broken():
        raise ValueError("made-up")

    out = run_in_worker(app, lambda: on_main_thread(broken))
    assert type(out["error"]) is ValueError


def test_on_the_main_thread_the_call_is_made_at_once(app):
    assert on_main_thread(lambda: threading.current_thread() is threading.main_thread()) is True


def test_a_main_thread_that_does_not_answer_in_time_gives_a_timeout_and_the_call_never_runs_later(app):
    ran = []
    out = {}
    worker = threading.Thread(target=lambda: out.update(
        result=pytest.raises(TimeoutError, on_main_thread, lambda: ran.append(1), 0.2)))
    worker.start()
    worker.join(5)  # the main thread handles no event meanwhile
    assert "result" in out and not worker.is_alive()
    for _ in range(20):
        app.processEvents()
        time.sleep(0.005)
    assert ran == []
