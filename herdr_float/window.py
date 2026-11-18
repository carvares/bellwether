"""Bring the Herdr app window to the front.

KWin does it. On Wayland a program cannot activate the window of a different program, and the app
has no command for it. The window runner of KWin (the one behind the KRunner search) is on D-Bus:
its "Run" restores a minimized window and activates it. (A window on a different virtual desktop
was not tested.)
"""
from __future__ import annotations

import json
import subprocess

APP_CLASS = "herdr-app"  # The window class of the app. Its .desktop file names it (StartupWMClass).
_ACTIVATE = "0_"  # The window runner names a match "<action>_<window id>". Action 0 activates.


_ERRORS = (OSError, subprocess.SubprocessError, ValueError, LookupError, TypeError, AttributeError)


def raise_app_window(run, busctl: str) -> bool:
    """Restore and activate the window of the Herdr app. Return False when that did not occur."""
    try:
        matches = _kwin(run, busctl, "/WindowsRunner", "org.kde.krunner1", "Match", "s", APP_CLASS)[0]
    except _ERRORS:
        return False  # No busctl, no KWin, or a reply with a different shape.
    for match in matches:
        try:
            window = match[0].partition("_")[2]
            # The runner also matches captions and partial names, so only the exact class counts.
            if _info(run, busctl, window).get("resourceClass") != APP_CLASS:
                continue
            _kwin(run, busctl, "/WindowsRunner", "org.kde.krunner1", "Run", "ss", _ACTIVATE + window, "")
            return _info(run, busctl, window).get("minimized") is False
        except _ERRORS:
            continue  # This match is not a window that KWin can give: try the next one.
    return False


def _kwin(run, busctl: str, path: str, interface: str, method: str, *arguments: str) -> list:
    done = run([busctl, "--user", "--json=short", "call", "org.kde.KWin", path, interface, method, *arguments])
    if done.returncode != 0:
        raise ValueError(method)
    return json.loads(done.stdout)["data"] if done.stdout.strip() else []


def _info(run, busctl: str, window: str) -> dict:
    """The properties of one window. Each value comes as {"type": ..., "data": ...}."""
    properties = _kwin(run, busctl, "/KWin", "org.kde.KWin", "getWindowInfo", "s", window)[0]
    return {name: value["data"] for name, value in properties.items()}
