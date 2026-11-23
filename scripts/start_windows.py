"""Start Bellwether on Windows as a process of its own and return at once: scripts/start.cmd runs this with the
pythonw of the checkout (no console window).

The widget is `pythonw -m bellwether` in the checkout: no console, not in the process group of the caller, out of a
job of the caller when the job allows it, and with no handle of the caller (a caller that reads the output of
start.cmd, as the `exec` of the Herdr mod does, sees its end at once). Its output goes to start.log in the log folder
of the program (%LOCALAPPDATA%\\bellwether\\Logs\\bellwether), so that a failure before the log file opens is
visible; start.log is emptied when it is larger than 1 MiB. A widget that runs already stays the only one: the new
process writes "already running" and ends (the lock of the program).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 1024 * 1024
DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP, CREATE_BREAKAWAY_FROM_JOB = 0x8, 0x200, 0x01000000


def log_folder() -> Path:
    """The log folder of the program on this system (bellwether/platform/windows.py)."""
    sys.path.insert(0, str(ROOT))
    from bellwether.platform import windows  # noqa: PLC0415  (no Qt: the module imports none at its top)
    return windows.state_home() / "bellwether"


def main(popen=subprocess.Popen, folder: Path | None = None, root: Path = ROOT) -> int:
    pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
    if not pythonw.is_file():
        print(f"bellwether: {pythonw} not found, run uv sync in {root}", file=sys.stderr)
        return 1
    folder = folder or log_folder()
    folder.mkdir(parents=True, exist_ok=True)
    log = folder / "start.log"
    if log.is_file() and log.stat().st_size > LIMIT:
        log.write_bytes(b"")
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    with open(log, "ab") as out:
        options = {"stdin": subprocess.DEVNULL, "stdout": out, "stderr": subprocess.STDOUT, "cwd": str(root),
                   "close_fds": True}
        try:
            popen([str(pythonw), "-m", "bellwether"], creationflags=flags | CREATE_BREAKAWAY_FROM_JOB, **options)
        except PermissionError:  # a job of the caller that allows no breakaway: the widget starts in it
            popen([str(pythonw), "-m", "bellwether"], creationflags=flags, **options)
    return 0


if __name__ == "__main__":
    sys.exit(main())
