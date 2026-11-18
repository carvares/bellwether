from herdr_float.settings import load_position, save_position


def test_missing_file_gives_none(tmp_path):
    assert load_position(tmp_path / "state.json") is None


def test_save_then_load(tmp_path):
    path = tmp_path / "dir" / "state.json"
    save_position(120, 48, path)
    assert load_position(path) == (120, 48)


def test_save_replaces_old_value(tmp_path):
    path = tmp_path / "state.json"
    save_position(1, 2, path)
    save_position(3, 4, path)
    assert load_position(path) == (3, 4)


def test_invalid_content_gives_none(tmp_path):
    path = tmp_path / "state.json"
    for text in ["", "not json", "[]", '{"x": 1}', '{"x": "a", "y": 2}', '{"x": true, "y": 2}']:
        path.write_text(text)
        assert load_position(path) is None, text
