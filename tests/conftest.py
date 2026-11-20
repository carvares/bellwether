import os

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


@pytest.fixture
def shell(request):
    """The window shell of the panel of a test: "layer" (the default), or the parameter that the test gives
    (`@pytest.mark.parametrize("shell", [...], indirect=True)`)."""
    return getattr(request, "param", "layer")
