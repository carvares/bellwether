"""Follow the changes of herdr-core, so that a change starts a read of the agent list at once.

`herdr-core events` writes one line for each change of a terminal, and a heartbeat each 15 seconds.
A line is only a trigger here. The lines hold terminal titles and folders: this module looks for the
end of a line and for the start of a heartbeat line, and keeps nothing. It does not parse, store or log
a line or a part of one.
"""
from __future__ import annotations

import logging
import os
import select
import subprocess
import threading
import time

from .platform import spawn_child

log = logging.getLogger("bellwether")

# Seconds before the next try to start the stream. The last one repeats.
BACKOFF = (1.0, 2.0, 5.0, 10.0)
# A stream that lived for this many seconds worked: the backoff starts again at its first step. A stream
# that ends before (for example a child that writes one error line at each start) does not reset it.
MIN_LIFE = 20.0
# A stream that writes nothing for this many seconds is ended and started again (three heartbeats).
QUIET = 45.0
# After terminate: the seconds that the child has to end before it is killed.
GRACE = 2.0

# The start of a heartbeat line. It is the only text of a line that this module looks at.
HEARTBEAT = b'{"jsonrpc":"2.0","method":"heartbeat"'


class EventSource:
    """One child process and one thread. `wake` is called for each line of the child, and one time when
    the stream is lost. `healthy()` is true from the first line of a child to the end of that child."""

    def __init__(self, argv: list[str], wake, spawn=spawn_child, pause=None, quiet: float = QUIET,
                 grace: float = GRACE, clock=time.monotonic) -> None:
        self._clock = clock
        self._argv = argv
        self._wake = wake
        self._spawn = spawn
        self._stop = threading.Event()
        self._pause = pause or self._stop.wait
        self._quiet = quiet
        self._grace = grace
        self._healthy = threading.Event()
        self._stop_pipe = os.pipe()  # stop() writes one byte: the thread stops its wait for a line
        self._thread: threading.Thread | None = None

    def healthy(self) -> bool:
        return self._healthy.is_set()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="herdr-events", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """End the thread. The thread ends the child and reaps it."""
        if self._stop.is_set():
            return
        self._stop.set()
        os.write(self._stop_pipe[1], b"x")  # The thread stops its wait for a line.
        if self._thread is not None:
            self._thread.join(timeout=2 * self._grace + 1.0)
            if self._thread.is_alive():
                return  # The thread still uses the pipe. The kernel ends the child with this process.
        for descriptor in self._stop_pipe:
            os.close(descriptor)

    def _run(self) -> None:
        try:
            self._retry_loop()
        except Exception as exc:  # The class name only. Without this thread the reads come each second.
            log.error("events: stopped (%s)", type(exc).__name__)
        finally:
            self._healthy.clear()
            self._wake()

    def _retry_loop(self) -> None:
        tries = 0  # the tries since the last stream that lived for MIN_LIFE
        logged = None  # the last retry time that was written to the log
        while not self._stop.is_set():
            code: object = "no start"
            connected = False
            began = self._clock()
            try:
                child = self._spawn(self._argv)
            except (OSError, subprocess.SubprocessError) as exc:  # also an error between fork and exec
                child = None
                code = type(exc).__name__
            if child is not None:
                try:
                    connected = self._follow(child, began, announce=tries == 0)
                finally:
                    code = self._end(child)
            self._healthy.clear()
            if self._stop.is_set():
                break
            if connected:
                self._wake()  # The reader goes back to its short interval now.
                if self._clock() - began >= MIN_LIFE:
                    tries, logged = 0, None
            # A long time with no stream that lives writes each line one time, not one line for each try.
            if tries == 0:
                log.warning("events: lost (exit code %s)", code)
            seconds = BACKOFF[min(tries, len(BACKOFF) - 1)]
            if seconds != logged:
                log.info("events: retry in %ds", seconds)
                logged = seconds
            tries += 1
            self._pause(seconds)

    def _follow(self, child, began: float, announce: bool) -> bool:
        """Call `wake` for each read that holds the end of a line, until the child ends, is silent for too
        long, or stop() runs. Return True when the child wrote one line or more. `announce` False: this
        child comes after one that ended early, so "connected" is logged only when it lived for MIN_LIFE."""
        descriptor = child.stdout.fileno()
        connected = False

        def lived() -> bool:
            """True one time: for a stream that was not announced and now lived for MIN_LIFE."""
            return not announce and connected and self._clock() - began >= MIN_LIFE

        while not self._stop.is_set():
            ready, _, _ = select.select([descriptor, self._stop_pipe[0]], [], [], self._quiet)
            # Here and not only at a line: the stream can end, or be silent, before its next line.
            if lived():
                announce = True
                log.info("events: connected")
            if descriptor not in ready:
                break  # stop(), or nothing for too long
            data = os.read(descriptor, 65536)
            if not data:
                break  # the child closed its output
            if b"\n" not in data:
                continue  # a part of a long line
            if not connected:
                connected = True
                self._healthy.set()
                if announce:
                    log.info("events: connected")
            elif data.startswith(HEARTBEAT) and data.count(b"\n") == 1:
                continue  # The stream lives and nothing changed: no read.
            self._wake()
        return connected

    def _end(self, child) -> object:
        """End the child if it runs, reap it, and return its exit code."""
        try:
            if child.poll() is None:
                child.terminate()
            try:
                code = child.wait(self._grace)
            except subprocess.TimeoutExpired:
                child.kill()
                code = child.wait(self._grace)
        except (OSError, subprocess.SubprocessError) as exc:
            code = type(exc).__name__
        finally:
            child.stdout.close()
        return code
