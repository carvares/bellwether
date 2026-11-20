import json

from bellwether.settings import (
    COLOR_ROLES, DEFAULT_LOOK, FONT_SCALE_LIMITS, SCALE_LIMITS, load_layout, load_look, load_position, save_layout,
    save_look, save_position, save_screen, valid_color)


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


# ----- the custom look: scale, fontScale, fontFamily, colors -----

FULL = {"scale": 1.5, "fontScale": 1.2, "fontFamily": "Some Font",
        "colors": {"blocked": "#112233", "done": "#223344", "working": "#334455", "idle": "#445566",
                   "background": "#cc101010", "text": "#ffffff", "frame": "#778899", "accent": "#abcdef"}}


def test_the_look_is_the_defaults_without_a_file_and_for_a_file_of_an_older_version(tmp_path):
    path = tmp_path / "state.json"
    assert load_look(path) == (DEFAULT_LOOK, [])
    assert DEFAULT_LOOK == {"scale": 1.0, "fontScale": 1.0, "fontFamily": "", "colors": {}}
    for text in ['{"x": 1, "y": 2, "screen": "DP-1", "layout": "B"}', "not json", "[]", "{}"]:
        path.write_text(text)
        assert load_look(path) == (DEFAULT_LOOK, []), text
    assert load_look(path)[0] is not DEFAULT_LOOK and load_look(path)[0]["colors"] is not DEFAULT_LOOK["colors"]


def test_the_look_goes_to_the_file_and_comes_back(tmp_path):
    path = tmp_path / "dir" / "state.json"
    save_look(FULL, path)
    assert json.loads(path.read_text()) == FULL
    assert load_look(path) == (FULL, [])


def test_a_value_at_its_default_has_no_key_in_the_file(tmp_path):
    path = tmp_path / "state.json"
    save_look(FULL, path)
    save_look({**FULL, "scale": 1.0, "colors": {"text": "#ffffff"}}, path)
    assert json.loads(path.read_text()) == {"fontScale": 1.2, "fontFamily": "Some Font", "colors": {"text": "#ffffff"}}
    save_look(DEFAULT_LOOK, path)  # reset everything: the file is as a file of an older version
    assert json.loads(path.read_text()) == {}


def test_saving_the_look_keeps_the_place_the_screen_and_the_layout_and_the_reverse(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"x": 30, "y": 40, "screen": "DP-1", "layout": "B", "later": [1]}')
    save_look(FULL, path)
    assert json.loads(path.read_text()) == {"x": 30, "y": 40, "screen": "DP-1", "layout": "B", "later": [1], **FULL}
    save_position(5, 6, path, screen="DP-2")
    save_layout("D", path)
    assert json.loads(path.read_text()) == {"x": 5, "y": 6, "screen": "DP-2", "layout": "D", "later": [1], **FULL}
    save_screen("DP-3", path)
    assert json.loads(path.read_text()) == {"screen": "DP-3", "layout": "D", "later": [1], **FULL}
    save_look(DEFAULT_LOOK, path)
    assert json.loads(path.read_text()) == {"screen": "DP-3", "layout": "D", "later": [1]}
    assert load_position(path) == (-1, -1, "DP-3") and load_layout(path) == "D"


def test_a_number_out_of_its_limits_is_clamped(tmp_path):
    path = tmp_path / "state.json"
    for saved, scale, font in ((0.1, 0.75, 0.8), (9, 2.0, 1.4), (0.75, 0.75, 0.8), (2, 2.0, 1.4), (1, 1.0, 1.0)):
        path.write_text(json.dumps({"scale": saved, "fontScale": saved}))
        look, ignored = load_look(path)
        assert (look["scale"], look["fontScale"], ignored) == (scale, font, []), saved
        assert type(look["scale"]) is float and type(look["fontScale"]) is float
    assert (SCALE_LIMITS, FONT_SCALE_LIMITS) == ((0.75, 2.0), (0.8, 1.4))


def test_each_value_that_is_not_valid_is_ignored_and_its_key_is_named(tmp_path):
    path = tmp_path / "state.json"
    cases = [
        ('{"scale": "2"}', ["scale"]), ('{"scale": true}', ["scale"]), ('{"scale": null}', ["scale"]),
        ('{"scale": NaN}', ["scale"]), ('{"scale": Infinity}', ["scale"]), ('{"scale": [1]}', ["scale"]),
        ('{"fontScale": "big"}', ["fontScale"]), ('{"fontScale": false}', ["fontScale"]),
        ('{"fontFamily": 3}', ["fontFamily"]), ('{"fontFamily": null}', ["fontFamily"]),
        ('{"colors": "#ffffff"}', ["colors"]), ('{"colors": ["#ffffff"]}', ["colors"]),
        ('{"colors": {"text": "white"}}', ["colors.text"]), ('{"colors": {"text": "#fff"}}', ["colors.text"]),
        ('{"colors": {"text": "#12345g"}}', ["colors.text"]), ('{"colors": {"text": 5}}', ["colors.text"]),
        ('{"colors": {"text": "#80ffffff"}}', ["colors.text"]),  # an alpha: only the background can have one
        ('{"colors": {"text": " #ffffff"}}', ["colors.text"]), ('{"colors": {"text": "#ffffff\\n"}}', ["colors.text"]),
        ('{"colors": {"background": "#1234567"}}', ["colors.background"]),
        ('{"colors": {"offline": "#ffffff"}}', ["colors"]),  # not one of the eight: its name is not written
        ('{"colors": {"none": "#ffffff", "panel": "#000000"}}', ["colors"]),
    ]
    for text, named in cases:
        path.write_text(text)
        assert load_look(path) == (DEFAULT_LOOK, named), text
    path.write_text(json.dumps({**FULL, "scale": "x", "colors": {**FULL["colors"], "idle": "green", "extra": "#000000"}}))
    look, ignored = load_look(path)  # the valid values of the same file apply
    wanted = {**FULL, "scale": 1.0, "colors": {k: v for k, v in FULL["colors"].items() if k != "idle"}}
    assert look == wanted and ignored == ["scale", "colors.idle", "colors"]


def test_a_colour_is_kept_in_small_letters_and_the_background_can_have_an_alpha(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"colors": {"text": "#ABCDEF", "background": "#80ABCDEF", "frame": "#abcdef"}}')
    assert load_look(path)[0]["colors"] == {"text": "#abcdef", "background": "#80abcdef", "frame": "#abcdef"}
    assert [valid_color(role, value) for role, value in (
        ("text", "#ABCDEF"), ("background", "#80ABCDEF"), ("background", "#abcdef"), ("text", "#80abcdef"),
        ("offline", "#abcdef"), ("text", "abcdef"), ("text", None), ("text", ""), ("", "#abcdef"))] == [
        "#abcdef", "#80abcdef", "#abcdef", None, None, None, None, None, None]
    assert COLOR_ROLES == ("blocked", "done", "working", "idle", "background", "text", "frame", "accent")
