"""The event source and the reads that it starts. No test runs the real herdr-core: the child is a pipe."""
import logging
import os
import threading
import time

import pytest

from herdr_float.backend import Backend
from herdr_float.events import BACKOFF, EventSource
from herdr_float.state import Agent

SECRET = b"title-of-a-terminal /home/person/folder"
LINE = b'{"method":"event","params":{"title":"' + SECRET + b'"}}\n'


class FakeChild:
    """A child process whose output is a pipe that the test writes."""

    def __init__(self):
        read_end, self._write_end = os.pipe()
        self.stdout = os.fdopen(read_end, "rb", buffering=0)
        self.returncode = None
        self.signals = []

    def write(self, data: bytes) -> None:
        os.write(self._write_end, data)

    def exit(self, code: int) -> None:
        if self.returncode is None:
            self.returncode = code
            os.close(self._write_end)

    def terminate(self) -> None:
        self.signals.append("terminate")
        self.exit(-15)

    def kill(self) -> None:
        self.signals.append("kill")
        self.exit(-9)

    def poll(self):
        return self.returncode

    def wait(self, timeout=None) -> int:
        return self.returncode


class Factory:
    """Gives the children that the test made, in order. With no child left, the start fails."""

    def __init__(self, *children):
        self.children = list(children)
        self.calls = []
        self.alive = 0  # children that were started and not yet reaped
        self.most_alive = 0

    def __call__(self, argv):
        self.calls.append(list(argv))
        if not self.children:
            raise FileNotFoundError("no program")
        child = self.children.pop(0)
        self.alive += 1
        self.most_alive = max(self.most_alive, self.alive)
        reap = child.wait

        def wait(timeout=None):
            if child.returncode is not None and not getattr(child, "reaped", False):
                child.reaped = True
                self.alive -= 1
            return reap(timeout)

        child.wait = wait
        return child


class Pauses:
    """The pause between two tries. It records the seconds and waits for the test to let it go."""

    def __init__(self):
        self.seconds = []
        self.go = threading.Semaphore(0)

    def __call__(self, seconds: float) -> None:
        self.seconds.append(seconds)
        self.go.acquire(timeout=5)


def until(condition, timeout=2.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.002)
    return False


@pytest.fixture
def source_of():
    """Make event sources that are stopped at the end of the test."""
    made = []

    def make(factory, wake=lambda: None, pause=None, **options):
        pause = pause or Pauses()
        source = EventSource(["herdr-core", "events", "--json"], wake, spawn=factory, pause=pause, **options)
        made.append((source, pause))
        return source

    yield make
    for source, pause in made:
        if isinstance(pause, Pauses):
            pause.go.release(100)
        source.stop()


def test_a_line_wakes_the_reader_and_makes_the_stream_healthy(source_of, caplog):
    caplog.set_level(logging.INFO, logger="herdr_float")
    child, wakes = FakeChild(), []
    factory = Factory(child)
    source = source_of(factory, lambda: wakes.append(1))
    assert source.healthy() is False
    source.start()
    assert until(lambda: factory.calls) and factory.calls == [["herdr-core", "events", "--json"]]
    assert source.healthy() is False and wakes == []  # a child that wrote nothing is not a stream yet
    child.write(LINE)
    assert until(lambda: wakes == [1])
    assert source.healthy() is True
    child.write(LINE)
    assert until(lambda: wakes == [1, 1])
    assert [r.getMessage() for r in caplog.records] == ["events: connected"]


def test_garbage_and_very_long_lines_do_not_break_the_reader_and_are_not_logged(source_of, caplog):
    caplog.set_level(logging.DEBUG)
    child, wakes = FakeChild(), []
    source = source_of(Factory(child), lambda: wakes.append(1))
    source.start()
    child.write(b"\xff\xfe not json {{{ " + SECRET + b"\n")
    assert until(lambda: len(wakes) == 1)
    long_line = SECRET * 30_000  # more than one megabyte, and more than the pipe holds
    writer = threading.Thread(target=child.write, args=(long_line + b"\n",))
    writer.start()
    writer.join(5)
    assert not writer.is_alive(), "the reader did not take the long line"
    assert until(lambda: len(wakes) == 2)
    assert len(wakes) == 2  # one wake for the long line, not one for each part of it
    child.write(b"\n\n" + LINE)
    assert until(lambda: len(wakes) >= 3)
    assert source.healthy() is True
    assert SECRET.decode() not in caplog.text and "title" not in caplog.text and "json" not in caplog.text
    assert [r.getMessage() for r in caplog.records] == ["events: connected"]


def test_a_heartbeat_keeps_the_stream_alive_and_starts_no_read(source_of):
    child, wakes, pauses = FakeChild(), [], Pauses()
    source = source_of(Factory(child), lambda: wakes.append(1), pause=pauses, quiet=0.15)
    source.start()
    child.write(LINE)
    assert until(lambda: wakes == [1])
    for seq in range(8):  # 0.4 s: longer than `quiet`
        child.write(b'{"jsonrpc":"2.0","method":"heartbeat","params":{"seq":%d}}\n' % seq)
        time.sleep(0.05)
    assert source.healthy() is True and pauses.seconds == []  # the heartbeats showed that the stream lives
    assert wakes == [1]  # and nothing changed, so there is no read
    child.write(b'{"jsonrpc":"2.0","method":"heartbeat","params":{"seq":9}}\n' + LINE)
    assert until(lambda: wakes == [1, 1])  # a heartbeat together with an event is an event


def test_the_end_of_the_child_makes_the_stream_unhealthy_and_wakes_the_reader(source_of, caplog):
    caplog.set_level(logging.INFO, logger="herdr_float")
    child, wakes, pauses = FakeChild(), [], Pauses()
    source = source_of(Factory(child), lambda: wakes.append(source.healthy()), pause=pauses)
    source.start()
    child.write(LINE)
    assert until(lambda: wakes == [True])
    child.exit(3)
    assert until(lambda: wakes == [True, False])  # the reader hears of the loss at once
    assert until(lambda: pauses.seconds == [1.0])
    assert [r.getMessage() for r in caplog.records] == [
        "events: connected", "events: lost (exit code 3)", "events: retry in 1s",
    ]


def test_retries_use_the_backoff_and_a_new_stream_starts_a_read_at_once(source_of, caplog):
    caplog.set_level(logging.INFO, logger="herdr_float")
    first, second, wakes, pauses = FakeChild(), FakeChild(), [], Pauses()
    factory = Factory(first)
    source = source_of(factory, lambda: wakes.append(source.healthy()), pause=pauses)
    source.start()
    first.write(LINE)
    assert until(lambda: source.healthy())
    first.exit(0)
    for count in range(1, 7):  # six tries with no program
        assert until(lambda: len(pauses.seconds) == count)
        pauses.go.release()
    assert until(lambda: len(pauses.seconds) == 7)
    assert BACKOFF == (1.0, 2.0, 5.0, 10.0)
    assert pauses.seconds == [1.0, 2.0, 5.0, 10.0, 10.0, 10.0, 10.0]
    assert source.healthy() is False
    del wakes[:]
    factory.children.append(second)
    pauses.go.release()
    assert until(lambda: len(factory.calls) == 8)
    second.write(LINE)
    assert until(lambda: wakes == [True])  # healthy again: the wake starts a read now
    second.exit(1)
    assert until(lambda: len(pauses.seconds) == 8)
    assert pauses.seconds[-1] == 1.0  # after a stream that worked, the backoff starts again
    assert factory.most_alive == 1  # never two children at the same time
    # A long time with no stream writes each line one time, not one line for each try.
    assert [r.getMessage() for r in caplog.records] == [
        "events: connected", "events: lost (exit code 0)", "events: retry in 1s", "events: retry in 2s",
        "events: retry in 5s", "events: retry in 10s",
        "events: connected", "events: lost (exit code 1)", "events: retry in 1s",
    ]


def test_a_child_that_ends_before_it_writes_is_never_healthy(source_of, caplog):
    caplog.set_level(logging.INFO, logger="herdr_float")
    child, wakes, pauses = FakeChild(), [], Pauses()
    source = source_of(Factory(child), lambda: wakes.append(source.healthy()), pause=pauses)
    child.exit(2)
    source.start()
    assert until(lambda: pauses.seconds == [1.0])
    assert source.healthy() is False and True not in wakes
    assert [r.getMessage() for r in caplog.records] == ["events: lost (exit code 2)", "events: retry in 1s"]


def test_a_stream_with_no_heartbeat_is_ended_and_started_again(source_of, caplog):
    caplog.set_level(logging.INFO, logger="herdr_float")
    child, pauses = FakeChild(), Pauses()
    source = source_of(Factory(child), pause=pauses, quiet=0.05)
    source.start()
    child.write(LINE)
    assert until(lambda: source.healthy())
    assert until(lambda: pauses.seconds == [1.0])  # nothing came for longer than `quiet`
    assert source.healthy() is False
    assert child.signals == ["terminate"]
    assert [r.getMessage() for r in caplog.records][:2] == ["events: connected", "events: lost (exit code -15)"]


def test_stop_ends_the_child_and_the_thread_in_a_short_time(source_of):
    child = FakeChild()
    factory = Factory(child)
    source = source_of(factory)
    source.start()
    child.write(LINE)
    assert until(lambda: source.healthy())
    began = time.monotonic()
    source.stop()
    assert time.monotonic() - began < 1.0
    assert child.signals == ["terminate"]
    assert factory.alive == 0  # the child was reaped
    assert not source._thread.is_alive()
    assert source.healthy() is False
    assert len(factory.calls) == 1  # no new child after the stop


def test_stop_during_the_pause_before_a_retry_ends_the_thread(source_of):
    source = EventSource(["herdr-core", "events"], lambda: None, spawn=Factory())  # the real pause
    source.start()
    assert until(lambda: source._thread.is_alive())
    time.sleep(0.02)
    began = time.monotonic()
    source.stop()
    assert time.monotonic() - began < 1.0
    assert not source._thread.is_alive()


def test_a_child_that_does_not_end_on_terminate_is_killed(source_of):
    child = FakeChild()
    child.terminate = lambda: child.signals.append("terminate")  # the child does not listen

    def wait(timeout=None):
        if child.returncode is None:
            raise __import__("subprocess").TimeoutExpired("herdr-core", timeout)
        return child.returncode

    child.wait = wait
    source = source_of(Factory(child), grace=0.05)
    source.start()
    child.write(LINE)
    assert until(lambda: source.healthy())
    source.stop()
    assert child.signals == ["terminate", "kill"]
    assert not source._thread.is_alive()


def test_an_error_in_the_thread_ends_it_with_the_stream_unhealthy_and_its_class_in_the_log(source_of, caplog):
    caplog.set_level(logging.INFO, logger="herdr_float")
    wakes = []

    def spawn(argv):
        raise RuntimeError(SECRET.decode())

    source = source_of(spawn, lambda: wakes.append(source.healthy()))
    source.start()
    assert until(lambda: not source._thread.is_alive())
    assert wakes == [False] and source.healthy() is False
    assert [r.getMessage() for r in caplog.records] == ["events: stopped (RuntimeError)"]
    assert SECRET.decode() not in caplog.text


def test_the_real_child_reads_no_input_and_ends_when_its_parent_is_killed(tmp_path):
    """The real start of a child, with a made-up program in the place of herdr-core."""
    import signal
    import subprocess
    import sys

    program = (
        "import sys, time\n"
        "from herdr_float.events import _spawn\n"
        "child = _spawn([sys.executable, '-c', 'import sys, time; print(repr(sys.stdin.read()), flush=True); "
        "time.sleep(30)'])\n"
        "print(child.pid, child.stdout.readline().decode().strip(), flush=True)\n"
        "time.sleep(30)\n"
    )
    parent = subprocess.Popen([sys.executable, "-c", program], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        pid, read = parent.stdout.readline().decode().split()
        assert read == "''"  # the input of the child is /dev/null: it read the end at once
        os.kill(int(pid), 0)  # the child runs
        parent.send_signal(signal.SIGKILL)
        parent.wait(5)

        def gone() -> bool:
            try:  # A child that ended has no /proc entry, or it is a zombie that waits for its new parent.
                return open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[0] == "Z"
            except OSError:
                return True

        assert until(gone), "the child lives after the kill of its parent"
    finally:
        parent.kill()
        parent.wait(5)
        parent.stdin.close()
        parent.stdout.close()


# ----- the reads that the events start -----


class CountingClient:
    def __init__(self, seconds: float = 0.0):
        self.reads = 0
        self.seconds = seconds  # how long one read takes
        self.result = [Agent("t1", "working", "", "Main")]

    def list_agents(self):
        self.reads += 1
        time.sleep(self.seconds)
        return self.result


@pytest.fixture
def running():
    """Start backends with a made-up child. They are stopped at the end of the test."""
    made = []

    def start(client, child=None, **options):
        factory = Factory(*([child] if child else []))
        pauses = Pauses()
        options.setdefault("after", ())  # no reads after the read of a wake, if the test does not ask
        backend = Backend(
            client, events=lambda wake: EventSource(["herdr-core", "events"], wake, spawn=factory, pause=pauses),
            **options,
        )
        made.append((backend, pauses))
        backend.start()
        return backend, factory, pauses

    yield start
    for backend, pauses in made:
        pauses.go.release(100)
        backend.stop()


def test_an_event_starts_a_read_at_once(app, tmp_path, running):
    client, child = CountingClient(), FakeChild()
    backend, _, _ = running(client, child, interval=30, slow_interval=30, settings_path=tmp_path / "s.json")
    assert until(lambda: client.reads == 1)  # the read at the start
    child.write(LINE)
    assert until(lambda: client.reads == 2, timeout=0.5)  # the new stream
    time.sleep(0.15)
    assert client.reads == 2
    began = time.monotonic()
    child.write(LINE)
    assert until(lambda: client.reads == 3, timeout=0.5)
    assert time.monotonic() - began < 0.15


def test_a_burst_of_100_events_causes_at_most_two_reads(app, tmp_path, running):
    client, child = CountingClient(seconds=0.05), FakeChild()
    backend, _, _ = running(client, child, interval=30, slow_interval=30, settings_path=tmp_path / "s.json")
    child.write(LINE)
    assert until(lambda: client.reads >= 2)
    time.sleep(0.3)
    before = client.reads
    for _ in range(100):
        child.write(LINE)  # the whole burst arrives before the first read of the burst ends
    time.sleep(0.5)
    assert 1 <= client.reads - before <= 2


def test_after_an_event_more_reads_follow_at_the_given_times_and_then_the_slow_interval(app, tmp_path, running):
    client, child = CountingClient(), FakeChild()
    backend, _, _ = running(
        client, child, interval=30, slow_interval=30, after=(0.05, 0.1), floor=0, settings_path=tmp_path / "s.json",
    )
    child.write(LINE)
    assert until(lambda: client.reads == 4, timeout=1.0)  # the start, the event, and two more reads
    times = [time.monotonic()]
    child.write(LINE)
    for count in (5, 6, 7):
        assert until(lambda: client.reads == count, timeout=1.0)
        times.append(time.monotonic())
    assert times[1] - times[0] < 0.045  # at once
    assert times[2] - times[1] > 0.045 and times[3] - times[2] > 0.095 and times[3] - times[0] < 0.5
    time.sleep(0.3)
    assert client.reads == 7  # the app had its time: no more reads until the slow interval


def test_a_stream_that_never_stops_cannot_start_reads_faster_than_the_floor(app, tmp_path, running):
    client, child = CountingClient(), FakeChild()
    backend, _, _ = running(
        client, child, interval=30, slow_interval=30, floor=0.05, settings_path=tmp_path / "s.json",
    )
    child.write(LINE)
    assert until(lambda: client.reads >= 2)
    before, end = client.reads, time.monotonic() + 0.5
    while time.monotonic() < end:
        child.write(LINE)
        time.sleep(0.001)
    assert 5 <= client.reads - before <= 11  # 0.5 s with one read each 0.05 s


def test_with_a_healthy_stream_and_no_event_the_reads_come_at_the_slow_interval(app, tmp_path, running):
    client, child = CountingClient(), FakeChild()
    backend, _, _ = running(client, child, interval=0.02, slow_interval=0.2, settings_path=tmp_path / "s.json")
    assert until(lambda: client.reads >= 3)  # no stream yet: the short interval
    child.write(LINE)
    assert until(lambda: backend._events.healthy())
    time.sleep(0.1)  # the read of the new stream is done
    before = client.reads
    time.sleep(0.5)
    assert 1 <= client.reads - before <= 3  # 0.5 s at 0.2 s; at 0.02 s it would be 25


def test_when_the_stream_ends_the_reads_come_at_the_short_interval_again(app, tmp_path, running):
    client, child = CountingClient(), FakeChild()
    backend, factory, pauses = running(
        client, child, interval=0.02, slow_interval=30, settings_path=tmp_path / "s.json",
    )
    child.write(LINE)
    assert until(lambda: backend._events.healthy())
    time.sleep(0.1)
    before = client.reads
    time.sleep(0.1)
    assert client.reads == before  # healthy: no read for 30 s
    child.exit(1)
    assert until(lambda: client.reads >= before + 5, timeout=1.0)  # unhealthy: a read each 0.02 s
    again = FakeChild()
    factory.children.append(again)
    pauses.go.release()
    again.write(LINE)
    assert until(lambda: backend._events.healthy())
    time.sleep(0.1)
    before = client.reads
    time.sleep(0.1)
    assert client.reads == before  # healthy again: the slow interval


def test_without_an_event_source_the_reads_come_at_the_interval(app, tmp_path):
    client = CountingClient()
    backend = Backend(client, interval=0.02, slow_interval=30, settings_path=tmp_path / "s.json")
    backend.start()
    try:
        assert until(lambda: client.reads >= 5, timeout=1.0)
    finally:
        backend.stop()


def test_stop_of_the_backend_ends_both_threads_and_the_child(app, tmp_path, running):
    client, child = CountingClient(), FakeChild()
    backend, factory, _ = running(client, child, interval=30, slow_interval=30, settings_path=tmp_path / "s.json")
    child.write(LINE)
    assert until(lambda: backend._events.healthy())
    began = time.monotonic()
    backend.stop()
    assert time.monotonic() - began < 1.0
    assert not backend._thread.is_alive() and not backend._events._thread.is_alive()
    assert child.signals == ["terminate"] and factory.alive == 0


def test_no_part_of_an_event_line_reaches_the_log(app, tmp_path, running, caplog):
    caplog.set_level(logging.DEBUG)
    client, child = CountingClient(), FakeChild()
    backend, _, _ = running(client, child, interval=30, slow_interval=30, settings_path=tmp_path / "s.json")
    for _ in range(20):
        child.write(LINE)
    child.write(b"not json " + SECRET + b"\n")
    assert until(lambda: client.reads >= 2)
    child.exit(1)
    assert until(lambda: "events: lost (exit code 1)" in caplog.text)
    assert SECRET.decode() not in caplog.text and "title" not in caplog.text and "folder" not in caplog.text
    assert {r.getMessage() for r in caplog.records} == {
        "events: connected", "events: lost (exit code 1)", "events: retry in 1s",
    }
