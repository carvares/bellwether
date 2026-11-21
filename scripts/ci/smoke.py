"""The smoke run of a CI runner: Bellwether started by its start script (scripts/start.sh; Windows:
scripts/start.cmd), against the made-up herdr-app and herdr-core of scripts/ci/fake-herdr (shell scripts; Windows:
the .cmd files), in a home folder of its own (`<out>/home`: no real setting, log or lock).

    python scripts/ci/smoke.py <out folder> [seconds]

It waits until the log has the lines of a good start (or the seconds are over), kills the event child one time and
checks that the widget starts and reads a new one, then kills the widget (SIGKILL; Windows: TerminateProcess: no
clean-up of its own), and checks that the event child is gone 3 seconds later (the kernel on Linux, the watcher on
macOS, the job object on Windows). It prints each check and the two logs (made-up data only),
and exits 1 when a check failed. Processes are found and killed by pid only.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAKE = ROOT / "scripts" / "ci" / "fake-herdr"
WINDOWS = sys.platform == "win32"
# The longest wait for the stream after its restart: the retry (1 s), and 20 s of life before "events: connected".
RESTART_SECONDS = 30


def table() -> dict[int, tuple[int, str]]:
    """Every process: pid → (parent pid, command line). `ps` (the same columns on Linux and macOS); psutil on
    Windows (a dependency of the program there)."""
    if WINDOWS:
        import psutil  # noqa: PLC0415
        rows = {}
        for process in psutil.process_iter(["pid", "ppid", "cmdline"]):
            words = process.info.get("cmdline") or []
            rows[process.info["pid"]] = (process.info.get("ppid") or 0, " ".join(words))
        return rows
    done = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True, check=True)
    rows = {}
    for line in done.stdout.splitlines():
        words = line.split(None, 2)
        if len(words) >= 2 and words[0].isdigit() and words[1].isdigit():
            rows[int(words[0])] = (int(words[1]), words[2] if len(words) > 2 else "")
    return rows


def is_event_stream(command: str) -> bool:
    """A made-up herdr-core event stream of this checkout (on Windows the cmd.exe that runs herdr-core.cmd)."""
    if WINDOWS:
        return str(FAKE / "herdr-core.cmd").lower() in command.lower() and command.rstrip().endswith("events --json")
    return command.endswith(f"{FAKE}/herdr-core events --json") and "bellwether.platform.guard" not in command


def event_children(rows) -> list[int]:
    return [pid for pid, (_, command) in rows.items() if is_event_stream(command)]


def widget_of(rows, child: int) -> int | None:
    """The widget that started the event stream `child`: the nearest process above it that runs `-m bellwether`
    (on macOS the watcher is between them; on Linux and Windows the widget is the parent)."""
    pid = rows.get(child, (0, ""))[0]
    seen = set()
    while pid > 1 and pid in rows and pid not in seen:
        seen.add(pid)
        parent, command = rows[pid]
        if command.rstrip().endswith("-m bellwether"):
            return pid
        pid = parent
    return None


def kill(pid: int) -> None:
    """Kill the process `pid` with no clean-up of its own."""
    if WINDOWS:
        import psutil  # noqa: PLC0415
        try:
            psutil.Process(pid).kill()
        except psutil.Error:  # gone already
            pass
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def gone(pid: int) -> bool:
    if WINDOWS:
        import psutil  # noqa: PLC0415
        return not psutil.pid_exists(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return not state or state.startswith("Z")


def made_up_environment(home: Path) -> dict[str, str]:
    """The environment of the run: the made-up programs first in PATH, every folder of the program in `home`."""
    environ = {**os.environ, "HOME": str(home), "PATH": f"{FAKE}{os.pathsep}{os.environ['PATH']}",
               "XDG_CONFIG_HOME": str(home / ".config"), "XDG_STATE_HOME": str(home / ".local" / "state"),
               "XDG_CACHE_HOME": str(home / ".cache"), "XDG_RUNTIME_DIR": str(home / "run")}
    if WINDOWS:
        environ.update(USERPROFILE=str(home), APPDATA=str(home / "AppData" / "Roaming"),
                       LOCALAPPDATA=str(home / "AppData" / "Local"))
    return environ


def start_command() -> list[str]:
    if WINDOWS:
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(ROOT / "scripts" / "start.cmd")]
    return ["/bin/sh", str(ROOT / "scripts" / "start.sh")]


def main(argv: list[str]) -> int:
    out = Path(argv[1]).resolve()
    seconds = float(argv[2]) if len(argv) > 2 else 20.0
    home = out / "home"
    home.mkdir(parents=True, exist_ok=True)
    environ = made_up_environment(home)
    (home / "run").mkdir(exist_ok=True)
    (home / "Library" / "Caches").mkdir(parents=True, exist_ok=True)  # as on every Mac (the lock is there)
    (home / "AppData" / "Local").mkdir(parents=True, exist_ok=True)  # as on every Windows
    os.environ.update(environ)  # the folders of the platform below are those of the made-up home
    sys.path.insert(0, str(ROOT))
    from bellwether import platform  # noqa: PLC0415

    folder = platform.state_home() / "bellwether"
    log, start_log = folder / "bellwether.log", folder / "start.log"
    if event_children(table()):
        print("FAIL an event stream of the made-up herdr-core runs already")
        return 1
    began = time.monotonic()
    subprocess.run(start_command(), env=environ, check=True, timeout=30)
    print(f"start script returned after {time.monotonic() - began:.1f} s")
    wanted = ["shell: plain", "source: app", "events: connected", "started"]
    if platform.SYSTEM in ("darwin", "win32"):
        wanted.append("herdr-app: PATH; herdr-core: PATH")

    def read(path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""

    text = ""
    while time.monotonic() - began < seconds:
        text = read(log)
        if all(line in text for line in wanted):
            break
        time.sleep(0.25)
    time.sleep(2)  # some more seconds of the running widget: a late error shows in the log
    text, started = read(log), read(start_log)
    rows = table()
    children = event_children(rows)
    widgets = {widget_of(rows, child) for child in children} - {None}
    # The processes of the run, for the record (made-up programs only): the widget, the watcher, the stream.
    print("\n".join(f"{pid} {parent} {command}" for pid, (parent, command) in sorted(rows.items())
                    if str(FAKE).lower() in command.lower() or pid in widgets or "-m bellwether" in command))
    checks = {f"log has {line!r}": line in text for line in wanted}
    checks["no traceback in the logs"] = "Traceback" not in text + started
    checks["one event child runs"] = len(children) == 1
    checks["one widget started it"] = len(widgets) == 1
    # One restart of the event stream: its child is killed (by pid); the widget must see the end, start a new child
    # and read it (a stream that comes after an other one is told as connected when it has lived 20 s: MIN_LIFE).
    # On Windows the new pipe can get the same file number and handle value as the ended one.
    for pid in children:
        kill(pid)
    end = time.monotonic() + RESTART_SECONDS
    while time.monotonic() < end and read(log).count("events: connected") < 2:
        time.sleep(0.25)
    text = read(log)
    rows = table()
    restarted = event_children(rows)
    checks["the event stream comes back after its child was killed (events: lost, then connected again)"] = (
        "events: lost" in text and text.count("events: connected") >= 2 and len(restarted) == 1
        and not set(restarted) & set(children))
    children = restarted
    widgets = {widget_of(rows, child) for child in children} - {None}
    for pid in widgets:
        kill(pid)  # no clean-up of its own: the kernel, the watcher or the job must end the child
    end = time.monotonic() + 3
    while time.monotonic() < end and not all(map(gone, children)):
        time.sleep(0.1)
    checks["the event child is gone 3 s after a kill of the widget"] = bool(children) and all(map(gone, children))
    checks["the widget is gone"] = bool(widgets) and all(map(gone, widgets))
    # A check that failed must not leave a process of this run behind (the self-test comes next): by pid.
    for pid, (_, command) in table().items():
        if is_event_stream(command) or pid in widgets:
            kill(pid)
    print(f"--- {log.name}\n{text}--- {start_log.name}\n{started}---")
    for name, good in checks.items():
        print(f"{'PASS' if good else 'FAIL'} {name}")
    print(f"smoke run: {time.monotonic() - began:.1f} s")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
