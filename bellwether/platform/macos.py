"""The macOS part of the program. Nobody has run it on a Mac yet: it is proven with fakes on Linux and on a GitHub
macOS runner (see the design of the port). It imports on every system: AppKit (pyobjc) and psutil are loaded only
when a member needs them, and each member takes a loader in their place for a test."""
from __future__ import annotations

import logging
import os
import plistlib
import subprocess
import time
from pathlib import Path

from ..layouts import UI_PATH
from .host import ProcessHost
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


# ----- the windows: the panel is a non-activating panel on every Space; the other windows activate the app -----
# Qt 6.12 (cocoa plugin) makes a Qt::Tool window a QNSPanel (an NSPanel) at the floating level. When it makes the
# native window it sets hidesOnDeactivate unless the QWindow has the property _q_macAlwaysShowToolWindow: an
# accessory app is almost never active, so the panel would almost never show. Qt reads the property only when it makes
# the native window (QCocoaWindow::createNSWindow), and the panel exists already when the program gets it (the QML
# shows it during its load): so the property is set for a later native window, and the panel gets its behaviour here
# through AppKit. Qt sets the level again only at a change of the flags or of the full screen state of this window
# (QCocoaWindow::setWindowFlags), which the panel does not have.

# A property of the QWindow that Qt's cocoa plugin reads (qt_mac_resolveOption in QCocoaWindow::alwaysShowToolWindow).
ALWAYS_SHOW = "_q_macAlwaysShowToolWindow"


def _panel_behaviour(appkit) -> int:
    """On every Space, also beside an app in full screen, not in the window cycle and not moved by Mission Control."""
    return (appkit.NSWindowCollectionBehaviorCanJoinAllSpaces | appkit.NSWindowCollectionBehaviorFullScreenAuxiliary
            | appkit.NSWindowCollectionBehaviorStationary | appkit.NSWindowCollectionBehaviorIgnoresCycle)


def native_window(window, kit):
    """The NSWindow of a QWindow: its winId is the NSView of Qt."""
    return kit.objc.objc_object(c_void_p=int(window.winId())).window()


def prepare_app(app, *, appkit=None) -> None:
    """After the QApplication: an accessory app (no Dock icon, no menu bar of its own; the tray item stays). Without
    pyobjc: one log line, and the program runs with a Dock icon and a plain panel."""
    kit = (appkit or load_appkit)()
    if kit is None:
        log.warning("pyobjc (AppKit) cannot be imported: the panel is a plain window above the others on the current "
                    "Space only, and the program has a Dock icon")
        return
    try:
        kit.AppKit.NSApplication.sharedApplication().setActivationPolicy_(
            kit.AppKit.NSApplicationActivationPolicyAccessory)
    except Exception as error:
        log.warning("the program could not be an accessory app (%s): it has a Dock icon", type(error).__name__)


def _make_again(window) -> None:
    """Make the native window again: Qt then reads ALWAYS_SHOW (the panel does not hide when the app is not active)."""
    shown = window.isVisible()
    window.hide()
    window.destroy()
    if shown:
        window.show()


def _prepare_panel(window, kit) -> None:
    window.setProperty(ALWAYS_SHOW, True)
    if kit is None:
        _make_again(window)
        return
    try:
        appkit = kit.AppKit
        panel = native_window(window, kit)
        panel.setLevel_(appkit.NSStatusWindowLevel)  # above the floating windows of other apps, under the menu bar
        panel.setCollectionBehavior_(_panel_behaviour(appkit))
        # A click does not activate the app (the keyboard stays where the person types). The style mask alone is not
        # enough after the window exists (AppKit, as found by Wine): the private call is used when it is there.
        panel.setStyleMask_(panel.styleMask() | appkit.NSWindowStyleMaskNonactivatingPanel)
        if panel.respondsToSelector_("_setPreventsActivation:"):
            panel._setPreventsActivation_(True)
        if panel.respondsToSelector_("setBecomesKeyOnlyIfNeeded:"):
            panel.setBecomesKeyOnlyIfNeeded_(True)
        panel.setHidesOnDeactivate_(False)
        panel.setHasShadow_(False)
        panel.setMovable_(False)  # only the drag of the panel moves it
    except Exception as error:
        log.warning("the panel could not get the behaviour of a macOS panel (%s): a plain window above the others",
                    type(error).__name__)
        _make_again(window)


def activate_app(window, kit) -> None:
    """Make this app the active app, so that the keyboard goes to `window`: AppKit's `activate` (macOS 14) or
    `activateIgnoringOtherApps:`; without pyobjc Qt's raise, which also activates the app."""
    if kit is None:
        window.raise_()
        return
    try:
        app = kit.AppKit.NSApplication.sharedApplication()
        if app.respondsToSelector_("activate"):
            app.activate()
        else:
            app.activateIgnoringOtherApps_(True)
    except Exception as error:
        log.info("the program could not activate itself (%s)", type(error).__name__)
        window.raise_()


def prepare_window(window, role: str, *, appkit=None) -> None:
    """After a window of the program exists. "panel": a non-activating panel at the status level on every Space,
    that does not hide when the app is not active. "answer" and "options": the app is activated at each show of the
    window (an accessory app is not active, and only the active app gets the keyboard)."""
    kit = (appkit or load_appkit)()
    if role == "panel":
        _prepare_panel(window, kit)
        return
    window.visibleChanged.connect(lambda visible: activate_app(window, kit) if visible else None)
    if window.isVisible():
        activate_app(window, kit)


def window_facts(window, *, appkit=None) -> dict:
    """The facts of the native window and of the app, for the self-test. Each value as AppKit gives it."""
    kit = (appkit or load_appkit)()
    if kit is None:
        return {"pyobjc": False, "always_show_property": bool(window.property(ALWAYS_SHOW))}
    appkit_ = kit.AppKit
    native = native_window(window, kit)
    app = appkit_.NSApplication.sharedApplication()
    return {
        "pyobjc": True,
        "class": str(native.className()),
        "panel": bool(native.isKindOfClass_(appkit_.NSPanel)),
        "level": int(native.level()),
        "collection_behavior": int(native.collectionBehavior()),
        "style_mask": int(native.styleMask()),
        "can_become_key": bool(native.canBecomeKeyWindow()),
        "key": bool(native.isKeyWindow()),
        "hides_on_deactivate": bool(native.hidesOnDeactivate()),
        "has_shadow": bool(native.hasShadow()),
        "movable": bool(native.isMovable()),
        "visible": bool(native.isVisible()),
        "on_active_space": bool(native.isOnActiveSpace()),
        "always_show_property": bool(window.property(ALWAYS_SHOW)),
        "activation_policy": int(app.activationPolicy()),
        "app_active": bool(app.isActive()),
    }


# ----- the process host: psutil (a dependency only where there is no /proc to read) -----

def load_psutil():
    """The module psutil, or None when it cannot be imported."""
    try:
        import psutil  # noqa: PLC0415  (a dependency on macOS and Windows only)
    except ImportError:
        return None
    return psutil


_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
# The most words of a command line and the most open files that are read of one process.
MAX_WORDS = 4096
MAX_FILES = 4096


def lstart(seconds: float) -> str:
    """The start of a process (seconds since 1970) as `LC_ALL=C TZ=UTC ps -o lstart= -p <pid>` prints it, the form
    of `procStart` that Claude Code writes on macOS: "Thu Nov 20 16:18:03 2026" (strftime %c in the C locale: the
    day of the month padded with a space). Whole seconds, as ps gives them."""
    t = time.gmtime(int(seconds))
    return (f"{_DAYS[t.tm_wday]} {_MONTHS[t.tm_mon - 1]} {t.tm_mday:2d} "
            f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d} {t.tm_year}")


class Host(ProcessHost):
    """The home folder of the user and the processes of this machine, read through psutil (None: nothing is known,
    so no row gets a model). A test gives its own home folder and a made-up psutil.

    The start of a process is in the form of Claude Code's `procStart` on macOS (see `lstart`): a session file is
    taken only when its procStart is exactly that text for the live process with its pid (the rule of sessions.py).
    When the form differs, no file is taken and the row shows the time of the terminal, never a model of a process
    that it cannot prove."""

    def __init__(self, home: Path | None = None, psutil=None) -> None:
        super().__init__(home)
        self._psutil = psutil
        self._errors = (OSError,) if psutil is None else (OSError, psutil.Error)

    def _process(self, pid: int):
        return self._psutil.Process(pid)

    def start_ticks(self, pid: int) -> str | None:
        if self._psutil is None:
            return None
        try:
            return lstart(self._process(pid).create_time())
        except self._errors:
            return None

    def children(self, pid: int) -> list[int]:
        if self._psutil is None:
            return []
        try:
            return [child.pid for child in self._process(pid).children()]
        except self._errors:
            return []

    def arguments(self, pid: int) -> list[str]:
        if self._psutil is None:
            return []
        try:
            return [str(word) for word in self._process(pid).cmdline()[:MAX_WORDS]]
        except self._errors:
            return []

    def open_files(self, pid: int) -> list[str]:
        if self._psutil is None:
            return []
        try:
            return [str(item.path) for item in self._process(pid).open_files()[:MAX_FILES]]
        except self._errors:
            return []


def process_host(*, psutil=None) -> Host:
    """The host of this machine. Without psutil: one log line, and a host that knows no process."""
    module = (psutil or load_psutil)()
    if module is None:
        log.warning("psutil cannot be imported: the rows show the time of the terminal and no model")
    return Host(None, module)


# ----- the icon file of the Herdr app: the .icns of its bundle -----

def app_icon_file(*, bundles=None) -> Path | None:
    """The .icns file of the Herdr app bundle (its Info.plist names it, CFBundleIconFile), or None. The bundles
    looked at: the one that ~/.local/bin/herdr-app points to (the Herdr installer makes that link), then Herdr.app
    in ~/Applications and /Applications. Qt reads .icns (its plugin qicns is in the PySide6 wheel)."""
    if bundles is None:
        bundles = [app_bundle(str(Path("~/.local/bin/herdr-app").expanduser())),
                   *(Path(folder).expanduser() / f"{APP_NAME}.app" for folder in APP_FOLDERS)]
    for bundle in bundles:
        if bundle is None:
            continue
        try:
            with open(Path(bundle) / "Contents" / "Info.plist", "rb") as file:
                name = plistlib.load(file).get("CFBundleIconFile")
        except (OSError, ValueError, plistlib.InvalidFileException, AttributeError):
            continue
        if not isinstance(name, str) or not name or "/" in name:
            continue
        path = Path(bundle) / "Contents" / "Resources" / (name if name.endswith(".icns") else f"{name}.icns")
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None
