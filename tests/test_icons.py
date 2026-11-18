import logging
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

from herdr_float.icons import Icons, find_icon, is_glyph, tinted

BLACK = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M2 2h20v20H2z"/></svg>'
STROKE = '<svg xmlns="http://www.w3.org/2000/svg" fill="none" stroke="currentColor"><path d="M2 2h20"/></svg>'
WHITE = '<svg xmlns="http://www.w3.org/2000/svg"><path fill="#fff" d="M2 2h20v20H2z"/></svg>'
PICTURE = '<svg xmlns="http://www.w3.org/2000/svg"><path fill="#D97757" d="M2 2h20v20H2z"/></svg>'
TWO = '<svg xmlns="http://www.w3.org/2000/svg"><path fill="#fff" d="M0 0h9v9H0z"/><path style="fill:#1783ff" d="M2 2h2"/></svg>'


@pytest.fixture
def home(tmp_path):
    """A made-up app folder with tiny icons."""
    folder = tmp_path / "app" / "icons"
    folder.mkdir(parents=True)
    for name, text in {"claude": PICTURE, "pi": WHITE, "codex": TWO, "copilot": BLACK, "agent": STROKE}.items():
        (folder / f"{name}.svg").write_text(text)
    return tmp_path / "app"


def name_of(path):
    return path.name if path else None


@pytest.mark.parametrize(
    "word, expected",
    [
        ("pi", "pi.svg"),  # the file with the name of the word
        ("claude-code", "claude.svg"),  # the word before the first "-"
        ("Claude-Code", "claude.svg"),
        ("github-copilot", "copilot.svg"),  # a name from the table of the app
        ("gemini", "agent.svg"),  # no file: the generic agent icon
        ("", "agent.svg"),
        ("../../etc/passwd", "agent.svg"),  # not a program word
        ("pi/../claude", "agent.svg"),
        (".hidden", "agent.svg"),
        ("pi" + "x" * 298, "agent.svg"),  # 300 characters: longer than a file name can be
        ("p" * 65, "agent.svg"),
    ],
)
def test_find_icon(home, word, expected):
    assert name_of(find_icon(word, home / "icons")) == expected


def test_find_icon_gives_none_when_the_generic_icon_or_the_folder_is_missing(home, tmp_path):
    (home / "icons" / "agent.svg").unlink()
    assert find_icon("gemini", home / "icons") is None
    assert name_of(find_icon("pi", home / "icons")) == "pi.svg"
    assert find_icon("pi", tmp_path / "no such folder") is None


@pytest.mark.parametrize("text, glyph", [(BLACK, True), (STROKE, True), (WHITE, True), (PICTURE, False), (TWO, False)])
def test_is_glyph_is_true_for_an_icon_of_one_colour(text, glyph):
    assert is_glyph(text) is glyph


def test_tinted_gives_every_kind_of_glyph_the_colour():
    assert tinted(STROKE, "#e8eaed") == STROKE.replace("currentColor", "#e8eaed")
    assert tinted(WHITE, "#e8eaed") == '<svg fill="#e8eaed" xmlns="http://www.w3.org/2000/svg"><path fill="#e8eaed" d="M2 2h20v20H2z"/></svg>'
    assert tinted(BLACK, "#e8eaed").startswith('<svg fill="#e8eaed" xmlns=')


def path_of(url):
    parts = urlparse(url)
    assert parts.scheme == "file"
    return unquote(parts.path)


def test_url_of_a_picture_is_the_file_of_the_app(home, tmp_path):
    icons = Icons(home, tmp_path / "cache")
    assert path_of(icons.url("claude-code")) == str(home / "icons" / "claude.svg")
    assert not (tmp_path / "cache").exists()


def test_url_of_a_glyph_is_a_copy_in_the_text_colour(home, tmp_path):
    icons = Icons(home, tmp_path / "cache", color="#e8eaed")
    copy = path_of(icons.url("pi"))
    assert copy.startswith(str(tmp_path / "cache")) and copy.endswith(".svg")
    assert Path(copy).read_text() == tinted(WHITE, "#e8eaed")
    assert (home / "icons" / "pi.svg").read_text() == WHITE  # the file of the app is not changed
    assert path_of(icons.url("gemini")) != copy and "agent-" in icons.url("gemini")


def test_a_changed_icon_of_the_app_gets_a_new_copy(home, tmp_path):
    first = Icons(home, tmp_path / "cache").url("pi")
    (home / "icons" / "pi.svg").write_text(BLACK)
    second = Icons(home, tmp_path / "cache").url("pi")
    assert first != second and Path(path_of(second)).read_text() == tinted(BLACK, "#e8eaed")


def test_url_is_read_one_time_for_each_word(home, tmp_path):
    icons = Icons(home, tmp_path / "cache")
    first = icons.url("pi")
    (home / "icons" / "pi.svg").unlink()
    assert icons.url("pi") == first


def test_missing_icon_is_logged_one_time_with_the_word_and_no_path(home, tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="herdr_float")
    icons = Icons(home, tmp_path / "cache")
    for _ in range(3):
        icons.url("gemini")
        icons.url("claude-code")
    assert [r.getMessage() for r in caplog.records] == ["no icon for program 'gemini': the generic icon is used"]
    assert str(tmp_path) not in caplog.text


def test_no_folder_gives_no_url_and_one_log_line(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="herdr_float")
    icons = Icons(tmp_path / "no app", tmp_path / "cache")
    assert [icons.url("pi"), icons.url("pi"), icons.url("")] == ["", "", ""]
    assert [r.getMessage() for r in caplog.records] == [
        "no icon for program 'pi': the row shows text", "no icon for program '': the row shows text",
    ]


def test_a_glyph_shows_as_text_when_the_copy_cannot_be_written(home, tmp_path):
    (tmp_path / "cache").write_text("a file where the folder must be")
    assert Icons(home, tmp_path / "cache").url("pi") == ""


def test_an_icon_that_cannot_be_read_as_text_is_shown_as_it_is(home, tmp_path):
    (home / "icons" / "pi.svg").write_bytes(b"\xff\xfe\x00")
    assert path_of(Icons(home, tmp_path / "cache").url("pi")) == str(home / "icons" / "pi.svg")


def test_home_follows_the_environment(monkeypatch, tmp_path):
    from herdr_float.icons import app_home

    monkeypatch.setenv("HERDR_APP_HOME", str(tmp_path))
    assert app_home() == tmp_path
    monkeypatch.delenv("HERDR_APP_HOME")
    assert app_home().name == "herdr-app" and app_home().parent.name == ".config"


def test_find_icon_takes_a_word_of_64_characters_and_no_longer_word(home):
    (home / "icons" / ("p" * 64 + ".svg")).write_text(BLACK)
    assert name_of(find_icon("p" * 64, home / "icons")) == "p" * 64 + ".svg"
    (home / "icons" / ("p" * 65 + ".svg")).write_text(BLACK)
    assert name_of(find_icon("p" * 65, home / "icons")) == "agent.svg"


def test_a_file_error_in_the_lookup_gives_the_fallback_and_is_read_one_time(home, tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="herdr_float")
    real, asked = Path.is_file, []

    def is_file(path, **options):
        asked.append(path.name)
        if path.name == "pi.svg":
            raise OSError(36, "File name too long")
        return real(path, **options)

    monkeypatch.setattr(Path, "is_file", is_file)
    assert name_of(find_icon("pi", home / "icons")) == "agent.svg"

    def broken(path, **options):
        asked.append(path.name)
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(Path, "is_file", broken)
    assert find_icon("pi", home / "icons") is None
    icons = Icons(home, tmp_path / "cache")
    del asked[:]
    assert [icons.url("pi"), icons.url("pi"), icons.url("pi")] == ["", "", ""]
    assert asked.count("pi.svg") == 1  # the failure is kept: no new read for each list
    assert [r.getMessage() for r in caplog.records] == ["no icon for program 'pi': the row shows text"]


def test_a_copy_that_was_deleted_is_made_again(home, tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="herdr_float")
    icons = Icons(home, tmp_path / "cache")
    first = icons.url("gemini")  # the generic icon: a glyph, so a copy
    import shutil

    shutil.rmtree(tmp_path / "cache")
    assert icons.url("gemini") == first and Path(path_of(first)).read_text() == tinted(STROKE, "#e8eaed")
    assert len(caplog.records) == 1  # one log line for the word, also after the new copy


def test_a_picture_of_the_app_that_was_deleted_is_looked_for_again(home, tmp_path):
    icons = Icons(home, tmp_path / "cache")
    assert path_of(icons.url("claude-code")).endswith("/claude.svg")
    (home / "icons" / "claude.svg").unlink()
    assert "agent-" in icons.url("claude-code")
