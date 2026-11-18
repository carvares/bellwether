"""Read the agents of the Herdr desktop app through its command-line programs.

`herdr-app ls` is the source: it has the status that the app shows. When the app window does not
answer, `herdr-core ls --json` is the source: herdr-core keeps the terminals alive without the window.
The jump shows an agent in the app window. It starts the app first when the window is closed.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from pathlib import Path

from .state import Agent, parse_app, parse_core
from .window import raise_app_window

log = logging.getLogger("herdr_float")

TIMEOUT = 2.0
# One jump ends this many seconds after the click, also when it has to start the app.
JUMP_SECONDS = 8.0
# After the start of the app: ask it again after this pause, until it answers or the jump time ends.
START_PAUSE = 0.25
# After that: ask the new window for the agent this many times, with the same pause (2 seconds).
SHOW_TRIES = 8


class HerdrOffline(Exception):
    """The Herdr app and herdr-core did not answer."""


class HerdrError(Exception):
    """Herdr refused a command. The message is fixed text for the person, never command output."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def find_executables() -> tuple[str | None, str | None]:
    """Return the paths of herdr-app and herdr-core. None means not found."""
    local_core = Path.home() / ".local" / "bin" / "herdr-core"
    core = shutil.which("herdr-core") or (str(local_core) if local_core.is_file() else None)
    return shutil.which("herdr-app"), core


def _run(argv: list[str], timeout: float = TIMEOUT) -> subprocess.CompletedProcess:
    return subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)


class HerdrClient:
    def __init__(self, app: str | None, core: str | None, run=_run, sleep=time.sleep, clock=time.monotonic,
                 busctl: str = "busctl", systemd_run: str = "systemd-run") -> None:
        self._app = app
        self._core = core
        self._run = run
        self._sleep = sleep
        self._clock = clock
        self._busctl = busctl
        self._systemd_run = systemd_run
        self._source: str | None = None  # "app", "core" or "none": where the last list came from

    def list_agents(self) -> list[Agent]:
        rows = self._read(self._app, ["ls"], "spaces")
        if rows is not None:
            self._set_source("app")
            return parse_app(rows)
        rows = self._read(self._core, ["ls", "--json"], "terminals")
        if rows is not None:
            self._set_source("core")
            return parse_core(rows)
        self._set_source("none")
        raise HerdrOffline("herdr-app and herdr-core did not answer")

    def focus_agent(self, key: str) -> None:
        """Show the agent in the app window and bring the window to the front. Start the app if it is closed.
        The jump ends JUMP_SECONDS after its start at the latest, with the error of the step in progress."""
        if self._app is None:
            raise HerdrError("no_app", "Herdr app is not installed")
        deadline = self._clock() + JUMP_SECONDS

        def left() -> float:
            return deadline - self._clock()

        def run(argv: list[str]) -> subprocess.CompletedProcess:
            """One command of the jump. It gets the time that is left, so it cannot run past the deadline."""
            if left() <= 0:
                raise subprocess.TimeoutExpired(argv, 0)
            return self._run(argv, timeout=min(TIMEOUT, left()))

        tries = 1
        if self._read(self._app, ["ls"], "spaces", run) is None:
            self._start_app(key, run, left)
            tries = SHOW_TRIES  # A window that just started answers before it has its terminals.
        gone = None  # the last "agent is gone" answer of a window that just started
        for attempt in range(1, tries + 1):
            try:
                self._show(key, run)
                break
            except HerdrError as exc:
                pause = min(START_PAUSE, left())  # One read of the clock: the pause is never negative.
                if exc.code != "agent_gone" or attempt == tries or pause <= 0:
                    raise
                gone = exc
                self._sleep(pause)
            except HerdrOffline:
                if gone is None or left() > 0:
                    raise
                raise gone  # The time ended during one more try: the last answer of the app stands.
        raised = raise_app_window(run, self._busctl)
        log.info("jump agent=%s step=raise kwin=%s", key, raised)
        # Without KWin, ask the app: plain `herdr-app` opens or raises its window. KWin is first because
        # its result is known, and it does not depend on the focus rules of the desktop.
        if not raised and self._launch(key, run) != 0:
            raise HerdrError("no_raise", "could not raise the window")

    def _launch(self, key: str, run) -> int | str:
        """Run plain `herdr-app` as the desktop does: a unit of the user's systemd, with the environment of
        the session and not of this process. The app does not end with the widget and has none of its files.
        Return the exit code of the launcher (0: accepted), or the name of the error."""
        try:
            code = run(
                [self._systemd_run, "--user", "--quiet", "--collect", "--slice=app.slice", "--", self._app]
            ).returncode
        except (OSError, subprocess.SubprocessError) as exc:
            code = type(exc).__name__
        log.info("jump agent=%s step=launch exit=%s", key, code)
        return code

    def _start_app(self, key: str, run, left) -> None:
        answered = False
        if self._launch(key, run) == 0:
            while not answered:
                pause = min(START_PAUSE, left())  # One read of the clock: the pause is never negative.
                if pause <= 0:
                    break
                self._sleep(pause)
                answered = self._read(self._app, ["ls"], "spaces", run) is not None
            log.info("jump agent=%s step=wait answered=%s", key, answered)
        if not answered:
            raise HerdrError("no_start", "Herdr app did not start")

    def _show(self, key: str, run) -> None:
        try:
            done = run([self._app, "do", "agent.focus", json.dumps({"terminal": key})])
        except (OSError, subprocess.SubprocessError) as exc:
            log.info("jump agent=%s step=show exit=%s", key, type(exc).__name__)
            raise HerdrOffline(type(exc).__name__) from exc
        log.info("jump agent=%s step=show exit=%d", key, done.returncode)
        try:
            reply = json.loads(done.stdout)
        except ValueError:
            reply = None  # No JSON after exit code 0 is not an error reply.
        error = reply.get("error") if isinstance(reply, dict) else None
        if isinstance(error, str) and error.startswith("no running terminal"):
            raise HerdrError("agent_gone", "agent is gone")
        if done.returncode != 0:
            raise HerdrError(f"exit_{done.returncode}", "Herdr did not show the agent")
        if error is not None:
            raise HerdrError("error_reply", "Herdr did not show the agent")

    def _read(self, executable: str | None, args: list[str], key: str, run=None) -> list | None:
        """Run one list command. Return the list at `key`, or None when there is no valid answer."""
        if executable is None:
            return None
        try:
            done = (run or self._run)([executable, *args])
            data = json.loads(done.stdout) if done.returncode == 0 else None
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
        rows = data.get(key) if isinstance(data, dict) else None
        return rows if isinstance(rows, list) else None

    def _set_source(self, source: str) -> None:
        if source != self._source:
            self._source = source
            log.info("source: %s", source)
