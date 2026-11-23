import fcntl
import json
import logging
from pathlib import Path

import pytest

from bellwether import __main__ as start
from bellwether import paths
from bellwether.settings import load_position

KINDS = {"config": "XDG_CONFIG_HOME", "state": "XDG_STATE_HOME", "cache": "XDG_CACHE_HOME"}


@pytest.fixture
def homes(tmp_path, monkeypatch):
    """The three XDG base folders and the runtime folder in tmp_path. Never the real folders."""
    bases = {kind: tmp_path / kind for kind in KINDS}
    for kind, variable in KINDS.items():
        bases[kind].mkdir()
        monkeypatch.setenv(variable, str(bases[kind]))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return bases


def tree(folder):
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*"))


def test_the_folders_follow_the_xdg_variables_with_the_standard_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for variable in [*KINDS.values(), "XDG_RUNTIME_DIR"]:
        monkeypatch.delenv(variable, raising=False)
    home = tmp_path / "home"
    assert (paths.config_home(), paths.state_home(), paths.cache_home(), paths.runtime_dir()) == (
        home / ".config", home / ".local" / "state", home / ".cache", Path("/tmp"))
    # A relative or empty value is not valid (XDG Base Directory Specification): the default is used.
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative/config")
    monkeypatch.setenv("XDG_STATE_HOME", "")
    assert (paths.config_home(), paths.state_home()) == (home / ".config", home / ".local" / "state")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "c"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "s"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "k"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "r"))
    assert (paths.config_home(), paths.state_home(), paths.cache_home(), paths.runtime_dir()) == (
        tmp_path / "c", tmp_path / "s", tmp_path / "k", tmp_path / "r")


def test_on_a_fresh_machine_nothing_moves_and_nothing_is_made(homes):
    assert paths.move_old_folders() == []
    assert [tree(base) for base in homes.values()] == [[], [], []]


def test_the_old_folders_get_the_new_name_with_their_content(homes):
    (homes["config"] / "herdr-float").mkdir()
    (homes["config"] / "herdr-float" / "state.json").write_text('{"x": 5, "y": 6, "screen": "DP-1"}', encoding="utf-8")
    (homes["state"] / "herdr-float").mkdir()
    (homes["state"] / "herdr-float" / "herdr-float.log").write_text("old log\n", encoding="utf-8")
    (homes["state"] / "herdr-float" / "start.log").write_text("old start log\n", encoding="utf-8")
    (homes["cache"] / "herdr-float" / "icons").mkdir(parents=True)
    (homes["cache"] / "herdr-float" / "icons" / "pi-e8eaed.svg").write_text("<svg/>", encoding="utf-8")
    lines = paths.move_old_folders()
    assert lines == [(logging.INFO, f"moved the {kind} folder herdr-float to bellwether") for kind in KINDS]
    assert tree(homes["config"]) == ["bellwether", "bellwether/state.json"]
    assert tree(homes["state"]) == ["bellwether", "bellwether/herdr-float.log", "bellwether/start.log"]
    assert tree(homes["cache"]) == ["bellwether", "bellwether/icons", "bellwether/icons/pi-e8eaed.svg"]
    assert (homes["state"] / "bellwether" / "herdr-float.log").read_text(encoding="utf-8") == "old log\n"
    assert paths.move_old_folders() == []  # the second start has nothing to move


def test_an_existing_new_folder_wins_and_the_old_one_is_not_touched(homes):
    for base in homes.values():
        (base / "herdr-float").mkdir()
        (base / "herdr-float" / "old.txt").write_text("old", encoding="utf-8")
        (base / "bellwether").mkdir()
        (base / "bellwether" / "new.txt").write_text("new", encoding="utf-8")
    assert paths.move_old_folders() == []
    for base in homes.values():
        assert tree(base) == ["bellwether", "bellwether/new.txt", "herdr-float", "herdr-float/old.txt"]
        assert (base / "bellwether" / "new.txt").read_text(encoding="utf-8") == "new"


def test_only_the_folders_that_exist_move_and_an_old_file_is_not_a_folder(homes):
    (homes["config"] / "herdr-float").write_text("a file, not a folder", encoding="utf-8")
    (homes["cache"] / "herdr-float").mkdir()
    assert paths.move_old_folders() == [(logging.INFO, "moved the cache folder herdr-float to bellwether")]
    assert tree(homes["config"]) == ["herdr-float"]
    assert tree(homes["state"]) == []
    assert tree(homes["cache"]) == ["bellwether"]


def test_a_move_that_fails_gives_one_line_and_the_start_continues_with_defaults(homes):
    (homes["config"] / "herdr-float").mkdir()
    (homes["config"] / "herdr-float" / "state.json").write_text('{"x": 5, "y": 6}', encoding="utf-8")
    homes["config"].chmod(0o555)  # the rename in this folder fails: PermissionError
    try:
        lines = paths.move_old_folders()
    finally:
        homes["config"].chmod(0o755)
    assert lines == [(logging.WARNING, "could not move the config folder herdr-float to bellwether (PermissionError): "
                                       "the widget uses its defaults")]
    assert tree(homes["config"]) == ["herdr-float", "herdr-float/state.json"]
    assert load_position(homes["config"] / "bellwether" / "state.json") is None  # the default position


def test_a_state_file_of_the_old_format_loads_after_the_move(homes):
    (homes["config"] / "herdr-float").mkdir()
    (homes["config"] / "herdr-float" / "state.json").write_text(json.dumps({"x": 120, "y": 48}), encoding="utf-8")  # x and y only
    paths.move_old_folders()
    assert load_position(homes["config"] / "bellwether" / "state.json") == (120, 48, "")


def held(path):
    handle = open(path, "w", encoding="utf-8")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return handle


def test_the_lock_is_refused_while_a_widget_of_either_name_runs(homes, tmp_path):
    for name in ("bellwether.lock", "herdr-float.lock"):
        other = held(tmp_path / name)  # a second open file in this process: flock treats it as another process
        try:
            assert start.take_single_instance_lock() is None, name
        finally:
            other.close()
    locks = start.take_single_instance_lock()
    try:
        assert locks is not None
        assert start.take_single_instance_lock() is None  # the new widget also holds the old lock
    finally:
        for handle in locks:
            handle.close()


def no_real_folders(homes, monkeypatch):
    """The paths that the modules made at import are in tmp_path, and a start that goes past the lock fails at
    once: a regression in main() cannot read or write the real home folder."""
    from bellwether import backend, icons, settings

    monkeypatch.setattr(start, "LOG_PATH", homes["state"] / "bellwether" / "bellwether.log")
    monkeypatch.setattr(settings, "DEFAULT_PATH", homes["config"] / "bellwether" / "state.json")
    monkeypatch.setattr(backend, "DEFAULT_PATH", homes["config"] / "bellwether" / "state.json")
    monkeypatch.setattr(icons, "CACHE_PATH", homes["cache"] / "bellwether" / "icons")

    def past_the_lock(*args, **kwargs):
        raise AssertionError("the start went past the lock")

    # The default arguments of Backend and Icons hold the real paths from the import: stop before them.
    for name in ("move_old_folders", "QApplication", "Backend", "Icons", "HerdrClient"):
        monkeypatch.setattr(start, name, past_the_lock)


@pytest.mark.parametrize("lock", ["herdr-float.lock", "bellwether.lock"])
def test_with_a_widget_running_the_start_exits_and_moves_and_makes_nothing(homes, tmp_path, monkeypatch, capsys, lock):
    no_real_folders(homes, monkeypatch)
    for base in homes.values():
        (base / "herdr-float").mkdir()
    old = held(tmp_path / lock)
    try:
        assert start.main() == 0
    finally:
        old.close()
    for base in homes.values():
        assert tree(base) == ["herdr-float"]
    # One line for start.log: no log folder exists here, so the log file has no line.
    assert capsys.readouterr() == ("", "bellwether: already running\n")


def test_an_old_folder_that_is_a_link_keeps_its_target_under_the_new_name(homes, tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "state.json").write_text('{"x": 5, "y": 6}', encoding="utf-8")
    (homes["config"] / "herdr-float").symlink_to(target)
    assert paths.move_old_folders() == [(logging.INFO, "moved the config folder herdr-float to bellwether")]
    new = homes["config"] / "bellwether"
    assert new.is_symlink() and new.resolve() == target  # the link has the new name: its target did not move
    assert not (homes["config"] / "herdr-float").is_symlink()
    assert tree(target) == ["state.json"] and load_position(new / "state.json") == (5, 6, "")


def test_a_new_folder_that_is_a_link_to_nothing_is_not_replaced(homes, tmp_path):
    (homes["config"] / "herdr-float").mkdir()
    (homes["config"] / "herdr-float" / "state.json").write_text('{"x": 5, "y": 6}', encoding="utf-8")
    (homes["config"] / "bellwether").symlink_to(tmp_path / "not-there")
    assert paths.move_old_folders() == []
    assert (homes["config"] / "bellwether").is_symlink() and not (homes["config"] / "bellwether").exists()
    assert tree(homes["config"] / "herdr-float") == ["state.json"]
