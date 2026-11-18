"""The event source and the reads that it starts. No test runs the real herdr-core: the child is a pipe."""
import logging
import os
import threading
import time

import pytest

from bellwether.backend import AFTER, FLOOR, SLOW_INTERVAL, Backend
from bellwether.events import BACKOFF, MIN_LIFE, EventSource
from bellwether.state import Agent

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
    caplog.set_level(logging.INFO, logger="bellwether")
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
    source = source_of(Factory(child), lambda: wakes.append(1), pause=pauses, quiet=1.0)
    source.start()
    child.write(LINE)
    assert until(lambda: wakes == [1])
    for seq in range(8):  # 1.6 s: longer than `quiet`, and each step is much shorter than `quiet`
        child.write(b'{"jsonrpc":"2.0","method":"heartbeat","params":{"seq":%d}}\n' % seq)
        time.sleep(0.2)
    assert source.healthy() is True and pauses.seconds == []  # the heartbeats showed that the stream lives
    assert wakes == [1]  # and nothing changed, so there is no read
    child.write(b'{"jsonrpc":"2.0","method":"heartbeat","params":{"seq":9}}\n' + LINE)
    assert until(lambda: wakes == [1, 1])  # a heartbeat together with an event is an event


def test_the_end_of_the_child_makes_the_stream_unhealthy_and_wakes_the_reader(source_of, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
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
    caplog.set_level(logging.INFO, logger="bellwether")
    first, second, wakes, pauses = FakeChild(), FakeChild(), [], Pauses()
    factory = Factory(first)
    now = [100.0]
    source = source_of(factory, lambda: wakes.append(source.healthy()), pause=pauses, clock=lambda: now[0])
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
    assert "events: connected" not in [r.getMessage() for r in caplog.records][1:]  # not yet: it can end at once
    now[0] += MIN_LIFE  # the stream lives
    second.write(b'{"jsonrpc":"2.0","method":"heartbeat","params":{"seq":1}}\n')
    assert until(lambda: [r.getMessage() for r in caplog.records].count("events: connected") == 2)
    second.exit(1)
    assert until(lambda: len(pauses.seconds) == 8)
    assert pauses.seconds[-1] == 1.0  # after a stream that lived, the backoff starts again
    assert factory.most_alive == 1  # never two children at the same time
    # A long time with no stream writes each line one time, not one line for each try.
    assert [r.getMessage() for r in caplog.records] == [
        "events: connected", "events: lost (exit code 0)", "events: retry in 1s", "events: retry in 2s",
        "events: retry in 5s", "events: retry in 10s",
        "events: connected", "events: lost (exit code 1)", "events: retry in 1s",
    ]


def test_children_that_write_one_line_and_end_do_not_reset_the_backoff_or_fill_the_log(source_of, caplog):
    """For example herdr-core that is not reachable and writes one error line at each start."""
    caplog.set_level(logging.INFO, logger="bellwether")
    children = [FakeChild() for _ in range(7)]
    for child in children:
        child.write(b'{"error":{"kind":"x"}}\n')
        child.exit(1)
    factory, wakes, pauses, now = Factory(*children), [], Pauses(), [100.0]
    source = source_of(factory, lambda: wakes.append(1), pause=pauses, clock=lambda: now[0])
    source.start()
    for count in range(1, 7):
        assert until(lambda: len(pauses.seconds) == count)
        now[0] += pauses.seconds[-1] + 0.01  # each child lived 10 ms
        pauses.go.release()
    assert until(lambda: len(pauses.seconds) == 7)
    assert pauses.seconds == [1.0, 2.0, 5.0, 10.0, 10.0, 10.0, 10.0]
    messages = [r.getMessage() for r in caplog.records]
    assert messages == [
        "events: connected", "events: lost (exit code 1)", "events: retry in 1s", "events: retry in 2s",
        "events: retry in 5s", "events: retry in 10s",
    ]
    assert len(wakes) == 14  # each child: its line and its loss; the reader takes the short interval
    assert factory.most_alive == 1


def test_an_error_at_the_start_of_the_child_is_a_failed_start_with_backoff(source_of, caplog):
    import subprocess
    caplog.set_level(logging.INFO, logger="bellwether")
    calls, pauses = [], Pauses()

    def spawn(argv):
        calls.append(1)
        raise subprocess.SubprocessError("Exception occurred in preexec_fn.")

    source = source_of(spawn, pause=pauses)
    source.start()
    assert until(lambda: pauses.seconds == [1.0])
    pauses.go.release()
    assert until(lambda: pauses.seconds == [1.0, 2.0])
    assert source._thread.is_alive() and len(calls) == 2
    assert [r.getMessage() for r in caplog.records] == [
        "events: lost (exit code SubprocessError)", "events: retry in 1s", "events: retry in 2s",
    ]


def test_a_child_that_ends_before_it_writes_is_never_healthy(source_of, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    child, wakes, pauses = FakeChild(), [], Pauses()
    source = source_of(Factory(child), lambda: wakes.append(source.healthy()), pause=pauses)
    child.exit(2)
    source.start()
    assert until(lambda: pauses.seconds == [1.0])
    assert source.healthy() is False and True not in wakes
    assert [r.getMessage() for r in caplog.records] == ["events: lost (exit code 2)", "events: retry in 1s"]


def test_a_stream_with_no_heartbeat_is_ended_and_started_again(source_of, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
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
    assert time.monotonic() - began < 3.0
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
    assert time.monotonic() - began < 3.0
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
    caplog.set_level(logging.INFO, logger="bellwether")
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
        "from bellwether.events import _spawn\n"
        "child = _spawn([sys.executable, '-c', 'import sys, time; print(repr(sys.stdin.read()), flush=True); "
        "time.sleep(30)'])\n"
        "print(child.pid, child.stdout.readline().decode().strip(), flush=True)\n"
        "time.sleep(30)\n"
    )
    parent = subprocess.Popen([sys.executable, "-c", program], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    pid = None
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
        if pid is not None:  # A failed check must not leave the child of the child behind.
            try:
                os.kill(int(pid), signal.SIGKILL)
            except ProcessLookupError:
                pass


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


def test_an_event_starts_a_read_in_the_real_threads(app, tmp_path, running):
    """A smoke test with real threads and real time. The times of the reads are tested on the made-up clock."""
    client, child = CountingClient(), FakeChild()
    backend, _, _ = running(client, child, interval=30, slow_interval=30, settings_path=tmp_path / "s.json")
    assert until(lambda: client.reads == 1, timeout=5.0)  # the read at the start
    child.write(LINE)
    assert until(lambda: client.reads == 2, timeout=5.0)  # the new stream
    child.write(LINE)
    assert until(lambda: client.reads == 3, timeout=5.0)  # 30 s is the next read by time


# ----- the times of the reads, on a made-up clock: no thread, no real time -----


class Timeline:
    """The clock and the wait of a Backend. Time moves only in the waits and in the reads.

    `events` are the times at which the event source wakes the reader. `health(now)` tells if the stream
    is healthy. `Backend._run` runs in the thread of the test until the time `end`."""

    def __init__(self, tmp_path, events=(), end=60.0, health=None, read_seconds=0.0, **options):
        self.now = 0.0
        self.end = end
        self.events = sorted(events)
        self.read_seconds = read_seconds
        self.reads = []  # the start time of each read
        self.waits = []  # ("wake" or "floor", seconds) for each wait
        source = None
        if health is not None:
            source = type("Source", (), {
                "healthy": lambda _: health(self.now), "start": lambda _: None, "stop": lambda _: None,
            })()
        self.backend = Backend(
            self, settings_path=tmp_path / "s.json", events=(lambda wake: source) if source else None,
            clock=lambda: self.now, wait=self.wait, **options,
        )

    def list_agents(self):
        while self.events and self.events[0] <= self.now:
            self.events.pop(0)  # The reader cleared its wake before this read: these events are in this read.
        self.reads.append(round(self.now, 6))
        self.now += self.read_seconds
        return []

    def wait(self, event, seconds):
        if self.now >= self.end:
            self.backend._stop.set()
            return False
        if event is self.backend._stop:  # the pause of the floor
            self.waits.append(("floor", round(seconds, 6)))
            self.now += seconds
            return False
        self.waits.append(("wake", seconds))
        woken = event.is_set() or bool(self.events and self.events[0] <= self.now + seconds)
        self.now = max(self.now, self.events[0]) if woken and self.events else self.now + (0 if woken else seconds)
        while self.events and self.events[0] <= self.now:
            self.events.pop(0)  # events that came before now are one wake: there is no queue
        if self.now >= self.end:
            self.backend._stop.set()
        return woken

    def run(self):
        self.backend._run()
        return self

    def reads_from(self, start, end=None):
        return [t for t in self.reads if t >= start and (end is None or t < end)]


HEALTHY = lambda now: True  # noqa: E731


def test_the_values_of_the_times_that_the_documents_state():
    assert (SLOW_INTERVAL, FLOOR, AFTER) == (2.0, 0.25, (0.15, 0.25, 0.15, 0.45, 0.6))


def test_with_a_healthy_stream_and_no_event_the_reads_come_each_two_seconds(app, tmp_path):
    line = Timeline(tmp_path, health=HEALTHY, end=60.0).run()
    assert line.reads == [2.0 * n for n in range(30)]  # 30 reads in 60 seconds
    assert set(line.waits) == {("wake", 2.0)}


def test_with_no_healthy_stream_the_reads_come_each_second(app, tmp_path):
    line = Timeline(tmp_path, health=lambda now: False, end=10.0).run()
    assert line.reads == [1.0 * n for n in range(10)] and set(line.waits) == {("wake", 1.0)}
    line = Timeline(tmp_path, end=10.0).run()  # no event source at all
    assert line.reads == [1.0 * n for n in range(10)] and set(line.waits) == {("wake", 1.0)}


def test_an_event_starts_a_read_at_once_and_more_reads_at_the_times_of_the_schedule(app, tmp_path):
    line = Timeline(tmp_path, health=HEALTHY, events=[10.9], end=17.0).run()
    assert line.reads_from(10.0) == pytest.approx([10.0, 10.9, 11.05, 11.3, 11.45, 11.9, 12.5, 14.5, 16.5])
    assert ("floor", pytest.approx(0)) not in line.waits and all(kind == "wake" for kind, _ in line.waits)


def test_a_second_event_starts_its_read_at_the_floor_and_the_schedule_again(app, tmp_path):
    line = Timeline(tmp_path, health=HEALTHY, events=[10.9, 11.0], end=14.0).run()
    # 11.0 is 0.1 s after the read of 10.9: the read waits 0.15 s more. Then the schedule starts again.
    assert line.reads_from(10.5) == pytest.approx([10.9, 11.15, 11.3, 11.55, 11.7, 12.15, 12.75])
    assert [seconds for kind, seconds in line.waits if kind == "floor"] == pytest.approx([0.15])


def test_a_storm_of_events_starts_four_reads_each_second_at_the_most(app, tmp_path):
    storm = [10.0 + n * 0.01 for n in range(6000)]  # 100 events each second for 60 seconds
    line = Timeline(tmp_path, health=HEALTHY, events=storm, end=75.0, read_seconds=0.005).run()
    during = line.reads_from(10.0, 70.0)
    assert len(during) == 240
    assert min(b - a for a, b in zip(during, during[1:])) == pytest.approx(0.25)
    assert len(line.reads_from(70.0, 72.0)) == 1 + len(AFTER)  # the last event, and the reads of the schedule


def test_a_burst_of_100_events_during_one_read_starts_one_more_read_and_the_reads_of_the_schedule(app, tmp_path):
    burst = [10.9 + n * 0.0004 for n in range(100)]  # all in the 0.05 s of the read that the first one starts
    line = Timeline(tmp_path, health=HEALTHY, events=burst, end=13.5, read_seconds=0.05).run()
    reads = line.reads_from(10.5, 13.5)
    assert len(reads) == 2 + len(AFTER)  # the production schedule: never one read for each event
    assert reads[:2] == pytest.approx([10.9, 11.15])  # the first event, and one read for the 99 others
    alone = Timeline(tmp_path, health=HEALTHY, events=burst, end=12.9, read_seconds=0.05, after=()).run()
    assert len(alone.reads_from(10.5)) == 2  # with no schedule: two reads


def test_a_new_stream_starts_a_read_at_once_and_then_the_slow_interval(app, tmp_path):
    # No stream until 5.5 s. Then its first line comes.
    line = Timeline(tmp_path, health=lambda now: now >= 5.5, events=[5.5], end=12.0).run()
    assert line.reads == pytest.approx([0, 1, 2, 3, 4, 5, 5.5, 5.65, 5.9, 6.05, 6.5, 7.1, 9.1, 11.1])
    assert [s for _, s in line.waits][:6] == [1.0] * 6 and [s for _, s in line.waits][-2:] == [2.0, 2.0]


def test_a_lost_stream_starts_a_read_at_once_and_then_one_read_each_second(app, tmp_path):
    # The stream ends at 20.5 s: the event source wakes the reader one time.
    line = Timeline(tmp_path, health=lambda now: now < 20.5, events=[20.5], end=26.0).run()
    assert line.reads_from(19.0) == pytest.approx([20.0, 20.5, 20.65, 20.9, 21.05, 21.5, 22.1, 23.1, 24.1, 25.1])


def test_without_an_event_source_the_reads_come_at_the_interval(app, tmp_path):
    client = CountingClient()
    backend = Backend(client, interval=0.02, slow_interval=30, settings_path=tmp_path / "s.json")
    backend.start()
    try:
        assert until(lambda: client.reads >= 5, timeout=5.0)
    finally:
        backend.stop()


def test_stop_of_the_backend_ends_both_threads_and_the_child(app, tmp_path, running):
    client, child = CountingClient(), FakeChild()
    backend, factory, _ = running(client, child, interval=30, slow_interval=30, settings_path=tmp_path / "s.json")
    child.write(LINE)
    assert until(lambda: backend._events.healthy())
    began = time.monotonic()
    backend.stop()
    assert time.monotonic() - began < 3.0
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
