"""Load and save the state file: the window position (x and y from the top-left corner of a screen, and the name
of that screen), the layout, the custom look (scale, fontScale, fontFamily, colors), and showMeta (the model and
session-time line of the agent rows). Each save reads the file and changes only its own keys."""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

from .paths import NAME, config_home

DEFAULT_PATH = config_home() / NAME / "state.json"
# The custom look. The least and the largest value of the two numbers; a number of the file out of them is clamped.
SCALE_LIMITS = (0.75, 2.0)
FONT_SCALE_LIMITS = (0.8, 1.4)
# The step of a slider of the options window, for both numbers.
SCALE_STEP = 0.05
FONT_SCALE_STEP = 0.05
# The opacity slider of the background in the options window: its limits and its step. A file can hold any opacity.
OPACITY_LIMITS = (0.1, 1.0)
OPACITY_STEP = 0.05
# The colours that the user can change. Only the background can have an alpha ("#aarrggbb").
COLOR_ROLES = ("blocked", "done", "working", "idle", "background", "text", "frame", "accent")
# No custom look: a file without these keys. fontFamily "": the font of the layout. colors: only the changed roles.
DEFAULT_LOOK = {"scale": 1.0, "fontScale": 1.0, "fontFamily": "", "colors": {}}
_LIMITS = {"scale": SCALE_LIMITS, "fontScale": FONT_SCALE_LIMITS}
_COLOR = re.compile(r"#(?:[0-9a-f]{2})?[0-9a-f]{6}", re.IGNORECASE)


def _load(path: Path) -> dict:
    """The content of the file. Empty when the file is not there or is not a JSON object."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data))
    os.replace(temporary, path)


def _save(path: Path, changes: dict, drop: tuple[str, ...] = ()) -> None:
    """Write the file with `changes` and without the keys of `drop`. The other keys stay as they are."""
    path = Path(path)
    data = {key: value for key, value in _load(path).items() if key not in drop}
    data.update(changes)
    _write(path, data)


def load_position(path: Path = DEFAULT_PATH) -> tuple[int, int, str] | None:
    """The saved (x, y, screen name). The screen is "" in a file of an older version: x and y only.
    (-1, -1, screen name) when only the screen is saved: the panel is at the default corner of that screen."""
    data = _load(path)
    x, y, screen = data.get("x"), data.get("y"), data.get("screen")
    screen = screen if isinstance(screen, str) else ""
    if type(x) is not int or type(y) is not int:
        return (-1, -1, screen) if screen else None
    return x, y, screen


def save_position(x: int, y: int, path: Path = DEFAULT_PATH, screen: str = "") -> None:
    _save(path, {"x": x, "y": y, "screen": screen})


def save_screen(screen: str, path: Path = DEFAULT_PATH) -> None:
    """Save the screen of a panel that is at its default corner: the file then has no place."""
    _save(path, {"screen": screen}, drop=("x", "y"))


def load_layout(path: Path = DEFAULT_PATH) -> str | None:
    """The saved layout name. None when the file has none. The caller knows which layouts exist."""
    layout = _load(path).get("layout")
    return layout if isinstance(layout, str) else None


def save_layout(layout: str, path: Path = DEFAULT_PATH) -> None:
    _save(path, {"layout": layout})


def load_show_meta(path: Path = DEFAULT_PATH) -> tuple[bool, bool]:
    """The saved "showMeta": the agent rows show the model and the session time. A file with no such key: True.
    The second value is True when the file has a value that is not true or false: it is ignored."""
    value = _load(path).get("showMeta", True)
    return (value, False) if type(value) is bool else (True, True)


def save_show_meta(show: bool, path: Path = DEFAULT_PATH) -> None:
    """Save "showMeta". True is the default: the file then has no such key. The other keys stay."""
    if show:
        if "showMeta" in _load(path):
            _save(path, {}, drop=("showMeta",))
    else:
        _save(path, {"showMeta": False})


def clamped(key: str, value) -> float | None:
    """The number of "scale" or "fontScale" inside its limits, with two decimal places. None for a value that is
    not a number."""
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    low, high = _LIMITS[key]
    return round(min(max(float(value), low), high), 2)


def valid_color(role: str, value) -> str | None:
    """The colour in small letters: "#rrggbb", and for the background also "#aarrggbb". None when the role is
    not one of COLOR_ROLES or the value is not such a colour."""
    if role not in COLOR_ROLES or not isinstance(value, str) or not _COLOR.fullmatch(value):
        return None
    return value.lower() if len(value) == 7 or role == "background" else None


def load_look(path: Path = DEFAULT_PATH) -> tuple[dict, list[str]]:
    """The saved custom look with the default for each value that is missing or not valid, and the keys of the
    values that are not valid (a colour as "colors.<role>"; "colors" for a role that is not one of the eight)."""
    data = _load(path)
    look = {**DEFAULT_LOOK, "colors": {}}
    ignored = []
    for key in _LIMITS:
        if key in data:
            number = clamped(key, data[key])
            if number is None:
                ignored.append(key)
            else:
                look[key] = number
    if "fontFamily" in data:
        if isinstance(data["fontFamily"], str):
            look["fontFamily"] = data["fontFamily"]
        else:
            ignored.append("fontFamily")
    colors = data.get("colors", {})
    if not isinstance(colors, dict):
        return look, [*ignored, "colors"]
    for role, value in colors.items():
        color = valid_color(role, value)
        if color is not None:
            look["colors"][role] = color
        elif role in COLOR_ROLES:
            ignored.append(f"colors.{role}")
        elif "colors" not in ignored:
            ignored.append("colors")  # Not the name: a file that a person changed can hold anything.
    return look, ignored


def save_look(look: dict, path: Path = DEFAULT_PATH, changed=None) -> None:
    """Save the custom look. A value at its default has no key in the file.
    `changed` names what to write: "scale", "fontScale", "fontFamily", "colors" (every colour: the key is replaced)
    and "colors.<role>" (one colour). What is not named stays in the file as it is: a font family that this
    system does not have now, a colour role of a later version. None: the four keys."""
    path = Path(path)
    before = _load(path)
    data = dict(before)
    for name in sorted(DEFAULT_LOOK if changed is None else changed):  # "colors" before "colors.<role>"
        key, _, role = name.partition(".")
        if role:
            colors = dict(data["colors"]) if isinstance(data.get("colors"), dict) else {}
            if role in look["colors"]:
                colors[role] = look["colors"][role]
            else:
                colors.pop(role, None)
            value = colors
        else:
            value = look[key]
        if value == DEFAULT_LOOK[key]:
            data.pop(key, None)
        else:
            data[key] = value
    if data != before:  # A save that changes nothing does not write (and does not make) the file.
        _write(path, data)
