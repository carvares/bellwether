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
# start.sh is a POSIX shell script: Windows has scripts/start.cmd (below).
posix = pytest.mark.skipif(sys.platform == "win32", reason="start.sh needs a POSIX shell")


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


@posix
def test_the_start_script_adds_to_a_small_start_log(tmp_path):
    log = start(tmp_path, b"an older line\n")
    assert log.read_text() == "an older line\nmade-up widget: -m bellwether\n"


@posix
def test_the_start_script_keeps_a_start_log_of_exactly_the_limit(tmp_path):
    log = start(tmp_path, b"x" * (LIMIT - 1) + b"\n")
    assert log.stat().st_size == LIMIT + len("made-up widget: -m bellwether\n")


@posix
def test_the_start_script_empties_a_start_log_that_is_larger_than_1_mib(tmp_path):
    log = start(tmp_path, b"x" * LIMIT + b"\n")
    assert log.read_text() == "made-up widget: -m bellwether\n"


@posix
def test_the_start_script_makes_the_start_log_when_there_is_none(tmp_path):
    log = start(tmp_path, None)
    assert log.read_text() == "made-up widget: -m bellwether\n"


@posix
def test_on_macos_the_start_log_is_in_the_logs_folder_of_the_library_and_nohup_starts_the_widget(tmp_path):
    """macOS has no setsid: nohup in the background. The XDG folder is not the log folder there."""
    log = start(tmp_path, None, system="Darwin", setsid=False)
    assert log.read_text() == "made-up widget: -m bellwether\n"
    assert not (tmp_path / "state").exists()


@posix
@pytest.mark.skipif(shutil.which("setsid") is None, reason="no setsid here")
def test_on_macos_with_a_setsid_the_start_log_is_in_the_library_too(tmp_path):
    log = start(tmp_path, b"an older line\n", system="Darwin", setsid=True)
    assert log.read_text() == "an older line\nmade-up widget: -m bellwether\n"


@posix
def test_on_linux_without_setsid_nohup_starts_the_widget_and_the_log_stays_in_the_xdg_folder(tmp_path):
    log = start(tmp_path, None, system="Linux", setsid=False)
    assert log.read_text() == "made-up widget: -m bellwether\n"
    assert not (tmp_path / "home" / "Library").exists()


# ----- Windows: scripts/start.cmd and scripts/start_windows.py (the real start runs in the smoke run of the runner) -----

WINDOWS_SCRIPT = SCRIPT.with_name("start.cmd")


def windows_launcher():
    import importlib.util
    spec = importlib.util.spec_from_file_location("start_windows", SCRIPT.with_name("start_windows.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def made_up_checkout(tmp_path):
    root = tmp_path / "repo"
    (root / ".venv" / "Scripts").mkdir(parents=True)
    (root / ".venv" / "Scripts" / "pythonw.exe").write_bytes(b"MZ")
    return root


def test_the_windows_start_runs_pythonw_with_no_console_out_of_the_group_and_its_output_in_start_log(tmp_path):
    module, root, started = windows_launcher(), made_up_checkout(tmp_path), []

    def popen(argv, **options):
        started.append((argv, {k: v for k, v in options.items() if k != "stdout"}, options["stdout"].name))

    assert module.main(popen=popen, folder=tmp_path / "logs", root=root) == 0
    assert started == [([str(root / ".venv" / "Scripts" / "pythonw.exe"), "-m", "bellwether"],
                        {"creationflags": 0x8 | 0x200 | 0x01000000, "stdin": subprocess.DEVNULL,
                         "stderr": subprocess.STDOUT, "cwd": str(root), "close_fds": True},
                        str(tmp_path / "logs" / "start.log"))]


def test_the_windows_start_log_is_emptied_above_1_mib_and_a_job_with_no_breakaway_is_kept(tmp_path):
    module, root, flags = windows_launcher(), made_up_checkout(tmp_path), []
    log = tmp_path / "logs" / "start.log"
    log.parent.mkdir()
    log.write_bytes(b"x" * (LIMIT + 1))

    def popen(argv, creationflags, **options):
        flags.append(creationflags)
        if creationflags & 0x01000000:
            raise PermissionError(5, "made-up: access denied")

    assert module.main(popen=popen, folder=log.parent, root=root) == 0
    assert flags == [0x8 | 0x200 | 0x01000000, 0x8 | 0x200] and log.read_bytes() == b""
    log.write_bytes(b"x" * LIMIT)
    module.main(popen=lambda argv, **options: None, folder=log.parent, root=root)
    assert log.stat().st_size == LIMIT


def test_the_windows_start_without_the_environment_of_the_checkout_says_what_to_do(tmp_path, capsys):
    module = windows_launcher()
    assert module.main(popen=lambda *a, **k: pytest.fail("no start"), folder=tmp_path, root=tmp_path) == 1
    assert "pythonw.exe not found, run uv sync in" in capsys.readouterr().err


def test_the_windows_log_folder_is_the_one_of_the_program(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert windows_launcher().log_folder() == tmp_path / "bellwether" / "Logs" / "bellwether"


def test_start_cmd_runs_the_launcher_with_the_pythonw_of_the_checkout_and_has_windows_line_ends():
    data = WINDOWS_SCRIPT.read_bytes()
    assert data.count(b"\r\n") == data.count(b"\n") and data.startswith(b"@echo off\r\n")
    text = data.decode()
    assert '"%root%\\.venv\\Scripts\\pythonw.exe" "%root%\\scripts\\start_windows.py"' in text
    assert 'for %%I in ("%~dp0..") do set "root=%%~fI"' in text and "exit /b %errorlevel%" in text
