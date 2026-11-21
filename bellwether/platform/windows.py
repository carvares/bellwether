"""The Windows part of the program. Nobody of the project has run it on a Windows machine: it is proven with fakes on
Linux and on a GitHub Windows runner (see the design of the port). It imports on every system: the Win32 calls
(ctypes.windll), msvcrt and psutil are loaded only when a member needs them, and each member takes a loader in their
place for a test. The Win32 part is the class Win32: thin calls. The prototype of each function (its argument and
result types) and the values that each call gives are tested on Linux with a made-up windll; the runner runs the
calls of the job, the pipes, the process names, the window search and the styles that the self-test reads, and those
of the raise and the foreground when they come up there. The calls that change a style (set_ex_style, set_topmost)
run on the runner only when Qt did not give a style, which it does.
"""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import threading
import time
from pathlib import Path

from ..layouts import UI_PATH
from .host import PsutilHost, load_psutil

log = logging.getLogger("bellwether")

# The name of the folder of the program under %LOCALAPPDATA% (the same name as paths.NAME).
PROGRAM = "bellwether"


# ----- the folders: %APPDATA% (it roams with the person) and %LOCALAPPDATA% (this machine) -----

def _folder(variable: str, *default: str) -> Path:
    """The folder in the variable; an empty or relative value is not valid: then the default in the home folder."""
    value = os.environ.get(variable, "")
    return Path(value) if os.path.isabs(value) else Path.home().joinpath(*default)


def _local() -> Path:
    return _folder("LOCALAPPDATA", "AppData", "Local")


def config_home() -> Path:
    """The base of the settings: %APPDATA% (the settings are in %APPDATA%\\bellwether)."""
    return _folder("APPDATA", "AppData", "Roaming")


def state_home() -> Path:
    """The base of the log: %LOCALAPPDATA%\\bellwether\\Logs (Windows has no shared log folder, as macOS has
    ~/Library/Logs: the base is in the folder of the program, and the log is in Logs\\bellwether)."""
    return _local() / PROGRAM / "Logs"


def cache_home() -> Path:
    """The base of the icon cache: %LOCALAPPDATA%\\bellwether\\Cache."""
    return _local() / PROGRAM / "Cache"


def runtime_dir() -> Path:
    """The folder of the lock files: %LOCALAPPDATA%\\bellwether, the same for every start (a start by the Herdr app
    and one from a terminal). The lock makes it when it is not there."""
    return _local() / PROGRAM


# ----- the single-instance lock: msvcrt.locking -----

def load_msvcrt():
    """The module msvcrt, or None (not Windows)."""
    try:
        import msvcrt  # noqa: PLC0415  (only on Windows)
    except ImportError:
        return None
    return msvcrt


def lock(path: Path, *, msvcrt=None):
    """Take the lock of the file at `path`: the first byte, locked with `msvcrt.locking` (LockFile: a lock of the open
    file, which the system gives back when the file is closed or the process ends). Return the open file that holds
    it, or None when a different process (or a different open file of this process) holds it. The file is opened
    without truncation: an other process may hold its lock. Chosen over a named mutex: the same handle and close as
    on the other systems, and a file a person can see."""
    module = (msvcrt or load_msvcrt)()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+", encoding="utf-8")
    try:
        handle.seek(0)
        module.locking(handle.fileno(), module.LK_NBLCK, 1)
    except OSError:
        handle.close()
        return None
    return handle


# ----- the set-up of Qt and the window shell: Windows has only the plain shell -----

SHELL_FILES = {"plain": UI_PATH / "shells" / "Plain.qml"}
SHELL_NEEDS = "a Wayland compositor with the layer-shell protocol, which Windows does not have"
SHELL_VARIABLE = "BELLWETHER_SHELL"


def prepare_environment() -> None:
    """Before the QApplication: nothing. Qt takes its windows plugin, which is aware of the scale of each monitor."""


def native() -> bool:
    """True when Qt uses its windows plugin: only then is the winId of a window an HWND. Off screen (the tests, a
    person's QT_QPA_PLATFORM) the program makes no native call."""
    from PySide6.QtGui import QGuiApplication  # noqa: PLC0415  (no Qt at the top: a module of the platform package)
    return QGuiApplication.platformName() == "windows"


def prepare_app(app) -> None:
    """After the QApplication: one log line when Qt does not use its windows plugin (no native set-up then)."""
    if app.platformName() != "windows":
        log.info("the Qt platform is %s, not windows: the program gets no set-up of Windows", app.platformName())


def prepare_engine(engine) -> None:
    """Before the load of the panel: nothing (the plain shell needs no import path of the system)."""


def shell(engine, environ=None, platform_name=None, compositor_globals=None) -> str:
    """Always "plain". BELLWETHER_SHELL=plain is fine; an other value gets one log line."""
    environ = os.environ if environ is None else environ
    chosen = environ.get(SHELL_VARIABLE, "")
    if chosen and chosen != "plain":
        log.warning("%s=%r: Windows has only the plain shell", SHELL_VARIABLE, chosen[:40])
    return "plain"


# ----- the values of Win32 that the program uses (WinUser.h, WinBase.h, winnt.h) -----

GWL_STYLE, GWL_EXSTYLE, GW_OWNER = -16, -20, 4
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x1, 0x2, 0x10, 0x20
SW_RESTORE = 9
WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW, WS_EX_NOACTIVATE = 0x8, 0x80, 0x40000, 0x08000000
# The names of the single bits of a style and of an extended style, for the facts of the self-test.
STYLES = {"WS_POPUP": 0x80000000, "WS_CHILD": 0x40000000, "WS_MINIMIZE": 0x20000000, "WS_VISIBLE": 0x10000000,
          "WS_DISABLED": 0x08000000, "WS_CLIPSIBLINGS": 0x04000000, "WS_CLIPCHILDREN": 0x02000000,
          "WS_MAXIMIZE": 0x01000000, "WS_BORDER": 0x00800000, "WS_DLGFRAME": 0x00400000, "WS_VSCROLL": 0x00200000,
          "WS_HSCROLL": 0x00100000, "WS_SYSMENU": 0x00080000, "WS_THICKFRAME": 0x00040000,
          "WS_MINIMIZEBOX": 0x00020000, "WS_MAXIMIZEBOX": 0x00010000}
EX_STYLES = {"WS_EX_DLGMODALFRAME": 0x1, "WS_EX_TOPMOST": WS_EX_TOPMOST, "WS_EX_ACCEPTFILES": 0x10,
             "WS_EX_TRANSPARENT": 0x20, "WS_EX_TOOLWINDOW": WS_EX_TOOLWINDOW, "WS_EX_WINDOWEDGE": 0x100,
             "WS_EX_CLIENTEDGE": 0x200, "WS_EX_CONTEXTHELP": 0x400, "WS_EX_CONTROLPARENT": 0x10000,
             "WS_EX_STATICEDGE": 0x20000, "WS_EX_APPWINDOW": WS_EX_APPWINDOW, "WS_EX_LAYERED": 0x80000,
             "WS_EX_NOINHERITLAYOUT": 0x100000, "WS_EX_NOREDIRECTIONBITMAP": 0x200000,
             "WS_EX_LAYOUTRTL": 0x400000, "WS_EX_COMPOSITED": 0x02000000, "WS_EX_NOACTIVATE": WS_EX_NOACTIVATE}
# The flags of a new process.
DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP = 0x8, 0x200
CREATE_BREAKAWAY_FROM_JOB, CREATE_NO_WINDOW = 0x01000000, 0x08000000
PROCESS_TERMINATE, PROCESS_SET_QUOTA, PROCESS_QUERY_LIMITED_INFORMATION = 0x1, 0x100, 0x1000
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x2000, 0x1000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


def bit_names(value: int, names: dict[str, int]) -> list[str]:
    return [name for name, bit in names.items() if value & bit]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount",
                                                     "OtherOperationCount", "ReadTransferCount",
                                                     "WriteTransferCount", "OtherTransferCount")]


class _BasicLimits(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", ctypes.c_uint32), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_uint32), ("SchedulingClass", ctypes.c_uint32)]


class JobLimits(ctypes.Structure):
    """JOBOBJECT_EXTENDED_LIMIT_INFORMATION (144 bytes on 64-bit Windows)."""
    _fields_ = [("BasicLimitInformation", _BasicLimits), ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


def kill_on_close_limits() -> JobLimits:
    """The processes of the job end when its last handle is closed; and a process that they start is NOT in the job
    (silent breakaway): only the event child itself ends with the program, as on Linux. herdr-core can start its
    server, which keeps every terminal running: it must never end with the panel."""
    limits = JobLimits()
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK
    return limits


class Win32:
    """The calls of user32 and kernel32 that the program makes, through ctypes, with their types (a handle is a
    pointer on 64-bit Windows). Only on Windows: `load_win32` makes it. A test gives a made-up object with the same
    methods."""

    def __init__(self, windll, msvcrt) -> None:
        from ctypes import wintypes  # noqa: PLC0415  (Windows types: only here)
        self._msvcrt = msvcrt
        self._user32, self._kernel32 = windll.user32, windll.kernel32
        handle, dword, boolean = wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL
        hwnd, pointer = wintypes.HWND, ctypes.c_void_p
        # WINFUNCTYPE (stdcall) on Windows; CFUNCTYPE where there is none (the tests of the prototypes on Linux).
        self._enum_proc = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(boolean, hwnd, wintypes.LPARAM)
        long_ptr = ctypes.c_ssize_t
        get_long = getattr(self._user32, "GetWindowLongPtrW", None) or self._user32.GetWindowLongW
        set_long = getattr(self._user32, "SetWindowLongPtrW", None) or self._user32.SetWindowLongW
        self._get_long, self._set_long = get_long, set_long
        for function, result, arguments in (
                (self._user32.EnumWindows, boolean, [self._enum_proc, wintypes.LPARAM]),
                (self._user32.GetWindowThreadProcessId, dword, [hwnd, ctypes.POINTER(dword)]),
                (self._user32.IsWindowVisible, boolean, [hwnd]),
                (self._user32.IsIconic, boolean, [hwnd]),
                (self._user32.GetWindow, hwnd, [hwnd, ctypes.c_uint]),
                (self._user32.ShowWindow, boolean, [hwnd, ctypes.c_int]),
                (self._user32.SetForegroundWindow, boolean, [hwnd]),
                (self._user32.GetForegroundWindow, hwnd, []),
                (self._user32.GetClassNameW, ctypes.c_int, [hwnd, wintypes.LPWSTR, ctypes.c_int]),
                (self._user32.SetWindowPos, boolean, [hwnd, hwnd, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                                      ctypes.c_int, ctypes.c_uint]),
                (get_long, long_ptr, [hwnd, ctypes.c_int]),
                (set_long, long_ptr, [hwnd, ctypes.c_int, long_ptr]),
                (self._kernel32.OpenProcess, handle, [dword, boolean, dword]),
                (self._kernel32.CloseHandle, boolean, [handle]),
                (self._kernel32.QueryFullProcessImageNameW, boolean, [handle, dword, wintypes.LPWSTR,
                                                                      ctypes.POINTER(dword)]),
                (self._kernel32.CreateJobObjectW, handle, [pointer, wintypes.LPCWSTR]),
                (self._kernel32.SetInformationJobObject, boolean, [handle, ctypes.c_int, pointer, dword]),
                (self._kernel32.AssignProcessToJobObject, boolean, [handle, handle]),
                (self._kernel32.PeekNamedPipe, boolean, [handle, pointer, dword, pointer, ctypes.POINTER(dword),
                                                         pointer]),
                (self._kernel32.ReadFile, boolean, [handle, pointer, dword, ctypes.POINTER(dword), pointer])):
            function.restype = result
            function.argtypes = arguments
        self._job = None

    # windows
    def windows(self) -> list[tuple[int, int, bool, bool, bool]]:
        """Every top-level window, the topmost first: (hwnd, pid, visible, minimized, has an owner)."""
        found = []

        def each(hwnd, _param):
            found.append(int(hwnd or 0))
            return True

        self._user32.EnumWindows(self._enum_proc(each), 0)
        return [(hwnd, self.window_pid(hwnd), bool(self._user32.IsWindowVisible(hwnd)),
                 bool(self._user32.IsIconic(hwnd)), bool(self._user32.GetWindow(hwnd, GW_OWNER)))
                for hwnd in found if hwnd]

    def window_pid(self, hwnd: int) -> int:
        from ctypes import wintypes  # noqa: PLC0415
        pid = wintypes.DWORD(0)
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)

    def process_name(self, pid: int) -> str | None:
        """The file name of the program of the process (for example "herdr-app.exe"), or None."""
        from ctypes import wintypes  # noqa: PLC0415
        process = self._kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not process:
            return None
        try:
            buffer, size = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
            if not self._kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                return None
            return os.path.basename(buffer.value.replace("\\", "/"))
        finally:
            self._kernel32.CloseHandle(process)

    def is_iconic(self, hwnd: int) -> bool:
        return bool(self._user32.IsIconic(hwnd))

    def is_visible(self, hwnd: int) -> bool:
        return bool(self._user32.IsWindowVisible(hwnd))

    def restore(self, hwnd: int) -> bool:
        return bool(self._user32.ShowWindow(hwnd, SW_RESTORE))

    def set_foreground(self, hwnd: int) -> bool:
        return bool(self._user32.SetForegroundWindow(hwnd))

    def foreground_window(self) -> int:
        return int(self._user32.GetForegroundWindow() or 0)

    def class_name(self, hwnd: int) -> str:
        buffer = ctypes.create_unicode_buffer(256)
        self._user32.GetClassNameW(hwnd, buffer, 256)
        return buffer.value

    def style(self, hwnd: int) -> int:
        return int(self._get_long(hwnd, GWL_STYLE)) & 0xFFFFFFFF

    def ex_style(self, hwnd: int) -> int:
        return int(self._get_long(hwnd, GWL_EXSTYLE)) & 0xFFFFFFFF

    def set_ex_style(self, hwnd: int, value: int) -> None:
        self._set_long(hwnd, GWL_EXSTYLE, ctypes.c_int32(value).value)

    def set_topmost(self, hwnd: int) -> bool:
        return bool(self._user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                              SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED))

    # processes
    def kill_job(self):
        """The job of the event children: made one time, with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE. This process holds
        its only handle until it ends; then the system closes it and ends every process in the job. None when it
        cannot be made."""
        if self._job is None:
            job = self._kernel32.CreateJobObjectW(None, None)
            limits = kill_on_close_limits()
            if job and self._kernel32.SetInformationJobObject(job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                                              ctypes.byref(limits), ctypes.sizeof(limits)):
                self._job = job
            elif job:
                self._kernel32.CloseHandle(job)
        return self._job

    def assign(self, job, pid: int) -> bool:
        process = self._kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
        if not process:
            return False
        try:
            return bool(self._kernel32.AssignProcessToJobObject(job, process))
        finally:
            self._kernel32.CloseHandle(process)

    def handle_of(self, descriptor: int) -> int:
        """The Win32 handle of an open file number."""
        return int(self._msvcrt.get_osfhandle(descriptor))

    def wait_data(self, handle: int, sleep=time.sleep) -> bool:
        """Wait until the pipe `handle` has data (True) or its writer is gone or the handle fails (False). A read of
        no bytes waits in the system until a byte is there and takes none (libuv waits for the anonymous pipes of
        Windows this way: `uv_pipe_zero_readfile_thread_proc`). Should it come back with no byte there, the pipe is
        looked at again after PIPE_POLL seconds: never a loop that does not wait."""
        from ctypes import wintypes  # noqa: PLC0415
        buffer, got, available = ctypes.create_string_buffer(1), wintypes.DWORD(0), wintypes.DWORD(0)
        while True:
            if not self._kernel32.ReadFile(handle, buffer, 0, ctypes.byref(got), None):
                return False
            if not self._kernel32.PeekNamedPipe(handle, None, 0, None, ctypes.byref(available), None):
                return False
            if available.value > 0:
                return True
            sleep(PIPE_POLL)


_win32: list = []


def load_win32():
    """The Win32 calls (one object for the process), or None when this is not Windows."""
    if not _win32:
        windll, msvcrt = getattr(ctypes, "windll", None), load_msvcrt()
        if windll is None or msvcrt is None:
            return None
        _win32.append(Win32(windll, msvcrt))
    return _win32[0]


# ----- the Herdr app: its programs, its window, its raise and its start -----

# The program of the Herdr app and of its core (the release archive of 0.1.16, the installers app/install.ps1 and
# core/install.ps1). The process of the app window is herdr-app.exe.
APP_PROCESSES = ("herdr-app.exe",)
# After PATH: where the installers put them (%LOCALAPPDATA%\Programs\…, added to the PATH of the user; a program that
# the Herdr app starts can have an older PATH), and cargo for herdr-core (the app looks there too).
APP_FOLDERS = (("LOCALAPPDATA", "Programs", "herdr-app"),)
CORE_FOLDERS = (("LOCALAPPDATA", "Programs", "herdr-core"), ("~", ".cargo", "bin"))
# Windows has no program to raise, to start or to clean an environment: the program makes these calls itself.
COMMANDS: dict[str, str] = {}
# Each program that the client starts (herdr-app, herdr-core): no console window. The program runs under pythonw,
# which has no console, and a console program would get a new console window for each call.
PROCESS_OPTIONS = {"creationflags": CREATE_NO_WINDOW}


def _place(parts: tuple[str, ...]) -> tuple[Path | None, str]:
    """The folder of `parts` and its name for the log (a variable or ~, never a path of the person)."""
    base, rest = parts[0], parts[1:]
    if base == "~":
        return Path.home().joinpath(*rest), "\\".join(parts)
    value = os.environ.get(base, "")
    return (Path(value).joinpath(*rest) if os.path.isabs(value) else None), "\\".join((f"%{base}%", *rest))


def _find(name: str, which, folders) -> tuple[str | None, str]:
    found = which(name)
    if found:
        return found, "PATH"
    for parts in folders:
        folder, label = _place(parts)
        if folder is None:
            continue
        path = folder / f"{name}.exe"
        try:
            if path.is_file():
                return str(path), label
        except OSError:
            continue
    return None, "not found"


def _which(which):
    if which is None:
        import shutil  # noqa: PLC0415
        which = shutil.which
    return which


def find_executables(*, which=None) -> tuple[str | None, str | None]:
    """Return the paths of herdr-app and herdr-core (None: not found), and log one line that says where each was
    found: PATH, then the folders of the installers (and cargo for herdr-core)."""
    which = _which(which)
    app, app_place = _find("herdr-app", which, APP_FOLDERS)
    core, core_place = _find("herdr-core", which, CORE_FOLDERS)
    log.info("herdr-app: %s; herdr-core: %s", app_place, core_place)
    return app, core


def app_window(api, names=APP_PROCESSES, pids=None) -> int | None:
    """The top-level window of the Herdr app: the first (the topmost) window with no owner that shows or is
    minimized, of a process whose program is one of `names` (or whose pid is one of `pids`, for a test). None."""
    known: dict[int, str | None] = {}
    for hwnd, pid, visible, iconic, owned in api.windows():
        if owned or not (visible or iconic):
            continue
        if pids is not None:
            if pid in pids:
                return hwnd
            continue
        if pid not in known:
            name = api.process_name(pid)
            known[pid] = name.lower() if name else None
        if known[pid] in names:
            return hwnd
    return None


def _raise(api, names, pids) -> bool:
    hwnd = app_window(api, names, pids)
    if hwnd is None:
        log.info("no window of the Herdr app was found")
        return False
    if api.is_iconic(hwnd):
        api.restore(hwnd)
    if api.set_foreground(hwnd):
        return True
    # Windows lets a process take the foreground only in some cases (it got the last input, it is in front, …): a
    # click on the panel is such an input; a jump that took long while the person typed elsewhere is not.
    log.info("Windows did not bring the Herdr window to the front (SetForegroundWindow refused)")
    return False


def raise_app(run, commands: dict[str, str], *, win32=None, main_thread=None, names=APP_PROCESSES,
              pids=None) -> bool:
    """Bring the window of the Herdr app to the front: restore it when it is minimized, then SetForegroundWindow, on
    the main thread of Qt (mainthread.py; `main_thread`: a test gives its own). False when there is no such window,
    or when Windows refused (the row then shows the failure message, see start_app)."""
    api = (win32 or load_win32)()
    if api is None:
        return False
    if main_thread is None:
        from .mainthread import on_main_thread as main_thread  # noqa: PLC0415
    try:
        return bool(main_thread(lambda: _raise(api, names, pids)))
    except Exception as error:  # a Win32 call that failed, or no answer of the main thread
        log.info("the raise of the Herdr window failed (%s)", type(error).__name__)
        return False


def start_app(run, app: str, commands: dict[str, str], *, popen=subprocess.Popen, win32=None,
              names=APP_PROCESSES) -> int:
    """Start the Herdr app as a process of its own: no console, not in our process group, out of a job of ours when
    the job allows it (else in it), in the home folder. Return 0 when it started; the errors of Popen go to the
    caller. When a window of the Herdr app is there already, nothing starts and the result is 1: on Windows a second
    start is not a way to raise a window (the raise was refused, so the row shows the failure message)."""
    api = (win32 or load_win32)()
    if api is not None and app_window(api, names) is not None:
        log.info("the Herdr app has a window: it is not started again")
        return 1
    options = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
               "close_fds": True, "cwd": str(Path.home())}
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        popen([app], creationflags=flags | CREATE_BREAKAWAY_FROM_JOB, **options)
    except PermissionError:  # a job of the caller that allows no breakaway: the app starts in it
        popen([app], creationflags=flags, **options)
    return 0


def clean_environment(argv: list[str], names, commands: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    """The command `argv` and its environment, to run without the environment variables `names` (no `env` program):
    the argv as it is, and the environment of this process without them. The names of Windows variables have no
    case."""
    drop = {name.upper() for name in names}
    return list(argv), {key: value for key, value in os.environ.items() if key.upper() not in drop}


# ----- the windows of the program -----
# Qt 6.12 (qwindowswindow.cpp, WindowCreationData::fromWindow, initialize, show_sys) gives the panel of Plain.qml all
# of it: Qt::WindowDoesNotAcceptFocus → WS_EX_NOACTIVATE, Qt::Tool → WS_EX_TOOLWINDOW (no taskbar button),
# Qt::WindowStaysOnTopHint → SetWindowPos(HWND_TOPMOST, … SWP_NOACTIVATE), and a Tool window shows with
# SW_SHOWNOACTIVATE. The program checks these and adds only what is missing (a later Qt).

# A property of the window: the styles that the program had to add to the panel ("" none), for the self-test.
ADDED = "bellwetherAdded"
# A property of the window: the call that asked for the foreground at the last show, and its answer.
ACTIVATION = "bellwetherActivation"
PANEL_EX = {"WS_EX_NOACTIVATE": WS_EX_NOACTIVATE, "WS_EX_TOOLWINDOW": WS_EX_TOOLWINDOW}


def _prepare_panel(window, api) -> None:
    try:
        hwnd = int(window.winId())
        ex = api.ex_style(hwnd)
        missing = [name for name, bit in PANEL_EX.items() if not ex & bit]
        if missing:
            api.set_ex_style(hwnd, ex | sum(PANEL_EX[name] for name in missing))
        if missing or not ex & WS_EX_TOPMOST:
            api.set_topmost(hwnd)
            missing += [] if ex & WS_EX_TOPMOST else ["HWND_TOPMOST"]
        window.setProperty(ADDED, ", ".join(missing))
        if missing:
            log.info("the panel got %s, which Qt did not give", ", ".join(missing))
    except Exception as error:
        log.warning("the panel could not get the styles of a Windows panel (%s): Qt's window as it is",
                    type(error).__name__)


def bring_forward(window, api) -> None:
    """Ask Windows to make `window` the foreground window (the keyboard goes to it). Windows allows it when this
    process got the last input (a click in the tray menu or on the panel opens these windows); else it refuses and
    flashes the taskbar button of the window: the window still shows, and the person clicks it."""
    try:
        done = api.set_foreground(int(window.winId()))
    except Exception as error:
        log.info("the program could not ask for the foreground (%s)", type(error).__name__)
        window.setProperty(ACTIVATION, "failed")
        return
    window.setProperty(ACTIVATION, "SetForegroundWindow" if done else "SetForegroundWindow refused")
    if not done:
        log.info("Windows did not bring the window to the front (SetForegroundWindow refused): its taskbar button "
                 "flashes")


def prepare_window(window, role: str, *, win32=None) -> None:
    """After a window of the program exists. "panel": the styles of a panel that takes no focus and has no taskbar
    button, topmost (only what Qt did not give). "answer" and "options": the foreground at each show. Nothing when Qt
    does not use its windows plugin (off screen)."""
    if win32 is None and not native():
        return
    api = (win32 or load_win32)()
    if api is None:
        return
    if role == "panel":
        _prepare_panel(window, api)
        return
    window.visibleChanged.connect(lambda visible: bring_forward(window, api) if visible else None)
    if window.isVisible():
        bring_forward(window, api)


def window_facts(window, *, win32=None) -> dict:
    """The facts of the native window, for the self-test: its class, its styles (with the names of their bits),
    topmost, whether it or an other window of this program is the foreground window, and its process. {} when Qt does
    not use its windows plugin (off screen), as on Linux."""
    if win32 is None and not native():
        return {}
    api = (win32 or load_win32)()
    if api is None:
        return {}
    hwnd = int(window.winId())
    style, ex = api.style(hwnd), api.ex_style(hwnd)
    front = api.foreground_window()
    return {
        "class": api.class_name(hwnd),
        "style": style, "style_names": bit_names(style, STYLES),
        "ex_style": ex, "ex_style_names": bit_names(ex, EX_STYLES),
        "topmost": bool(ex & WS_EX_TOPMOST),
        "no_activate": bool(ex & WS_EX_NOACTIVATE),
        "tool_window": bool(ex & WS_EX_TOOLWINDOW),
        "visible": api.is_visible(hwnd),
        "foreground": front == hwnd,
        "foreground_of_this_program": bool(front) and api.window_pid(front) == os.getpid(),
        "process_is_this_program": api.window_pid(hwnd) == os.getpid(),
        "added_by_program": str(window.property(ADDED) or ""),
        "activation_asked": str(window.property(ACTIVATION) or ""),
    }


# ----- the event child, which ends with this process: a job object that is closed when this process ends -----
# Chosen over the watcher of macOS: Windows has no SIGTERM to the watcher (terminate() is TerminateProcess, which runs
# no handler), so a watcher that the program ends would leave its child; and a job is one call of the kernel, which
# the runner proves with a real process tree.

_job_failed: list[bool] = []


def spawn_child(argv: list[str], *, popen=subprocess.Popen, win32=None) -> subprocess.Popen:
    """Start the child (stdin NUL, stdout a pipe, stderr dropped, unbuffered, no console) and put it in the job of the
    event children: the system ends it when this process ends, also after a kill. When the job cannot be made or
    the child cannot join it: one log line, and the child is ended only by the program (as before the job)."""
    child = popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
                  creationflags=CREATE_NO_WINDOW)
    api = (win32 or load_win32)()
    try:
        job = api.kill_job() if api is not None else None
        joined = job is not None and api.assign(job, child.pid)
    except Exception:  # a Win32 call that failed: as a child that did not join
        joined = False
    if not joined and not _job_failed:
        _job_failed.append(True)
        log.warning("the event child is not in a job that ends it with the program: it can outlive a killed program")
    return child


# The seconds before a pipe is looked at again when a read of no bytes came back with no byte (see wait_data).
PIPE_POLL = 0.05


class PipeWatch:
    """A thread that waits until a pipe has data or its writer is gone (Win32.wait_data), and takes no byte. It
    tells `changed` (a Condition that `readable` waits on). After the reader took the data, `again` lets it wait
    once more. When the writer is gone it stays ready (a read gives the end) and its thread ends."""

    def __init__(self, descriptor: int, handle: int, wait_data, changed: threading.Condition) -> None:
        self.descriptor, self.handle = descriptor, handle
        self.ready = self.ended = False
        self._wait_data, self._changed = wait_data, changed
        self._go = threading.Event()
        self._go.set()
        threading.Thread(target=self._run, name="pipe-watch", daemon=True).start()

    def _run(self) -> None:
        while True:
            self._go.wait()
            self._go.clear()
            try:
                alive = bool(self._wait_data(self.handle))
            except Exception:  # a failed call: as the end of the pipe (the read tells)
                alive = False
            with self._changed:
                self.ready, self.ended = True, not alive
                self._changed.notify_all()
            if not alive:
                return

    def again(self) -> None:
        """The data that it told of was read (the caller holds `changed`): wait for new data."""
        if self.ready and not self.ended:
            self.ready = False
            self._go.set()


_watches: dict[int, PipeWatch] = {}
_changed = threading.Condition()


def readable(descriptors: list[int], timeout: float, *, win32=None) -> list[int]:
    """The open file numbers of `descriptors` (pipes) that have data or whose writer is gone, after at most `timeout`
    seconds (empty: none). select takes only sockets on Windows: a thread of each pipe waits in the system for its
    data (PipeWatch), and this call waits on them with its time limit. No thread wakes while no data comes. A pipe
    that this call told of last time waits again (its data was read since). A file number that now names an other
    pipe gets a new watch."""
    api = (win32 or load_win32)()
    with _changed:
        for descriptor in descriptors:
            handle = api.handle_of(descriptor)
            watch = _watches.get(descriptor)
            if watch is None or watch.handle != handle:
                _watches[descriptor] = PipeWatch(descriptor, handle, api.wait_data, _changed)
            else:
                watch.again()

        def ready() -> list[int]:
            return [descriptor for descriptor in descriptors if _watches[descriptor].ready]

        _changed.wait_for(ready, timeout)
        return ready()


# ----- the process host: psutil -----

class Host(PsutilHost):
    """The process host of psutil (platform/host.py). The start of a process is the time that psutil gives, as a text.
    Claude Code writes `procStartFt` on Windows, not `procStart` (its form is not known here): a session file is then
    never the file of a live process (the rule of sessions.py), and the row shows the time of the terminal, never a
    model that cannot be proven."""

    def start_text(self, seconds: float) -> str:
        return repr(float(seconds))


def process_host(*, psutil=None) -> Host:
    """The host of this machine. Without psutil: one log line, and a host that knows no process."""
    return Host(None, (psutil or load_psutil)())


# ----- the icon file of the Herdr app: herdr-app.svg beside herdr-app.exe -----

def app_icon_file(*, which=None) -> Path | None:
    """The icon of the Herdr app: herdr-app.svg, which the release archive puts beside herdr-app.exe. None: the tray
    draws its circle."""
    app, _place_name = _find("herdr-app", _which(which), APP_FOLDERS)
    if app is None:
        return None
    path = Path(app).with_name("herdr-app.svg")
    try:
        return path if path.is_file() else None
    except OSError:
        return None
