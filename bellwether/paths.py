"""The folders of the widget (the platform gives the base folders of this system), and the move of the folders of
its old name: the widget was called herdr-float before 2026-11-18."""
from __future__ import annotations

import logging

from .platform import cache_home, config_home, runtime_dir, state_home

NAME = "bellwether"
OLD_NAME = "herdr-float"  # Only for the move of the old folders and for the lock of an old widget that still runs.

__all__ = ["NAME", "OLD_NAME", "cache_home", "config_home", "move_old_folders", "runtime_dir", "state_home"]


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
