"""The self-test mode (`python -m bellwether --self-test`) off screen on Linux: the steps, the one JSON object, and
nothing of the user touched. On a runner of an other system the same mode gives the facts of the real windows."""
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bellwether import selftest
from bellwether.__main__ import load_panel

ROOT = Path(__file__).parent.parent
STEPS = ["panel-C", "layout-A", "layout-B", "layout-C", "layout-D", "layout-E", "options"]


def test_the_self_test_shows_each_step_and_gives_the_facts_of_the_windows(app, monkeypatch):
    monkeypatch.delenv("BELLWETHER_SHELL", raising=False)
    out, err = io.StringIO(), io.StringIO()
    assert selftest.run(load_panel, show=0.05, step=0.05, out=out, err=err) == 0
    lines = out.getvalue().splitlines()
    assert len(lines) == 1  # ONE object
    facts = json.loads(lines[0])
    assert [line[len("self-test: shown "):] for line in err.getvalue().splitlines()
            if line.startswith("self-test: shown ")] == STEPS
    assert (facts["system"], facts["qt_platform"], facts["shell"]) == (sys.platform, "offscreen", "plain")
    assert facts["native"] == {} and facts["options"]["native"] == {}  # Linux: no native facts
    assert facts["panel"]["visible"] is True and facts["panel"]["frame"][2:] == facts["panel"]["geometry"][2:]
    assert facts["panel"]["flag_names"] == ["Tool", "FramelessWindowHint", "NoDropShadowWindowHint",
                                            "WindowDoesNotAcceptFocus", "WindowStaysOnTopHint"]
    assert facts["panel"]["screen"]["geometry"] == [0, 0, 800, 800]
    assert set(facts["layouts"]) == set("ABCDE")
    assert all(one["shown"] and one["visible"] and one["size"][0] > 200 for one in facts["layouts"].values())
    assert facts["options"]["visible"] is True and facts["options"]["flag_names"][0] == "Window"
    assert facts["tray"] == {"available": False, "visible": False}  # no tray off screen
    assert facts["messages"] == [] and "error" not in facts
    assert "INFO shell: plain" in err.getvalue()


def test_the_flags_have_the_type_and_the_hints_by_name():
    from PySide6.QtCore import Qt
    flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
    assert selftest.flag_names(flags) == ["Tool", "FramelessWindowHint"]
    assert selftest.flag_names(Qt.WindowType.Window) == ["Window"]


def test_the_command_prints_one_json_object_and_touches_nothing_of_the_user(tmp_path):
    """The real command, in a process of its own, with a made-up home: no lock, no log file, no settings file."""
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "c"),
           "XDG_STATE_HOME": str(tmp_path / "s"), "XDG_CACHE_HOME": str(tmp_path / "k"),
           "XDG_RUNTIME_DIR": str(tmp_path / "r")}
    env.pop("BELLWETHER_SHELL", None)
    (tmp_path / "r").mkdir()
    done = subprocess.run([sys.executable, "-m", "bellwether", "--self-test"], capture_output=True, text=True,
                          cwd=ROOT, env=env, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    facts = json.loads(done.stdout)
    assert facts["shell"] == "plain" and facts["panel"]["visible"] is True and 10 < facts["seconds"] < 60
    assert list((tmp_path / "r").iterdir()) == []  # no lock file
    assert not (tmp_path / "s" / "bellwether").exists() and not (tmp_path / "c" / "bellwether").exists()
