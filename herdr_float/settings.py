"""Load and save the window position."""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_PATH = Path.home() / ".config" / "herdr-float" / "state.json"


def load_position(path: Path = DEFAULT_PATH) -> tuple[int, int] | None:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    x, y = data.get("x"), data.get("y")
    if type(x) is not int or type(y) is not int:
        return None
    return x, y


def save_position(x: int, y: int, path: Path = DEFAULT_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"x": x, "y": y}))
    os.replace(temporary, path)
