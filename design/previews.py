"""Makes the pictures of the options window, bellwether/ui/previews/<letter>.png, from the REAL skins: the real
Main.qml with each built layout, closed, with the made-up counts blocked 1, done 2, working 3, idle 4, on a dark
background, cropped to the panel, 360 px wide (shown 180 px wide, so it is sharp at scale 2 too).

Off screen only: no window opens on the desktop. Run from the repository root:  uv run python design/previews.py
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render as R  # noqa: E402  (sets the off-screen platform and scale 2, and makes the application)

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402,F401

from bellwether import layouts  # noqa: E402
from bellwether.__main__ import IMPORT_PATH  # noqa: E402
from bellwether.backend import Backend  # noqa: E402
from bellwether.state import Agent  # noqa: E402
from bellwether.tray import STATE_COLORS  # noqa: E402

WIDTH = 360
COUNTS = {"blocked": 1, "done": 2, "working": 3, "idle": 4}


class NoClient:
    """The backend is never started: it gets its agents from apply()."""


def settle(times: int = 12) -> None:
    for _ in range(times):
        R.app.processEvents()
        time.sleep(0.005)


def panel(letter: str, folder: Path) -> QImage:
    """The real panel in one layout, as an image with a transparent background."""
    backend = Backend(NoClient(), settings_path=folder / "state.json")
    backend.setLayout(letter)
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda ws: R.warnings.extend(w.toString() for w in ws))
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("stateColors_", STATE_COLORS)
    engine.addImportPath(str(IMPORT_PATH))
    engine.load(layouts.UI_PATH / "Main.qml")
    root = engine.rootObjects()[0]
    backend.apply([Agent(f"{state[0]}{n}", state, f"agent {n}", "Main") for state, count in COUNTS.items() for n in range(count)])
    settle()
    assert backend.layout == letter, f"layout {letter} did not load"
    image = root.grabWindow().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(R.SCALE)
    del engine
    R.app.processEvents()
    return image


def main() -> None:
    folder = Path(tempfile.mkdtemp(prefix="bellwether-previews-"))
    layouts.PREVIEWS_PATH.mkdir(parents=True, exist_ok=True)
    for letter in sorted(layouts.built_skins()):
        shot = panel(letter, folder)
        w, h = R.size_of(shot)
        picture = R.canvas(w, h)
        painter = R.painter_for(picture)
        R.backdrop(painter, QRectF(0, 0, w, h), True)
        painter.drawImage(QPointF(0, 0), shot)
        painter.end()
        small = picture.scaledToWidth(WIDTH, Qt.TransformationMode.SmoothTransformation)
        small.setDevicePixelRatio(1)
        path = layouts.PREVIEWS_PATH / f"{letter}.png"
        small.save(str(path))
        print(f"{letter}: panel {w:.0f}x{h:.0f}, file {small.width()}x{small.height()}, {path.stat().st_size} bytes")
    for line in dict.fromkeys(R.warnings):
        print("QML WARNING", line)


if __name__ == "__main__":
    main()
