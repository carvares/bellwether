"""The macOS part of the program. Nobody has run it on a Mac yet: it is proven with fakes on Linux and on a GitHub
macOS runner (see the design of the port). It imports on every system: AppKit (pyobjc) and psutil are loaded only
when a member needs them, and each member takes a loader in their place for a test."""
from __future__ import annotations

import logging
import os
import subprocess
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


# ----- AppKit, through pyobjc (a dependency only on macOS) -----

def load_appkit():
    """The modules AppKit and objc of pyobjc (as .AppKit and .objc), or None when pyobjc cannot be imported. Each
    member that needs them takes a loader as its `appkit` argument (None: this one); a test gives a fake."""
    try:
        import AppKit  # noqa: PLC0415  (only on macOS)
        import objc  # noqa: PLC0415
    except ImportError:
        return None

    class Kit:
        pass

    kit = Kit()
    kit.AppKit, kit.objc = AppKit, objc
    return kit


# ----- the Herdr app: its bundle, its programs, its raise and its start -----

# The facts of the Herdr app bundle (its Info.plist, release 0.1.16): the name, the identifier, the program.
APP_NAME = "Herdr"
BUNDLE_ID = "dev.herdr.app"
BUNDLE_PROGRAM = "Contents/MacOS/Herdr"
# The folders of the app bundle: the Herdr installer puts it in ~/Applications; a person can move it.
APP_FOLDERS = ("~/Applications", "/Applications")
# The folders of the programs, after PATH: the installers of Herdr put herdr-app (a link into the bundle) and
# herdr-core in ~/.local/bin; then the places where the Herdr app itself looks for herdr-core (Homebrew, mise, Nix,
# cargo). A program that the Herdr app starts can have a short PATH.
PROGRAM_FOLDERS = ("~/.local/bin", "/opt/homebrew/bin", "/usr/local/bin", "~/.local/share/mise/shims",
                   "/run/current-system/sw/bin", "~/.nix-profile/bin", "~/.cargo/bin")

# By role: the start of the app, and its second raise. `open` asks Launch Services, which starts the app outside
# our process tree, with the environment of the session. An absolute path: the PATH can be short.
COMMANDS = {"launcher": "/usr/bin/open"}


def _is_program(path: Path) -> bool:
    try:
        return path.is_file() and os.access(path, os.X_OK)
    except OSError:
        return False


def _find(name: str, which, folders, bundle_folders=()) -> tuple[str | None, str]:
    """The path of the program `name` and where it was found (for the log: a folder name, never a path in the
    home folder): PATH, a folder of `folders`, or the app bundle in a folder of `bundle_folders`."""
    found = which(name)
    if found:
        return found, "PATH"
    for folder in folders:
        path = Path(folder).expanduser() / name
        if _is_program(path):
            return str(path), folder
    for folder in bundle_folders:
        path = Path(folder).expanduser() / f"{APP_NAME}.app" / BUNDLE_PROGRAM
        if _is_program(path):
            return str(path), f"{folder}/{APP_NAME}.app"
    return None, "not found"


def find_executables(*, which=None, folders=PROGRAM_FOLDERS, bundle_folders=APP_FOLDERS
                     ) -> tuple[str | None, str | None]:
    """Return the paths of herdr-app and herdr-core (None: not found), and log one line that says where each was
    found. herdr-app can also be the program inside Herdr.app (the link in ~/.local/bin points to it)."""
    if which is None:
        import shutil  # noqa: PLC0415
        which = shutil.which
    app, app_place = _find("herdr-app", which, folders, bundle_folders)
    core, core_place = _find("herdr-core", which, folders)
    log.info("herdr-app: %s; herdr-core: %s", app_place, core_place)
    return app, core


def app_bundle(app: str | None) -> Path | None:
    """The .app folder that holds the program `app` (after its links), or None."""
    if not app:
        return None
    path = Path(os.path.realpath(app))
    for folder in path.parents:
        if folder.suffix == ".app" and (folder / "Contents" / "MacOS") in path.parents:
            return folder
    return None


def _open_argv(app: str | None, commands: dict[str, str]) -> list[str]:
    """`open -a <the bundle of app>`, or `open -b <bundle id>` when the program is not in a bundle."""
    bundle = app_bundle(app)
    return [commands["launcher"], "-a", str(bundle)] if bundle else [commands["launcher"], "-b", BUNDLE_ID]


def raise_app(run, commands: dict[str, str], *, appkit=None) -> bool:
    """Bring the Herdr app to the front. Return False when that did not occur.

    First the running app is activated through AppKit (NSRunningApplication, by its bundle identifier: no
    permission is needed). Then `open -b dev.herdr.app` asks Launch Services to reopen it: that also shows a
    minimized window, which the activation alone does not. True when one of the two worked."""
    activated = False
    kit = (appkit or load_appkit)()
    if kit is not None:
        try:
            for running in kit.AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(BUNDLE_ID):
                running.unhide()
                activated = bool(running.activateWithOptions_(kit.AppKit.NSApplicationActivateAllWindows)) or activated
        except Exception as error:  # a call of AppKit that failed: the second method follows
            log.info("the activation of the Herdr app failed (%s)", type(error).__name__)
    try:
        reopened = run(_open_argv(None, commands)).returncode == 0
    except (OSError, subprocess.SubprocessError) as error:  # no `open`, or the end of the time of the jump
        log.info("the reopen of the Herdr app failed (%s)", type(error).__name__)
        reopened = False
    return activated or reopened


def start_app(run, app: str, commands: dict[str, str]) -> int:
    """Start the Herdr app through Launch Services (`open -a` of its bundle, else `open -b dev.herdr.app`): it does
    not end with the widget and has none of its files. Return the exit code of `open` (0: accepted). The errors of
    `run` go to the caller."""
    return run(_open_argv(app, commands)).returncode


def clean_environment(argv: list[str], names, commands: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    """The command `argv` and its environment, to run without the environment variables `names`: the argv stays as it
    is, and the environment is the one of this process without them (no `env` program is needed)."""
    names = set(names)
    return list(argv), {key: value for key, value in os.environ.items() if key not in names}
