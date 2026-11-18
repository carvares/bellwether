"""Load and save the state file: the window position (x and y from the top-left corner of a screen, and the name
of that screen) and the layout. Each save reads the file and changes only its own keys."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .paths import NAME, config_home

DEFAULT_PATH = config_home() / NAME / "state.json"


def _load(path: Path) -> dict:
    """The content of the file. Empty when the file is not there or is not a JSON object."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(path: Path, changes: dict, drop: tuple[str, ...] = ()) -> None:
    """Write the file with `changes` and without the keys of `drop`. The other keys stay as they are."""
    path = Path(path)
    data = {key: value for key, value in _load(path).items() if key not in drop}
    data.update(changes)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data))
    os.replace(temporary, path)


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
