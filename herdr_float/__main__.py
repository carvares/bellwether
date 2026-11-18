"""Start the herdr-float widget."""
from __future__ import annotations

import fcntl
import logging
import os
import signal
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from .backend import Backend
from .client import HerdrClient
from .tray import STATE_COLORS, Tray

LOG_PATH = Path.home() / ".local" / "state" / "herdr-float" / "herdr-float.log"
UI_PATH = Path(__file__).parent / "ui"
# Holds only a link to the system module org.kde.layershell. The Qt of the wheel does not find it alone.
IMPORT_PATH = UI_PATH / "imports"


def setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=1)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def take_single_instance_lock():
    """Return an open lock file, or None if a different widget process has the lock."""
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp")
    handle = open(runtime / "herdr-float.lock", "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def main() -> int:
    setup_logging()
    lock = take_single_instance_lock()
    if lock is None:
        logging.getLogger("herdr_float").info("a widget is already running, exit")
        return 0

    os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
    app = QApplication(sys.argv)
    app.setApplicationName("herdr-float")
    app.setQuitOnLastWindowClosed(False)
    if app.platformName() != "wayland":
        logging.getLogger("herdr_float").warning(
            "the Qt platform is %s, not wayland: the widget cannot be an overlay", app.platformName()
        )
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    backend = Backend(HerdrClient())
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("stateColors_", STATE_COLORS)
    engine.addImportPath(str(IMPORT_PATH))
    if (IMPORT_PATH / "org" / "kde" / "layershell" / "qmldir").is_file():
        engine.load(UI_PATH / "Main.qml")
    if not engine.rootObjects():
        logging.getLogger("herdr_float").error(
            "the QML interface did not load: it needs the QML module org.kde.layershell (package layer-shell-qt)"
        )
        return 1

    tray = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = Tray(backend, engine.rootObjects()[0], app)
    else:
        logging.getLogger("herdr_float").warning("no system tray, the widget has no tray icon")

    backend.start()
    app.aboutToQuit.connect(backend.stop)
    logging.getLogger("herdr_float").info("started")
    code = app.exec()
    # Delete the QML engine (and its window) first: its bindings read the backend until they are gone.
    del engine
    del tray
    del backend
    return code


if __name__ == "__main__":
    sys.exit(main())
