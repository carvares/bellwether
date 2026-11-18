import json

from bellwether.settings import load_layout, load_position, save_layout, save_position, save_screen


def test_missing_file_gives_none(tmp_path):
    assert load_position(tmp_path / "state.json") is None


def test_save_then_load(tmp_path):
    path = tmp_path / "dir" / "state.json"
    save_position(120, 48, path)
    assert load_position(path) == (120, 48, "")


def test_save_replaces_old_value(tmp_path):
    path = tmp_path / "state.json"
    save_position(1, 2, path)
    save_position(3, 4, path)
    assert load_position(path) == (3, 4, "")


def test_invalid_content_gives_none(tmp_path):
    path = tmp_path / "state.json"
    for text in ["", "not json", "[]", '{"x": 1}', '{"x": "a", "y": 2}', '{"x": true, "y": 2}']:
        path.write_text(text)
        assert load_position(path) is None, text


def test_the_screen_is_saved_with_the_position(tmp_path):
    path = tmp_path / "state.json"
    save_position(30, 40, path, screen="DP-1")
    assert load_position(path) == (30, 40, "DP-1")
    save_position(5, 6, path)  # no screen: the position is for the screen that the compositor gives
    assert load_position(path) == (5, 6, "")


def test_a_file_of_an_older_version_has_no_screen(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"x": 1845, "y": 358}')
    assert load_position(path) == (1845, 358, "")


def test_a_screen_that_is_not_text_is_ignored(tmp_path):
    path = tmp_path / "state.json"
    for text in ['{"x": 1, "y": 2, "screen": 3}', '{"x": 1, "y": 2, "screen": null}', '{"x": 1, "y": 2, "screen": ["a"]}']:
        path.write_text(text)
        assert load_position(path) == (1, 2, ""), text


# ----- the whole state: one key does not drop the others -----

def test_saving_the_layout_keeps_the_position_and_the_reverse(tmp_path):
    path = tmp_path / "state.json"
    save_position(30, 40, path, screen="DP-1")
    save_layout("B", path)
    assert load_position(path) == (30, 40, "DP-1") and load_layout(path) == "B"
    save_position(5, 6, path, screen="DP-2")
    assert load_position(path) == (5, 6, "DP-2") and load_layout(path) == "B"
    assert json.loads(path.read_text()) == {"x": 5, "y": 6, "screen": "DP-2", "layout": "B"}


def test_a_key_of_a_later_version_stays_in_the_file(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"x": 1, "y": 2, "later": [1, 2]}')
    save_layout("C", path)
    save_position(3, 4, path)
    assert json.loads(path.read_text()) == {"x": 3, "y": 4, "screen": "", "later": [1, 2], "layout": "C"}


def test_the_layout_is_none_without_the_key_and_for_a_value_that_is_not_text(tmp_path):
    path = tmp_path / "state.json"
    assert load_layout(path) is None  # no file
    for text in ['{"x": 1, "y": 2}', '{"layout": 3}', '{"layout": null}', "not json", "[]"]:
        path.write_text(text)
        assert load_layout(path) is None, text
    path.write_text('{"layout": "Z"}')
    assert load_layout(path) == "Z"  # the caller knows which layouts exist


def test_saving_into_a_file_that_is_not_valid_starts_a_new_one(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("not json")
    save_layout("C", path)
    assert json.loads(path.read_text()) == {"layout": "C"}


def test_saving_only_the_screen_drops_the_place_and_keeps_the_layout(tmp_path):
    """The panel at its default corner has no place of its own: only its screen is saved."""
    path = tmp_path / "state.json"
    save_position(30, 40, path, screen="DP-1")
    save_layout("C", path)
    save_screen("DP-2", path)
    assert json.loads(path.read_text()) == {"screen": "DP-2", "layout": "C"}
    assert load_position(path) == (-1, -1, "DP-2")  # no place: the default corner of that screen
    path.write_text('{"layout": "C"}')
    assert load_position(path) is None  # no place and no screen
