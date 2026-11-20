"""scripts/start.sh with a made-up program in the place of the widget: what it does with start.log."""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "start.sh"
LIMIT = 1024 * 1024


def made_up_system(tmp_path, system: str, setsid: bool) -> str:
    """A PATH with the programs that the script uses, `uname` that names `system`, and setsid only when asked."""
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in ("dirname", "readlink", "mkdir", "wc", "nohup", "cat") + (("setsid",) if setsid else ()):
        found = shutil.which(name)
        assert found, name
        (tools / name).symlink_to(found)
    (tools / "uname").write_text(f'#!/bin/sh\n[ "$1" = "-s" ] && echo {system}\n')
    (tools / "uname").chmod(0o755)
    return str(tools)


def start(tmp_path, old_log: bytes | None, system: str | None = None, setsid: bool = True,
          log: Path | None = None) -> Path:
    """Run a copy of the script in a made-up repository. Return the start.log after the program wrote its line.
    `system`: the answer of a made-up `uname -s` (None: the real system); `log`: where the start.log must be."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts" / "start.sh")
    python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text('#!/bin/sh\necho "made-up widget: $*"\n')
    python.chmod(0o755)
    if log is None:  # the log folder of the real system (`uname -s`): macOS has its Library
        darwin = system == "Darwin" or (system is None and sys.platform == "darwin")
        log = (tmp_path / "home" / "Library" / "Logs" if darwin else tmp_path / "state") / "bellwether" / "start.log"
    if old_log is not None:
        log.parent.mkdir(parents=True)
        log.write_bytes(old_log)
    env = {**os.environ, "XDG_STATE_HOME": str(tmp_path / "state"), "HOME": str(tmp_path / "home")}
    if system is not None:
        env["PATH"] = made_up_system(tmp_path, system, setsid)
    subprocess.run(["/bin/sh", str(root / "scripts" / "start.sh")], env=env, check=True, timeout=10)
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


def test_on_macos_the_start_log_is_in_the_logs_folder_of_the_library_and_nohup_starts_the_widget(tmp_path):
    """macOS has no setsid: nohup in the background. The XDG folder is not the log folder there."""
    log = start(tmp_path, None, system="Darwin", setsid=False)
    assert log.read_text() == "made-up widget: -m bellwether\n"
    assert not (tmp_path / "state").exists()


@pytest.mark.skipif(shutil.which("setsid") is None, reason="no setsid here")
def test_on_macos_with_a_setsid_the_start_log_is_in_the_library_too(tmp_path):
    log = start(tmp_path, b"an older line\n", system="Darwin", setsid=True)
    assert log.read_text() == "an older line\nmade-up widget: -m bellwether\n"


def test_on_linux_without_setsid_nohup_starts_the_widget_and_the_log_stays_in_the_xdg_folder(tmp_path):
    log = start(tmp_path, None, system="Linux", setsid=False)
    assert log.read_text() == "made-up widget: -m bellwether\n"
    assert not (tmp_path / "home" / "Library").exists()
