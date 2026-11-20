"""The options window: a normal window, made at its first open, and then the same window at each open."""
from __future__ import annotations

import logging
from pathlib import Path

from . import platform
from .layouts import UI_PATH

log = logging.getLogger("bellwether")


class Options:
    def __init__(self, engine, source: Path = UI_PATH / "Options.qml") -> None:
        self._engine = engine  # The engine of the panel: the window reads the same backend, and ends with it.
        self._source = Path(source)
        self._window = None

    def open(self) -> None:
        """Show the window and bring it to the front."""
        if self._window is None:
            before = len(self._engine.rootObjects())
            self._engine.load(self._source)
            roots = self._engine.rootObjects()
            if len(roots) == before:
                log.error("the options window did not load")
                return
            self._window = roots[-1]
            platform.prepare_window(self._window, "options")  # the set-up of the system (macOS: activate at each open)
        if self._window.isVisible() and not self._window.isActive():
            # Behind a different window. On Wayland a program cannot raise its window without a click in one of
            # its windows (the tray menu is not one), but a new window comes to the front: show it again.
            self._window.hide()
        self._window.show()
        self._window.requestActivate()
