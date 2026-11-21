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
            panel = panel_of(self._engine)
            if panel is not None and panel.screen() is not None and can_place_windows():
                self._window.setScreen(panel.screen())  # the first show on the screen of the panel
        fitted = self.fit_screen()
        if self._window.isVisible() and not self._window.isActive():
            # Behind a different window. On Wayland a program cannot raise its window without a click in one of
            # its windows (the tray menu is not one), but a new window comes to the front: show it again.
            self._window.hide()
        self._window.show()
        if self._window.screen() != fitted:
            self.fit_screen()  # the system showed it on an other screen: the room of that one
        self.keep_on_screen()
        self._window.requestActivate()

    def fit_screen(self):
        """The window gets the width of the free part of its screen (`roomWidth`): on a narrow screen its cards wrap
        and its sections are one below the other. Before each show (the layout of the sections follows at once, see
        Options.qml), and again after it when the system showed it on an other screen. Return that screen."""
        screen = self._window.screen()
        if screen is not None:
            self._window.setProperty("roomWidth", screen.availableGeometry().width())
        return screen

    def keep_on_screen(self) -> None:
        keep_on_screen(self._window, panel_of(self._engine))


def panel_of(engine):
    """The panel window of the engine (the first window with a place of the panel), or None."""
    for root in engine.rootObjects():
        if root.property("posX") is not None and root.property("screenName") is not None:
            return root
    return None


def can_place_windows() -> bool:
    """False where the window system places the windows of a program (a Wayland compositor): then the program does
    not move them."""
    from PySide6.QtGui import QGuiApplication  # noqa: PLC0415
    return not QGuiApplication.platformName().startswith("wayland")


# Pixels between the window and the panel when the window goes clear of it.
PANEL_GAP = 16


def clear_place(frame, free, avoid, gap: int = PANEL_GAP):
    """The top-left corner (x, y) for a window `frame` (x, y, width, height) inside the free area `free` of its
    screen: kept inside it as far as it fits, and clear of the panel `avoid` (None: no panel there) when the free
    area has room at its left, below it, at its right or above it (in this order; the nearest place of each side).
    Where no side has room the window stays where it is in the free area: under the panel."""
    x0, y0, w, h = frame
    fx, fy, fw, fh = free

    def inside(x, y):
        return max(fx, min(x, fx + fw - w)), max(fy, min(y, fy + fh - h))

    x, y = inside(x0, y0)
    if avoid is None:
        return x, y
    ax, ay, aw, ah = avoid

    def clear(cx, cy):
        return cx + w <= ax or cx >= ax + aw or cy + h <= ay or cy >= ay + ah

    if clear(x, y):
        return x, y
    for cx, cy in ((ax - gap - w, y), (x, ay + ah + gap), (ax + aw + gap, y), (x, ay - gap - h)):
        if fx <= cx and cx + w <= fx + fw and fy <= cy and cy + h <= fy + fh:
            return cx, cy
    return x, y


def keep_on_screen(window, panel=None) -> None:
    """After a show: a window that the system put partly outside the free part of its screen (Windows places a new
    window at a default place) comes inside it, as far as it fits, and goes clear of the panel (a window that stays
    above every other) when the screen has room for that. Where the window system places the windows (Wayland):
    no move."""
    screen = window.screen()
    if screen is None or not can_place_windows():
        return
    free, frame = screen.availableGeometry(), window.frameGeometry()
    avoid = None
    if panel is not None and panel.isVisible() and panel.screen() == screen:
        box = panel.frameGeometry()
        avoid = (box.x(), box.y(), box.width(), box.height())
    x, y = clear_place((frame.x(), frame.y(), frame.width(), frame.height()),
                       (free.x(), free.y(), free.width(), free.height()), avoid)
    if (x, y) != (frame.x(), frame.y()):
        window.setPosition(window.x() + x - frame.x(), window.y() + y - frame.y())
