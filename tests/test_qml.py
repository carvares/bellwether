"""Smoke test of the real Main.qml, loaded the same way as herdr_float/__main__.py (off screen)."""
from pathlib import Path

import pytest
from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow

from herdr_float.__main__ import IMPORT_PATH, UI_PATH
from herdr_float.backend import Backend
from herdr_float.state import Agent
from herdr_float.tray import STATE_COLORS

LAYERSHELL_QMLDIR = Path("/usr/lib/qt6/qml/org/kde/layershell/qmldir")
# layer-shell-qt says this for every window on a platform that is not Wayland. It is expected off screen.
OFFSCREEN_NOTE = "is not a wayland window"

pytestmark = pytest.mark.skipif(
    not LAYERSHELL_QMLDIR.is_file(),
    reason=f"the system QML module org.kde.layershell is not installed ({LAYERSHELL_QMLDIR} not found)",
)


def walk(item):
    yield item
    for child in item.childItems():
        yield from walk(child)


@pytest.fixture
def window(app, fake_client, tmp_path):
    """Yield (root window, backend, Qt messages). The poll thread is not started."""
    assert app.platformName() == "offscreen"
    backend = Backend(fake_client, settings_path=tmp_path / "state.json")
    messages = []
    previous = qInstallMessageHandler(lambda mode, context, text: messages.append(text))
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda errors: messages.extend(e.toString() for e in errors))
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("stateColors_", STATE_COLORS)
    engine.addImportPath(str(IMPORT_PATH))
    engine.load(UI_PATH / "Main.qml")
    try:
        roots = engine.rootObjects()
        assert roots, f"Main.qml did not load: {messages}"
        assert isinstance(roots[0], QQuickWindow)
        yield roots[0], backend, messages
    finally:
        del engine
        app.processEvents()
        qInstallMessageHandler(previous)
    assert backend._thread is None


def test_main_qml_loads_and_follows_the_backend(app, window):
    root, backend, messages = window
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []

    backend.apply([Agent("t1", "blocked", "rev", "Main")])
    root.setProperty("expanded", True)
    app.processEvents()
    assert root.width() == 300

    backend.apply(None)
    app.processEvents()
    assert root.property("expanded") is False

    items = list(walk(root.contentItem()))
    agent_list = next(i for i in items if i.property("failedPane") is not None)
    offline_text = next(i for i in items if i.property("text") == "offline")
    assert backend.online is False
    assert agent_list.isVisible() is False
    assert offline_text.isVisible() is True
    assert [m for m in messages if OFFSCREEN_NOTE not in m] == []
