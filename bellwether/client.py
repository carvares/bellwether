"""Read the agents of the Herdr desktop app through its command-line programs.

`herdr-app ls` is the source: it has the status that the app shows. When the app window does not
answer two times one after the other, `herdr-core ls --json` is the source: herdr-core keeps the terminals
alive without the window. One read that fails changes nothing: the last list of the app stays.
The jump shows an agent in the app window. It starts the app first when the window is closed.

The screen calls (`read_screen`, `press`, `send_text`) are for the answer to a blocked agent. They take only an
address of the last list of agents. Their errors are values with a reason code. The text of a screen is private:
no log line, no error and no file of this module has it, and the output of a failed command is never logged.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .state import Agent, parse_app, parse_core
from .window import raise_app_window

log = logging.getLogger("bellwether")

TIMEOUT = 2.0
# One jump ends this many seconds after the click, also when it has to start the app.
JUMP_SECONDS = 8.0
# After the start of the app: ask it again after this pause, until it answers or the jump time ends.
START_PAUSE = 0.25
# After that: ask the new window for the agent this many times, with the same pause (2 seconds).
SHOW_TRIES = 8
# The deadlines of the screen calls. herdr-core can hold keys and a text for a short time before it types them.
READ_TIMEOUT = TIMEOUT
PRESS_TIMEOUT = 5.0
SEND_TIMEOUT = 8.0
# The form of a terminal address: "t7", "t1c", or "machine/t7". herdr-core takes also the name of a terminal in
# the place of an address: this form keeps a name out.
_ADDRESS = re.compile(r"(?:[a-z0-9][a-z0-9._-]{0,31}/)?t[0-9a-z]{1,8}")
# The keys that `press` can press: the digit of an option. The readers give no other key.
KEYS = frozenset("123456789")
MAX_KEYS = 4
TEXT_LIMIT = 2000  # characters of one free-text answer
_KIND = re.compile(r"[a-z_]{1,32}")  # an error kind of herdr-core, for example "not_found"
# `herdr-core send` puts a tag with the address of the caller around the text when these are set.
_CALLER_VARIABLES = ("HC_TERMINAL_ID", "HC_SCOPE", "HC_TERMINAL_SOCKET")


@dataclass(frozen=True)
class Screen:
    """The text on the screen of one terminal. `complete` False: Herdr could not give the whole screen."""
    text: str = field(repr=False)  # Private: not in the text form of this object.
    complete: bool = True


@dataclass(frozen=True)
class Failure:
    """A screen call that did not work. `code` is a reason code, never the output of a command."""
    code: str


def valid_address(address: object) -> bool:
    return isinstance(address, str) and _ADDRESS.fullmatch(address) is not None


def valid_text(text: object) -> bool:
    """A free-text answer: one line that a person can see, with text in it, not longer than TEXT_LIMIT."""
    return (isinstance(text, str) and 0 < len(text) <= TEXT_LIMIT and bool(text.strip())
            and all(char.isprintable() for char in text))


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
                 busctl: str = "busctl", systemd_run: str = "systemd-run", env: str = "env") -> None:
        self._app = app
        self._core = core
        self._run = run
        self._sleep = sleep
        self._clock = clock
        self._busctl = busctl
        self._systemd_run = systemd_run
        self._env = env
        # The addresses of the last list of agents. A screen call takes no other address.
        self._known: frozenset[str] = frozenset()
        self._source: str | None = None  # "app", "core" or "none": where the last list came from
        self._app_failures = 0  # reads of the app that failed, one after the other
        self._app_agents: list[Agent] | None = None  # the last list of the app; None before its first answer

    def list_agents(self) -> list[Agent]:
        rows = self._read(self._app, ["ls"], "spaces")
        if rows is not None:
            self._set_source("app")
            self._app_failures = 0
            self._app_agents = parse_app(rows)
            self._known = frozenset(agent.key for agent in self._app_agents)
            return list(self._app_agents)
        self._app_failures += 1
        if self._app_failures == 1 and self._app_agents is not None:
            # One read that failed (the app was busy for a moment): the source does not go to the core and back.
            return list(self._app_agents)
        rows = self._read(self._core, ["ls", "--json"], "terminals")
        if rows is not None:
            self._set_source("core")
            agents = parse_core(rows)
            self._known = frozenset(agent.key for agent in agents)
            return agents
        self._known = frozenset()
        self._set_source("none")
        raise HerdrOffline("herdr-app and herdr-core did not answer")

    # ----- the screen of one agent -----

    def read_screen(self, terminal: str) -> Screen | Failure:
        """The text on the screen of the terminal."""
        done = self._screen_call("read", terminal, ["read", terminal, "--json"], READ_TIMEOUT)
        if isinstance(done, Failure):
            return done
        try:
            data = json.loads(done.stdout)
        except ValueError:
            data = None
        text = data.get("text") if isinstance(data, dict) else None
        complete = data.get("complete") if isinstance(data, dict) else None
        if not isinstance(text, str) or not isinstance(complete, bool):
            return self._failed("read", terminal, "bad_reply")
        return Screen(text, complete)

    def press(self, terminal: str, keys) -> Failure | None:
        """Press the keys in the terminal, in sequence. None: herdr-core took them."""
        if (not isinstance(keys, (list, tuple)) or not 0 < len(keys) <= MAX_KEYS
                or not all(isinstance(key, str) and key in KEYS for key in keys)):
            return self._failed("keys", terminal, "bad_key")
        done = self._screen_call("keys", terminal, ["keys", terminal, *keys], PRESS_TIMEOUT)
        if isinstance(done, Failure):
            return done
        log.info("screen keys ok terminal=%s keys=%s", terminal, ",".join(keys))
        return None

    def send_text(self, terminal: str, text: str) -> Failure | None:
        """Paste the text in the terminal and press Enter, also when its program is blocked (`--force`: the text
        answers the text entry of its dialog). None: herdr-core took it."""
        if not valid_text(text):
            return self._failed("send", terminal, "bad_text")
        done = self._screen_call("send", terminal, ["send", "--force", "--", terminal, text], SEND_TIMEOUT,
                                 no_caller=True)
        if isinstance(done, Failure):
            return done
        log.info("screen send ok terminal=%s", terminal)
        return None

    def _failed(self, action: str, terminal: object, code: str) -> Failure:
        # An address that is not valid can be any text: it is not in the log.
        log.warning("screen %s failed terminal=%s code=%s", action, terminal if valid_address(terminal) else "?", code)
        return Failure(code)

    def _screen_call(self, action: str, terminal: str, args: list[str], timeout: float,
                     no_caller: bool = False) -> subprocess.CompletedProcess | Failure:
        """Run one herdr-core command for a terminal of the last list. The output of a command that failed is
        not logged and not kept: it can hold the text of a screen."""
        if not valid_address(terminal):
            return self._failed(action, terminal, "bad_address")
        if terminal not in self._known:
            return self._failed(action, terminal, "unknown_terminal")
        if self._core is None:
            return self._failed(action, terminal, "no_core")
        argv = [self._core, *args]
        if no_caller:
            argv = [self._env, *(part for name in _CALLER_VARIABLES for part in ("-u", name)), *argv]
        try:
            done = self._run(argv, timeout=timeout)
        except subprocess.TimeoutExpired:
            return self._failed(action, terminal, "timeout")
        except (OSError, subprocess.SubprocessError):
            return self._failed(action, terminal, "no_run")
        if done.returncode != 0:
            return self._failed(action, terminal, self._error_kind(done.stderr) or f"exit_{done.returncode}")
        return done

    @staticmethod
    def _error_kind(stderr: bytes) -> str | None:
        """The error kind that herdr-core wrote, as a reason code. Only a short word of small letters is taken."""
        try:
            kind = json.loads(stderr)["error"]["kind"]
        except (ValueError, TypeError, KeyError):
            return None
        return f"herdr_{kind}" if isinstance(kind, str) and _KIND.fullmatch(kind) else None

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
