"""The Linux part of the program: KDE Plasma on Wayland."""
from __future__ import annotations

import ctypes
import fcntl
import json
import os
import shutil
import signal
import subprocess
from pathlib import Path


# ----- the folders: the XDG base folders with the standard defaults -----

def _base(variable: str, default: str) -> Path:
    """The folder in the variable. An empty or relative value is not valid: then the default in the home folder."""
    value = os.environ.get(variable, "")
    return Path(value) if os.path.isabs(value) else Path.home() / default


def config_home() -> Path:
    return _base("XDG_CONFIG_HOME", ".config")


def state_home() -> Path:
    return _base("XDG_STATE_HOME", ".local/state")


def cache_home() -> Path:
    return _base("XDG_CACHE_HOME", ".cache")


def runtime_dir() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp")


# ----- the single-instance lock -----

def lock(path: Path):
    """Take the lock of the file at `path`. Return the open file that holds it, or None when a different process
    (or a different open file of this process) holds it. Close the file to give the lock back."""
    handle = open(path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


# ----- the programs of the system that the client runs -----

# By name. A test of the client gives fakes in their place (HerdrClient takes them as keyword arguments).
COMMANDS = {"busctl": "busctl", "systemd_run": "systemd-run", "env": "env"}


# ----- the raise of the Herdr app window -----
# KWin does it. On Wayland a program cannot activate the window of a different program, and the app
# has no command for it. The window runner of KWin (the one behind the KRunner search) is on D-Bus:
# its "Run" restores a minimized window and activates it. (A window on a different virtual desktop
# was not tested.)

APP_CLASS = "herdr-app"  # The window class of the app. Its .desktop file names it (StartupWMClass).
_ACTIVATE = "0_"  # The window runner names a match "<action>_<window id>". Action 0 activates.
_ERRORS = (OSError, subprocess.SubprocessError, ValueError, LookupError, TypeError, AttributeError)


def raise_app_window(run, busctl: str) -> bool:
    """Restore and activate the window of the Herdr app. Return False when that did not occur."""
    try:
        matches = list(_kwin(run, busctl, "/WindowsRunner", "org.kde.krunner1", "Match", "s", APP_CLASS)[0])
    except _ERRORS:
        return False  # No busctl, no KWin, or a reply with a different shape.
    for match in matches:
        try:
            window = match[0].partition("_")[2]
            # The runner also matches captions and partial names, so only the exact class counts.
            if _info(run, busctl, window).get("resourceClass") != APP_CLASS:
                continue
            _kwin(run, busctl, "/WindowsRunner", "org.kde.krunner1", "Run", "ss", _ACTIVATE + window, "")
            return _info(run, busctl, window).get("minimized") is False
        except _ERRORS:
            continue  # This match is not a window that KWin can give: try the next one.
    return False


def _kwin(run, busctl: str, path: str, interface: str, method: str, *arguments: str) -> list:
    done = run([busctl, "--user", "--json=short", "call", "org.kde.KWin", path, interface, method, *arguments])
    if done.returncode != 0:
        raise ValueError(method)
    return json.loads(done.stdout)["data"] if done.stdout.strip() else []


def _info(run, busctl: str, window: str) -> dict:
    """The properties of one window. Each value comes as {"type": ..., "data": ...}."""
    properties = _kwin(run, busctl, "/KWin", "org.kde.KWin", "getWindowInfo", "s", window)[0]
    return {name: value["data"] for name, value in properties.items()}


def raise_app(run, commands: dict[str, str]) -> bool:
    """Restore and activate the window of the Herdr app. Return False when that did not occur."""
    return raise_app_window(run, commands["busctl"])


# ----- the start of a closed Herdr app -----

def start_app(run, app: str, commands: dict[str, str]) -> int:
    """Run plain `herdr-app` as the desktop does: a unit of the user's systemd, with the environment of the session
    and not of this process. The app does not end with the widget and has none of its files. Return the exit code
    of the launcher (0: accepted). The errors of `run` go to the caller."""
    return run([commands["systemd_run"], "--user", "--quiet", "--collect", "--slice=app.slice", "--", app]).returncode


# ----- a command without some variables of this process -----

def clean_environment(argv: list[str], names, commands: dict[str, str]) -> list[str]:
    """The command `argv`, run without the environment variables `names`."""
    return [commands["env"], *(part for name in names for part in ("-u", name)), *argv]


# ----- where the Herdr programs are -----

def find_executables() -> tuple[str | None, str | None]:
    """Return the paths of herdr-app and herdr-core. None means not found."""
    local_core = Path.home() / ".local" / "bin" / "herdr-core"
    core = shutil.which("herdr-core") or (str(local_core) if local_core.is_file() else None)
    return shutil.which("herdr-app"), core


# ----- the event child, which ends with this process -----

_PR_SET_PDEATHSIG = 1
# The function is found and its types are set here and not in the child: between fork and exec the child
# must not load a library or look for a symbol.
_prctl = ctypes.CDLL(None).prctl
_prctl.argtypes = [ctypes.c_int, ctypes.c_ulong]
_prctl.restype = ctypes.c_int


def spawn_child(argv: list[str]) -> subprocess.Popen:
    """Start the child. The kernel ends it when this process ends, also when this process is killed."""
    parent = os.getpid()

    def die_with_parent() -> None:
        # No child without the signal. And the parent can end before the call: then the child ends here.
        if _prctl(_PR_SET_PDEATHSIG, signal.SIGTERM) != 0 or os.getppid() != parent:
            os._exit(1)

    return subprocess.Popen(
        argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
        preexec_fn=die_with_parent,
    )


# ----- the process host: the home folder and /proc -----

# The most processes of one terminal that are asked.
MAX_PROCESSES = 32
# The most threads of one process whose child processes are read.
MAX_TASKS = 256


class Host:
    """The home folder of the user and /proc. A test gives its own folders. `bytes_read` counts what was read of
    transcripts and rollout files."""

    def __init__(self, home: Path | None = None, proc: Path = Path("/proc")) -> None:
        self.home = Path(os.path.realpath(home if home is not None else Path.home()))
        self.proc = Path(proc)
        self.bytes_read = 0

    def start_ticks(self, pid: int) -> str | None:
        """The start of the process as /proc has it (field 22 of `stat`, in clock ticks since the boot)."""
        try:
            text = (self.proc / str(pid) / "stat").read_text(errors="replace")
        except OSError:
            return None
        fields = text.rsplit(")", 1)[-1].split()  # the name of a process can have spaces and brackets
        return fields[19] if len(fields) > 19 and fields[19].isdigit() else None

    def children(self, pid: int) -> list[int]:
        found: list[int] = []
        try:
            tasks = sorted((self.proc / str(pid) / "task").iterdir())
        except OSError:
            return found
        for task in tasks[:MAX_TASKS]:
            try:
                found += [int(word) for word in (task / "children").read_text().split() if word.isdigit()]
            except OSError:
                continue
        return found

    def family(self, *pids: int):
        """These processes and then their child processes, the nearest first, each one time, at most
        MAX_PROCESSES. One at a time: the child processes are read only when a reader asks for more."""
        order = [pid for pid in dict.fromkeys(pids) if pid > 0]
        at = 0
        while at < len(order) and at < MAX_PROCESSES:
            yield order[at]
            order += [child for child in self.children(order[at]) if child not in order]
            at += 1

    def open_files(self, pid: int) -> list[str]:
        """The files that the process has open (the names only)."""
        found = []
        try:
            numbers = list((self.proc / str(pid) / "fd").iterdir())
        except OSError:
            return found
        for number in numbers[:4096]:
            try:
                found.append(os.readlink(number))
            except OSError:
                continue
        return found


def process_host() -> Host:
    """The host of this machine: the home folder of the user and the real /proc."""
    return Host()
