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
PYTHON = ROOT / ".venv" / "bin" / "python"


def pids(pattern: str) -> list[int]:
    """The processes whose whole command line matches `pattern` (an extended regular expression of pgrep)."""
    done = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    return [int(word) for word in done.stdout.split()]


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
    # Only a widget of this tree, started here: anchored to the python of this checkout.
    widget = f"^{PYTHON} -m bellwether$"
    events = f"^/bin/sh {FAKE}/herdr-core events --json$"
    if pids(widget):
        print(f"FAIL a widget of this checkout runs already: {pids(widget)}")
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
    found = pids(widget)
    children = pids(events)
    checks = {f"log has {line!r}": line in text for line in wanted}
    checks["no traceback in the logs"] = "Traceback" not in text + started
    checks["one widget runs"] = len(found) == 1
    checks["one event child runs"] = len(children) == 1
    for pid in found:
        os.kill(pid, signal.SIGKILL)
    time.sleep(3)
    checks["the event child is gone 3 s after a SIGKILL of the widget"] = pids(events) == []
    for pid in pids(events):  # a check that failed must not leave the child behind
        os.kill(pid, signal.SIGKILL)
    print(f"--- {log.name}\n{text}--- {start_log.name}\n{started}---")
    for name, good in checks.items():
        print(f"{'PASS' if good else 'FAIL'} {name}")
    print(f"smoke run: {time.monotonic() - began:.1f} s")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
