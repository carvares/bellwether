"""The macOS part of the program. Nobody has run it on a Mac yet: it is proven with fakes on Linux and on a GitHub
macOS runner (see the design of the port). It imports on every system: AppKit (pyobjc) and psutil are loaded only
when a member needs them, and each member takes a loader in their place for a test."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from ..layouts import UI_PATH
from .posix import lock  # noqa: F401  (the single-instance lock: fcntl.flock works on macOS)

log = logging.getLogger("bellwether")


# ----- the folders: the folders of the user's Library -----

def config_home() -> Path:
    return Path.home() / "Library" / "Application Support"


def state_home() -> Path:
    return Path.home() / "Library" / "Logs"


def cache_home() -> Path:
    return Path.home() / "Library" / "Caches"


def runtime_dir() -> Path:
    """The folder of the lock files. Not $TMPDIR: a program that the Herdr app starts and one that a terminal
    starts can have a different $TMPDIR, and two lock files would let two panels run. The Caches folder of the
    user always exists and is the same for every start."""
    return cache_home()


# ----- the set-up of Qt and the window shell: macOS has only the plain shell -----

# The QML file of each window shell. The layer shell is a protocol of Wayland compositors.
SHELL_FILES = {"plain": UI_PATH / "shells" / "Plain.qml"}
# What the layer shell needs, for the log line when the QML interface does not load (never: there is no layer
# shell here).
SHELL_NEEDS = "a Wayland compositor with the layer-shell protocol, which macOS does not have"
SHELL_VARIABLE = "BELLWETHER_SHELL"


def prepare_environment() -> None:
    """Before the QApplication: nothing. Qt takes its cocoa plugin (a person can choose an other one with
    QT_QPA_PLATFORM, for example offscreen)."""


def prepare_engine(engine) -> None:
    """Before the load of the panel: nothing (the plain shell needs no import path of the system)."""


def shell(engine, environ=None, platform_name=None, compositor_globals=None) -> str:
    """Always "plain". BELLWETHER_SHELL=plain is fine; an other value gets one log line. The arguments are those of
    the interface (the Linux rule needs them)."""
    environ = os.environ if environ is None else environ
    chosen = environ.get(SHELL_VARIABLE, "")
    if chosen and chosen != "plain":
        log.warning("%s=%r: macOS has only the plain shell", SHELL_VARIABLE, chosen[:40])
    return "plain"
