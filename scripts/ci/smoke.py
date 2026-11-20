"""The smoke run of a CI runner: Bellwether started by scripts/start.sh, against the made-up herdr-app and
herdr-core of scripts/ci/fake-herdr, in a home folder of its own (`<out>/home`: no real setting, log or lock).

    python scripts/ci/smoke.py <out folder> [seconds]

It waits until the log has the lines of a good start (or the seconds are over), kills the widget with SIGKILL (no
clean-up of its own), and checks that the event child is gone 3 seconds later (the watcher on macOS, the kernel on
Linux). It prints each check and the two logs (made-up data only), and exits 1 when a check failed.
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


def table() -> dict[int, tuple[int, str]]:
    """Every process: pid → (parent pid, command line), from `ps` (the same columns on Linux and macOS)."""
    done = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True, check=True)
    rows = {}
    for line in done.stdout.splitlines():
        words = line.split(None, 2)
        if len(words) >= 2 and words[0].isdigit() and words[1].isdigit():
            rows[int(words[0])] = (int(words[1]), words[2] if len(words) > 2 else "")
    return rows


def event_children(rows) -> list[int]:
    """The made-up herdr-core event streams of this checkout."""
    return [pid for pid, (_, command) in rows.items()
            if command.endswith(f"{FAKE}/herdr-core events --json") and "bellwether.platform.guard" not in command]


def widget_of(rows, child: int) -> int | None:
    """The widget that started the event stream `child`: the nearest process above it that runs
    `-m bellwether` (on macOS the watcher is between them, on Linux the widget is the parent)."""
    pid = rows.get(child, (0, ""))[0]
    while pid > 1 and pid in rows:
        parent, command = rows[pid]
        if command.endswith("-m bellwether"):
            return pid
        pid = parent
    return None


def gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return not state or state.startswith("Z")


def main(argv: list[str]) -> int:
    out = Path(argv[1]).resolve()
    seconds = float(argv[2]) if len(argv) > 2 else 20.0
    home = out / "home"
    home.mkdir(parents=True, exist_ok=True)
    environ = {**os.environ, "HOME": str(home), "PATH": f"{FAKE}{os.pathsep}{os.environ['PATH']}",
               "XDG_CONFIG_HOME": str(home / ".config"), "XDG_STATE_HOME": str(home / ".local" / "state"),
               "XDG_CACHE_HOME": str(home / ".cache"), "XDG_RUNTIME_DIR": str(home / "run")}
    (home / "run").mkdir(exist_ok=True)
    (home / "Library" / "Caches").mkdir(parents=True, exist_ok=True)  # as on every Mac (the lock is there)
    os.environ.update(environ)  # the folders of the platform below are those of the made-up home
    sys.path.insert(0, str(ROOT))
    from bellwether import platform  # noqa: PLC0415

    folder = platform.state_home() / "bellwether"
    log, start_log = folder / "bellwether.log", folder / "start.log"
    if event_children(table()):
        print("FAIL an event stream of the made-up herdr-core runs already")
        return 1
    began = time.monotonic()
    subprocess.run(["/bin/sh", str(ROOT / "scripts" / "start.sh")], env=environ, check=True, timeout=30)
    print(f"start.sh returned after {time.monotonic() - began:.1f} s")
    wanted = ["shell: plain", "source: app", "events: connected", "started"]
    if platform.SYSTEM == "darwin":
        wanted.append("herdr-app: PATH; herdr-core: PATH")
    text = ""
    while time.monotonic() - began < seconds:
        text = log.read_text(errors="replace") if log.is_file() else ""
        if all(line in text for line in wanted):
            break
        time.sleep(0.25)
    time.sleep(2)  # some more seconds of the running widget: a late error shows in the log
    text = log.read_text(errors="replace") if log.is_file() else ""
    started = start_log.read_text(errors="replace") if start_log.is_file() else ""
    rows = table()
    children = event_children(rows)
    widgets = {widget_of(rows, child) for child in children} - {None}
    # The processes of the run, for the record (made-up programs only): the widget, the watcher, the stream.
    print("\n".join(f"{pid} {parent} {command}" for pid, (parent, command) in sorted(rows.items())
                    if str(FAKE) in command or pid in widgets or "bellwether.platform.guard" in command))
    checks = {f"log has {line!r}": line in text for line in wanted}
    checks["no traceback in the logs"] = "Traceback" not in text + started
    checks["one event child runs"] = len(children) == 1
    checks["one widget started it"] = len(widgets) == 1
    for pid in widgets:
        os.kill(pid, signal.SIGKILL)  # no clean-up of its own: the watcher must see it
    end = time.monotonic() + 3
    while time.monotonic() < end and not all(map(gone, children)):
        time.sleep(0.1)
    checks["the event child is gone 3 s after a SIGKILL of the widget"] = bool(children) and all(map(gone, children))
    checks["the widget is gone"] = bool(widgets) and all(map(gone, widgets))
    # A check that failed must not leave a process of this run behind (the self-test comes next): by pid.
    for pid, (_, command) in table().items():
        if command.endswith(f"{FAKE}/herdr-core events --json") or pid in widgets:
            os.kill(pid, signal.SIGKILL)
    print(f"--- {log.name}\n{text}--- {start_log.name}\n{started}---")
    for name, good in checks.items():
        print(f"{'PASS' if good else 'FAIL'} {name}")
    print(f"smoke run: {time.monotonic() - began:.1f} s")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
