"""The self-test mode (`python -m bellwether --self-test`) off screen on Linux: the steps, the one JSON object, and
nothing of the user touched. On a runner of an other system the same mode gives the facts of the real windows."""
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bellwether import selftest
from bellwether.__main__ import start_panel

ROOT = Path(__file__).parent.parent
STEPS = ["panel-C", "layout-A", "layout-B", "layout-C", "layout-D", "layout-E", "options", "answer"]
# Qt's offscreen plugin says this for the answer window (its size hints): not a fault of the program.
OFFSCREEN = "This plugin does not support propagateSizeHints()"


def test_the_self_test_shows_each_step_and_gives_the_facts_of_the_windows(app, monkeypatch):
    monkeypatch.delenv("BELLWETHER_SHELL", raising=False)
    out, err = io.StringIO(), io.StringIO()
    assert selftest.run(start_panel, show=0.05, step=0.05, out=out, err=err) == 0
    lines = out.getvalue().splitlines()
    assert len(lines) == 1  # ONE object
    facts = json.loads(lines[0])
    assert [line[len("self-test: shown "):] for line in err.getvalue().splitlines()
            if line.startswith("self-test: shown ")] == STEPS
    assert (facts["system"], facts["qt_platform"], facts["shell"]) == (sys.platform, "offscreen", "plain")
    assert facts["native"] == {} and facts["options"]["native"] == {}  # Linux: no native facts
    assert facts["panel"]["visible"] is True and facts["panel"]["frame"][2:] == facts["panel"]["geometry"][2:]
    assert facts["panel"]["flag_names"] == ["Tool", "FramelessWindowHint", "NoDropShadowWindowHint",
                                            "WindowDoesNotAcceptFocus", "WindowStaysOnTopHint"]
    assert facts["panel"]["screen"]["geometry"] == [0, 0, 800, 800]
    assert set(facts["layouts"]) == set("ABCDE")
    assert all(one["shown"] and one["visible"] and one["size"][0] > 200 for one in facts["layouts"].values())
    assert facts["options"]["visible"] is True and facts["options"]["flag_names"][0] == "Window"
    assert facts["tray"] == {"available": False, "visible": False, "items": 0}  # no tray off screen
    assert facts["answer"]["visible"] is True and facts["answer"]["prompt"] == "ready"
    assert facts["answer"]["native"] == {} and facts["answer"]["flag_names"][0] == "Window"
    # The plain shell: the bodies of the answer and the options window are opaque (the panel keeps its opacity).
    assert [facts[name]["body_alpha"] for name in ("options", "answer")] == [1.0, 1.0]
    assert facts["options"]["opaque_dialogs"] is True
    assert [m for m in facts["messages"] if m != OFFSCREEN] == [] and "error" not in facts
    assert "INFO shell: plain" in err.getvalue()


def test_the_flags_have_the_type_and_the_hints_by_name():
    from PySide6.QtCore import Qt
    flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
    assert selftest.flag_names(flags) == ["Tool", "FramelessWindowHint"]
    assert selftest.flag_names(Qt.WindowType.Window) == ["Window"]


def test_the_command_prints_one_json_object_and_touches_nothing_of_the_user(tmp_path):
    """The real command, in a process of its own, with a made-up home: no lock, no log file, no settings file."""
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "c"),
           "XDG_STATE_HOME": str(tmp_path / "s"), "XDG_CACHE_HOME": str(tmp_path / "k"),
           "XDG_RUNTIME_DIR": str(tmp_path / "r")}
    env.pop("BELLWETHER_SHELL", None)
    (tmp_path / "r").mkdir()
    done = subprocess.run([sys.executable, "-m", "bellwether", "--self-test"], capture_output=True, text=True,
                          cwd=ROOT, env=env, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    facts = json.loads(done.stdout)
    assert facts["shell"] == "plain" and facts["panel"]["visible"] is True and 10 < facts["seconds"] < 60
    assert list((tmp_path / "r").iterdir()) == []  # no lock file
    assert not (tmp_path / "s" / "bellwether").exists() and not (tmp_path / "c" / "bellwether").exists()


def ci_checks():
    """The checks of scripts/ci/selftest.py (the script of the runner)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ci_selftest", ROOT / "scripts" / "ci" / "selftest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.checks


def mac_facts(frame, app_active, items=1):
    """Facts as the macOS runner gave them in run 1 (made-up agents): a 1024 × 768 screen with a menu bar of 31 px."""
    native = {"pyobjc": True, "panel": True, "class": "QNSPanel", "level": 25, "collection_behavior": 337,
              "style_mask": 142, "can_become_key": False, "key": False, "hides_on_deactivate": False,
              "has_shadow": False, "always_show_property": True, "activation_policy": 1, "app_active": app_active,
              "visible": True}
    # As run 2 gave them: the activation was refused (no input of a person); now the call is in the facts.
    asked = {"app_active": False, "key": False, "can_become_key": True,
             "activation_asked": "activate, activateIgnoringOtherApps"}
    return {"system": "darwin", "qt_platform": "cocoa", "shell": "plain", "messages": [],
            "panel": {"visible": True, "active": False, "frame": frame, "flag_names": [
                "Tool", "FramelessWindowHint", "WindowStaysOnTopHint", "WindowDoesNotAcceptFocus"],
                "screen": {"geometry": [0, 0, 1024, 768], "available": [0, 31, 1024, 674]}},
            "native": native, "layouts": {letter: {"shown": True, "visible": True} for letter in "ABCDE"},
            "options": {"visible": True, "native": asked, "body_alpha": 1.0, "opaque_dialogs": True,
                        "frame": [16, 47, 992, 640],
                        "screen": {"geometry": [0, 0, 1024, 768], "available": [0, 31, 1024, 674]}},
            "answer": {"visible": True, "prompt": "ready", "native": asked, "body_alpha": 1.0, "opaque_dialogs": True},
            "panel_after_options": {"native": {"visible": True}},
            "tray": {"available": True, "visible": True, "items": items}}


def test_the_checks_of_the_runner_fail_on_the_faults_of_run_1_and_pass_without_them():
    checks = ci_checks()

    def failed(facts):
        return [name for status, name, _ in checks(facts) if status == "FAIL"]

    assert failed(mac_facts([688, 16, 320, 192], app_active=True, items=2)) == [
        "the program made one tray item at most",
        "the panel is inside the available area of its screen (not under a menu bar, a Dock or a panel)",
        "the app was not active while only the panel showed (the panel and the start take no focus)"]
    assert failed(mac_facts([688, 47, 320, 192], app_active=False)) == []
    without_call = mac_facts([688, 47, 320, 192], app_active=False)
    without_call["answer"]["native"] = {**without_call["answer"]["native"], "activation_asked": ""}
    assert failed(without_call) == ["the answer window asked the system to activate the app"]
    warned = [name for status, name, _ in checks(without_call) if status == "WARN"]
    assert "the options window made the app active (no input of a person here)" in warned


def ci_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("ci_selftest", ROOT / "scripts" / "ci" / "selftest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_checks_fail_when_the_facts_are_not_of_the_system_of_the_job():
    """Without the system fact every check of the system would be skipped: the job names its system."""
    module = ci_module()
    facts = mac_facts([688, 47, 320, 192], app_active=False)
    assert [n for s, n, _ in module.checks(facts, "darwin") if s == "FAIL"] == []
    del facts["system"]
    failed = [n for s, n, _ in module.checks(facts, "darwin") if s == "FAIL"]
    assert failed == ["the facts are of the system of the job"]
    assert any(n == "the panel is an NSPanel" for _, n, _ in module.checks(facts, "darwin"))  # still checked
    assert [n for s, n, _ in module.checks(mac_facts([688, 47, 320, 192], False), "win32") if s == "FAIL"][0] == (
        "the facts are of the system of the job")


def test_a_macos_without_the_private_call_is_a_warning():
    module = ci_module()
    facts = mac_facts([688, 47, 320, 192], app_active=False)
    facts["native"]["prevents_activation_call"] = False
    found = {n: s for s, n, _ in module.checks(facts, "darwin")}
    assert found["this macOS has the private call that keeps a clicked panel from activating the app"] == "WARN"


def test_pictures_only_on_a_ci_runner_and_the_home_folder_is_never_written(monkeypatch, tmp_path, capsys):
    module = ci_module()
    assert module.on_a_runner({"CI": "true"}) and module.on_a_runner({"GITHUB_ACTIONS": "true"})
    assert not module.on_a_runner({}) and not module.on_a_runner({"CI": "false"})
    assert module.private("file:///home/made-up-person/src/bellwether/ui/X.qml:3", "/home/made-up-person") == (
        "file://~/src/bellwether/ui/X.qml:3")
    assert module.private(f"made-up {Path.home()} line") == "made-up ~ line"  # the home folder of this system
    path_entries = len(sys.path)
    for _ in range(3):
        module.private("made-up line")
    assert len(sys.path) == path_entries  # the checkout is added to the path one time, not at each line
    assert module.main(["selftest.py", str(tmp_path)]) == 2 and module.main(["selftest.py", str(tmp_path), "linux"]) == 2
    picture = tmp_path / "it's.png"  # a path of this system, with a quote
    assert module.shot_command("linux", picture, which=lambda name: name) is None
    assert module.shot_command("darwin", picture, which=lambda name: name) == ["screencapture", "-x", str(picture)]
    command = module.shot_command("win32", picture, which=lambda name: name)
    assert command[:4] == ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
    assert f"$i.Save('{str(picture).replace(chr(39), chr(39) * 2)}', " in command[-1]  # a quote doubled
    assert module.shot_command("win32", picture, which=lambda name: None) is None  # no PowerShell


def windows_facts(foreground_of_program=False, added=""):
    """Facts as the Windows module gives them (made-up agents): the panel of Qt 6.12 with its styles."""
    panel = {"no_activate": True, "tool_window": True, "topmost": True, "foreground": False, "visible": True,
             "foreground_of_this_program": foreground_of_program, "added_by_program": added,
             "ex_style_names": ["WS_EX_TOPMOST", "WS_EX_TOOLWINDOW", "WS_EX_NOACTIVATE"]}
    window = {"no_activate": False, "tool_window": False, "foreground": False,
              "activation_asked": "SetForegroundWindow refused", "ex_style_names": ["WS_EX_WINDOWEDGE"]}
    return {"system": "win32", "qt_platform": "windows", "shell": "plain", "messages": [],
            "panel": {"visible": True, "active": False, "frame": [1584, 16, 320, 192], "flag_names": [
                "Tool", "FramelessWindowHint", "WindowStaysOnTopHint", "WindowDoesNotAcceptFocus"],
                "screen": {"geometry": [0, 0, 1920, 1080], "available": [0, 0, 1920, 1040]}},
            "native": panel, "layouts": {letter: {"shown": True, "visible": True} for letter in "ABCDE"},
            "options": {"visible": True, "native": dict(window), "body_alpha": 1.0, "opaque_dialogs": True,
                        "frame": [16, 40, 992, 680],
                        "screen": {"geometry": [0, 0, 1024, 768], "available": [0, 0, 1024, 720]}},
            "answer": {"visible": True, "prompt": "ready", "native": dict(window), "body_alpha": 1.0,
                       "opaque_dialogs": True},
            "panel_after_options": {"native": {"visible": True, "topmost": True}},
            "tray": {"available": True, "visible": True, "items": 1}}


def test_the_checks_of_the_windows_runner():
    module = ci_module()

    def by(facts):
        return {status: [n for s, n, _ in module.checks(facts, "win32") if s == status] for status in ("FAIL", "WARN")}

    assert by(windows_facts()) == {"FAIL": [], "WARN": ["the options window is the foreground window (no input of a "
                                                        "person here)", "the answer window is the foreground window "
                                                        "(no input of a person here)"]}
    bad = windows_facts(foreground_of_program=True, added="WS_EX_NOACTIVATE")
    bad["native"].update(no_activate=False, topmost=False)
    bad["options"]["native"]["activation_asked"] = ""
    assert by(bad)["FAIL"] == [
        "the panel takes no activation (WS_EX_NOACTIVATE)", "the panel is topmost",
        "no window of the program was in front while only the panel showed (the panel and the start take no focus)",
        "the options window asked for the foreground"]
    assert "Qt gave the panel all its styles (the program added none)" in by(bad)["WARN"]
    cut = windows_facts()
    cut["options"]["frame"] = [0, 0, 1076, 720]  # as run 1 of the Windows runner showed it on a 1024 px screen
    assert by(cut)["FAIL"] == ["the options window is inside the available area of its screen (a narrow screen too)"]
    see_through = windows_facts()
    see_through["answer"]["body_alpha"] = 0.94  # as run 1 of the Windows runner drew it
    assert by(see_through)["FAIL"] == ["the body of the answer window is opaque (an other app's text cannot show "
                                       "through it)"]


@pytest.mark.parametrize("home, text, wanted", [
    ("/home/made-up-person", "file:///home/made-up-person/src/X.qml:3: made-up", "file://~/src/X.qml:3: made-up"),
    ("/home/made-up-person", "/home/made-up-person/a and /home/other/b", "~/a and /home/other/b"),
    ("C:\\Users\\Made-Up", "C:\\Users\\Made-Up\\src\\bellwether\\ui\\X.qml", "~\\src\\bellwether\\ui\\X.qml"),
    ("C:\\Users\\Made-Up", "file:///C:/Users/Made-Up/src/X.qml:3", "file:///~/src/X.qml:3"),
    ("C:\\Users\\Made-Up", "c:\\users\\made-up\\x and C:/USERS/MADE-UP/y", "~\\x and ~/y"),
    ("C:\\Users\\Made-Up\\", "C:\\Users\\Made-Up\\x", "~\\x"),
    ("/", "/etc/made-up", "/etc/made-up"),  # no home folder to hide
    # A path boundary: an other folder whose name starts with the name of the home folder stays.
    ("/home/al", "/home/alice/x and /home/al/y and /home/al", "/home/alice/x and ~/y and ~"),
    ("/home/al", "'/home/al' file:///home/al:3 (/home/al), /home/al.bak /home/al-2", "'~' file://~:3 (~), /home/al.bak /home/al-2"),
    ("C:\\Users\\Al", "C:\\Users\\Alice\\x C:\\Users\\Al\\y", "C:\\Users\\Alice\\x ~\\y"),
])
def test_the_home_folder_is_never_written_in_any_form_of_a_path(home, text, wanted):
    assert selftest.without_home(text, home) == wanted
