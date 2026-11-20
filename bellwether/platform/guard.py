"""The watcher of the event child where the kernel cannot end a child with its parent (macOS has no parent-death
signal):

    python -m bellwether.platform.guard <parent pid> <command…>

It starts the command, which inherits its stdin, stdout and stderr (nothing is copied), and checks the parent once a
second. When the parent is gone (also after a SIGKILL), it ends the command and itself. When the command ends, it
exits with the code of the command. A SIGTERM, SIGINT or SIGHUP to the watcher ends the command too: the program
stops its event child with a SIGTERM to this process. Plain Python: the logic is the same on each system and is
tested on Linux. (`-m` imports the package bellwether.platform, so the module of the system too: on macOS that is
no Qt.)
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

# Seconds between two checks of the parent.
POLL = 1.0
# Seconds that the command has to end after SIGTERM, before it is killed. Shorter than the grace of the event source
# (events.GRACE, 2 s): the watcher kills a command that ignores SIGTERM before the program kills the watcher.
GRACE = 1.0
USAGE = "usage: python -m bellwether.platform.guard <parent pid> <command…>"


# The signals that stop the watcher (and its command). SIGHUP is not on every system.
STOP_SIGNALS = tuple(getattr(signal, name) for name in ("SIGTERM", "SIGINT", "SIGHUP") if hasattr(signal, name))


class _Stop(Exception):
    """A signal asked the watcher to stop."""


def _stop(signum, _frame):
    for number in STOP_SIGNALS:
        signal.signal(number, signal.SIG_IGN)  # one stop: a second signal does not break the end of the command
    raise _Stop(signum)


def _code(returncode: int) -> int:
    """The exit code of the watcher for the code of the command: a command ended by signal N gives 128 + N."""
    return returncode if returncode >= 0 else 128 - returncode


def _end(child: subprocess.Popen, grace: float) -> int:
    child.terminate()
    try:
        return child.wait(grace)
    except subprocess.TimeoutExpired:
        child.kill()
        return child.wait()


def _let_go_of_stdout() -> None:
    """The command has its own copy of stdout (the pipe of the program): the watcher writes nothing there, and with its
    copy gone the reader of the pipe sees its end as soon as the command ends."""
    try:
        sys.stdout.flush()
        empty = os.open(os.devnull, os.O_WRONLY)
        os.dup2(empty, 1)
        os.close(empty)
    except (OSError, ValueError, AttributeError):  # no stdout of its own (a test): nothing to give away
        pass


def run(parent: int, command: list[str], poll: float = POLL, grace: float = GRACE, alive=None,
        sleep=time.sleep, started=lambda: None) -> int:
    """Run `command` while the process `parent` lives. `alive`: the check of the parent (a test gives its own); by
    default the parent of this process must still be `parent` (when it ends, this process gets a new parent). One
    check of the parent and of the command each `poll` seconds, and no other wake-up. `started` is called once the
    command runs (the watcher process gives its stdout away there)."""
    alive = alive or (lambda: os.getppid() == parent)
    if not alive():
        return 1  # the parent ended before the command could start: no command
    # The handlers first: a stop signal that comes while the command starts must not leave the command alone.
    previous = {number: signal.signal(number, _stop) for number in STOP_SIGNALS}
    child = None
    try:
        child = subprocess.Popen(command)
        started()
        while True:
            code = child.poll()
            if code is not None:
                return _code(code)
            if not alive():
                _end(child, grace)
                return 1
            sleep(poll)
    except _Stop as stop:
        if child is not None:
            _end(child, grace)
        return 128 + stop.args[0]
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def main(argv: list[str]) -> int:
    if len(argv) < 3 or not argv[1].isdigit():
        print(USAGE, file=sys.stderr)
        return 2
    try:
        return run(int(argv[1]), argv[2:], started=_let_go_of_stdout)
    except OSError as error:  # the command cannot start: its name only, no path
        print(f"bellwether guard: the command cannot start ({type(error).__name__})", file=sys.stderr)
        return 127


if __name__ == "__main__":
    sys.exit(main(sys.argv))
