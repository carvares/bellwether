"""scripts/start.sh with a made-up program in the place of the widget: what it does with start.log."""
import os
import shutil
import subprocess
import time
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "start.sh"
LIMIT = 1024 * 1024


def start(tmp_path, old_log: bytes | None) -> Path:
    """Run a copy of the script in a made-up repository. Return the start.log after the program wrote its line."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts" / "start.sh")
    python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text('#!/bin/sh\necho "made-up widget: $*"\n')
    python.chmod(0o755)
    log = tmp_path / "state" / "bellwether" / "start.log"
    if old_log is not None:
        log.parent.mkdir(parents=True)
        log.write_bytes(old_log)
    env = {**os.environ, "XDG_STATE_HOME": str(tmp_path / "state"), "HOME": str(tmp_path / "home")}
    subprocess.run(["sh", str(root / "scripts" / "start.sh")], env=env, check=True, timeout=10)
    end = time.monotonic() + 5
    while time.monotonic() < end and not (log.is_file() and log.read_bytes().endswith(b"-m bellwether\n")):
        time.sleep(0.02)
    return log


def test_the_start_script_adds_to_a_small_start_log(tmp_path):
    log = start(tmp_path, b"an older line\n")
    assert log.read_text() == "an older line\nmade-up widget: -m bellwether\n"


def test_the_start_script_keeps_a_start_log_of_exactly_the_limit(tmp_path):
    log = start(tmp_path, b"x" * (LIMIT - 1) + b"\n")
    assert log.stat().st_size == LIMIT + len("made-up widget: -m bellwether\n")


def test_the_start_script_empties_a_start_log_that_is_larger_than_1_mib(tmp_path):
    log = start(tmp_path, b"x" * LIMIT + b"\n")
    assert log.read_text() == "made-up widget: -m bellwether\n"


def test_the_start_script_makes_the_start_log_when_there_is_none(tmp_path):
    log = start(tmp_path, None)
    assert log.read_text() == "made-up widget: -m bellwether\n"
