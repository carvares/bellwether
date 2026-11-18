"""System tray icon: hide, show and quit."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

log = logging.getLogger("herdr_float")

STATE_COLORS: dict[str, str] = {
    "blocked": "#f28b82",
    "done": "#fdd663",
    "working": "#8ab4f8",
    "idle": "#81c995",
    "unknown": "#9aa0a6",
    "offline": "#5f6368",
    "none": "#5f6368",
}


def top_state(online: bool, counters: list[dict]) -> str:
    if not online:
        return "offline"
    for counter in counters:
        if counter["count"] > 0:
            return counter["state"]
    return "none"


def tooltip_text(online: bool, counters: list[dict]) -> str:
    if not online:
        return "Herdr Float: offline"
    return "Herdr Float: " + ", ".join(f'{c["count"]} {c["state"]}' for c in counters)


def make_icon(color: str) -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(8, 8, 48, 48)
    painter.end()
    return QIcon(pixmap)


class Tray(QObject):
    def __init__(self, backend, window, app) -> None:
        super().__init__()
        self._backend = backend
        self._window = window
        self._shown_state: str | None = None

        self._menu = QMenu()
        self._toggle_action = self._menu.addAction("Hide widget")
        self._toggle_action.triggered.connect(self.toggle)
        self._menu.addSeparator()
        self._menu.addAction("Quit").triggered.connect(app.quit)

        self._icon = QSystemTrayIcon(self)
        self._icon.setContextMenu(self._menu)
        self._icon.activated.connect(self._on_activated)

        backend.changed.connect(self.refresh)
        window.visibleChanged.connect(self._sync_label)
        self.refresh()
        self._sync_label()
        self._icon.show()

    def toggle(self, *_args) -> None:
        visible = not self._window.isVisible()
        self._window.setVisible(visible)
        log.info("widget %s from tray", "shown" if visible else "hidden")

    def refresh(self) -> None:
        online, counters = self._backend.online, self._backend.counters
        state = top_state(online, counters)
        if state != self._shown_state:
            self._icon.setIcon(make_icon(STATE_COLORS[state]))
            self._shown_state = state
        self._icon.setToolTip(tooltip_text(online, counters))

    def _sync_label(self, *_args) -> None:
        self._toggle_action.setText("Hide widget" if self._window.isVisible() else "Show widget")

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle()
