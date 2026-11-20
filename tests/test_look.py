"""The custom look in the backend: the scale, the font scale, the font family and the colours. Their values, their
limits, the slots that change them, the signals, and the save at the end of a burst of changes."""
import json
import logging
from pathlib import Path

import pytest

from bellwether import layouts, settings
from bellwether.backend import Backend
from bellwether.icons import TEXT_COLOR, Icons
from bellwether.state import STATE_COLORS, Agent

SKINS = {"C": layouts.built_skins()["C"], "A": layouts.built_skins()["A"], "T": Path("/skins/T.qml")}
FAMILIES = ["Made Up Mono", "Made Up Sans"]
ROLES = ["blocked", "done", "working", "idle", "background", "text", "frame", "accent"]
C_DEFAULTS = {**{state: STATE_COLORS[state] for state in ROLES[:4]},
              "background": "#f00b0e11", "text": "#e3e9ee", "frame": "#2b333b", "accent": "#8ab4f8"}
A_DEFAULTS = {**C_DEFAULTS, "background": "#f21f2023", "text": "#e8eaed", "frame": "#3c4043"}
CUSTOM = {"blocked": "#aa0000", "done": "#bbbb00", "working": "#0000cc", "idle": "#00dd00",
          "background": "#80101010", "text": "#fefefe", "frame": "#123456", "accent": "#ff00ff"}
SIGNALS = ("scaleChanged", "fontScaleChanged", "fontFamilyChanged", "colorsChanged")


def make(fake_client, path, **more):
    more.setdefault("skins", SKINS)
    more.setdefault("families", FAMILIES)
    return Backend(fake_client, settings_path=path, **more)


@pytest.fixture
def path(tmp_path):
    return tmp_path / "state.json"


@pytest.fixture
def backend(app, fake_client, path):
    return make(fake_client, path)


def told_by(backend):
    """The names of the look signals in the order in which the backend sends them."""
    told = []
    for name in SIGNALS:
        getattr(backend, name).connect(lambda name=name: told.append(name))
    return told


def fire(timer):
    """The time of the timer is over."""
    timer.stop()
    timer.timeout.emit()


def saved(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# ----- the values, their limits and their defaults -----

def test_with_no_custom_look_every_value_is_its_default_and_no_colour_is_changed(backend, path):
    assert (backend.scale, backend.fontScale, backend.fontFamily) == (1.0, 1.0, "")
    assert (backend.scaleMin, backend.scaleMax, backend.scaleDefault) == (0.75, 2.0, 1.0)
    assert (backend.fontScaleMin, backend.fontScaleMax, backend.fontScaleDefault) == (0.8, 1.4, 1.0)
    assert backend.colorRoles == ROLES
    assert backend.colorOverrides == {} and backend.colors == backend.defaultColors == C_DEFAULTS
    assert backend.stateColors == STATE_COLORS and backend.stateColors is not STATE_COLORS
    assert not path.exists()  # a start writes nothing


def test_the_default_colours_are_those_of_the_theme_of_the_layout_that_shows(backend):
    told = told_by(backend)
    backend.setLayout("A")
    assert backend.defaultColors == backend.colors == A_DEFAULTS and told == ["colorsChanged"]
    backend.setLayout("T")  # a skin with no theme file: the theme of the default layout, as themeSource
    assert backend.defaultColors == C_DEFAULTS
    backend.setLayout("A")
    backend.skinFailed("Error")  # Layout C shows now
    assert backend.layout == "C" and backend.defaultColors == C_DEFAULTS


def test_the_default_colours_of_every_real_theme_file_are_read(app, fake_client, path):
    backend = make(fake_client, path, skins=None)
    seen = {}
    for letter in "ABCDE":
        backend.setLayout(letter)
        seen[letter] = backend.defaultColors
        assert list(seen[letter]) == ROLES and all(settings.valid_color(r, c) == c for r, c in seen[letter].items())
    assert seen["A"] == A_DEFAULTS and seen["C"] == C_DEFAULTS
    assert seen["B"]["background"] == "#f21b1c1f" and seen["D"] == seen["E"] == seen["A"]


def test_the_theme_colours_of_a_file_that_cannot_be_read_are_those_of_layout_c(tmp_path):
    assert layouts.theme_colors(tmp_path / "NoTheme.qml") == layouts.FALLBACK_COLORS
    (tmp_path / "ZTheme.qml").write_text('ThemeBase { readonly property color textColor: text("#010203") }', encoding="utf-8")
    with pytest.raises(layouts.ThemeColorError, match="panelColor"):  # a file that can be read: no colour of C
        layouts.theme_colors(tmp_path / "ZTheme.qml")
    (tmp_path / "ZTheme.qml").write_text("""ThemeBase {
        readonly property color panelColor: background("#0A0B0C")
        readonly property color textColor: text("#010203")
        readonly property color frameColor: "#040506"
        readonly property color accentColor: accent("#070809") }""", encoding="utf-8")
    assert layouts.theme_colors(tmp_path / "ZTheme.qml") == {
        "background": "#ff0a0b0c", "text": "#010203", "frame": "#040506", "accent": "#070809"}
    assert layouts.FALLBACK_COLORS == {role: C_DEFAULTS[role] for role in ROLES[4:]}


# ----- the scale and the font scale -----

@pytest.mark.parametrize("name, low, high", [("scale", 0.75, 2.0), ("fontScale", 0.8, 1.4)])
def test_a_number_is_applied_at_once_clamped_to_its_limits_and_told_one_time(backend, name, low, high):
    slot = getattr(backend, "set" + name[0].upper() + name[1:])
    told = told_by(backend)
    assert slot(1.25) is True and getattr(backend, name) == 1.25 and told == [name + "Changed"]
    assert slot(1.25) is True and told == [name + "Changed"]  # the same value: accepted, nothing to tell
    assert slot(99) is True and getattr(backend, name) == high
    assert slot(-3) is True and getattr(backend, name) == low
    assert slot(low) is True and slot(high) is True and getattr(backend, name) == high
    assert slot(1.23456) is True and getattr(backend, name) == 1.23  # two decimal places
    count = len(told)
    for bad in (float("nan"), float("inf"), float("-inf")):
        assert slot(bad) is False and getattr(backend, name) == 1.23
    assert len(told) == count and set(told) == {name + "Changed"}


# ----- the font family -----

def test_a_font_family_of_the_list_is_applied_and_an_unknown_one_changes_nothing(backend):
    told = told_by(backend)
    assert backend.fontFamilies == FAMILIES
    assert backend.setFontFamily("Made Up Sans") is True and backend.fontFamily == "Made Up Sans"
    assert backend.setFontFamily("Not Here") is False and backend.setFontFamily("made up sans") is False
    assert backend.fontFamily == "Made Up Sans" and told == ["fontFamilyChanged"]
    assert backend.setFontFamily("") is True and backend.fontFamily == "" and told == ["fontFamilyChanged"] * 2


def test_the_font_list_of_the_system_is_sorted_has_no_duplicates_and_only_fonts_for_latin_text(app, fake_client, path):
    from PySide6.QtGui import QFontDatabase
    listed = Backend(fake_client, settings_path=path, skins=SKINS).fontFamilies
    assert listed and listed == sorted(set(listed), key=str.casefold)
    assert set(listed) <= set(QFontDatabase.families())
    for family in listed:
        assert QFontDatabase.WritingSystem.Latin in QFontDatabase.writingSystems(family), family
        assert QFontDatabase.isSmoothlyScalable(family) and not QFontDatabase.isPrivateFamily(family), family
    assert "Noto Color Emoji" not in listed


# ----- the colours -----

def test_each_colour_is_applied_told_and_listed_as_changed(backend):
    told = told_by(backend)
    for n, (role, colour) in enumerate(CUSTOM.items(), 1):
        assert backend.setColor(role, colour.upper()) is True
        assert backend.colors[role] == colour and backend.colorOverrides[role] == colour and len(told) == n
    assert set(told) == {"colorsChanged"}
    assert backend.colors == backend.colorOverrides == CUSTOM and backend.defaultColors == C_DEFAULTS
    assert backend.stateColors == {**STATE_COLORS, **{state: CUSTOM[state] for state in ROLES[:4]}}
    assert backend.setColor("text", CUSTOM["text"]) is True and len(told) == 8  # the same colour: nothing to tell
    backend.setLayout("A")  # a layout switch keeps the custom colours
    assert backend.colors == CUSTOM and backend.defaultColors == A_DEFAULTS


def test_a_colour_that_is_not_valid_changes_nothing(backend):
    told = told_by(backend)
    for role, value in (("text", "white"), ("text", "#fff"), ("text", "#80ffffff"), ("text", ""), ("offline", "#ffffff"),
                        ("none", "#ffffff"), ("", "#ffffff"), ("panel", "#ffffff"), ("background", "#12345")):
        assert backend.setColor(role, value) is False, (role, value)
    assert backend.colorOverrides == {} and told == []
    assert backend.setColor("background", "#101010") is True and backend.setColor("background", "#CC101010") is True
    assert backend.colors["background"] == "#cc101010"


def test_one_colour_goes_back_to_its_default_and_then_everything(backend):
    for role, colour in CUSTOM.items():
        backend.setColor(role, colour)
    backend.setScale(1.5), backend.setFontScale(1.2), backend.setFontFamily("Made Up Mono")
    told = told_by(backend)
    assert backend.resetColor("text") is True and backend.colors["text"] == C_DEFAULTS["text"]
    assert "text" not in backend.colorOverrides and told == ["colorsChanged"]
    assert backend.resetColor("text") is True and told == ["colorsChanged"]  # not changed: accepted, nothing to tell
    assert backend.resetColor("offline") is False and backend.resetColor("") is False
    backend.resetLook()
    assert (backend.scale, backend.fontScale, backend.fontFamily, backend.colorOverrides) == (1.0, 1.0, "", {})
    assert backend.colors == C_DEFAULTS and backend.stateColors == STATE_COLORS
    assert sorted(told[1:]) == sorted(SIGNALS)  # each one time
    backend.resetLook()
    assert len(told) == 5  # nothing to reset: nothing to tell


def test_the_background_colour_in_effect_is_the_colour_that_is_drawn_with_its_opacity(backend):
    """colors: what the panel draws. colorOverrides: what the user chose and the file holds. defaultColors: the
    layout."""
    assert backend.colors["background"] == backend.defaultColors["background"] == "#f00b0e11"
    told = told_by(backend)
    backend.setColor("background", "#102030")  # no opacity of its own: the opacity of the layout
    assert backend.colorOverrides["background"] == "#102030" and backend.colors["background"] == "#f0102030"
    backend.setLayout("A")  # the opacity of Layout A is f2
    assert backend.defaultColors["background"] == "#f21f2023" and backend.colors["background"] == "#f2102030"
    assert told == ["colorsChanged", "colorsChanged"]
    backend.setColor("background", "#80102030")  # its own opacity, in every layout
    assert backend.colorOverrides["background"] == backend.colors["background"] == "#80102030"
    backend.resetColor("background")
    assert backend.colors["background"] == "#f21f2023" and "background" not in backend.colorOverrides
    assert all(len(colour) == 7 for role, colour in backend.colors.items() if role != "background")


def test_the_steps_of_the_two_sliders_come_from_the_backend(backend):
    assert (backend.scaleStep, backend.fontScaleStep) == (0.05, 0.05)
    assert (backend.opacityMin, backend.opacityMax, backend.opacityStep) == (0.1, 1.0, 0.05)  # the background's
    assert backend.lookIsCustom is False
    told = []
    backend.lookIsCustomChanged.connect(lambda: told.append(backend.lookIsCustom))
    backend.setScale(1.0)
    backend.setScale(1.25)
    backend.setColor("text", "#ffffff")
    assert told == [True] and backend.lookIsCustom is True
    backend.setScale(1.0)
    assert told == [True]  # the colour is still custom
    backend.resetColor("text")
    backend.setFontFamily("Made Up Mono"), backend.setFontFamily("")
    backend.setFontScale(1.1)
    backend.resetLook()
    assert told == [True, False, True, False, True, False]


# ----- the save -----

def test_a_burst_of_changes_is_saved_one_time_at_its_end_with_the_last_value(backend, path, monkeypatch):
    writes = []
    real = settings.save_look
    monkeypatch.setattr("bellwether.backend.save_look",
                        lambda look, where, changed: (writes.append(dict(look)), real(look, where, changed)))
    timer = backend._look_timer
    assert timer.isSingleShot() and timer.interval() == 400 and not timer.isActive()
    for step in range(76, 151):  # a slider that moves
        backend.setScale(step / 100)
        assert timer.isActive()
    assert writes == [] and not path.exists()
    fire(timer)  # 0.4 s after the last change
    assert len(writes) == 1 and saved(path) == {"scale": 1.5}
    backend.setScale(1.5)  # no change: no new save
    assert not timer.isActive()
    backend.setColor("text", "#ffffff"), backend.setFontScale(0.9), backend.setFontFamily("Made Up Sans")
    fire(timer)
    assert len(writes) == 2
    assert saved(path) == {"scale": 1.5, "fontScale": 0.9, "fontFamily": "Made Up Sans", "colors": {"text": "#ffffff"}}
    backend.resetLook()
    fire(timer)
    assert len(writes) == 3 and saved(path) == {}


def test_a_change_that_is_not_saved_yet_is_saved_when_the_program_stops(backend, path):
    backend.setScale(1.75)
    backend.setColor("idle", "#00ff00")
    assert not path.exists()
    backend.stop()  # the program calls this before it ends
    assert saved(path) == {"scale": 1.75, "colors": {"idle": "#00ff00"}} and not backend._look_timer.isActive()
    path.unlink()
    backend.stop()  # nothing waits: nothing is written
    assert not path.exists()


def test_the_look_the_place_and_the_layout_do_not_drop_each_other(app, fake_client, path):
    backend = make(fake_client, path)
    backend.savePosition(300, 40, "DP-1")
    backend.setLayout("A")
    backend.setScale(1.5), backend.setColor("accent", "#ff00ff")
    backend.stop()
    wanted = {"x": 300, "y": 40, "screen": "DP-1", "layout": "A", "scale": 1.5, "colors": {"accent": "#ff00ff"}}
    assert saved(path) == wanted
    backend.savePosition(1, 2, "DP-2"), backend.setLayout("C"), backend.saveScreen("DP-3")
    assert saved(path) == {"screen": "DP-3", "layout": "C", "scale": 1.5, "colors": {"accent": "#ff00ff"}}
    later = make(fake_client, path)
    assert (later.scale, later.colorOverrides, later.layout, later.savedScreen) == (1.5, {"accent": "#ff00ff"}, "C", "DP-3")


def test_a_look_that_cannot_be_saved_still_applies_and_gives_one_log_line(app, fake_client, tmp_path, caplog):
    (tmp_path / "file").write_text("", encoding="utf-8")
    backend = make(fake_client, tmp_path / "file" / "state.json")  # the folder cannot be made
    with caplog.at_level(logging.INFO, logger="bellwether"):
        assert backend.setScale(1.5) is True
        backend.stop()
    assert backend.scale == 1.5 and [r.getMessage() for r in caplog.records] == ["the custom look was not saved"]


def failing_once(monkeypatch):
    """The first save of the look fails (a full disk, made up); the saves after it work."""
    real, calls = settings.save_look, []

    def save(look, where, changed):
        calls.append(set(changed))
        if len(calls) == 1:
            raise OSError("disk full (made up)")
        real(look, where, changed)
    monkeypatch.setattr("bellwether.backend.save_look", save)
    return calls


def test_a_save_that_fails_keeps_its_values_for_the_next_save(backend, path, monkeypatch):
    calls = failing_once(monkeypatch)
    backend.setScale(1.5)
    fire(backend._look_timer)  # fails
    assert not path.exists()
    backend.setFontScale(1.2)
    fire(backend._look_timer)
    assert calls == [{"scale"}, {"scale", "fontScale"}] and saved(path) == {"scale": 1.5, "fontScale": 1.2}


def test_a_save_that_fails_is_tried_again_when_the_program_stops(backend, path, monkeypatch):
    failing_once(monkeypatch)
    backend.setColor("idle", "#00ff00")
    fire(backend._look_timer)  # fails
    backend.stop()
    assert saved(path) == {"colors": {"idle": "#00ff00"}}


def test_a_reset_whose_save_fails_still_empties_the_file_at_the_next_save(backend, path, monkeypatch):
    backend.setScale(1.5), backend.setColor("text", "#ffffff")
    fire(backend._look_timer)
    assert saved(path) == {"scale": 1.5, "colors": {"text": "#ffffff"}}
    calls = failing_once(monkeypatch)
    backend.resetLook()
    fire(backend._look_timer)  # fails
    assert saved(path) == {"scale": 1.5, "colors": {"text": "#ffffff"}}
    backend.setFontFamily("Made Up Sans")
    fire(backend._look_timer)
    assert calls[1] == set(settings.DEFAULT_LOOK) and saved(path) == {"fontFamily": "Made Up Sans"}


# ----- the start -----

def test_a_saved_look_applies_at_the_start_with_no_log_line_and_no_write(app, fake_client, path, caplog):
    text = json.dumps({"x": 1, "y": 2, "scale": 1.5, "fontScale": 0.9, "fontFamily": "Made Up Mono", "colors": CUSTOM})
    path.write_text(text, encoding="utf-8")
    with caplog.at_level(logging.INFO, logger="bellwether"):
        backend = make(fake_client, path)
    assert (backend.scale, backend.fontScale, backend.fontFamily) == (1.5, 0.9, "Made Up Mono")
    assert backend.colors == backend.colorOverrides == CUSTOM
    assert caplog.records == [] and path.read_text(encoding="utf-8") == text and not backend._look_timer.isActive()


def test_a_saved_look_with_bad_values_gives_the_defaults_for_them_and_one_log_line_with_the_keys(
        app, fake_client, path, caplog):
    text = json.dumps({"scale": "huge", "fontScale": 1.2, "fontFamily": "Not On This System",
                       "colors": {"text": "white", "idle": "#00ff00", "secret name": "#000000"}})
    path.write_text(text, encoding="utf-8")
    with caplog.at_level(logging.INFO, logger="bellwether"):
        backend = make(fake_client, path)
    assert (backend.scale, backend.fontScale, backend.fontFamily) == (1.0, 1.2, "")
    assert backend.colorOverrides == {"idle": "#00ff00"}
    assert [r.getMessage() for r in caplog.records] == [
        "the saved custom look has values that cannot be used: scale, colors.text, colors, fontFamily"]
    assert "secret" not in caplog.text and "white" not in caplog.text and "Not On" not in caplog.text
    assert path.read_text(encoding="utf-8") == text  # the file stays as it is
# ----- the program icons follow the text colour -----

GLYPH = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M2 2h20v20H2z"/></svg>'


def icon_file(backend):
    from urllib.parse import unquote, urlparse
    return Path(unquote(urlparse(backend.groups[2]["agents"][0]["icon"]).path))


def test_a_new_text_colour_makes_new_program_icons_and_removes_the_old_copies(app, fake_client, tmp_path, path):
    (tmp_path / "app" / "icons").mkdir(parents=True)
    (tmp_path / "app" / "icons" / "pi.svg").write_text(GLYPH, encoding="utf-8")
    cache = tmp_path / "cache"
    backend = make(fake_client, path, icons=Icons(tmp_path / "app", cache))
    backend.apply([Agent("t1", "working", "ana", "", "pi")])
    first = icon_file(backend)
    assert TEXT_COLOR in first.read_text(encoding="utf-8") and first.parent == cache
    changes = []
    backend.changed.connect(lambda: changes.append(icon_file(backend)))
    backend.setColor("text", "#112233")
    second = icon_file(backend)
    assert changes == [second] and second != first and "#112233" in second.read_text(encoding="utf-8") and TEXT_COLOR not in second.read_text(encoding="utf-8")
    assert sorted(cache.iterdir()) == [second]  # the copy in the old colour is gone: the cache does not grow
    backend.setColor("accent", "#445566")  # a different role: the icons stay
    assert changes == [second]
    backend.resetColor("text")
    assert icon_file(backend).read_text(encoding="utf-8") == first.read_text(encoding="utf-8") and sorted(cache.iterdir()) == [icon_file(backend)]
    path.write_text(json.dumps({"colors": {"text": "#abcdef"}}), encoding="utf-8")  # a saved text colour: the icons have it at the start
    later = make(fake_client, path, icons=Icons(tmp_path / "app", cache))
    later.apply([Agent("t1", "working", "ana", "", "pi")])
    assert "#abcdef" in icon_file(later).read_text(encoding="utf-8")


# ----- a save changes only what the user changed -----

def test_a_font_family_that_is_not_installed_now_stays_in_the_file_when_a_different_value_changes(
        app, fake_client, path, caplog):
    path.write_text(json.dumps({"fontFamily": "Made Up Serif", "fontScale": 1.2, "colors": {"text": "#ffffff"}}), encoding="utf-8")
    backend = make(fake_client, path)  # this system does not have "Made Up Serif" now
    assert backend.fontFamily == "" and backend.lookIsCustom is True
    backend.setScale(1.5), backend.setColor("idle", "#00ff00")
    backend.stop()
    assert saved(path) == {"fontFamily": "Made Up Serif", "fontScale": 1.2, "scale": 1.5,
                           "colors": {"text": "#ffffff", "idle": "#00ff00"}}
    later = make(fake_client, path, families=[*FAMILIES, "Made Up Serif"])  # the font is installed later
    assert later.fontFamily == "Made Up Serif"
    later.setFontFamily("Made Up Mono")  # the user chooses a family: now the key changes
    later.stop()
    assert saved(path)["fontFamily"] == "Made Up Mono"


def test_a_colour_role_of_a_later_version_and_a_bad_value_stay_in_the_file_when_other_values_change(
        app, fake_client, path):
    start = {"scale": "big", "colors": {"sparkle": "#123456", "text": "#ffffff", "done": "green"}, "later": [1]}
    path.write_text(json.dumps(start), encoding="utf-8")
    backend = make(fake_client, path)
    backend.setFontScale(1.2)
    backend.stop()
    assert saved(path) == {**start, "fontScale": 1.2}  # nothing of the other keys is touched
    backend.setColor("idle", "#00ff00"), backend.resetColor("text")
    backend.stop()
    assert saved(path)["colors"] == {"sparkle": "#123456", "done": "green", "idle": "#00ff00"}
    backend.setColor("done", "#0000ff"), backend.resetColor("idle")
    backend.stop()
    assert saved(path)["colors"] == {"sparkle": "#123456", "done": "#0000ff"}
    backend.resetColor("done")
    backend.stop()
    assert saved(path) == {"scale": "big", "colors": {"sparkle": "#123456"}, "later": [1], "fontScale": 1.2}


def test_reset_everything_removes_the_four_keys_from_the_file_with_all_that_they_hold(app, fake_client, path):
    path.write_text(json.dumps({"x": 3, "y": 4, "scale": 1.5, "fontFamily": "Made Up Serif",
                                "colors": {"sparkle": "#123456", "text": "#ffffff"}}), encoding="utf-8")
    backend = make(fake_client, path)
    backend.resetLook()
    backend.stop()
    assert saved(path) == {"x": 3, "y": 4}


def test_a_save_that_changes_nothing_does_not_write_the_file(app, fake_client, path):
    backend = make(fake_client, path)
    backend.setScale(1.5), backend.setScale(1.0)
    backend.stop()
    assert not path.exists()
