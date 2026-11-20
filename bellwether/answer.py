"""The answer window: a normal window, made at its first open, and then the same window at each open. The "Answer"
control of an agent row asks for it (`Backend.answerRequested`, after the prompt of that row is open)."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QObject

from .layouts import UI_PATH

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
        self._window.requestActivate()
