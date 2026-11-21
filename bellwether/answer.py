"""The answer window: a normal window, made at its first open, and then the same window at each open. The "Answer"
control of an agent row asks for it (`Backend.answerRequested`, after the prompt of that row is open)."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QObject

from . import platform
from .layouts import UI_PATH
from .options import can_place_windows, keep_on_screen, panel_of

log = logging.getLogger("bellwether")


class _KeyWatch(QObject):
    """Sees each key press of the window before any item of it: an answer sent from the window is then no longer
    "with no key since" (the rule of the number keys in Answer.qml). It changes nothing else and keeps no key."""

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            watched.setProperty("answerSent", False)
        return False


class Answer:
    def __init__(self, engine, backend, source: Path = UI_PATH / "Answer.qml") -> None:
        self._engine = engine  # The engine of the panel: the window reads the same backend, and ends with it.
        self._backend = backend
        self._source = Path(source)
        self._window = None
        self._keys = _KeyWatch()
        backend.answerRequested.connect(self.open)

    @property
    def window(self):
        """The window, or None before its first open."""
        return self._window

    def open(self) -> None:
        """Show the window and bring it to the front. The prompt is open already: the window only shows it."""
        if self._window is None:
            before = len(self._engine.rootObjects())
            self._engine.load(self._source)
            roots = self._engine.rootObjects()
            if len(roots) == before:
                log.error("the answer window did not load")
                self._backend.closePrompt()  # no window shows the prompt: it does not stay open
                return
            self._window = roots[-1]
            platform.prepare_window(self._window, "answer")  # the set-up of the system (macOS: activate at each open)
            panel = panel_of(self._engine)
            if panel is not None and panel.screen() is not None and can_place_windows():
                self._window.setScreen(panel.screen())  # the first show on the screen of the panel
            self._window.installEventFilter(self._keys)
        if self._window.isVisible() and not self._window.isActive():
            # Behind a different window. On Wayland a program cannot raise its window, but a new window comes to
            # the front: show it again. `raising` tells the window that this hide is not a close of the prompt.
            self._window.setProperty("raising", True)
            self._window.hide()
            self._window.show()
            self._window.setProperty("raising", False)
        else:
            self._window.show()
        # Inside the free part of its screen (600 px fit in 640), clear of the panel when there is room.
        keep_on_screen(self._window, panel_of(self._engine))
        self._window.requestActivate()
