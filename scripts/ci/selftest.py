"""The self-test of a CI runner: `python -m bellwether --self-test` (made-up agents), a picture of the runner's own
screen at each step that it announces (macOS: `screencapture`; Windows: PowerShell with System.Drawing), and the
checks of the facts that it prints.

    python scripts/ci/selftest.py <out folder> <system of the job: darwin | win32> [--pictures]

Writes <out>/self-test.json, <out>/self-test.log (its stderr) and <out>/<step>.png. Prints each check: FAIL (the
exit code is 1), or WARN for a fact that a runner may not give (the activation of the app, the menu bar item).
The pictures show the whole screen: they are taken only on a CI runner (CI or GITHUB_ACTIONS is "true") or with
--pictures. The home folder in the text that it writes is "~" (a path can hold the name of a person).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "self-test: shown "
USAGE = "usage: python scripts/ci/selftest.py <out folder> <darwin | win32> [--pictures]"

# macOS (bellwether/platform/macos.py): the status window level, the collection behaviour canJoinAllSpaces |
# stationary | ignoresCycle | fullScreenAuxiliary, the style mask bit of a non-activating panel, the accessory app.
STATUS_LEVEL = 25
BEHAVIOUR = 1 | 16 | 64 | 256
NONACTIVATING = 1 << 7
ACCESSORY = 1


# Windows: the whole desktop (all screens) as a PNG, with what every Windows has (no new dependency).
WINDOWS_SHOT = ("Add-Type -AssemblyName System.Windows.Forms, System.Drawing; "
                "$b = [System.Windows.Forms.SystemInformation]::VirtualScreen; "
                "$i = New-Object System.Drawing.Bitmap $b.Width, $b.Height; "
                "$g = [System.Drawing.Graphics]::FromImage($i); "
                "$g.CopyFromScreen($b.Left, $b.Top, 0, 0, $i.Size); "
                "$i.Save('{path}', [System.Drawing.Imaging.ImageFormat]::Png)")


_without_home: list = []  # bellwether.selftest.without_home, imported at the first use


def private(text: str, home=None) -> str:
    """The text with the home folder as "~" in each form a path takes (bellwether/selftest.py, `without_home`): a
    path of a checkout can hold the name of a person."""
    if not _without_home:
        sys.path.insert(0, str(ROOT))
        from bellwether.selftest import without_home  # noqa: PLC0415
        _without_home.append(without_home)
    return _without_home[0](text, home)


def on_a_runner(environ=None) -> bool:
    environ = os.environ if environ is None else environ
    return "true" in (environ.get("CI", "").lower(), environ.get("GITHUB_ACTIONS", "").lower())


def shot_command(system: str, path: Path, which=shutil.which) -> list[str] | None:
    """The command that takes a picture of the whole screen into `path`, or None when this system has none (or the
    program is not there: `which`, a test gives its own)."""
    if system == "darwin" and which("screencapture"):
        return ["screencapture", "-x", str(path)]
    if system == "win32" and which("powershell"):
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                WINDOWS_SHOT.replace("{path}", str(path).replace("'", "''"))]
    return None


def capture(folder: Path, name: str, pictures: list, system: str) -> None:
    path = folder / f"{name}.png"
    command = shot_command(system, path)
    if command is None:
        return
    began = time.monotonic()
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=20)
        code, err = done.returncode, done.stderr.strip()[:200]
    except (OSError, subprocess.SubprocessError) as error:
        code, err = type(error).__name__, ""
    pictures.append({"step": name, "file": path.name, "code": code, "stderr": private(err),
                     "seconds": round(time.monotonic() - began, 1)})


def checks(facts: dict, system: str | None = None) -> list[tuple[str, str, object]]:
    """(PASS | FAIL | WARN, the check, the value that was seen). `system`: the system of the job; without it the
    checks of a system are skipped when the facts do not name it."""
    found = []

    def check(name, good, value, soft=False):
        found.append(("PASS" if good else "WARN" if soft else "FAIL", name, value))

    if system is not None:
        check("the facts are of the system of the job", facts.get("system") == system, facts.get("system"))
    system = system or facts.get("system")

    panel, layouts, options = facts.get("panel", {}), facts.get("layouts", {}), facts.get("options", {})
    check("no error", "error" not in facts, facts.get("error"))
    check("the shell is plain", facts.get("shell") == "plain", facts.get("shell"))
    check("the panel is visible", panel.get("visible") is True, panel.get("visible"))
    check("the panel is a frameless tool window above the others that takes no focus",
          {"Tool", "FramelessWindowHint", "WindowStaysOnTopHint", "WindowDoesNotAcceptFocus"} <= set(
              panel.get("flag_names", [])), panel.get("flag_names"))
    check("each layout showed", sorted(layouts) == list("ABCDE") and all(
        one.get("shown") and one.get("visible") for one in layouts.values()), layouts)
    check("the options window is visible", options.get("visible") is True, options.get("visible"))
    answer = facts.get("answer", {})
    check("the answer window is visible with the made-up prompt", answer.get("visible") is True
          and answer.get("prompt") == "ready", {k: answer.get(k) for k in ("visible", "prompt", "error")})
    for name, window in (("options", options), ("answer", answer)):
        check(f"the body of the {name} window is opaque (an other app's text cannot show through it)",
              window.get("opaque_dialogs") is True and window.get("body_alpha") == 1.0,
              {k: window.get(k) for k in ("opaque_dialogs", "body_alpha")})
    check("no Qt warning", facts.get("messages") == [], facts.get("messages"), soft=True)
    tray = facts.get("tray", {})
    check("the tray item is there", tray.get("visible") is True, tray, soft=True)
    check("the program made one tray item at most", tray.get("items", 0) <= 1, tray.get("items"))
    def inside(window):
        frame, area = window.get("frame") or [0, 0, 0, 0], (window.get("screen") or {}).get("available") or [0, 0, 0, 0]
        return (area[0] <= frame[0] and area[1] <= frame[1] and frame[0] + frame[2] <= area[0] + area[2]
                and frame[1] + frame[3] <= area[1] + area[3]), {"frame": frame, "available": area}

    check("the panel is inside the available area of its screen (not under a menu bar, a Dock or a panel)",
          *inside(panel))
    check("the options window is inside the available area of its screen (a narrow screen too)", *inside(options))
    check("the options window opens at the top of its sections (the first section title shows)",
          options.get("first_title_visible") is True, {k: options.get(k) for k in ("first_title_visible", "scroll")})
    close, under = options.get("close") or [0, 0, 0, 0], options.get("panel_frame") or [0, 0, 0, 0]
    covered = (close[0] < under[0] + under[2] and under[0] < close[0] + close[2]
               and close[1] < under[1] + under[3] and under[1] < close[1] + close[3])
    check("the close control of the options window is not under the panel", bool(options.get("close")) and not covered,
          {"close": close, "panel": under})
    if system == "darwin":
        native = facts.get("native", {})
        check("Qt uses its cocoa plugin", facts.get("qt_platform") == "cocoa", facts.get("qt_platform"))
        check("pyobjc is there", native.get("pyobjc") is True, native.get("pyobjc"))
        check("the panel is an NSPanel", native.get("panel") is True, native.get("class"))
        check("the panel is at the status level", native.get("level") == STATUS_LEVEL, native.get("level"))
        check("the panel is on every Space, beside a full-screen app, out of the window cycle",
              native.get("collection_behavior") == BEHAVIOUR, native.get("collection_behavior"))
        check("the panel is a non-activating panel", bool(native.get("style_mask", 0) & NONACTIVATING),
              native.get("style_mask"))
        check("the panel cannot become the key window", native.get("can_become_key") is False,
              native.get("can_become_key"))
        check("the panel is not the key window", native.get("key") is False, native.get("key"))
        check("the panel does not hide when the app is not active", native.get("hides_on_deactivate") is False,
              native.get("hides_on_deactivate"))
        check("the panel has no shadow", native.get("has_shadow") is False, native.get("has_shadow"))
        check("the panel has the property for Qt", native.get("always_show_property") is True,
              native.get("always_show_property"))
        check("this macOS has the private call that keeps a clicked panel from activating the app",
              native.get("prevents_activation_call") is True, native.get("prevents_activation_call"), soft=True)
        check("the app is an accessory app (no Dock icon)", native.get("activation_policy") == ACCESSORY,
              native.get("activation_policy"))
        check("the panel is not active while the app is not", panel.get("active") is False, panel.get("active"),
              soft=True)
        check("the app was not active while only the panel showed (the panel and the start take no focus)",
              native.get("app_active") is False, native.get("app_active"))
        after = facts.get("panel_after_options", {}).get("native", {})
        check("the panel is still visible after the options window opened", after.get("visible") is True,
              after.get("visible"))
        # The activation of an app that is not active: macOS 14 and later give it when the person acts in the app
        # (a click in the tray menu or on the panel). The self-test opens the windows with no input of a person, so
        # a refusal here proves nothing; that the program asked for it is a fact.
        for name, window in (("options", options), ("answer", answer)):
            native = window.get("native", {})
            check(f"the {name} window asked the system to activate the app",
                  native.get("activation_asked") in ("activate", "activate, activateIgnoringOtherApps",
                                                     "activateIgnoringOtherApps"),
                  native.get("activation_asked"))
            check(f"the {name} window can become the key window", native.get("can_become_key") is True,
                  native.get("can_become_key"))
            check(f"the {name} window made the app active (no input of a person here)",
                  native.get("app_active") is True, native.get("app_active"), soft=True)
            check(f"the {name} window is the key window (no input of a person here)", native.get("key") is True,
                  native.get("key"), soft=True)
    if system == "win32":
        native = facts.get("native", {})
        check("Qt uses its windows plugin", facts.get("qt_platform") == "windows", facts.get("qt_platform"))
        check("the panel takes no activation (WS_EX_NOACTIVATE)", native.get("no_activate") is True,
              native.get("ex_style_names"))
        check("the panel has no taskbar button (WS_EX_TOOLWINDOW)", native.get("tool_window") is True,
              native.get("ex_style_names"))
        check("the panel is topmost", native.get("topmost") is True, native.get("ex_style_names"))
        check("the panel is not the foreground window", native.get("foreground") is False, native.get("foreground"))
        check("no window of the program was in front while only the panel showed (the panel and the start take no "
              "focus)", native.get("foreground_of_this_program") is False, native.get("foreground_of_this_program"))
        check("Qt gave the panel all its styles (the program added none)", native.get("added_by_program") == "",
              native.get("added_by_program"), soft=True)
        check("the panel is not active", panel.get("active") is False, panel.get("active"))
        after = facts.get("panel_after_options", {}).get("native", {})
        check("the panel is still visible and topmost after the options window opened",
              after.get("visible") is True and after.get("topmost") is True, after)
        # SetForegroundWindow: Windows gives the foreground to a process that got the last input (a click in the tray
        # menu or on the panel). The self-test opens the windows with no input of a person: a refusal proves nothing.
        for name, window in (("options", options), ("answer", answer)):
            native = window.get("native", {})
            check(f"the {name} window asked for the foreground",
                  str(native.get("activation_asked", "")).startswith("SetForegroundWindow"),
                  native.get("activation_asked"))
            check(f"the {name} window has a taskbar button and takes the focus",
                  native.get("tool_window") is False and native.get("no_activate") is False, native.get("ex_style_names"))
            check(f"the {name} window is the foreground window (no input of a person here)",
                  native.get("foreground") is True, native.get("foreground"), soft=True)
    return found


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[2] not in ("darwin", "win32") or argv[3:] not in ([], ["--pictures"]):
        print(USAGE, file=sys.stderr)
        return 2
    out, system = Path(argv[1]).resolve(), argv[2]
    out.mkdir(parents=True, exist_ok=True)
    pictures_allowed = on_a_runner() or argv[3:] == ["--pictures"]
    if not pictures_allowed:
        print("no pictures of the screen: this is not a CI runner (CI or GITHUB_ACTIONS is not true); --pictures "
              "takes them")
    began = time.monotonic()
    process = subprocess.Popen([sys.executable, "-m", "bellwether", "--self-test"], cwd=ROOT, text=True,
                               encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pictures: list = []
    lines: list[str] = []

    def read_stderr():
        for line in process.stderr:
            lines.append(private(line))
            if line.startswith(PREFIX) and pictures_allowed:
                capture(out, line[len(PREFIX):].strip(), pictures, system)

    reader = threading.Thread(target=read_stderr)
    reader.start()
    try:
        stdout = process.stdout.read()
        code = process.wait(timeout=120)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, code = "", "timeout"
    reader.join(timeout=30)
    (out / "self-test.log").write_text("".join(lines), encoding="utf-8")
    print("".join(lines), end="")
    try:
        facts = json.loads(stdout)
    except ValueError:
        print(f"FAIL the self-test printed no JSON object (exit {code}): {private(stdout[:2000])!r}")
        return 1
    facts["pictures"] = pictures
    text = private(json.dumps(facts, indent=2, sort_keys=True))
    (out / "self-test.json").write_text(text, encoding="utf-8")
    print(text)
    found = checks(facts, system)
    found.insert(0, ("PASS" if code == 0 else "FAIL", "the self-test exits 0", code))
    for status, name, value in found:
        print(f"{status} {name}" + ("" if status == "PASS" else f": {private(repr(value))}"))
    print(f"self-test: {time.monotonic() - began:.1f} s, {len(pictures)} pictures")
    return 1 if any(status == "FAIL" for status, _, _ in found) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
