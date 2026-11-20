import os
import sys
from pathlib import Path

# Every Qt test runs off screen: no test opens a window on the real desktop.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def app():
    """The one Qt application object of the test session. QML needs a GUI application."""
    made = QApplication.instance() or QApplication([])
    if sys.platform != "linux":
        font_that_exists(made)
    return made


def font_that_exists(app):
    """Off screen the default font of Qt is "Sans Serif" (the theme of the offscreen plugin). Linux has it (a name
    of fontconfig); macOS and Windows do not, and Qt then warns at the first text with it ("Populating font family
    aliases … missing font family"). The tests there get the family that Qt finds for it. The program never runs
    off screen: there the default font of the system exists."""
    from PySide6.QtGui import QFont, QFontDatabase, QFontInfo
    font = app.font()
    if font.family() not in QFontDatabase.families():
        app.setFont(QFont(QFontInfo(font).family(), font.pointSize()))


# The width of the screen that the options window gets in the tests: the screen of the off-screen platform is 800 px
# wide, narrower than the window of five cards in one row (1076). A test of a narrow screen gives its own width.
ROOM_WIDTH = 1920


def wide_options(engine, *args):
    """The options object of the program, whose window gets a screen of ROOM_WIDTH before each show."""
    from bellwether.options import Options

    class WideOptions(Options):
        def fit_screen(self) -> None:
            self._window.setProperty("roomWidth", ROOM_WIDTH)

    return WideOptions(engine, *args)


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


# The cases of the panel tests that the macOS runner runs (marker `runner`): the plain shell on a real macOS Qt, off
# screen. All plain cases take 5 minutes there (5 times the time on Linux), over the budget of the job; these take
# about 12 s on Linux. They cover: the load and the flags of the plain shell, the window at the place of the panel
# (one request), the default corner, the work area, the clamp, the start from a saved place, a drag and its stop at an
# edge, a drag and a move to an other screen, the window system that moves the window, a layout switch, the status
# rows and a group, a click on a row, the answer control (click, row, drag), and a long group that scrolls.
RUNNER = {
    "tests/test_qml.py::" + name for name in (
        "test_the_program_loads_the_panel_in_the_shell_of_the_rule_and_writes_the_shell_in_the_log[None-plain]",
        "test_the_start_of_the_panel_gives_the_plain_shell_the_work_area_of_each_screen[plain-plain]",
        "test_the_plain_shell_is_a_frameless_tool_window_above_the_others_with_a_clear_background[plain]",
        "test_the_plain_window_is_at_the_place_of_the_panel_and_a_new_size_keeps_its_top_left_corner[plain]",
        "test_a_place_change_of_the_plain_window_is_one_request_with_both_coordinates[plain]",
        "test_a_new_size_at_the_default_corner_is_one_request_and_never_past_the_right_edge[plain]",
        "test_a_plain_window_that_the_window_system_moves_goes_back_one_time[plain]",
        "test_the_panel_stays_out_of_the_part_of_the_screen_that_the_system_keeps[plain]",
        "test_the_panel_is_kept_on_the_screen_that_holds_it[plain]",
        "test_a_bigger_skin_is_kept_on_the_screen_and_the_default_corner_follows_the_width[plain]",
        'test_the_start_uses_the_saved_screen_and_place[{"x": 120, "y": 48, "screen": "%s"}-False-120-48-plain]',
        "test_a_drag_from_a_row_moves_the_widget_and_does_not_click[plain]",
        "test_a_drag_stops_at_an_edge_with_no_screen_behind_it[plain]",
        "test_a_drag_to_the_other_screen_leaves_the_panel_there[plain]",
        "test_move_to_next_screen_keeps_the_distance_to_the_nearer_edges[plain]",
        "test_the_plain_window_goes_to_the_screen_of_the_panel_and_qt_follows_it_during_a_drag",
        "test_a_different_layout_shows_in_the_same_window_and_keeps_the_place_the_screen_and_the_open_group[plain]",
        "test_main_qml_shows_four_status_rows_and_opens_one_group_at_a_time[plain]",
        "test_a_click_on_an_agent_row_jumps_one_time[plain]",
    )} | {
    "tests/test_answer_control.py::" + name for name in (
        "test_a_click_on_the_control_opens_the_prompt_of_that_agent_and_does_not_jump[A-1.0-plain]",
        "test_a_click_on_the_rest_of_the_row_jumps_and_does_not_open[C-1.0-plain]",
        "test_a_drag_from_the_control_moves_the_panel_and_does_nothing_else[C-1.0-plain]",
    )} | {
    "tests/test_skins.py::test_a_group_of_12_shows_8_rows_and_scrolls_and_the_hint_takes_no_click_and_no_wheel_turn"
    "[A-1.0-plain]",
}


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.nodeid in RUNNER:
            item.add_marker(pytest.mark.runner)
