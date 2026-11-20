"""The Windows module of the platform, on any system: its folders, its lock, its shell, its Win32 calls with a made-up
Win32 object, its job for the event child, its wait for a pipe, its process host with a made-up psutil, and the
client with it. Tests that need a real Windows are marked `on_windows` (they run on the Windows runner of the
workflow)."""
import ast
import ctypes
import logging
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from bellwether.platform import windows

on_windows = pytest.mark.skipif(sys.platform != "win32", reason="needs Windows")
ROOT = Path(__file__).parent.parent
# The Python of the tests that start real processes: the interpreter itself, not the launcher of the virtual
# environment (on Windows it runs the interpreter as a child of its own, a process more in each tree). The code of
# these processes needs only the standard library and the platform package (from the checkout).
PYTHON = getattr(sys, "_base_executable", sys.executable)


def records(caplog):
    return [(r.levelno, r.getMessage()) for r in caplog.records]


class FakeWin32:
    """A made-up Win32 object: the same methods as windows.Win32, each call recorded. `tops` are the top-level
    windows, the topmost first: (hwnd, pid, visible, minimized, owned); `names` the program of each pid."""

    def __init__(self, tops=(), names=None, foreground_ok=True, ex_style=0, style=0x96000000, job=0x50,
                 joins=True, ready=()):
        self.calls = []
        self.tops, self.names = list(tops), dict(names or {})
        self.foreground_ok, self.ex = foreground_ok, {0x7f00: ex_style}
        self.style_value, self.job, self.joins = style, job, joins
        self.ready = set(ready)
        self.front = 0

    def windows(self):
        self.calls.append(("windows",))
        return list(self.tops)

    def process_name(self, pid):
        self.calls.append(("process_name", pid))
        return self.names.get(pid)

    def window_pid(self, hwnd):
        return {top[0]: top[1] for top in self.tops}.get(hwnd, os.getpid() if hwnd == 0x7f00 else 0)

    def is_iconic(self, hwnd):
        return any(top[0] == hwnd and top[3] for top in self.tops)

    def is_visible(self, hwnd):
        return True

    def restore(self, hwnd):
        self.calls.append(("restore", hwnd))
        return True

    def set_foreground(self, hwnd):
        self.calls.append(("set_foreground", hwnd))
        if self.foreground_ok:
            self.front = hwnd
        return self.foreground_ok

    def foreground_window(self):
        return self.front

    def class_name(self, hwnd):
        return "Qt612QWindowToolSaveBits"

    def style(self, hwnd):
        return self.style_value

    def ex_style(self, hwnd):
        return self.ex.get(hwnd, 0)

    def set_ex_style(self, hwnd, value):
        self.calls.append(("set_ex_style", hwnd, value))
        self.ex[hwnd] = value

    def set_topmost(self, hwnd):
        self.calls.append(("set_topmost", hwnd))
        self.ex[hwnd] = self.ex.get(hwnd, 0) | windows.WS_EX_TOPMOST
        return True

    def kill_job(self):
        self.calls.append(("kill_job",))
        return self.job

    def assign(self, job, pid):
        self.calls.append(("assign", job, pid))
        return self.joins

    def pipe_ready(self, descriptor):
        self.calls.append(("pipe_ready", descriptor))
        return descriptor in self.ready


def through(function):
    return function()


# ----- the module imports on every system -----

def test_the_module_imports_no_module_of_windows_at_its_top():
    tree = ast.parse(Path(windows.__file__).read_text(encoding="utf-8"))
    top = [alias.name for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names]
    top += [node.module for node in tree.body if isinstance(node, ast.ImportFrom) and node.module]
    assert not {"msvcrt", "winreg", "psutil", "wintypes", "ctypes.wintypes", "_winapi"} & set(top)


# ----- the folders, the lock, the shell -----

def test_the_folders_are_in_appdata_and_in_the_folder_of_the_program_in_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("XDG_CONFIG_HOME", "/made/up")  # the XDG rules are not those of Windows
    assert windows.config_home() == tmp_path / "Roaming"
    assert windows.state_home() == tmp_path / "Local" / "bellwether" / "Logs"
    assert windows.cache_home() == tmp_path / "Local" / "bellwether" / "Cache"
    assert windows.runtime_dir() == tmp_path / "Local" / "bellwether"
    monkeypatch.setenv("APPDATA", "relative")  # not valid: the default in the home folder
    monkeypatch.delenv("LOCALAPPDATA")
    assert windows.config_home() == Path.home() / "AppData" / "Roaming"
    assert windows.runtime_dir() == Path.home() / "AppData" / "Local" / "bellwether"


class FakeMsvcrt:
    """msvcrt.locking as Windows does it: one lock of the first byte per file, for one open file at a time."""
    LK_NBLCK = 2

    def __init__(self):
        self.held, self.calls = {}, []

    def locking(self, fileno, mode, size):
        status = os.fstat(fileno)
        name = (status.st_dev, status.st_ino)
        self.calls.append((mode, size, os.lseek(fileno, 0, os.SEEK_CUR)))
        if name in self.held:
            raise PermissionError(13, "made-up: locked")
        self.held[name] = fileno


def test_the_lock_takes_the_first_byte_without_truncating_and_a_second_lock_is_refused(tmp_path):
    fake = FakeMsvcrt()
    path = tmp_path / "made" / "bellwether.lock"  # the folder is made
    first = windows.lock(path, msvcrt=lambda: fake)
    assert first is not None and fake.calls == [(2, 1, 0)]
    path.write_text("x")  # an other process wrote into it: a second open must not empty it
    assert windows.lock(path, msvcrt=lambda: fake) is None and path.read_text() == "x"
    first.close()


@on_windows
def test_on_windows_the_lock_of_a_second_open_file_is_refused_until_the_first_is_closed(tmp_path):
    path = tmp_path / "bellwether.lock"
    first = windows.lock(path)
    assert first is not None and windows.lock(path) is None
    first.close()
    again = windows.lock(path)
    assert again is not None
    again.close()


def test_the_shell_is_always_plain_and_another_choice_gets_one_log_line(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    assert windows.shell(None, {}) == "plain" and windows.shell(None, {"BELLWETHER_SHELL": "plain"}) == "plain"
    assert records(caplog) == []
    assert windows.shell(None, {"BELLWETHER_SHELL": "layer"}) == "plain"
    assert records(caplog) == [(logging.WARNING, "BELLWETHER_SHELL='layer': Windows has only the plain shell")]
    assert set(windows.SHELL_FILES) == {"plain"} and windows.SHELL_FILES["plain"].is_file()


def test_qt_gets_no_platform_and_a_plugin_that_is_not_windows_gets_one_log_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    windows.prepare_environment()
    assert "QT_QPA_PLATFORM" not in os.environ and windows.prepare_engine(object()) is None
    windows.prepare_app(SimpleNamespace(platformName=lambda: "windows"))
    assert records(caplog) == []
    windows.prepare_app(SimpleNamespace(platformName=lambda: "offscreen"))
    assert records(caplog) == [(logging.INFO, "the Qt platform is offscreen, not windows: the program gets no set-up "
                                              "of Windows")]


# ----- the Herdr programs, the raise and the start -----

def test_the_programs_are_found_in_path_first_and_the_log_says_where_without_a_path(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    assert windows.find_executables(which=lambda name: f"C:/made/up/{name}.EXE") == (
        "C:/made/up/herdr-app.EXE", "C:/made/up/herdr-core.EXE")
    assert records(caplog) == [(logging.INFO, "herdr-app: PATH; herdr-core: PATH")]


def test_without_path_the_programs_are_found_in_the_folders_of_the_installers(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    app = tmp_path / "Local" / "Programs" / "herdr-app" / "herdr-app.exe"
    core = tmp_path / "home" / ".cargo" / "bin" / "herdr-core.exe"
    for path in (app, core):
        path.parent.mkdir(parents=True)
        path.write_bytes(b"MZ")
    monkeypatch.setattr(windows.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    assert windows.find_executables(which=lambda name: None) == (str(app), str(core))
    core.unlink()
    official = tmp_path / "Local" / "Programs" / "herdr-core" / "herdr-core.exe"
    official.parent.mkdir(parents=True)
    official.write_bytes(b"MZ")
    assert windows.find_executables(which=lambda name: None) == (str(app), str(official))
    monkeypatch.delenv("LOCALAPPDATA")
    assert windows.find_executables(which=lambda name: None) == (None, None)
    assert [message for _, message in records(caplog)] == [
        "herdr-app: %LOCALAPPDATA%\\Programs\\herdr-app; herdr-core: ~\\.cargo\\bin",
        "herdr-app: %LOCALAPPDATA%\\Programs\\herdr-app; herdr-core: %LOCALAPPDATA%\\Programs\\herdr-core",
        "herdr-app: not found; herdr-core: not found"]


HERDR = {41: "herdr-app.exe", 42: "Herdr-App.EXE", 7: "explorer.exe"}


@pytest.mark.parametrize("tops, found", [
    ([(0x10, 7, True, False, False), (0x20, 41, True, False, False)], 0x20),
    ([(0x20, 41, False, False, False), (0x21, 41, True, False, True), (0x22, 42, True, False, False)], 0x22),
    ([(0x20, 41, False, True, False)], 0x20),  # minimized
    ([(0x20, 41, False, False, False), (0x10, 7, True, False, False)], None),  # hidden
    ([], None),
])
def test_the_herdr_window_is_the_topmost_shown_or_minimized_unowned_window_of_herdr_app(tops, found):
    api = FakeWin32(tops, HERDR)
    assert windows.app_window(api) == found
    asked = [call[1] for call in api.calls if call[0] == "process_name"]
    assert len(asked) == len(set(asked))  # one question for each process


def test_the_raise_restores_a_minimized_window_and_asks_for_the_foreground_on_the_main_thread():
    api, used = FakeWin32([(0x20, 41, False, True, False)], HERDR), []
    assert windows.raise_app(None, {}, win32=lambda: api,
                             main_thread=lambda function: used.append(1) or function()) is True
    assert used == [1] and api.calls[-2:] == [("restore", 0x20), ("set_foreground", 0x20)]


@pytest.mark.parametrize("api, line", [
    (FakeWin32([], HERDR), "no window of the Herdr app was found"),
    (FakeWin32([(0x20, 41, True, False, False)], HERDR, foreground_ok=False),
     "Windows did not bring the Herdr window to the front (SetForegroundWindow refused)"),
])
def test_a_raise_that_finds_no_window_or_is_refused_is_false_with_one_log_line(api, line, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    assert windows.raise_app(None, {}, win32=lambda: api, main_thread=through) is False
    assert records(caplog) == [(logging.INFO, line)]


def test_a_main_thread_that_does_not_answer_and_no_win32_give_false(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")

    def no_answer(function):
        raise TimeoutError("made-up")

    assert windows.raise_app(None, {}, win32=lambda: FakeWin32(), main_thread=no_answer) is False
    assert windows.raise_app(None, {}, win32=lambda: None) is False
    assert records(caplog) == [(logging.INFO, "the raise of the Herdr window failed (TimeoutError)")]


def test_the_start_is_a_detached_process_out_of_our_job_with_no_console_in_the_home_folder():
    started = []
    assert windows.start_app(None, "C:/made/up/herdr-app.exe", {}, win32=lambda: FakeWin32(),
                             popen=lambda argv, **options: started.append((argv, options))) == 0
    assert started == [(["C:/made/up/herdr-app.exe"], {
        "creationflags": 0x8 | 0x200 | 0x01000000, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL, "close_fds": True, "cwd": str(Path.home())})]


def test_a_job_that_allows_no_breakaway_starts_the_app_in_it_and_an_error_of_the_start_goes_to_the_caller():
    flags = []

    def popen(argv, creationflags, **options):
        flags.append(creationflags)
        if creationflags & windows.CREATE_BREAKAWAY_FROM_JOB:
            raise PermissionError(5, "made-up: access denied")

    assert windows.start_app(None, "x.exe", {}, win32=lambda: None, popen=popen) == 0
    assert flags == [0x8 | 0x200 | 0x01000000, 0x8 | 0x200]
    with pytest.raises(FileNotFoundError):
        windows.start_app(None, "x.exe", {}, win32=lambda: None,
                          popen=lambda argv, **options: (_ for _ in ()).throw(FileNotFoundError("x")))


def test_with_a_herdr_window_there_the_app_is_not_started_again_and_the_jump_shows_its_failure(caplog):
    """Windows refused the raise: a second start would not show the window, so the row shows the failure."""
    caplog.set_level(logging.INFO, logger="bellwether")
    started = []
    api = FakeWin32([(0x20, 41, True, False, False)], HERDR)
    assert windows.start_app(None, "x.exe", {}, win32=lambda: api, popen=lambda *a, **k: started.append(a)) == 1
    assert started == [] and records(caplog) == [(logging.INFO, "the Herdr app has a window: it is not started again")]


def test_the_environment_of_a_command_has_no_caller_variable_whatever_the_case_of_its_name(monkeypatch):
    monkeypatch.setenv("HC_TERMINAL_ID", "t1")
    monkeypatch.setenv("hc_scope", "made-up")
    monkeypatch.setenv("BELLWETHER_MADE_UP", "kept")
    argv = ["C:/made/up/herdr-core.exe", "send", "--", "t1", "x"]
    given, env = windows.clean_environment(argv, ("HC_TERMINAL_ID", "HC_SCOPE", "HC_TERMINAL_SOCKET"), {})
    assert given == argv and given is not argv
    assert "HC_TERMINAL_ID" not in env and "hc_scope" not in env and env["BELLWETHER_MADE_UP"] == "kept"


def test_each_program_of_the_client_gets_no_console_window(monkeypatch):
    from bellwether import client as client_module
    monkeypatch.setattr(client_module, "platform", windows)
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **options: seen.append(options))
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **options: seen.append(options))
    client_module._run(["herdr-app", "ls"])
    client_module._spawn(["herdr-core", "send"], env={"PATH": "x"})
    assert [options["creationflags"] for options in seen] == [0x08000000] * 2 and seen[1]["env"] == {"PATH": "x"}


def test_the_client_with_the_windows_module_takes_no_command_of_an_other_system(monkeypatch):
    from bellwether import client as client_module
    monkeypatch.setattr(client_module, "platform", windows)
    client_module.HerdrClient("app", "core")
    with pytest.raises(TypeError):
        client_module.HerdrClient("app", "core", launcher="x")


# ----- the windows of the program -----

class QtWindow:
    def __init__(self, visible=True):
        self.visible, self.properties = visible, {}
        self.slots = []
        self.visibleChanged = SimpleNamespace(connect=self.slots.append)

    def winId(self):
        return 0x7f00

    def setProperty(self, name, value):
        self.properties[name] = value

    def property(self, name):
        return self.properties.get(name)

    def isVisible(self):
        return self.visible

    def show(self):
        self.visible = True
        for slot in self.slots:
            slot(True)


QT_PANEL = windows.WS_EX_NOACTIVATE | windows.WS_EX_TOOLWINDOW | windows.WS_EX_TOPMOST


def test_a_panel_that_has_the_styles_of_qt_gets_nothing_more(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    api, window = FakeWin32(ex_style=QT_PANEL), QtWindow()
    windows.prepare_window(window, "panel", win32=lambda: api)
    assert api.calls == [] and window.properties == {"bellwetherAdded": ""} and records(caplog) == []


def test_a_panel_without_them_gets_no_activation_no_taskbar_button_and_topmost_with_one_log_line(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    api, window = FakeWin32(ex_style=0x100), QtWindow()
    windows.prepare_window(window, "panel", win32=lambda: api)
    assert api.calls == [("set_ex_style", 0x7f00, 0x100 | windows.WS_EX_NOACTIVATE | windows.WS_EX_TOOLWINDOW),
                         ("set_topmost", 0x7f00)]
    assert window.properties["bellwetherAdded"] == "WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, HWND_TOPMOST"
    assert records(caplog) == [(logging.INFO, "the panel got WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, HWND_TOPMOST, which "
                                              "Qt did not give")]


def test_a_failed_call_leaves_the_panel_of_qt_with_one_log_line(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    api = FakeWin32()
    api.ex_style = lambda hwnd: (_ for _ in ()).throw(OSError("made-up"))
    windows.prepare_window(QtWindow(), "panel", win32=lambda: api)
    assert records(caplog) == [(logging.WARNING, "the panel could not get the styles of a Windows panel (OSError): "
                                                 "Qt's window as it is")]


@pytest.mark.parametrize("role", ["answer", "options"])
def test_the_answer_and_the_options_window_ask_for_the_foreground_at_each_show(role):
    api, window = FakeWin32(), QtWindow(visible=False)
    windows.prepare_window(window, role, win32=lambda: api)
    assert api.calls == []
    window.show()
    window.slots[0](False)  # hidden: nothing
    window.show()
    assert api.calls == [("set_foreground", 0x7f00)] * 2
    assert window.properties["bellwetherActivation"] == "SetForegroundWindow"
    shown = QtWindow(visible=True)
    windows.prepare_window(shown, role, win32=lambda: api)  # shown already: at once
    assert api.calls[-1] == ("set_foreground", 0x7f00)


def test_a_refused_foreground_is_a_fact_and_one_log_line(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    api, window = FakeWin32(foreground_ok=False), QtWindow()
    windows.prepare_window(window, "options", win32=lambda: api)
    assert window.properties["bellwetherActivation"] == "SetForegroundWindow refused"
    assert records(caplog) == [(logging.INFO, "Windows did not bring the window to the front (SetForegroundWindow "
                                              "refused): its taskbar button flashes")]


def test_off_screen_the_program_makes_no_native_call(app):
    assert app.platformName() == "offscreen"
    window = QtWindow()
    windows.prepare_window(window, "panel")
    assert window.properties == {} and windows.window_facts(window) == {}


def test_the_facts_of_the_native_window_for_the_self_test():
    api, window = FakeWin32(ex_style=QT_PANEL), QtWindow()
    windows.prepare_window(window, "panel", win32=lambda: api)
    facts = windows.window_facts(window, win32=lambda: api)
    assert facts == {
        "class": "Qt612QWindowToolSaveBits", "style": 0x96000000,
        "style_names": ["WS_POPUP", "WS_VISIBLE", "WS_CLIPSIBLINGS", "WS_CLIPCHILDREN"],
        "ex_style": QT_PANEL, "ex_style_names": ["WS_EX_TOPMOST", "WS_EX_TOOLWINDOW", "WS_EX_NOACTIVATE"],
        "topmost": True, "no_activate": True, "tool_window": True, "visible": True, "foreground": False,
        "foreground_of_this_program": False, "process_is_this_program": True, "added_by_program": "",
        "activation_asked": ""}
    api.front = 0x7f00
    assert windows.window_facts(window, win32=lambda: api)["foreground_of_this_program"] is True


# ----- the event child: a job that ends it with this process -----

class Child:
    pid = 4321


def test_the_event_child_has_no_console_and_joins_the_job_that_ends_it_with_the_program(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    seen, api = {}, FakeWin32()
    child = windows.spawn_child(["C:/made/up/herdr-core.exe", "events", "--json"], win32=lambda: api,
                                popen=lambda argv, **options: seen.update(options, argv=argv) or Child())
    assert isinstance(child, Child)
    assert seen == {"argv": ["C:/made/up/herdr-core.exe", "events", "--json"], "stdin": subprocess.DEVNULL,
                    "stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL, "bufsize": 0, "creationflags": 0x08000000}
    assert api.calls == [("kill_job",), ("assign", 0x50, 4321)] and records(caplog) == []


@pytest.mark.parametrize("api", [FakeWin32(job=None), FakeWin32(joins=False), None])
def test_a_child_that_cannot_join_the_job_still_runs_with_one_log_line(api, caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="bellwether")
    monkeypatch.setattr(windows, "_job_failed", [])
    for _ in range(2):
        assert isinstance(windows.spawn_child(["x"], win32=lambda: api, popen=lambda argv, **o: Child()), Child)
    assert records(caplog) == [(logging.WARNING, "the event child is not in a job that ends it with the program: it can "
                                                 "outlive a killed program")]


def test_the_limits_of_the_job_end_its_processes_when_it_is_closed():
    limits = windows.kill_on_close_limits()
    # KILL_ON_JOB_CLOSE, and SILENT_BREAKAWAY_OK: a process that the child starts (the server of herdr-core, which
    # runs the terminals) is not in the job and never ends with the panel.
    assert limits.BasicLimitInformation.LimitFlags == 0x2000 | 0x1000
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        assert ctypes.sizeof(limits) == 144  # JOBOBJECT_EXTENDED_LIMIT_INFORMATION on 64-bit Windows


@on_windows
def test_on_windows_a_process_that_the_event_child_starts_does_not_end_with_the_program(tmp_path):
    """The server of herdr-core, started by `herdr-core events`, must outlive the panel: only the child is in the job."""
    psutil = pytest.importorskip("psutil")
    grandchild = (f"import os, time; open({str(tmp_path / 'pid')!r}, 'w').write(str(os.getpid())); time.sleep(30)")
    child_code = (f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {grandchild!r}], "
                  f"creationflags=0x8); print('started', flush=True); time.sleep(60)")
    parent = subprocess.Popen([PYTHON, "-c", textwrap.dedent(f"""
        import sys, time
        from bellwether.platform import windows
        process = windows.spawn_child([sys.executable, "-c", {child_code!r}])
        print(process.stdout.readline().decode().strip(), flush=True)
        time.sleep(60)
    """)], stdout=subprocess.PIPE, cwd=ROOT)
    other = None
    try:
        assert parent.stdout.readline().strip() == b"started"
        end = time.monotonic() + 5
        while not (tmp_path / "pid").exists() and time.monotonic() < end:
            time.sleep(0.05)
        other = int((tmp_path / "pid").read_text())
        parent.kill()
        parent.wait(10)
        time.sleep(1.0)
        assert psutil.pid_exists(other), "a process that the event child started ended with the program"
    finally:
        parent.kill()
        parent.wait(10)
        parent.stdout.close()
        if other is not None and psutil.pid_exists(other):
            psutil.Process(other).kill()


@on_windows
def test_on_windows_a_killed_parent_leaves_no_event_child():
    """The parent uses spawn_child of the Windows module; it is killed (TerminateProcess: no clean-up of its own).
    The system closes the job and ends the child."""
    child_code = "import os, time; print(os.getpid(), flush=True); time.sleep(60)"
    parent = subprocess.Popen([PYTHON, "-c", textwrap.dedent(f"""
        import sys, time
        from bellwether.platform import windows
        process = windows.spawn_child([sys.executable, "-c", {child_code!r}])
        print(process.stdout.readline().decode().strip(), flush=True)
        time.sleep(60)
    """)], stdout=subprocess.PIPE, cwd=ROOT)
    psutil = pytest.importorskip("psutil")
    try:
        child = int(parent.stdout.readline())
        assert psutil.pid_exists(child)
        parent.kill()
        parent.wait(10)
        end = time.monotonic() + 3
        while time.monotonic() < end and psutil.pid_exists(child):
            time.sleep(0.05)
        assert not psutil.pid_exists(child), "the event child lives on after its parent was killed"
    finally:
        parent.kill()
        parent.wait(10)
        parent.stdout.close()


# ----- the wait for the event stream -----

def test_the_wait_looks_at_each_pipe_until_one_has_data_or_the_time_is_over():
    api, now, sleeps = FakeWin32(ready={7}), [0.0], []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    assert windows.readable([5, 7], 1.0, win32=lambda: api, sleep=sleep, clock=lambda: now[0]) == [7]
    assert sleeps == []
    api.ready = set()
    assert windows.readable([5, 7], 0.12, win32=lambda: api, sleep=sleep, clock=lambda: now[0]) == []
    assert [round(s, 3) for s in sleeps] == [0.05, 0.05, 0.02]


@on_windows
def test_on_windows_the_wait_sees_data_and_the_end_of_a_real_pipe():
    read_end, write_end = os.pipe()
    try:
        assert windows.readable([read_end], 0.1) == []
        os.write(write_end, b"x")
        assert windows.readable([read_end], 0.1) == [read_end]
        os.read(read_end, 1)
        os.close(write_end)
        write_end = None
        assert windows.readable([read_end], 0.1) == [read_end] and os.read(read_end, 1) == b""
    finally:
        os.close(read_end)
        if write_end is not None:
            os.close(write_end)


# ----- the Win32 calls on a real Windows -----

@on_windows
def test_on_windows_the_window_of_a_process_is_found_by_its_pid_and_its_program_has_a_name():
    api = windows.load_win32()
    assert api is not None and api.process_name(os.getpid()).lower().startswith("python")
    shown = subprocess.Popen([PYTHON, "-c", "import tkinter; r = tkinter.Tk(); r.title('made-up'); "
                                                    "r.after(20000, r.destroy); r.mainloop()"])
    try:
        end, hwnd = time.monotonic() + 10, None
        while hwnd is None and time.monotonic() < end:
            hwnd = windows.app_window(api, pids={shown.pid})
            time.sleep(0.1)
        assert hwnd, "the made-up window was not found"
        assert api.window_pid(hwnd) == shown.pid and api.class_name(hwnd)
        assert isinstance(windows.raise_app(None, {}, pids={shown.pid}, main_thread=through), bool)
    finally:
        shown.kill()
        shown.wait(10)


# ----- the process host and the icon -----

class Proc:
    def __init__(self, start):
        self.start = start

    def create_time(self):
        return self.start


def test_the_start_of_a_process_is_never_the_form_of_claude_code_so_a_session_gives_no_model(tmp_path):
    """Claude Code writes procStartFt on Windows (its form is not known): no file is taken, the time shows."""
    import json
    from bellwether import sessions
    psutil = SimpleNamespace(Error=Exception, Process=lambda pid: Proc(1795191483.25))
    host = windows.Host(tmp_path, psutil)
    assert host.start_ticks(700) == "1795191483.25" and host.start_ticks(700) == host.start_ticks(700)
    folder = tmp_path / ".claude" / "sessions"
    folder.mkdir(parents=True)
    (folder / "700.json").write_text(json.dumps({"pid": 700, "procStartFt": "134077000000000000",
                                                 "sessionId": "0" * 8 + "-0000-0000-0000-" + "0" * 12,
                                                 "startedAt": 1795191483000}))
    assert sessions.read_claude(host, [700]).reason == "other_process"


def test_the_host_without_psutil_knows_no_process_and_says_so(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    host = windows.process_host(psutil=lambda: None)
    assert (host.start_ticks(1), host.children(1), host.open_files(1)) == (None, [], [])
    assert records(caplog) == [(logging.WARNING, "psutil cannot be imported: the rows show the time of the terminal "
                                                 "and no model")]


def test_the_icon_is_the_svg_beside_herdr_app(tmp_path):
    app = tmp_path / "herdr-app.exe"
    app.write_bytes(b"MZ")
    assert windows.app_icon_file(which=lambda name: str(app)) is None  # no svg: the circle
    (tmp_path / "herdr-app.svg").write_text("<svg/>")
    assert windows.app_icon_file(which=lambda name: str(app)) == tmp_path / "herdr-app.svg"
    assert windows.app_icon_file(which=lambda name: None) is None or os.environ.get("LOCALAPPDATA")


@on_windows
def test_on_windows_psutil_sees_a_file_that_a_process_holds_open_with_a_lock(tmp_path):
    """The thread locks of Codex: a file held open (and locked). psutil.open_files lists it on Windows?"""
    psutil = pytest.importorskip("psutil")
    path = tmp_path / "made-up.lock"
    holder = windows.lock(path)
    try:
        names = [os.path.normcase(item.path) for item in psutil.Process().open_files()]
        assert os.path.normcase(str(path)) in names
    finally:
        holder.close()
