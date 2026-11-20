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
        self.fit_screen()
        if self._window.isVisible() and not self._window.isActive():
            # Behind a different window. On Wayland a program cannot raise its window without a click in one of
            # its windows (the tray menu is not one), but a new window comes to the front: show it again.
            self._window.hide()
        self._window.show()
        self.keep_on_screen()
        self._window.requestActivate()

    def fit_screen(self) -> None:
        """Before each show: the window gets the width of the free part of its screen (`roomWidth`): on a narrow
        screen its cards wrap and its sections are one below the other."""
        screen = self._window.screen()
        if screen is not None:
            self._window.setProperty("roomWidth", screen.availableGeometry().width())

    def keep_on_screen(self) -> None:
        keep_on_screen(self._window)


def keep_on_screen(window) -> None:
    """After a show: a window that the system put partly outside the free part of its screen (Windows places a new
    window at a default place) comes inside it, as far as it fits. Where the window system places it (Wayland), or
    when it is inside: no move."""
    screen = window.screen()
    if screen is None:
        return
    free, frame = screen.availableGeometry(), window.frameGeometry()
    x = max(free.x(), min(frame.x(), free.x() + free.width() - frame.width()))
    y = max(free.y(), min(frame.y(), free.y() + free.height() - frame.height()))
    if (x, y) != (frame.x(), frame.y()):
        window.setPosition(window.x() + x - frame.x(), window.y() + y - frame.y())
