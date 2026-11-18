"""System tray icon in the colour of the top state: hide, show and quit."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .appicon import SIZES, load_app_icon, mark, plate_tone, tint
from .state import PRIORITY

log = logging.getLogger("herdr_float")

STATE_COLORS: dict[str, str] = {
    "blocked": "#f28b82",
    "done": "#fdd663",
    "working": "#8ab4f8",
    "idle": "#81c995",
    "offline": "#5f6368",
    "none": "#5f6368",
}


def tooltip_text(online: bool, counters: list[dict]) -> str:
    if not online:
        return "Herdr Float: offline"
    counts = {c["state"]: c["count"] for c in counters}
    return "Herdr Float: " + ", ".join(f"{counts[state]} {state}" for state in PRIORITY)


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


class TrayIcons:
    """The tray icon of each colour: the Herdr app icon in that colour, or the circle without it. Made once."""

    def __init__(self, source: QImage | None) -> None:
        tone = None if source is None else plate_tone(source)
        self._shapes = None if source is None else [mark(source, size, tone) for size in SIZES]
        self._icons: dict[str, QIcon] = {}

    def icon(self, color: str) -> QIcon:
        if color not in self._icons:
            if self._shapes is None:
                self._icons[color] = make_icon(color)
            else:
                icon = QIcon()
                for shape in self._shapes:
                    icon.addPixmap(QPixmap.fromImage(tint(shape, color)))
                self._icons[color] = icon
        return self._icons[color]


class Tray(QObject):
    def __init__(self, backend, window, app) -> None:
        super().__init__()
        self._backend = backend
        self._window = window
        self._shown_state: str | None = None
        self._icons = TrayIcons(load_app_icon())

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
        state = self._backend.topState  # The same state as the border of the panel.
        if state != self._shown_state:
            self._icon.setIcon(self._icons.icon(STATE_COLORS[state]))
            self._shown_state = state
        self._icon.setToolTip(tooltip_text(online, counters))

    def _sync_label(self, *_args) -> None:
        self._toggle_action.setText("Hide widget" if self._window.isVisible() else "Show widget")

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle()
