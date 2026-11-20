"""The folders of the widget (XDG base folders with the standard defaults), and the move of the folders of its old
name: the widget was called herdr-float before 2026-11-18."""
from __future__ import annotations

import logging
import os
from pathlib import Path

NAME = "bellwether"
OLD_NAME = "herdr-float"  # Only for the move of the old folders and for the lock of an old widget that still runs.


def _base(variable: str, default: str) -> Path:
    """The folder in the variable. An empty or relative value is not valid: then the default in the home folder."""
    value = os.environ.get(variable, "")
    return Path(value) if os.path.isabs(value) else Path.home() / default


def config_home() -> Path:
    return _base("XDG_CONFIG_HOME", ".config")


def state_home() -> Path:
    return _base("XDG_STATE_HOME", ".local/state")


def cache_home() -> Path:
    return _base("XDG_CACHE_HOME", ".cache")


def runtime_dir() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp")


def move_old_folders() -> list[tuple[int, str]]:
    """Give each folder of the old name (config, state, cache) the new name, when only the old folder exists. An
    existing new folder is never replaced. A move that fails does not stop the start: the widget uses its defaults.
    Returns the log lines (level, text). The caller logs them when the log file is open: the log folder moves too."""
    lines = []
    for kind, base in (("config", config_home()), ("state", state_home()), ("cache", cache_home())):
        old, new = base / OLD_NAME, base / NAME
        try:
            if new.exists() or new.is_symlink() or not old.is_dir():
                continue
            old.rename(new)
        except OSError as error:
            lines.append((logging.WARNING, f"could not move the {kind} folder {OLD_NAME} to {NAME} "
                                           f"({type(error).__name__}): the widget uses its defaults"))
        else:
            lines.append((logging.INFO, f"moved the {kind} folder {OLD_NAME} to {NAME}"))
    return lines
