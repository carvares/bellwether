"""What Linux and macOS do the same way."""
from __future__ import annotations

import select
from pathlib import Path


def lock(path: Path):
    """Take the lock of the file at `path`. Return the open file that holds it, or None when a different process
    (or a different open file of this process) holds it. Close the file to give the lock back."""
    import fcntl  # noqa: PLC0415  (here: the Linux module, which imports this one, imports on Windows for its tests)
    handle = open(path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def readable(descriptors: list[int], timeout: float) -> list[int]:
    """The open file numbers of `descriptors` (pipes) that have data or whose writer is gone, after at most `timeout`
    seconds of wait (empty: none). `select` works on pipes here."""
    return select.select(descriptors, [], [], timeout)[0]
