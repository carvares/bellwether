"""Read the agents of the Herdr desktop app through its command-line programs.

`herdr-app ls` is the source: it has the status that the app shows. When the app window does not
answer, `herdr-core ls --json` is the source: herdr-core keeps the terminals alive without the window.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from .state import Agent, parse_app, parse_core

log = logging.getLogger("herdr_float")

TIMEOUT = 2.0


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


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=TIMEOUT)


class HerdrClient:
    def __init__(self, app: str | None, core: str | None, run=_run) -> None:
        self._app = app
        self._core = core
        self._run = run
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
        """Show the agent in the app window: its space, its tab and its terminal."""
        if self._source != "app":
            # Without the window there is no place to go to. No command runs: it must not open a window.
            raise HerdrError("app_closed", "Herdr app is not open")
        try:
            done = self._run([self._app, "do", "agent.focus", json.dumps({"terminal": key})])
        except (OSError, subprocess.SubprocessError) as exc:
            raise HerdrOffline(type(exc).__name__) from exc
        if done.returncode != 0:
            raise HerdrError(f"exit_{done.returncode}", "Herdr did not show the agent")
        try:
            reply = json.loads(done.stdout)
        except ValueError:
            return  # No JSON after exit code 0 is not an error reply.
        if isinstance(reply, dict) and "error" in reply:
            raise HerdrError("error_reply", "Herdr did not show the agent")

    def _read(self, executable: str | None, args: list[str], key: str) -> list | None:
        """Run one list command. Return the list at `key`, or None when there is no valid answer."""
        if executable is None:
            return None
        try:
            done = self._run([executable, *args])
            data = json.loads(done.stdout) if done.returncode == 0 else None
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
        rows = data.get(key) if isinstance(data, dict) else None
        return rows if isinstance(rows, list) else None

    def _set_source(self, source: str) -> None:
        if source != self._source:
            self._source = source
            log.info("source: %s", source)
