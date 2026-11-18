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
        self.result = {"type": "agent_list", "agents": []}
        self.list_error = None
        self.focus_error = None
        self.focused = []

    def list_agents(self):
        if self.list_error:
            raise self.list_error
        return self.result

    def focus_agent(self, pane_id):
        self.focused.append(pane_id)
        if self.focus_error:
            raise self.focus_error


@pytest.fixture
def fake_client():
    return FakeClient()
