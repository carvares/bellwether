"""The panel in the plain shell on two real off-screen screens, in a process of its own (the screens of the off-screen
platform are fixed when the application starts). `tests/test_qml.py` runs it with
QT_QPA_PLATFORM=offscreen:configfile=<a file with the screens LEFT (1920 x 1080 at 0, 0) and RIGHT (1280 x 720 at
1920, 0)> and reads one JSON object for each step: the place of the panel, the place of the window, its screen in Qt.
Run: python -m tests.plain_screens <state file>"""
import json
import sys
import time
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression, qmlContext
from PySide6.QtQuick import QQuickWindow  # noqa: F401  (the type of the root object)
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bellwether.backend import Backend
from bellwether.layouts import UI_PATH, built_skins


class NoClient:
    def list_agents(self):
        return []

    def focus_agent(self, key):
        pass


def main() -> None:
    app = QApplication([])
    backend = Backend(NoClient(), settings_path=Path(sys.argv[1]), skins=built_skins())
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(UI_PATH / "shells" / "Plain.qml")
    root = engine.rootObjects()[0]

    def settle():
        for _ in range(5):
            app.processEvents()
            time.sleep(0.01)

    def run(text):
        expression = QQmlExpression(qmlContext(root), root, text)
        expression.evaluate()
        assert not expression.hasError(), expression.error().toString()

    def step(name):
        print(json.dumps({"step": name, "screens": [s.name() for s in app.screens()],
                          "place": [root.property("screenName"), root.property("posX"), root.property("posY")],
                          "window": [root.x(), root.y(), root.width(), root.height()],
                          "qtScreen": root.screen().name(), "surfaceScreen": root.property("surfaceScreen"),
                          "visible": root.isVisible()}), flush=True)

    settle()
    step("start")
    run("root.moveToNextScreen()")
    settle()
    step("next screen")
    run("root.moveToNextScreen()")
    settle()
    step("next screen again")
    run("root.atDefault = false; root.posX = 1500; root.posY = 300")
    settle()
    step("placed")
    # A drag to the right, across the edge of the two screens. Each move is one step (minMoveMs) after the last.
    # The pointer moves in the desktop and the window moves with the panel: each event is at the place of the
    # pointer in the window as it is now (as a real pointer).
    left, none, start, origin = Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(100, 20), root.position()
    QTest.mousePress(root, left, none, start)
    settle()
    for dx in (100, 250, 300):
        time.sleep(0.03)
        QTest.mouseMove(root, start + QPoint(dx, 0) - (root.position() - origin))
        settle()
        step(f"drag {dx}")
    QTest.mouseRelease(root, left, none, start + QPoint(300, 0) - (root.position() - origin))
    settle()
    step("released")
    del engine


if __name__ == "__main__":
    main()
