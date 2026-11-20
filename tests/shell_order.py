"""The order of what a shell does when the panel goes to an other real screen, in a process of its own with two real
off-screen screens (LEFT 1920 x 1080 at 0, 0 and RIGHT 1280 x 720 at 1920, 0, from the configfile of
QT_QPA_PLATFORM). A recording double of the shell (a type derived from it, made from a text in the folder of the
shells) writes each change: the visibility, the screen name of the panel, the screen of the window, the window
place, surfaceScreen. `tests/test_qml.py` runs it and reads one JSON object for each step.
Run: python -m tests.shell_order <Layer|Plain> <state file>"""
import json
import sys
import time
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression, qmlContext
from PySide6.QtQuick import QQuickWindow  # noqa: F401  (the type of the object)
from PySide6.QtWidgets import QApplication

from bellwether.backend import Backend
from bellwether.layouts import UI_PATH, built_skins
from bellwether.platform.linux import IMPORT_PATH

DOUBLE = """import QtQuick
%s {
    property string log: ""
    onVisibleChanged: log += "visible " + visible + ";"
    onScreenNameChanged: log += "screenName " + screenName + ";"
    onScreenChanged: log += "screen " + (screen ? screen.name : "") + ";"
    onXChanged: log += "x " + x + ";"
    onSurfaceScreenChanged: log += "surface " + surfaceScreen + ";"
}
"""


class NoClient:
    def list_agents(self):
        return []

    def focus_agent(self, key):
        pass


def main() -> None:
    app = QApplication([])
    backend = Backend(NoClient(), settings_path=Path(sys.argv[2]), skins=built_skins())
    engine = QQmlEngine()
    engine.addImportPath(str(IMPORT_PATH))
    engine.rootContext().setContextProperty("backend", backend)
    component = QQmlComponent(engine)
    component.setData((DOUBLE % sys.argv[1]).encode(), QUrl.fromLocalFile(str(UI_PATH / "shells" / "OrderDouble.qml")))
    root = component.create()
    assert root is not None, [e.toString() for e in component.errors()]

    def settle():
        for _ in range(5):
            app.processEvents()
            time.sleep(0.01)

    def step(name, script=None):
        if script:
            root.setProperty("log", "")
            expression = QQmlExpression(qmlContext(root), root, script)
            expression.evaluate()
            assert not expression.hasError(), expression.error().toString()
        settle()
        print(json.dumps({"step": name, "log": [w for w in root.property("log").split(";") if w],
                          "window": [root.x(), root.y()], "qtScreen": root.screen().name(),
                          "place": [root.property("screenName"), root.property("posX"), root.property("posY")]}),
              flush=True)

    settle()
    step("start")
    step("next screen", "moveToNextScreen()")
    step("next screen again", "moveToNextScreen()")
    del root


if __name__ == "__main__":
    main()
