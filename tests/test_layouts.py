"""The layout choice: the catalogue of the five designs, and the layout of the backend (saved, and live)."""
import json
import logging
from pathlib import Path

from PySide6.QtCore import QUrl

from bellwether import layouts
from bellwether.backend import Backend

# Made-up skin files: the backend only gives their paths to the QML.
SKINS = {"C": Path("/skins/C.qml"), "T": Path("/skins/T.qml")}


def make(fake_client, path, skins=SKINS):
    return Backend(fake_client, settings_path=path, skins=skins)


def test_the_catalogue_has_the_five_approved_designs_and_c_is_the_default():
    assert [(letter, name) for letter, name, _ in layouts.LAYOUTS] == [
        ("A", "Refined list"), ("B", "Tiles"), ("C", "Techno / HUD"), ("D", "Signal strip"), ("E", "Ring")]
    assert all(text and len(text) < 70 for _, _, text in layouts.LAYOUTS)  # one line each
    assert layouts.DEFAULT == "C"


def test_a_layout_is_built_when_its_skin_file_is_there(tmp_path):
    for name in ("C.qml", "E.qml", "Z.qml", "notes.txt"):  # Z is not a design of the catalogue
        (tmp_path / name).write_text("")
    assert layouts.built_skins(tmp_path) == {"C": tmp_path / "C.qml", "E": tmp_path / "E.qml"}
    assert layouts.built_skins(tmp_path / "not-there") == {}


def test_the_program_has_the_default_skin_and_a_preview_of_each_design():
    assert layouts.DEFAULT in layouts.built_skins()
    for letter, _, _ in layouts.LAYOUTS:
        assert (layouts.PREVIEWS_PATH / f"{letter}.png").is_file(), letter


def test_the_layout_is_c_without_a_saved_one_and_with_no_log_line(app, fake_client, tmp_path, caplog):
    path = tmp_path / "state.json"
    path.write_text('{"x": 7, "y": 8}')  # a file of an older version
    with caplog.at_level(logging.INFO, logger="bellwether"):
        backend = make(fake_client, path)
    assert backend.layout == "C" and backend.skinSource == QUrl.fromLocalFile("/skins/C.qml")
    assert caplog.records == []
    assert json.loads(path.read_text()) == {"x": 7, "y": 8}  # a start writes nothing


def test_a_new_layout_is_told_one_time_and_saved_and_a_later_start_loads_it(app, fake_client, tmp_path):
    path = tmp_path / "state.json"
    backend = make(fake_client, path)
    told = []
    backend.layoutChanged.connect(lambda: told.append(backend.layout))
    backend.setLayout("T")
    assert told == ["T"] and backend.skinSource == QUrl.fromLocalFile("/skins/T.qml")
    assert json.loads(path.read_text()) == {"layout": "T"}
    backend.setLayout("T")  # the same layout: nothing to do
    assert told == ["T"]
    assert make(fake_client, path).layout == "T"


def test_a_layout_that_is_not_built_cannot_be_chosen(app, fake_client, tmp_path):
    path = tmp_path / "state.json"
    backend = make(fake_client, path)
    told = []
    backend.layoutChanged.connect(lambda: told.append(backend.layout))
    for name in ("A", "Z", "", "c"):
        backend.setLayout(name)
    assert backend.layout == "C" and told == [] and not path.exists()


def test_a_saved_layout_that_is_unknown_or_not_built_gives_c_with_one_log_line(app, fake_client, tmp_path, caplog):
    path = tmp_path / "state.json"
    for saved in ("Z", "A", ""):  # not a design, a design that is not built, an empty name
        path.write_text(json.dumps({"layout": saved, "x": 1, "y": 2}))
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="bellwether"):
            backend = make(fake_client, path)
        assert backend.layout == "C", saved
        assert [r.getMessage() for r in caplog.records] == ["the saved layout is not available: the layout is C"]
        assert json.loads(path.read_text())["layout"] == saved  # the file stays as it is


def test_saving_the_layout_keeps_the_position_and_saving_the_position_keeps_the_layout(app, fake_client, tmp_path):
    path = tmp_path / "state.json"
    backend = make(fake_client, path)
    backend.savePosition(300, 40, "DP-1")
    backend.setLayout("T")
    assert json.loads(path.read_text()) == {"x": 300, "y": 40, "screen": "DP-1", "layout": "T"}
    backend.savePosition(10, 20, "DP-2")
    assert json.loads(path.read_text()) == {"x": 10, "y": 20, "screen": "DP-2", "layout": "T"}
    later = make(fake_client, path)
    assert (later.savedX, later.savedY, later.savedScreen, later.layout) == (10, 20, "DP-2", "T")


def test_a_layout_that_cannot_be_saved_is_still_shown_and_gives_one_log_line(app, fake_client, tmp_path, caplog):
    (tmp_path / "file").write_text("")
    backend = make(fake_client, tmp_path / "file" / "state.json")  # the folder cannot be made
    with caplog.at_level(logging.INFO, logger="bellwether"):
        backend.setLayout("T")
    assert backend.layout == "T"
    assert [r.getMessage() for r in caplog.records] == ["layout: T", "layout was not saved"]


def test_the_options_list_has_the_five_designs_and_marks_the_built_ones(app, fake_client, tmp_path):
    backend = make(fake_client, tmp_path / "state.json")
    listed = backend.layouts
    assert [(row["id"], row["name"], row["built"]) for row in listed] == [
        ("A", "Refined list", False), ("B", "Tiles", False), ("C", "Techno / HUD", True),
        ("D", "Signal strip", False), ("E", "Ring", False)]  # T is a skin of the tests: not a design, not listed
    assert all(row["description"] for row in listed)
    assert [row["preview"] for row in listed] == [
        QUrl.fromLocalFile(str(layouts.PREVIEWS_PATH / f"{letter}.png")) for letter in "ABCDE"]


def test_a_skin_that_does_not_load_gives_c_in_memory_and_the_saved_layout_stays(app, fake_client, tmp_path, caplog):
    path = tmp_path / "state.json"
    backend = make(fake_client, path)
    backend.setLayout("T")
    told = []
    backend.layoutChanged.connect(lambda: told.append(backend.layout))
    with caplog.at_level(logging.INFO, logger="bellwether"):
        backend.skinFailed("Error")
    assert backend.layout == "C" and told == ["C"]
    assert json.loads(path.read_text()) == {"layout": "T"}  # the file is not changed: a later version can load T
    assert [r.getMessage() for r in caplog.records] == ["the layout T did not load (Error): the layout is C"]
    assert make(fake_client, path).layout == "T"  # the next start tries the saved layout again
    caplog.clear()
    backend.skinFailed("Error")  # the default skin itself: there is no other one to show
    assert backend.layout == "C" and [r.getMessage() for r in caplog.records] == ["the layout C did not load (Error)"]
    backend.setLayout("C")  # the person chooses the layout that shows: it is saved now
    assert told == ["C"] and json.loads(path.read_text()) == {"layout": "C"}


def test_a_start_without_the_default_skin_file_says_so_in_the_log(app, fake_client, tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="bellwether"):
        backend = make(fake_client, tmp_path / "state.json", skins={"T": Path("/skins/T.qml")})
    assert backend.layout == "C" and backend.skinSource == QUrl()
    assert [r.getMessage() for r in caplog.records] == ["the skin file of the default layout C is missing: the panel cannot show"]
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="bellwether"):
        make(fake_client, tmp_path / "state.json")
    assert caplog.records == []


def test_only_the_screen_is_saved_for_a_panel_at_its_default_corner(app, fake_client, tmp_path):
    path = tmp_path / "state.json"
    backend = make(fake_client, path)
    backend.savePosition(300, 40, "DP-1")
    backend.setLayout("T")
    backend.saveScreen("DP-2")
    assert json.loads(path.read_text()) == {"screen": "DP-2", "layout": "T"}
    later = make(fake_client, path)
    assert (later.savedX, later.savedY, later.savedScreen) == (-1, -1, "DP-2")
