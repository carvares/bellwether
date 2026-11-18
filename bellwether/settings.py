"""Load and save the window position: x and y from the top-left corner of a screen, and the name of that screen."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .paths import NAME, config_home

DEFAULT_PATH = config_home() / NAME / "state.json"


def load_position(path: Path = DEFAULT_PATH) -> tuple[int, int, str] | None:
    """The saved (x, y, screen name). The screen is "" in a file of an older version: x and y only."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    x, y, screen = data.get("x"), data.get("y"), data.get("screen")
    if type(x) is not int or type(y) is not int:
        return None
    return x, y, screen if isinstance(screen, str) else ""


def save_position(x: int, y: int, path: Path = DEFAULT_PATH, screen: str = "") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"x": x, "y": y, "screen": screen}))
    os.replace(temporary, path)
