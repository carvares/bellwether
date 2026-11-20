"""The self-test of a CI runner: `python -m bellwether --self-test` (made-up agents), a picture of the runner's own
screen at each step that it announces (macOS: `screencapture`), and the checks of the facts that it prints.

    python scripts/ci/selftest.py <out folder>

Writes <out>/self-test.json, <out>/self-test.log (its stderr) and <out>/<step>.png. Prints each check: FAIL (the
exit code is 1), or WARN for a fact that a runner may not give (the activation of the app, the menu bar item).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "self-test: shown "

# macOS (bellwether/platform/macos.py): the status window level, the collection behaviour canJoinAllSpaces |
# stationary | ignoresCycle | fullScreenAuxiliary, the style mask bit of a non-activating panel, the accessory app.
STATUS_LEVEL = 25
BEHAVIOUR = 1 | 16 | 64 | 256
NONACTIVATING = 1 << 7
ACCESSORY = 1


def capture(folder: Path, name: str, pictures: list) -> None:
    if shutil.which("screencapture") is None:
        return
    path = folder / f"{name}.png"
    done = subprocess.run(["screencapture", "-x", str(path)], capture_output=True, text=True, timeout=20)
    pictures.append({"step": name, "file": path.name, "code": done.returncode, "stderr": done.stderr.strip()[:200]})


def checks(facts: dict) -> list[tuple[str, str, object]]:
    """(PASS | FAIL | WARN, the check, the value that was seen)."""
    found = []

    def check(name, good, value, soft=False):
        found.append(("PASS" if good else "WARN" if soft else "FAIL", name, value))

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
    check("no Qt warning", facts.get("messages") == [], facts.get("messages"), soft=True)
    tray = facts.get("tray", {})
    check("the tray item is there", tray.get("visible") is True, tray, soft=True)
    check("the program made one tray item at most", tray.get("items", 0) <= 1, tray.get("items"))
    frame, area = panel.get("frame") or [0, 0, 0, 0], (panel.get("screen") or {}).get("available") or [0, 0, 0, 0]
    check("the panel is inside the available area of its screen (not under a menu bar, a Dock or a panel)",
          area[0] <= frame[0] and area[1] <= frame[1] and frame[0] + frame[2] <= area[0] + area[2]
          and frame[1] + frame[3] <= area[1] + area[3], {"frame": frame, "available": area})
    if facts.get("system") == "darwin":
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
    return found


def main(argv: list[str]) -> int:
    out = Path(argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    process = subprocess.Popen([sys.executable, "-m", "bellwether", "--self-test"], cwd=ROOT, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pictures: list = []
    lines: list[str] = []

    def read_stderr():
        for line in process.stderr:
            lines.append(line)
            if line.startswith(PREFIX):
                capture(out, line[len(PREFIX):].strip(), pictures)

    reader = threading.Thread(target=read_stderr)
    reader.start()
    try:
        stdout = process.stdout.read()
        code = process.wait(timeout=120)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, code = "", "timeout"
    reader.join(timeout=30)
    (out / "self-test.log").write_text("".join(lines))
    print("".join(lines), end="")
    try:
        facts = json.loads(stdout)
    except ValueError:
        print(f"FAIL the self-test printed no JSON object (exit {code}): {stdout[:2000]!r}")
        return 1
    facts["pictures"] = pictures
    (out / "self-test.json").write_text(json.dumps(facts, indent=2, sort_keys=True))
    print(json.dumps(facts, indent=2, sort_keys=True))
    found = checks(facts)
    found.insert(0, ("PASS" if code == 0 else "FAIL", "the self-test exits 0", code))
    for status, name, value in found:
        print(f"{status} {name}" + ("" if status == "PASS" else f": {value!r}"))
    print(f"self-test: {time.monotonic() - began:.1f} s, {len(pictures)} pictures")
    return 1 if any(status == "FAIL" for status, _, _ in found) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
