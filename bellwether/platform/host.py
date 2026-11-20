"""The process host of sessions.py: the part that every system shares. The module of each system gives a subclass
with the reads of its processes (`start_ticks`, `children`, `arguments`, `open_files`)."""
from __future__ import annotations

import os
from pathlib import Path

# The most processes of one terminal that are asked.
MAX_PROCESSES = 32


class ProcessHost:
    """The home folder of the user and the processes of this machine. A test gives its own home folder.
    `bytes_read` counts what was read of transcripts and rollout files."""

    def __init__(self, home: Path | None = None) -> None:
        self.home = Path(os.path.realpath(home if home is not None else Path.home()))
        self.bytes_read = 0

    def start_ticks(self, pid: int) -> str | None:
        """The start of the process, as a text that is the same for the life of the process and different for a
        later process with the same pid; in the form that Claude Code writes as `procStart` on this system. None
        when it cannot be read."""
        raise NotImplementedError

    def children(self, pid: int) -> list[int]:
        """The child processes of the process. Empty when they cannot be read."""
        raise NotImplementedError

    def arguments(self, pid: int) -> list[str]:
        """The words of the command line of the process. Empty when they cannot be read."""
        raise NotImplementedError

    def open_files(self, pid: int) -> list[str]:
        """The files that the process has open (the names only)."""
        raise NotImplementedError

    def family(self, *pids: int):
        """These processes and then their child processes, the nearest first, each one time, at most
        MAX_PROCESSES. One at a time: the child processes are read only when a reader asks for more."""
        order = [pid for pid in dict.fromkeys(pids) if pid > 0]
        at = 0
        while at < len(order) and at < MAX_PROCESSES:
            yield order[at]
            order += [child for child in self.children(order[at]) if child not in order]
            at += 1
