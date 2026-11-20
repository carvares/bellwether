"""The macOS module of the platform, on any system: its folders, its lock, its shell, the commands it builds, its
native window calls with a fake AppKit, its process host with a fake psutil, and the client with it. Tests that
need a real Mac are marked `on_mac` (they run on the macOS runner of the workflow)."""
import ast
import json
import logging
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bellwether.platform import macos
from tests.fake_appkit import make_kit

on_mac = pytest.mark.skipif(sys.platform != "darwin", reason="needs macOS")


def records(caplog):
    return [(r.levelno, r.getMessage()) for r in caplog.records]


# ----- the module imports on every system -----

def test_the_module_imports_no_module_of_macos_at_its_top():
    tree = ast.parse(Path(macos.__file__).read_text())
    top = [alias.name for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
           for alias in node.names] + [node.module for node in tree.body if isinstance(node, ast.ImportFrom) and node.module]
    assert not {"AppKit", "objc", "Foundation", "Quartz", "psutil"} & set(top)


# ----- the folders, the lock, the shell -----

def test_the_folders_are_those_of_the_library_of_the_user(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", "/made/up")  # the XDG rules are not those of macOS
    monkeypatch.setenv("TMPDIR", "/made/up/tmp")
    assert macos.config_home() == tmp_path / "Library" / "Application Support"
    assert macos.state_home() == tmp_path / "Library" / "Logs"
    assert macos.cache_home() == tmp_path / "Library" / "Caches"
    assert macos.runtime_dir() == tmp_path / "Library" / "Caches"  # not $TMPDIR: the same folder for every start


def test_the_lock_is_the_lock_of_the_posix_systems(tmp_path):
    from bellwether.platform import posix
    assert macos.lock is posix.lock
    first = macos.lock(tmp_path / "bellwether.lock")
    assert first is not None and macos.lock(tmp_path / "bellwether.lock") is None
    first.close()
    again = macos.lock(tmp_path / "bellwether.lock")
    assert again is not None
    again.close()


def test_the_shell_is_always_plain_and_another_choice_gets_one_log_line(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    assert macos.shell(None, {}) == "plain"
    assert macos.shell(None, {"BELLWETHER_SHELL": "plain"}) == "plain"
    assert records(caplog) == []
    assert macos.shell(None, {"BELLWETHER_SHELL": "layer"}) == "plain"
    assert records(caplog) == [(logging.WARNING, "BELLWETHER_SHELL='layer': macOS has only the plain shell")]
    assert set(macos.SHELL_FILES) == {"plain"} and macos.SHELL_FILES["plain"].is_file()


def test_qt_gets_no_platform_and_the_engine_no_import_path(monkeypatch):
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.delenv("QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM", raising=False)
    assert macos.prepare_environment(appkit_found=False) is None
    assert "QT_QPA_PLATFORM" not in macos.os.environ
    assert "QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM" not in macos.os.environ  # no pyobjc: Qt's own way
    assert macos.prepare_engine(object()) is None


def test_with_pyobjc_qt_does_not_make_the_program_a_foreground_app_that_it_activates_at_its_start(monkeypatch):
    monkeypatch.delenv("QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM", raising=False)
    macos.prepare_environment(appkit_found=True)
    assert macos.os.environ["QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM"] == "1"
    monkeypatch.setenv("QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM", "")  # a choice of the person stays
    macos.prepare_environment(appkit_found=True)
    assert macos.os.environ["QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM"] == ""
    monkeypatch.delenv("QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM")
    macos.prepare_environment()  # looks for AppKit: there only on a Mac with pyobjc
    assert ("QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM" in macos.os.environ) == (sys.platform == "darwin")


# ----- the Herdr programs, the raise and the start of the app -----

def program(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def test_the_programs_are_found_in_path_first_and_the_log_says_where_without_a_path(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    found = macos.find_executables(which=lambda name: f"/made/up/bin/{name}", folders=(), bundle_folders=())
    assert found == ("/made/up/bin/herdr-app", "/made/up/bin/herdr-core")
    assert records(caplog) == [(logging.INFO, "herdr-app: PATH; herdr-core: PATH")]


def test_without_path_the_programs_are_found_in_the_known_folders_and_the_bundle(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    local, brew, apps = tmp_path / "local", tmp_path / "brew", tmp_path / "Applications"
    folders, bundles = (str(local), str(brew)), (str(apps),)
    assert macos.find_executables(which=lambda name: None, folders=folders, bundle_folders=bundles) == (None, None)
    bundled = program(apps / "Herdr.app" / "Contents" / "MacOS" / "Herdr")
    core = program(brew / "herdr-core")
    (local / "herdr-core").parent.mkdir()
    (local / "herdr-core").write_text("not a program")  # no x bit: not taken
    assert macos.find_executables(which=lambda name: None, folders=folders, bundle_folders=bundles) == (
        str(bundled), str(core))
    linked = local / "herdr-app"
    linked.symlink_to(bundled)  # as the Herdr installer makes it
    assert macos.find_executables(which=lambda name: None, folders=folders, bundle_folders=bundles)[0] == str(linked)
    assert [message for _, message in records(caplog)] == [
        "herdr-app: not found; herdr-core: not found",
        f"herdr-app: {apps}/Herdr.app; herdr-core: {brew}",
        f"herdr-app: {local}; herdr-core: {brew}"]


def test_the_default_folders_are_those_of_the_herdr_installers():
    assert macos.PROGRAM_FOLDERS[:3] == ("~/.local/bin", "/opt/homebrew/bin", "/usr/local/bin")
    assert macos.APP_FOLDERS == ("~/Applications", "/Applications")
    assert (macos.APP_NAME, macos.BUNDLE_ID, macos.BUNDLE_PROGRAM) == ("Herdr", "dev.herdr.app", "Contents/MacOS/Herdr")


def test_the_bundle_of_the_program_is_found_through_its_link(tmp_path):
    bundled = program(tmp_path / "Apps" / "Herdr.app" / "Contents" / "MacOS" / "Herdr")
    link = tmp_path / "bin" / "herdr-app"
    link.parent.mkdir()
    link.symlink_to(bundled)
    assert macos.app_bundle(str(link)) == tmp_path / "Apps" / "Herdr.app"
    assert macos.app_bundle(str(program(tmp_path / "bin" / "herdr-core"))) is None
    assert macos.app_bundle(str(program(tmp_path / "x.app" / "herdr-app"))) is None  # not in Contents/MacOS
    assert macos.app_bundle(None) is None and macos.app_bundle("") is None


class Run:
    def __init__(self, code=0, error=None):
        self.code, self.error, self.calls = code, error, []

    def __call__(self, argv, timeout=2.0):
        self.calls.append(argv)
        if self.error:
            raise self.error
        return SimpleNamespace(returncode=self.code, stdout=b"", stderr=b"")


def test_the_start_is_open_of_the_bundle_or_of_the_bundle_id(tmp_path):
    run = Run()
    bundled = program(tmp_path / "Herdr.app" / "Contents" / "MacOS" / "Herdr")
    assert macos.start_app(run, str(bundled), macos.COMMANDS) == 0
    assert macos.start_app(run, "/made/up/herdr-app", macos.COMMANDS) == 0
    assert run.calls == [["/usr/bin/open", "-a", str(tmp_path / "Herdr.app")], ["/usr/bin/open", "-b", "dev.herdr.app"]]
    assert macos.start_app(Run(code=1), "/made/up/herdr-app", {"launcher": "/fake/open"}) == 1
    with pytest.raises(FileNotFoundError):
        macos.start_app(Run(error=FileNotFoundError("open")), "/made/up/herdr-app", macos.COMMANDS)


def test_the_raise_activates_the_running_app_and_asks_launch_services_to_reopen_it():
    kit, run = make_kit(running=(True,)), Run()
    assert macos.raise_app(run, macos.COMMANDS, appkit=lambda: kit) is True
    assert kit.calls == [("runningApplicationsWithBundleIdentifier_", "dev.herdr.app"), ("unhide",),
                         ("activateWithOptions_", 1)]
    assert run.calls == [["/usr/bin/open", "-b", "dev.herdr.app"]]


@pytest.mark.parametrize("running, code, error, raised", [
    ((), 0, None, True),  # not seen by AppKit: the reopen
    ((False,), 0, None, True),  # the activation was refused: the reopen
    ((True,), 1, None, True),  # the reopen failed: the activation counts
    ((False,), 1, None, False),
    ((), 0, FileNotFoundError("open"), False),
    ((), 0, subprocess.TimeoutExpired("open", 0), False),  # the end of the time of the jump
])
def test_the_raise_is_true_when_one_of_its_two_ways_worked(running, code, error, raised, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    assert macos.raise_app(Run(code, error), macos.COMMANDS, appkit=lambda: make_kit(running=running)) is raised
    if error:
        assert records(caplog) == [(logging.INFO, f"the reopen of the Herdr app failed ({type(error).__name__})")]


def test_without_pyobjc_or_when_appkit_fails_the_raise_is_the_reopen(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    run = Run()
    assert macos.raise_app(run, macos.COMMANDS, appkit=lambda: None) is True
    broken = make_kit()
    broken.AppKit.NSRunningApplication = SimpleNamespace()  # no such method: an AttributeError of pyobjc
    assert macos.raise_app(run, macos.COMMANDS, appkit=lambda: broken) is True
    assert run.calls == [["/usr/bin/open", "-b", "dev.herdr.app"]] * 2
    assert records(caplog) == [(logging.INFO, "the activation of the Herdr app failed (AttributeError)")]


def test_the_environment_of_a_command_has_no_caller_variable_and_the_argv_is_unchanged(monkeypatch):
    monkeypatch.setenv("HC_TERMINAL_ID", "t1")
    monkeypatch.setenv("HC_SCOPE", "made-up")
    monkeypatch.setenv("BELLWETHER_MADE_UP", "kept")
    argv = ["/fake/herdr-core", "send", "--", "t1", "x"]
    given, env = macos.clean_environment(argv, ("HC_TERMINAL_ID", "HC_SCOPE", "HC_TERMINAL_SOCKET"), macos.COMMANDS)
    assert given == argv and given is not argv
    assert "HC_TERMINAL_ID" not in env and "HC_SCOPE" not in env and env["BELLWETHER_MADE_UP"] == "kept"
    names = ("HC_TERMINAL_ID", "HC_SCOPE", "HC_TERMINAL_SOCKET")
    assert env == {k: v for k, v in macos.os.environ.items() if k not in names}


# ----- the client with the macOS module -----

APP_LIST = {"spaces": [{"id": "sp1", "name": "Main", "tabs": [{"id": "tb1", "name": "1", "terminals": [
    {"terminal": "t1", "pane": "p1", "status": "blocked", "app": "claude-code", "name": "made-up", "sub_agents": []}]}]}]}


class Desk:
    """The Herdr app and Launch Services, made up: `ls`, `do agent.focus` and `open`."""

    def __init__(self, running=True, open_code=0):
        self.running, self.open_code, self.calls = running, open_code, []

    def __call__(self, argv, timeout=2.0, **options):
        self.calls.append((argv, options))
        if argv[0] == "/usr/bin/open":
            self.running = self.running or self.open_code == 0
            return SimpleNamespace(returncode=self.open_code, stdout=b"", stderr=b"")
        if argv[1] == "ls":
            return SimpleNamespace(returncode=0 if self.running else 1,
                                   stdout=json.dumps(APP_LIST).encode() if self.running else b"", stderr=b"")
        if argv[1] == "do":
            return SimpleNamespace(returncode=0, stdout=b"null\n", stderr=b"")
        return SimpleNamespace(returncode=0, stdout=b'{"started": true}', stderr=b"")


@pytest.fixture
def mac_client(monkeypatch):
    from bellwether import client as client_module
    monkeypatch.setattr(client_module, "platform", macos)
    monkeypatch.setattr(macos, "load_appkit", lambda: None)  # no pyobjc: the raise is the reopen

    def make(desk):
        return client_module.HerdrClient("/made/up/herdr-app", "/made/up/herdr-core", run=desk,
                                         sleep=lambda seconds: None, clock=lambda: 0.0)
    return make


def test_the_jump_with_the_macos_module_shows_the_agent_and_reopens_the_app(mac_client):
    desk = Desk()
    client = mac_client(desk)
    client.focus_agent("t1")
    assert [argv for argv, _ in desk.calls] == [
        ["/made/up/herdr-app", "ls"], ["/made/up/herdr-app", "do", "agent.focus", '{"terminal": "t1"}'],
        ["/usr/bin/open", "-b", "dev.herdr.app"]]


def test_the_jump_with_the_app_closed_starts_it_with_open(mac_client):
    desk = Desk(running=False)
    client = mac_client(desk)
    client.focus_agent("t1")
    assert [argv[0] if argv[0] == "/usr/bin/open" else argv[1] for argv, _ in desk.calls] == [
        "ls", "/usr/bin/open", "ls", "do", "/usr/bin/open"]


def test_a_text_is_sent_with_the_environment_of_the_platform(mac_client, monkeypatch):
    monkeypatch.setenv("HC_TERMINAL_ID", "t9")
    desk = Desk()

    class Core:
        def __call__(self, argv, timeout=2.0, **options):
            if argv[1:] == ["ls", "--json"]:
                return SimpleNamespace(returncode=0, stderr=b"", stdout=json.dumps({"terminals": [
                    {"address": "t1", "agent": "claude-code", "state": "live", "status": "blocked"}]}).encode())
            if argv[1] == "get":
                return SimpleNamespace(returncode=0, stderr=b"", stdout=b'{"address": "t1", "state": "live"}')
            return desk(argv, timeout, **options)

    from bellwether import client as client_module
    client = client_module.HerdrClient(None, "/made/up/herdr-core", run=Core())
    client.list_agents()
    assert client.send_text("t1", "made-up text") is None
    (argv, options), = desk.calls
    assert argv == ["/made/up/herdr-core", "send", "--force", "--", "t1", "made-up text"]
    assert "HC_TERMINAL_ID" not in options["env"] and options["env"]["PATH"] == macos.os.environ["PATH"]


# ----- the windows -----

class Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def emit(self, *args):
        for slot in self.slots:
            slot(*args)


class QtWindow:
    """A made-up QWindow: what prepare_window and window_facts use of it, with each call recorded."""

    def __init__(self, visible=True):
        self.visible, self.properties, self.calls = visible, {}, []
        self.visibleChanged = Signal()

    def winId(self):
        return 0x7f00

    def setProperty(self, name, value):
        self.calls.append(("setProperty", name, value))
        self.properties[name] = value

    def property(self, name):
        return self.properties.get(name)

    def isVisible(self):
        return self.visible

    def hide(self):
        self.calls.append(("hide",))
        self.visible = False

    def destroy(self):
        self.calls.append(("destroy",))

    def show(self):
        self.calls.append(("show",))
        self.visible = True
        self.visibleChanged.emit(True)

    def raise_(self):
        self.calls.append(("raise_",))


PANEL_CALLS = [("objc_object", 0x7f00), ("setLevel_", 25), ("setCollectionBehavior_", 1 | 16 | 64 | 256),
               ("setStyleMask_", 16 | 128), ("_setPreventsActivation_", True), ("setBecomesKeyOnlyIfNeeded_", True),
               ("setHidesOnDeactivate_", False), ("setHasShadow_", False), ("setMovable_", False)]


def test_the_panel_is_a_non_activating_panel_at_the_status_level_on_every_space(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    kit, window = make_kit(), QtWindow()
    macos.prepare_window(window, "panel", appkit=lambda: kit)
    assert kit.calls == PANEL_CALLS
    # The property that Qt reads when it makes a native window again; the window is not made again here.
    assert window.calls == [("setProperty", "_q_macAlwaysShowToolWindow", True)]
    assert kit.window.state["hidesOnDeactivate"] is False and records(caplog) == []


def test_a_window_without_the_private_call_or_not_a_panel_gets_the_rest(caplog):
    from tests.fake_appkit import Window
    kit = make_kit(window=Window([], class_name="QNSWindow", private=False))
    macos.prepare_window(QtWindow(), "panel", appkit=lambda: kit)
    assert [call[0] for call in kit.calls] == [call[0] for call in PANEL_CALLS if call[0] not in (
        "_setPreventsActivation_", "setBecomesKeyOnlyIfNeeded_")]


def test_without_pyobjc_the_panel_is_made_again_so_that_qt_reads_the_property():
    window = QtWindow()
    macos.prepare_window(window, "panel", appkit=lambda: None)
    assert window.calls == [("setProperty", "_q_macAlwaysShowToolWindow", True), ("hide",), ("destroy",), ("show",)]
    hidden = QtWindow(visible=False)
    macos.prepare_window(hidden, "panel", appkit=lambda: None)
    assert hidden.calls[-2:] == [("hide",), ("destroy",)] and not hidden.visible  # a hidden panel stays hidden


def test_when_appkit_fails_the_panel_is_made_again_with_one_log_line(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    kit, window = make_kit(), QtWindow()
    kit.objc.objc_object = lambda c_void_p: (_ for _ in ()).throw(ValueError("made-up"))
    macos.prepare_window(window, "panel", appkit=lambda: kit)
    assert window.calls[-3:] == [("hide",), ("destroy",), ("show",)]
    assert records(caplog) == [(logging.WARNING, "the panel could not get the behaviour of a macOS panel (ValueError): "
                                                 "a plain window above the others")]


@pytest.mark.parametrize("role", ["answer", "options"])
def test_the_answer_and_the_options_window_activate_the_app_at_each_show(role):
    kit, window = make_kit(), QtWindow(visible=False)
    macos.prepare_window(window, role, appkit=lambda: kit, later=lambda ms, function: function())
    assert kit.calls == [] and window.calls == []  # nothing until it shows
    window.show()
    window.hide()
    window.visibleChanged.emit(False)
    window.show()
    assert kit.calls == [("activate",), ("objc_object", 0x7f00), ("makeKeyAndOrderFront_", None)] * 2
    assert window.properties["bellwetherActivation"] == "activate"


def test_an_older_macos_activates_the_app_the_old_way_and_without_pyobjc_qt_raises_the_window():
    kit, window = make_kit(has_activate=False), QtWindow(visible=True)
    macos.prepare_window(window, "options", appkit=lambda: kit, later=None)  # shown: at once; no second way
    assert kit.calls == [("activateIgnoringOtherApps_", True), ("objc_object", 0x7f00), ("makeKeyAndOrderFront_", None)]
    assert window.properties["bellwetherActivation"] == "activateIgnoringOtherApps"
    plain = QtWindow(visible=False)
    macos.prepare_window(plain, "answer", appkit=lambda: None)
    plain.show()
    assert plain.calls == [("show",), ("raise_",), ("setProperty", "bellwetherActivation", "raise")]


def test_when_the_system_refuses_the_activation_the_older_call_asks_again_after_300_ms():
    """macOS 14 and later can refuse `activate` with no input of the person (the self-test of the runner)."""
    kit, window = make_kit(), QtWindow(visible=False)
    kit.app.activate = lambda: kit.calls.append(("activate",))  # refused: the app stays inactive
    waits = []
    macos.prepare_window(window, "options", appkit=lambda: kit,
                         later=lambda ms, function: (waits.append(ms), function()))
    window.show()
    assert waits == [300]
    assert kit.calls == [("activate",), ("objc_object", 0x7f00), ("makeKeyAndOrderFront_", None),
                         ("activateIgnoringOtherApps_", True), ("objc_object", 0x7f00), ("makeKeyAndOrderFront_", None)]
    assert window.properties["bellwetherActivation"] == "activate, activateIgnoringOtherApps"
    kit.calls.clear()
    window.hide()
    window.visible = False
    kit.app.activate = lambda: kit.calls.append(("activate",))
    macos.activate_app(window, kit, later=lambda ms, function: function())  # hidden by then: no second way
    assert ("activateIgnoringOtherApps_", True) not in kit.calls


def test_an_activation_that_fails_falls_back_to_the_raise_of_qt_with_one_log_line(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    kit, window = make_kit(), QtWindow(visible=False)
    kit.app.activate = lambda: (_ for _ in ()).throw(RuntimeError("made-up"))
    macos.prepare_window(window, "answer", appkit=lambda: kit, later=lambda ms, function: function())
    window.show()
    assert window.calls[-2:] == [("raise_",), ("setProperty", "bellwetherActivation", "raise")]
    assert records(caplog) == [(logging.INFO, "the program could not activate itself (RuntimeError)")]


def test_the_app_is_an_accessory_app_and_without_pyobjc_one_log_line(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    kit = make_kit()
    macos.prepare_app(object(), appkit=lambda: kit)
    assert kit.calls == [("setActivationPolicy_", 1)] and records(caplog) == []
    macos.prepare_app(object(), appkit=lambda: None)
    assert records(caplog) == [(logging.WARNING, "pyobjc (AppKit) cannot be imported: the panel is a plain window above "
                                                 "the others on the current Space only, and the program has a Dock icon")]


def test_the_facts_of_the_native_window_for_the_self_test():
    kit, window = make_kit(), QtWindow()
    macos.prepare_app(object(), appkit=lambda: kit)
    macos.prepare_window(window, "panel", appkit=lambda: kit)
    assert macos.window_facts(window, appkit=lambda: kit) == {
        "pyobjc": True, "class": "QNSPanel", "panel": True, "level": 25, "collection_behavior": 337,
        "style_mask": 144, "can_become_key": False, "key": False, "hides_on_deactivate": False, "has_shadow": False,
        "movable": False, "visible": True, "on_active_space": True, "always_show_property": True,
        "activation_policy": 1, "activation_asked": "", "app_active": False}
    assert macos.window_facts(QtWindow(), appkit=lambda: None) == {"pyobjc": False, "always_show_property": False,
                                                                    "activation_asked": ""}


def test_the_panel_of_the_program_is_made_again_and_shows_as_before(app, tmp_path):
    """The way of the program without pyobjc, on the real panel (off screen): hide, destroy, show."""
    from PySide6.QtQml import QQmlApplicationEngine
    from bellwether.__main__ import load_panel
    from bellwether.backend import Backend
    from bellwether.icons import Icons
    from tests.conftest import FakeClient
    backend = Backend(FakeClient(), settings_path=tmp_path / "state.json", icons=Icons(tmp_path / "a", tmp_path / "c"))
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    try:
        assert load_panel(engine) == "plain"
        window = engine.rootObjects()[0]
        before = (window.isVisible(), window.geometry(), window.flags())
        macos.prepare_window(window, "panel", appkit=lambda: None)
        app.processEvents()
        assert (window.isVisible(), window.geometry(), window.flags()) == before
        assert window.property("_q_macAlwaysShowToolWindow") is True and window.property("panel") is not None
    finally:
        del engine
        app.processEvents()


# ----- the process host: psutil -----

class PsError(Exception):
    """The base of the errors of the made-up psutil (psutil.Error)."""


class NoSuchProcess(PsError):
    pass


class AccessDenied(PsError):
    pass


class Proc:
    def __init__(self, table, pid):
        self.table, self.pid = table, pid

    def _row(self):
        row = self.table.get(self.pid)
        if row is None:
            raise NoSuchProcess(self.pid)
        if row.get("denied"):
            raise AccessDenied(self.pid)
        return row

    def create_time(self):
        return self._row()["start"]

    def children(self):
        return [Proc(self.table, pid) for pid in self._row().get("children", ())]

    def cmdline(self):
        return self._row().get("argv", [])

    def open_files(self):
        return [SimpleNamespace(path=path, fd=3) for path in self._row().get("files", ())]


def made_up_psutil(table):
    return SimpleNamespace(Error=PsError, NoSuchProcess=NoSuchProcess, AccessDenied=AccessDenied,
                           Process=lambda pid: Proc(table, pid))


# 2026-11-20 16:18:03.75 UTC, and 2026-11-05 09:04:05 UTC (a day of the month with one digit).
START, EARLY = 1795191483.75, 1793869445.0


def test_the_start_of_a_process_has_the_form_of_ps_lstart_in_the_c_locale_and_utc():
    assert macos.lstart(START) == "Fri Nov 20 16:18:03 2026"
    assert macos.lstart(EARLY) == "Thu Nov  5 09:04:05 2026"  # %e: the day is padded with a space
    assert macos.lstart(0) == "Thu Jan  1 00:00:00 1970"


def test_the_host_reads_the_processes_through_psutil(tmp_path):
    table = {700: {"start": START, "children": [701, 702], "argv": ["codex", "--no-daemon"],
                   "files": ["/made/up/rollout.jsonl", "/dev/null"]},
             701: {"start": EARLY}, 702: {"start": EARLY, "denied": True}}
    host = macos.process_host(psutil=lambda: made_up_psutil(table))
    assert isinstance(host, macos.ProcessHost) and host.home == Path.home().resolve()
    host = macos.Host(tmp_path, made_up_psutil(table))
    assert host.start_ticks(700) == "Fri Nov 20 16:18:03 2026" and host.start_ticks(701) == "Thu Nov  5 09:04:05 2026"
    assert host.start_ticks(702) is None and host.start_ticks(999) is None  # denied, gone
    assert host.children(700) == [701, 702] and host.children(999) == [] and host.children(702) == []
    assert host.arguments(700) == ["codex", "--no-daemon"] and host.arguments(999) == []
    assert host.open_files(700) == ["/made/up/rollout.jsonl", "/dev/null"] and host.open_files(702) == []
    assert list(host.family(700, 700)) == [700, 701, 702]


def test_without_psutil_the_host_knows_no_process_and_one_log_line_says_so(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    host = macos.process_host(psutil=lambda: None)
    assert (host.start_ticks(1), host.children(1), host.arguments(1), host.open_files(1)) == (None, [], [], [])
    assert list(host.family(5, 6)) == [5, 6]
    assert records(caplog) == [(logging.WARNING, "psutil cannot be imported: the rows show the time of the terminal "
                                                 "and no model")]


def claude_home(tmp_path, pid, proc_start):
    """A made-up home with a session file of Claude Code for `pid` and its transcript."""
    session = "0a1b2c3d-1111-2222-3333-444455556666"
    folder = tmp_path / "home" / ".claude"
    (folder / "sessions").mkdir(parents=True)
    (folder / "sessions" / f"{pid}.json").write_text(json.dumps(
        {"pid": pid, "sessionId": session, "cwd": "/made/up", "startedAt": 1_795_000_000_000, "procStart": proc_start}))
    transcript = folder / "projects" / "-made-up" / f"{session}.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(json.dumps({"type": "assistant", "message": {"model": "claude-opus-5-5", "role": "assistant",
                                                                       "content": []}}, separators=(",", ":")) + "\n")
    return tmp_path / "home"


@pytest.mark.parametrize("proc_start, model, reason", [
    ("Fri Nov 20 16:18:03 2026", "claude-opus-5-5", "ok"),  # the form of ps lstart: proven for this process
    ("Fri Nov 20 16:18:04 2026", None, "other_process"),  # an older process with this pid
    ("Fri Nov 20 16:18:03 2026 ", None, "other_process"),  # an other form: no model, never a guess
    ("1795191483750", None, "other_process"),
    (1795191483, None, "other_process"),
])
def test_a_claude_session_counts_only_when_its_proc_start_is_the_start_of_the_live_process(
        tmp_path, proc_start, model, reason):
    from bellwether.sessions import read_claude
    home = claude_home(tmp_path, 700, proc_start)
    host = macos.Host(home, made_up_psutil({700: {"start": START}}))
    facts = read_claude(host, host.family(700))
    assert (facts.model, facts.reason) == (model, reason)


@on_mac
def test_on_a_mac_the_start_of_a_process_is_what_ps_lstart_prints():
    """The proof on the runner: the same text as Claude Code's way to read it (`LC_ALL=C TZ=UTC ps -o lstart=`)."""
    import os
    done = subprocess.run(["ps", "-o", "lstart=", "-p", str(os.getpid())], capture_output=True, text=True,
                          env={**os.environ, "LC_ALL": "C", "TZ": "UTC"}, check=True)
    host = macos.process_host()
    assert host.start_ticks(os.getpid()) == done.stdout.strip()


@on_mac
def test_on_a_mac_psutil_gives_the_children_the_arguments_and_the_open_files(tmp_path):
    import os
    path = tmp_path / "made-up.jsonl"
    path.write_text("")
    child = subprocess.Popen([sys.executable, "-c", "import sys, time; f = open(sys.argv[1]); time.sleep(30)",
                              str(path)])
    try:
        host = macos.process_host()
        import time
        end = time.monotonic() + 10
        while time.monotonic() < end and str(path.resolve()) not in map(os.path.realpath, host.open_files(child.pid)):
            time.sleep(0.1)
        assert child.pid in host.children(os.getpid())
        assert host.arguments(child.pid)[-1] == str(path)
        assert str(path.resolve()) in map(os.path.realpath, host.open_files(child.pid))
    finally:
        child.kill()
        child.wait()


# ----- the icon of the Herdr app -----

def png(size, color):
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QColor, QImage
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def icns(path, entries):
    """An .icns file: its header, then each entry (a type of 4 letters, its length, a PNG)."""
    import struct
    body = b"".join(kind + struct.pack(">I", 8 + len(data)) + data for kind, data in entries)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"icns" + struct.pack(">I", 8 + len(body)) + body)
    return path


def bundle(folder, icon_name="Herdr", plist=None):
    import plistlib
    (folder / "Contents" / "Resources").mkdir(parents=True, exist_ok=True)
    (folder / "Contents" / "Info.plist").write_bytes(plist if plist is not None else plistlib.dumps(
        {"CFBundleIdentifier": "dev.herdr.app", "CFBundleIconFile": icon_name}))
    return folder


def test_the_icon_is_the_icns_that_the_info_plist_of_the_bundle_names(tmp_path, app):
    first, second = tmp_path / "a" / "Herdr.app", tmp_path / "b" / "Herdr.app"
    assert macos.app_icon_file(bundles=[None, first, second]) is None
    bundle(first, "Missing")  # names a file that is not there
    bundle(second, "Herdr")
    icon = icns(second / "Contents" / "Resources" / "Herdr.icns", [(b"ic07", png(128, "#ff0000"))])
    assert macos.app_icon_file(bundles=[None, first, second]) == icon
    bundle(first, "Other.icns")
    other = icns(first / "Contents" / "Resources" / "Other.icns", [(b"ic07", png(128, "#00ff00"))])
    assert macos.app_icon_file(bundles=[first, second]) == other


@pytest.mark.parametrize("plist", [b"not a plist", None])
def test_a_bundle_with_a_bad_info_plist_or_icon_name_is_passed_over(tmp_path, app, plist):
    import plistlib
    first, second = tmp_path / "a" / "Herdr.app", tmp_path / "b" / "Herdr.app"
    bundle(first, plist=plist if plist is not None else plistlib.dumps({"CFBundleIconFile": "../../x"}))
    bundle(second)
    icon = icns(second / "Contents" / "Resources" / "Herdr.icns", [(b"ic07", png(128, "#ff0000"))])
    assert macos.app_icon_file(bundles=[first, second]) == icon


def test_the_default_bundles_follow_the_link_of_the_installer(tmp_path, monkeypatch, app):
    monkeypatch.setenv("HOME", str(tmp_path))
    moved = bundle(tmp_path / "Elsewhere" / "Herdr.app")
    icon = icns(moved / "Contents" / "Resources" / "Herdr.icns", [(b"ic07", png(128, "#ff0000"))])
    assert macos.app_icon_file() is None or macos.app_icon_file() != icon  # no link yet (a real /Applications aside)
    program(moved / "Contents" / "MacOS" / "Herdr")
    (tmp_path / ".local" / "bin").mkdir(parents=True)
    (tmp_path / ".local" / "bin" / "herdr-app").symlink_to(moved / "Contents" / "MacOS" / "Herdr")
    assert macos.app_icon_file() == icon


def test_the_tray_takes_the_largest_image_of_an_icns(tmp_path, app):
    from PySide6.QtGui import QColor
    from bellwether.appicon import load_source
    path = icns(tmp_path / "Herdr.icns", [(b"icp6", png(64, "#ff0000")), (b"ic08", png(256, "#0000ff")),
                                         (b"icp5", png(32, "#00ff00"))])
    image = load_source(path)
    assert image.width() == 256 and image.pixelColor(128, 128) == QColor("#0000ff")


# ----- the fonts: the macOS families come after the Linux ones, so Linux keeps its fonts -----

UI = Path(macos.__file__).parent.parent / "ui"


@pytest.mark.parametrize("file, linux, mac", [
    *[(f"skins/{letter}Theme.qml", ["Adwaita Sans", "Inter", "Noto Sans", "DejaVu Sans"], ["SF Pro", "Helvetica Neue"])
      for letter in "ABDE"],
    *[(file, ["Hack", "JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono"], ["SF Mono", "Menlo"])
      for file in ("skins/CTheme.qml", "controls/TextView.qml")],
])
def test_each_font_list_has_the_macos_families_at_its_end(file, linux, mac):
    import re
    text = (UI / file).read_text()
    lists = re.findall(r"Fonts\.first\(\s*\[([^\]]*)\]", text)
    assert len(lists) == 1
    assert re.findall(r'"([^"]+)"', lists[0]) == linux + mac


def test_pyobjc_and_psutil_are_dependencies_only_where_they_are_used():
    import tomllib
    project = tomllib.loads((Path(macos.__file__).parents[2] / "pyproject.toml").read_text())["project"]
    marks = {d.split(";")[0].split(">")[0].split("=")[0].strip(): d.split(";")[1].strip() if ";" in d else None
             for d in project["dependencies"]}
    assert marks["pyobjc-framework-cocoa"] == "sys_platform == 'darwin'"
    assert marks["psutil"] == "sys_platform != 'linux'"


def test_off_screen_the_program_makes_no_native_call_and_says_so_one_time(app, caplog):
    """The Qt platform of the tests is offscreen: the winId of a window is no NSView, so nothing native is done."""
    caplog.set_level(logging.INFO, logger="bellwether")
    assert macos.cocoa() is False and macos.load_appkit() is None
    window = QtWindow()
    macos.prepare_window(window, "panel")
    macos.prepare_window(window, "options")
    window.show()
    assert window.calls == [("show",)] and window.visibleChanged.slots == []
    assert macos.window_facts(window) == {}
    macos.prepare_app(app)
    assert records(caplog) == [(logging.INFO, "the Qt platform is offscreen, not cocoa: the program gets no set-up of "
                                              "macOS")]
