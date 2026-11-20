"""Start the Bellwether widget."""
from __future__ import annotations

import logging
import signal
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from . import platform
from .answer import Answer
from .backend import Backend
from .client import HerdrClient
from .events import EventSource
from .icons import Icons
from .layouts import UI_PATH
from .options import Options
from .paths import NAME, OLD_NAME, move_old_folders, runtime_dir, state_home
from .sessions import SessionWatch
from .tray import Tray, window_icon

LOG_PATH = state_home() / NAME / f"{NAME}.log"


def setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=1)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def take_single_instance_lock():
    """Return the open lock files, or None if a different widget process has one of them. The lock of the old name
    is taken too: an old herdr-float widget and a new one never run together."""
    handles = []
    for name in (NAME, OLD_NAME):
        handle = platform.lock(runtime_dir() / f"{name}.lock")
        if handle is None:
            for opened in handles:
                opened.close()
            return None
        handles.append(handle)
    return handles


def follow_refresh_rate(window) -> None:
    """Give the QML the refresh rate of the screen of the window: now, when the window changes its screen, and
    when that screen changes its rate. With no screen the rate is 0 (not known)."""
    link = []  # The connection to the current screen. Not the screen: a monitor can go away.

    def update(*_args) -> None:
        screen = window.screen()
        window.setProperty("refreshRate", screen.refreshRate() if screen is not None else 0.0)

    def follow(*_args) -> None:
        if link:
            QObject.disconnect(link.pop())  # Does nothing when the old screen is gone.
        screen = window.screen()
        if screen is not None:
            link.append(screen.refreshRateChanged.connect(update))
        update()

    window.screenChanged.connect(follow)
    follow()


def main() -> int:
    # The lock comes first: a widget that runs (of the old name too) still uses its folders.
    lock = take_single_instance_lock()
    if lock is None:
        # For start.log: this line is there also when no log folder exists yet.
        print("bellwether: already running", file=sys.stderr)
        # Make no log folder here: it would stop the move of the old one at the next start.
        if LOG_PATH.parent.is_dir():
            setup_logging()
            logging.getLogger("bellwether").info("a widget is already running, exit")
        return 0
    moves = move_old_folders()  # before anything reads or makes the folders
    setup_logging()
    for level, line in moves:
        logging.getLogger("bellwether").log(level, line)

    platform.prepare_environment()
    app = QApplication(sys.argv)
    app.setApplicationName("bellwether")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(window_icon())  # for the taskbar entry of the answer and the options window
    platform.prepare_app(app)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    app_path, core_path = platform.find_executables()
    # herdr-core tells of each change, so a change shows at once. Without herdr-core: one read each second.
    events = (lambda wake: EventSource([core_path, "events", "--json"], wake)) if core_path else None
    client = HerdrClient(app_path, core_path)
    backend = Backend(client, icons=Icons(), events=events, sessions=SessionWatch(client))
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    if platform.prepare_engine(engine):
        engine.load(UI_PATH / "shells" / "Layer.qml")
    if not engine.rootObjects():
        logging.getLogger("bellwether").error("the QML interface did not load: it needs %s", platform.SHELL_NEEDS)
        return 1

    follow_refresh_rate(engine.rootObjects()[0])
    logging.getLogger("bellwether").info("screen refresh rate: %.0f Hz", engine.rootObjects()[0].property("refreshRate"))

    answer = Answer(engine, backend)  # the answer window, at the "Answer" control of a blocked agent row
    tray = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = Tray(backend, engine.rootObjects()[0], app, Options(engine).open)
    else:
        logging.getLogger("bellwether").warning("no system tray, the widget has no tray icon")

    backend.start()
    app.aboutToQuit.connect(backend.stop)
    logging.getLogger("bellwether").info("started")
    code = app.exec()
    # The tray first: its options entry holds the engine. Then the QML engine (and its windows), before the
    # backend: the bindings of the engine read the backend until they are gone.
    del tray
    del answer
    del engine
    del backend
    return code


if __name__ == "__main__":
    sys.exit(main())
