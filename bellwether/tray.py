"""System tray icon in the colour of the top state: options, hide, show and quit."""
from __future__ import annotations

import logging

from PySide6.QtCore import QMetaObject, QObject, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from . import appicon
from .appicon import tint
from .state import PRIORITY, STATE_COLORS  # noqa: F401  (STATE_COLORS: the older place of the name)

log = logging.getLogger("bellwether")


def tooltip_text(online: bool, counters: list[dict]) -> str:
    if not online:
        return "Bellwether: offline"
    counts = {c["state"]: c["count"] for c in counters}
    return "Bellwether: " + ", ".join(f"{counts[state]} {state}" for state in PRIORITY)


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
        self._shapes = None if source is None else appicon.shapes(source)
        self._icons: dict[str, QIcon] = {}

    @classmethod
    def load(cls, desktop_dirs=None, icon_dirs=None) -> "TrayIcons":
        """The icons from the installed Herdr app icon. Any failure gives the circle: the widget must start."""
        try:
            return cls(appicon.load_app_icon(desktop_dirs, icon_dirs))
        except Exception as exc:  # The class name only: the text of an error can hold a path.
            log.info("the Herdr app icon cannot be used (%s): the tray icon is a circle", type(exc).__name__)
            return cls(None)

    def icon(self, color: str) -> QIcon:
        if color not in self._icons:
            self._icons[color] = self._tinted(color) if self._shapes is not None else make_icon(color)
        return self._icons[color]

    def _tinted(self, color: str) -> QIcon:
        """The app icon in one colour. Any failure gives the circle from now on: the widget must start."""
        try:
            icon = QIcon()
            for shape in self._shapes:
                icon.addPixmap(QPixmap.fromImage(tint(shape, color)))
            return icon
        except Exception as exc:  # The class name only: the text of an error can hold a path.
            log.info("the Herdr app icon cannot be used (%s): the tray icon is a circle", type(exc).__name__)
            self._shapes = None
            return make_icon(color)


class Tray(QObject):
    def __init__(self, backend, window, app, options=None) -> None:
        """`options` opens the options window. None: the menu has no entry for it."""
        super().__init__()
        self._backend = backend
        self._window = window
        self._shown_state: str | None = None
        self._icons = TrayIcons.load()

        self._menu = QMenu()
        if options is not None:
            self._menu.addAction("Options…").triggered.connect(lambda *_args: options())
        self._toggle_action = self._menu.addAction("Hide widget")
        self._toggle_action.triggered.connect(self.toggle)
        # The way to a different monitor that needs no drag. Only with more than one screen.
        self._move_action = self._menu.addAction("Move to next screen")
        self._move_action.triggered.connect(self.move_to_next_screen)
        app.screenAdded.connect(self._sync_screens)
        app.screenRemoved.connect(self._sync_screens)
        self._app = app
        self._sync_screens()
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

    def move_to_next_screen(self, *_args) -> None:
        QMetaObject.invokeMethod(self._window, "moveToNextScreen")
        log.info("widget moved to the next screen from tray")

    def _sync_screens(self, *_args) -> None:
        self._move_action.setVisible(len(self._app.screens()) > 1)

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
