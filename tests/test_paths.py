import fcntl
import json
import logging

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
        home / ".config", home / ".local" / "state", home / ".cache", paths.Path("/tmp"))
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
    (homes["config"] / "herdr-float" / "state.json").write_text('{"x": 5, "y": 6, "screen": "DP-1"}')
    (homes["state"] / "herdr-float").mkdir()
    (homes["state"] / "herdr-float" / "herdr-float.log").write_text("old log\n")
    (homes["state"] / "herdr-float" / "start.log").write_text("old start log\n")
    (homes["cache"] / "herdr-float" / "icons").mkdir(parents=True)
    (homes["cache"] / "herdr-float" / "icons" / "pi-e8eaed.svg").write_text("<svg/>")
    lines = paths.move_old_folders()
    assert lines == [(logging.INFO, f"moved the {kind} folder herdr-float to bellwether") for kind in KINDS]
    assert tree(homes["config"]) == ["bellwether", "bellwether/state.json"]
    assert tree(homes["state"]) == ["bellwether", "bellwether/herdr-float.log", "bellwether/start.log"]
    assert tree(homes["cache"]) == ["bellwether", "bellwether/icons", "bellwether/icons/pi-e8eaed.svg"]
    assert (homes["state"] / "bellwether" / "herdr-float.log").read_text() == "old log\n"
    assert paths.move_old_folders() == []  # the second start has nothing to move


def test_an_existing_new_folder_wins_and_the_old_one_is_not_touched(homes):
    for base in homes.values():
        (base / "herdr-float").mkdir()
        (base / "herdr-float" / "old.txt").write_text("old")
        (base / "bellwether").mkdir()
        (base / "bellwether" / "new.txt").write_text("new")
    assert paths.move_old_folders() == []
    for base in homes.values():
        assert tree(base) == ["bellwether", "bellwether/new.txt", "herdr-float", "herdr-float/old.txt"]
        assert (base / "bellwether" / "new.txt").read_text() == "new"


def test_only_the_folders_that_exist_move_and_an_old_file_is_not_a_folder(homes):
    (homes["config"] / "herdr-float").write_text("a file, not a folder")
    (homes["cache"] / "herdr-float").mkdir()
    assert paths.move_old_folders() == [(logging.INFO, "moved the cache folder herdr-float to bellwether")]
    assert tree(homes["config"]) == ["herdr-float"]
    assert tree(homes["state"]) == []
    assert tree(homes["cache"]) == ["bellwether"]


def test_a_move_that_fails_gives_one_line_and_the_start_continues_with_defaults(homes):
    (homes["config"] / "herdr-float").mkdir()
    (homes["config"] / "herdr-float" / "state.json").write_text('{"x": 5, "y": 6}')
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
    (homes["config"] / "herdr-float" / "state.json").write_text(json.dumps({"x": 120, "y": 48}))  # x and y only
    paths.move_old_folders()
    assert load_position(homes["config"] / "bellwether" / "state.json") == (120, 48, "")


def held(path):
    handle = open(path, "w")
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


def test_with_an_old_widget_running_the_start_exits_and_moves_and_makes_nothing(homes, tmp_path, monkeypatch):
    monkeypatch.setattr(start, "LOG_PATH", homes["state"] / "bellwether" / "bellwether.log")
    for base in homes.values():
        (base / "herdr-float").mkdir()
    old = held(tmp_path / "herdr-float.lock")
    try:
        assert start.main() == 0
    finally:
        old.close()
    for base in homes.values():
        assert tree(base) == ["herdr-float"]
