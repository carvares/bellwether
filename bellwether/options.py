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
            # A Wayland compositor tells the screen of a window only after it shows: the room of that screen then
            # (the sections are laid out at once from the asked size: no scroll fault; the same room changes nothing).
            self._window.screenChanged.connect(lambda _screen: self.fit_screen() if self._window.isVisible() else None)
        fitted = self.fit_screen()
        if self._window.isVisible() and not self._window.isActive():
            # Behind a different window. On Wayland a program cannot raise its window without a click in one of
            # its windows (the tray menu is not one), but a new window comes to the front: show it again.
            self._window.hide()
        # The place and the height before the show, where the program places windows: the first frame shows the
        # window where it stays (on a small screen: already lower, below the panel).
        self.keep_on_screen()
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
            # As Screen.height: keep_on_screen can have lowered it at the last show (below the panel).
            self._window.setProperty("roomHeight", screen.geometry().height())
        return screen

    def keep_on_screen(self) -> None:
        keep_on_screen(self._window, panel_of(self._engine), lower=True)


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


def clear_place(frame, free, avoid, gap: int = PANEL_GAP, min_height: int | None = None):
    """The place (x, y, height) for a window `frame` (x, y, width, height) inside the free area `free` of its screen:
    kept inside it as far as it fits, and clear of the panel `avoid` (None: no panel there) when the free area has
    room at its left, below it, at its right or above it (in this order; the nearest place of each side). With
    `min_height` (a window that can be lower: its sections scroll) and no side with room for all of it: below the
    panel (else above it) with the height that is there, when that is `min_height` or more. Else the window stays
    where it is in the free area: under the panel."""
    x0, y0, w, h = frame
    fx, fy, fw, fh = free

    def inside(x, y):
        return max(fx, min(x, fx + fw - w)), max(fy, min(y, fy + fh - h))

    x, y = inside(x0, y0)
    if avoid is None:
        return x, y, h
    ax, ay, aw, ah = avoid

    def clear(cx, cy):
        return cx + w <= ax or cx >= ax + aw or cy + h <= ay or cy >= ay + ah

    if clear(x, y):
        return x, y, h
    for cx, cy in ((ax - gap - w, y), (x, ay + ah + gap), (ax + aw + gap, y), (x, ay - gap - h)):
        if fx <= cx and cx + w <= fx + fw and fy <= cy and cy + h <= fy + fh:
            return cx, cy, h
    if min_height is not None:
        below, above = fy + fh - (ay + ah + gap), ay - gap - fy
        if below >= min_height:
            return x, ay + ah + gap, min(h, below)
        if above >= min_height:
            return x, ay - gap - min(h, above), min(h, above)
    return x, y, h


# The lowest options or answer window that goes below the panel (a header, a footer and some lines of its sections).
MIN_HEIGHT = 240


def keep_on_screen(window, panel=None, lower: bool = False) -> None:
    """After a show: a window that the system put partly outside the free part of its screen (Windows places a new
    window at a default place) comes inside it, as far as it fits, and goes clear of the panel (a window that stays
    above every other, and could cover the close control) when the screen has room for that. `lower` (the options
    window): on a small screen it goes below the panel and is lower (its `roomHeight`: its sections scroll). Where
    the window system places the windows (Wayland): no move."""
    screen = window.screen()
    if screen is None or not can_place_windows():
        return
    free, frame = screen.availableGeometry(), window.frameGeometry()
    avoid = None
    if panel is not None and panel.isVisible() and panel.screen() == screen:
        box = panel.frameGeometry()
        avoid = (box.x(), box.y(), box.width(), box.height())
    x, y, height = clear_place((frame.x(), frame.y(), frame.width(), frame.height()),
                               (free.x(), free.y(), free.width(), free.height()), avoid,
                               min_height=MIN_HEIGHT if lower else None)
    if height < frame.height():
        # The window takes its height from the room (fixedHeight: at most roomHeight - 80), and the frame is a
        # few pixels higher than the window.
        window.setProperty("roomHeight", height - (frame.height() - window.height()) + 80)
    if (x, y) != (frame.x(), frame.y()):
        window.setPosition(window.x() + x - frame.x(), window.y() + y - frame.y())
