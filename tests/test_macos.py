"""The macOS module of the platform, on any system: its folders, its lock, its shell, the commands it builds, its
native window calls with a fake AppKit, its process host with a fake psutil, and the client with it. Tests that
need a real Mac are marked `on_mac` (they run on the macOS runner of the workflow)."""
import ast
import logging
import sys
from pathlib import Path

import pytest

from bellwether.platform import macos

on_mac = pytest.mark.skipif(sys.platform != "darwin", reason="needs macOS")


def records(caplog):
    return [(r.levelno, r.getMessage()) for r in caplog.records]


# ----- the module imports on every system -----

def test_the_module_imports_no_module_of_macos_at_its_top():
    tree = ast.parse(Path(macos.__file__).read_text())
    top = [alias.name for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
           for alias in node.names] + [node.module for node in tree.body if isinstance(node, ast.ImportFrom) and node.module]
    assert not {"AppKit", "objc", "Foundation", "Quartz", "psutil"} & set(top)


# ----- the folders, the lock, the shell -----

def test_the_folders_are_those_of_the_library_of_the_user(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", "/made/up")  # the XDG rules are not those of macOS
    monkeypatch.setenv("TMPDIR", "/made/up/tmp")
    assert macos.config_home() == tmp_path / "Library" / "Application Support"
    assert macos.state_home() == tmp_path / "Library" / "Logs"
    assert macos.cache_home() == tmp_path / "Library" / "Caches"
    assert macos.runtime_dir() == tmp_path / "Library" / "Caches"  # not $TMPDIR: the same folder for every start


def test_the_lock_is_the_lock_of_the_posix_systems(tmp_path):
    from bellwether.platform import posix
    assert macos.lock is posix.lock
    first = macos.lock(tmp_path / "bellwether.lock")
    assert first is not None and macos.lock(tmp_path / "bellwether.lock") is None
    first.close()
    assert macos.lock(tmp_path / "bellwether.lock") is not None


def test_the_shell_is_always_plain_and_another_choice_gets_one_log_line(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    assert macos.shell(None, {}) == "plain"
    assert macos.shell(None, {"BELLWETHER_SHELL": "plain"}) == "plain"
    assert records(caplog) == []
    assert macos.shell(None, {"BELLWETHER_SHELL": "layer"}) == "plain"
    assert records(caplog) == [(logging.WARNING, "BELLWETHER_SHELL='layer': macOS has only the plain shell")]
    assert set(macos.SHELL_FILES) == {"plain"} and macos.SHELL_FILES["plain"].is_file()


def test_qt_gets_no_platform_and_the_engine_no_import_path(monkeypatch):
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    assert macos.prepare_environment() is None
    assert "QT_QPA_PLATFORM" not in macos.os.environ
    assert macos.prepare_engine(object()) is None
