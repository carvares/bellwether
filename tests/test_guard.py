"""The watcher of the event child (bellwether/platform/guard.py), with real processes: it runs on every system."""
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from bellwether.platform import guard, macos

ROOT = Path(__file__).parent.parent
# A made-up event child: it writes its pid and one line, then nothing for 60 s (a child that writes would end by
# itself at its next write into a pipe with no reader: the watcher must end a quiet one too).
CHILD = [sys.executable, "-c", textwrap.dedent("""
    import os, time
    print(os.getpid(), flush=True)
    print("made-up event", flush=True)
    time.sleep(60)
""")]


def gone(pid):
    """True when the process is gone, or a zombie that waits for its parent (it runs no more)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    stat = Path(f"/proc/{pid}/stat")
    if stat.exists():
        try:
            return stat.read_text().rsplit(")", 1)[1].split()[0] == "Z"
        except (OSError, IndexError):
            return True
    done = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return not done.stdout.strip() or done.stdout.strip().startswith("Z")


def wait_gone(pids, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if all(gone(pid) for pid in pids):
            return True
        time.sleep(0.05)
    return all(gone(pid) for pid in pids)


def guarded(command):
    """The watcher of this process (the test is its parent) for `command`, as spawn_child of macOS starts it."""
    return subprocess.Popen([sys.executable, "-m", "bellwether.platform.guard", str(os.getpid()), *command],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT)


def test_the_child_writes_into_the_pipe_itself_and_the_watcher_exits_with_its_code():
    watcher = guarded([sys.executable, "-c", "print('made-up line'); raise SystemExit(7)"])
    out, err = watcher.communicate(timeout=30)
    assert (watcher.returncode, out, err) == (7, b"made-up line\n", b"")


def test_a_child_ended_by_a_signal_gives_128_and_the_signal():
    watcher = guarded([sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"])
    assert watcher.wait(timeout=30) == 128 + signal.SIGKILL


def test_a_sigterm_to_the_watcher_ends_the_child_and_the_watcher():
    watcher = guarded(CHILD)
    try:
        child = int(watcher.stdout.readline())
        assert watcher.stdout.readline() == b"made-up event\n"
        watcher.terminate()
        assert watcher.wait(timeout=5) == 128 + signal.SIGTERM
        assert wait_gone([child], 3)
    finally:
        watcher.kill()


def test_a_parent_killed_with_sigkill_leaves_no_child_after_2_seconds(tmp_path):
    """The parent is a program with spawn_child of the macOS module; it is killed with SIGKILL (no clean-up of its
    own). The watcher sees that its parent is gone and ends the event child and itself."""
    parent = subprocess.Popen([sys.executable, "-c", textwrap.dedent(f"""
        import sys, time
        from bellwether.platform import macos
        process = macos.spawn_child({CHILD!r})
        print(process.pid, process.stdout.readline().decode().strip(), flush=True)
        time.sleep(60)
    """)], stdout=subprocess.PIPE, cwd=ROOT)
    try:
        watcher, child = map(int, parent.stdout.readline().split())
        assert not gone(watcher) and not gone(child)
        parent.kill()
        parent.wait()
        assert wait_gone([watcher, child], 2.0), "a process of the event child lives on"
    finally:
        parent.kill()


def test_a_parent_that_is_gone_before_the_start_starts_no_command(tmp_path):
    marker = tmp_path / "started"
    assert guard.run(1, [sys.executable, "-c", f"open({str(marker)!r}, 'w')"], alive=lambda: False) == 1
    time.sleep(0.2)
    assert not marker.exists()


def test_the_check_of_the_parent_ends_the_command_and_gives_1():
    checks = []
    began = time.monotonic()
    code = guard.run(os.getpid(), CHILD, poll=0.05, grace=1.0, alive=lambda: checks.append(1) or len(checks) < 4)
    assert code == 1 and time.monotonic() - began < 5


def test_a_wrong_call_and_a_command_that_cannot_start(capsys):
    assert guard.main(["guard"]) == 2 and guard.main(["guard", "x", "true"]) == 2
    assert capsys.readouterr().err.count(guard.USAGE) == 2
    assert guard.main(["guard", str(os.getppid()), "/made/up/not-there"]) == 127
    assert capsys.readouterr().err == "bellwether guard: the command cannot start (FileNotFoundError)\n"


def test_spawn_child_of_macos_starts_the_watcher_with_this_process_and_a_pipe():
    seen = {}

    def popen(argv, **options):
        seen.update(options, argv=argv)
        return "process"

    assert macos.spawn_child(["/made/up/herdr-core", "events", "--json"], popen=popen) == "process"
    assert seen.pop("argv") == [sys.executable, "-m", "bellwether.platform.guard", str(os.getpid()),
                                "/made/up/herdr-core", "events", "--json"]
    assert seen == {"stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL, "bufsize": 0,
                    "cwd": ROOT.resolve()}
