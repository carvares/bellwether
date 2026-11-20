import os
from pathlib import Path

# Every Qt test runs off screen: no test opens a window on the real desktop.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def app():
    """The one Qt application object of the test session. QML needs a GUI application."""
    return QApplication.instance() or QApplication([])


class FakeClient:
    def __init__(self):
        self.result = []
        self.list_error = None
        self.focus_error = None
        self.focused = []
        self.focus_gate = None  # a threading.Event: focus_agent waits for it

    def list_agents(self):
        if self.list_error:
            raise self.list_error
        return self.result

    def focus_agent(self, key):
        self.focused.append(key)
        if self.focus_gate is not None:
            self.focus_gate.wait(5)
        if self.focus_error:
            raise self.focus_error


@pytest.fixture
def fake_client():
    return FakeClient()


# The system QML module of the layer shell. Without it (macOS, Windows, a desktop with no layer-shell-qt) only the
# tests of the layer shell are skipped: the plain shell needs nothing.
LAYERSHELL_QMLDIR = Path("/usr/lib/qt6/qml/org/kde/layershell/qmldir")
needs_layershell = pytest.mark.skipif(not LAYERSHELL_QMLDIR.is_file(),
                                      reason=f"the system QML module org.kde.layershell is not installed ({LAYERSHELL_QMLDIR})")


def shell_for(chosen, qmldir=LAYERSHELL_QMLDIR):
    """The shell of a test; a skip of the test when it is the layer shell and its module is not installed."""
    if chosen == "layer" and not qmldir.is_file():
        pytest.skip(f"the system QML module org.kde.layershell is not installed ({qmldir})")
    return chosen


@pytest.fixture
def shell(request):
    """The window shell of the panel of a test: "layer" (the default), or the parameter that the test gives
    (`@pytest.mark.parametrize("shell", [...], indirect=True)`)."""
    return shell_for(getattr(request, "param", "layer"))
