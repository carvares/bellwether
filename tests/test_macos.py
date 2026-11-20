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
    assert macos.lock(tmp_path / "bellwether.lock") is not None


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
    assert macos.prepare_environment() is None
    assert "QT_QPA_PLATFORM" not in macos.os.environ
    assert macos.prepare_engine(object()) is None


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
