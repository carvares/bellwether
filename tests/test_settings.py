from bellwether.settings import load_position, save_position


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
