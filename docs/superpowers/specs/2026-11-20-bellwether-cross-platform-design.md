# Bellwether on every system — design

Date: 2026-11-20. Branch: `cross-platform` (from `unblock-agents` at `525907c`, 1667 tests). Base product spec: `2026-11-18-bellwether-design.md`. This document takes the place of `2026-11-19-bellwether-macos-port-design.md` (kept for its detail on the macOS window; where the two differ, this one is right).

## Request and decisions of the user

- 2026-11-20: "check if we can re-write or maybe just adapt this mod to run on all OS", then "do the suggested order, open a branch for it". The order: (1) a platform layer, pure move; (2) a second window shell; (3) macOS, proven on a GitHub runner; (4) Windows.
- Decisions of 2026-11-19 that still hold: the user has no Mac (and no Windows machine); the install is from source with `uv` on each system (no bundle, no installer); the goal is full parity; a CI runner is accepted within the free minutes; the work is on its own branch.

## Goal

The same program runs on Linux (KDE Wayland as today; other Wayland desktops and X11 through the second shell), macOS and Windows: the floating panel above all windows that does not take the keyboard, five layouts, the options window, the tray or menu bar icon, the jump to an agent, the answer window, the names by terminal title, the model and session-time line, the custom look.

Linux on KDE Wayland must stay exactly as it is: the same pixels, the same protocol behaviour, every test.

## What is tied to Linux today

| # | Where | Today | macOS | Windows |
|---|---|---|---|---|
| 1 | `ui/Main.qml`, `__main__.py` | A wlr-layer-shell surface (`org.kde.layershell`) placed with margins | A frameless always-on-top panel that never becomes the key window, on all Spaces | A frameless topmost tool window with no activation |
| 2 | `window.py`, `client.py` (`busctl`) | Raise of the Herdr window with the KWin runner | Activate the Herdr app | `SetForegroundWindow` of the Herdr window |
| 3 | `client.py` (`systemd-run`) | Start of a closed Herdr app outside our process tree | `open -a` | A detached process |
| 4 | `client.py` (`env -u …`) | The caller variables are removed with `env` | The same, or an environment given to the process | An environment given to the process (no `env` program) |
| 5 | `sessions.py` (`Host`) | `/proc`: the start of a process, its children, its open files | A `Host` built on `psutil` | A `Host` built on `psutil` |
| 6 | `events.py` (`prctl`) | The event child ends with us | A watcher process | A watcher process (or a job object) |
| 7 | `paths.py` | XDG folders | `~/Library/Application Support`, `~/Library/Logs`, `~/Library/Caches` | `%APPDATA%`, `%LOCALAPPDATA%` |
| 8 | `appicon.py` | The Herdr icon from the `.desktop` file and the icon theme | The icon of the app bundle | The icon beside the program, else the circle |
| 9 | `__main__.py` (`fcntl.flock`) | The single-instance lock | The same | `msvcrt.locking` |
| 10 | `scripts/start.sh` | `setsid -f`, XDG state folder | `nohup … &` | `scripts/start.cmd` with `pythonw` |
| 11 | `skins/*Theme.qml`, `Fonts` | Linux font families first | Add Menlo, SF | Add Consolas, Segoe UI |
| 12 | `__main__.py` (`signal`, `QT_QPA_PLATFORM=wayland`) | Forces the Wayland plugin | Not set | Not set |

Portable already: the Herdr commands (`herdr-app ls`, `do agent.focus`, `herdr-core events`, `ls`, `get`, `read`, `keys`, `send`), the prompt readers, the backend, the settings file, every QML skin, theme and control, the options window, the answer window, the tray through `QSystemTrayIcon`, the window icon.

## Design

### 1. A platform package

`bellwether/platform/`: `__init__.py` picks one module from `sys.platform` one time (`linux.py`, `macos.py`, `windows.py`) and gives its members. The rest of the program calls only this interface. No `sys.platform` test and no system-specific import outside the package.

The interface **as built in P1** (Linux only). `tests/test_platform.py` holds the same table (member → kind and parameter names): it is the contract that `macos.py` and `windows.py` implement. `load(name)` takes a value of `sys.platform`; a system with no module is an `ImportError` ("bellwether does not run on this system ('darwin'): it runs on linux"), so the program stops at the import of the package with a clear message. A function takes an injected `run` or folders where a test needs them.

| Member | Signature | What it gives |
|---|---|---|
| `config_home` | `config_home() -> Path` | The base folder of the settings (Linux: `$XDG_CONFIG_HOME`, else `~/.config`). |
| `state_home` | `state_home() -> Path` | The base folder of the log (Linux: `$XDG_STATE_HOME`, else `~/.local/state`). |
| `cache_home` | `cache_home() -> Path` | The base folder of the icon cache (Linux: `$XDG_CACHE_HOME`, else `~/.cache`). |
| `runtime_dir` | `runtime_dir() -> Path` | The folder of the lock files (Linux: `$XDG_RUNTIME_DIR`, else `/tmp`). |
| `lock` | `lock(path) -> handle \| None` | Takes the lock of the file at `path`: the open file that holds it, or None when another process holds it. Close it to give the lock back (Linux: `fcntl.flock`). |
| `COMMANDS` | `dict[str, str]` | The system programs that the client runs, by name → default program. `HerdrClient(..., **commands)` takes fakes by these names; another name is a `TypeError` (Linux: `busctl`, `systemd_run`, `env`). |
| `raise_app` | `raise_app(run, commands) -> bool` | Brings the Herdr window to the front; False when that did not occur (Linux: the KWin window runner through `busctl`). |
| `start_app` | `start_app(run, app, commands) -> int` | Starts `app` outside our process tree; the exit code of the launcher, 0 = accepted; errors of `run` go to the caller (Linux: `systemd-run --user --quiet --collect --slice=app.slice -- <app>`). |
| `clean_environment` | `clean_environment(argv, names, commands) -> list[str]` | The command `argv`, run without the environment variables `names` (Linux: `env -u <name> … <argv>`). The names (`HC_TERMINAL_ID`, `HC_SCOPE`, `HC_TERMINAL_SOCKET`) stay in `client.py`: they are Herdr facts, not system facts. |
| `find_executables` | `find_executables() -> (str \| None, str \| None)` | The paths of `herdr-app` and `herdr-core` (Linux: `PATH`, and `~/.local/bin/herdr-core`). |
| `spawn_child` | `spawn_child(argv) -> subprocess.Popen` | The event child (stdin `/dev/null`, stdout a pipe, stderr dropped, unbuffered), which ends when we end (Linux: `prctl(PR_SET_PDEATHSIG)`). |
| `process_host` | `process_host() -> Host` | The process host of `sessions.py`: `home`, `bytes_read`, `start_ticks(pid)`, `family(*pids)`, `open_files(pid)` (Linux: `Host(home, proc)` on `/proc`, in `linux.py` with `MAX_PROCESSES` and `MAX_TASKS`). |
| `app_icon_file` | `app_icon_file(desktop_dirs=None, icon_dirs=None) -> Path \| None` | The icon file of the Herdr app. The folders are for a test; None = the places of the system (Linux: `herdr-app.desktop` and the hicolor theme, then pixmaps). |
| `SHELL_NEEDS` | `str` | What the layer shell needs, for the log line when the QML interface does not load. |
| `prepare_environment` | `prepare_environment() -> None` | Before the `QApplication` (Linux: `QT_QPA_PLATFORM=wayland;xcb` unless set — P2; was `wayland`). |
| `prepare_app` | `prepare_app(app) -> None` | After the `QApplication` (Linux: a warning when the Qt platform is not wayland). |
| `prepare_engine` | `prepare_engine(engine) -> None` | Gives the QML engine the import path of the shell (Linux: `ui/imports`, for `org.kde.layershell`). P2: it no longer decides the load; `shell()` does. |
| `SHELL_FILES` | `dict[str, Path]` | (P2) The QML file of each shell this system can use: Linux `{"layer": ui/shells/Layer.qml, "plain": ui/shells/Plain.qml}`; macOS and Windows give only `"plain"`. |
| `shell` | `shell(engine, environ=None, platform_name=None, compositor_globals=None) -> str` | (P2) `"layer"` or `"plain"`, by the rule of section 2. The other arguments are for a test. |

**Changed in P3** (Linux command lines and behaviour identical):

| Member | Signature | What changed |
|---|---|---|
| `COMMANDS` | `dict[str, str]` | Keys are roles, not program names. Linux `{"raiser": "busctl", "launcher": "systemd-run", "env_cleaner": "env"}`; macOS `{"launcher": "/usr/bin/open"}`. `HerdrClient(..., raiser=…, launcher=…)` takes fakes by role; a role the platform does not have is a `TypeError`. The client passes the dict to `raise_app`, `start_app`, `clean_environment` only. |
| `clean_environment` | `clean_environment(argv, names, commands) -> (list[str], dict \| None)` | The argv AND the environment to run it in. Linux: `(env -u <name> … <argv>, None)`, the same command line as before. macOS: `(argv, os.environ without names)`. The client gives `env=` to `run`/`spawn` only when the mapping is not None, so the Linux calls are the same as before (the tests of the Linux command lines did not change). |
| `app_icon_file` | `app_icon_file() -> Path \| None` | No folders: a test calls the Linux finder `find_app_icon(desktop_dirs, icon_dirs)`; `appicon.load_app_icon(find=None)` and `TrayIcons.load(find=None)` take a finder. |
| `process_host` | `process_host() -> ProcessHost` | `platform/host.py`: `ProcessHost(home)` with `home`, `bytes_read`, the shared `family()` and `MAX_PROCESSES`; each system implements `start_ticks`, `children`, `arguments`, `open_files`. `sessions.py` type hints name the base. |
| `prepare_window` | `prepare_window(window, role) -> None` | New. After a window exists; `role` is `"panel"` (`__main__.main`), `"answer"` (`answer.py`), `"options"` (`options.py`), once per window. Linux: nothing. |
| `window_facts` | `window_facts(window) -> dict` | New. The native facts of a window for the self-test. Linux: `{}`. |
| `lock` | `lock(path)` | Moved to `platform/posix.py` (shared by Linux and macOS, `fcntl.flock`). |

A system module may add parameters after those of the table, only keyword-only with a default (the loaders of AppKit or psutil, a finder): the table test checks that. The package also has `SYSTEM` (= `sys.platform`, for the self-test). `MODULES` is `{"linux": "linux", "darwin": "macos"}`; Windows is still the clear `ImportError` (P4). `platform/linux.py` imports on macOS too (`prctl` is looked up with `getattr`), so the tests of the Linux logic with fakes run on the macOS runner (`tests/test_client.py` and `tests/test_client_screen.py` pin the client to the Linux module).

**Changed in P4** (Linux and macOS command lines and behaviour identical):

| Member | Signature | What changed |
|---|---|---|
| `MODULES` | `dict` | `{"linux": "linux", "darwin": "macos", "win32": "windows"}`. Any other system: the clear `ImportError` ("… it runs on linux, darwin, win32"). |
| `readable` | `readable(descriptors, timeout) -> list[int]` | New. The pipes of `descriptors` that have data or whose writer is gone, after at most `timeout` s. Linux, macOS: `select.select` (`platform/posix.py`, the call `events.py` made before). Windows: `PeekNamedPipe` each 50 ms (`select` takes only sockets there). `events.py` waits through it. |
| `PROCESS_OPTIONS` | `dict` | New. More `Popen` options for each program that the client runs: `{}` on Linux and macOS (the calls are the same as before), `{"creationflags": CREATE_NO_WINDOW}` on Windows (the program runs under `pythonw`: a console program would get a console window at each call). |
| `COMMANDS` | `dict[str, str]` | Windows: `{}` (no program to raise, start or clean an environment). The table test allows an empty dict. |
| `raise_app` (macOS) | | The AppKit calls run on the main thread of Qt (`platform/mainthread.py`, `on_main_thread(function, wait=3.0)`); the reopen with `open` stays on the worker. |

The package also has `platform/mainthread.py` (a call on the main thread of Qt from a worker, with a time limit; a
late call never runs) and the psutil host moved to `platform/host.py` (`PsutilHost`, `load_psutil`, `MAX_WORDS`,
`MAX_FILES`; each system gives `start_text(seconds)`). `platform/linux.py` imports on Windows (`fcntl` inside
`posix.lock`, `ctypes.CDLL(None)` guarded), so the client tests that pin it run on the Windows runner.

Kept outside the package: `paths.py` keeps `NAME`, `OLD_NAME` and `move_old_folders()` (the move of the `herdr-float` folders is plain file work on the platform folders: on a new system it finds nothing to move) and gives the four folders again for its callers. `appicon.py` keeps the image work (load, mark, tint).

`platform/linux.py` gets the code that exists today, **moved, not rewritten**.

### 2. Two window shells, one panel

`Main.qml` today mixes (a) the layer-shell properties, (b) the place model (x, y, screen, clamp, default corner, drag, move to next screen, hot-plug), (c) the Loader, the pointer handler and the hit test. Split:

- `ui/PanelShell.qml` — (b) and (c): nothing that names a window system.
- `ui/shells/Layer.qml` — (a): the layer surface. KDE Wayland, and any compositor with the layer-shell protocol.
- `ui/shells/Plain.qml` — a frameless `Window` with `Tool | FramelessWindowHint | WindowStaysOnTopHint | WindowDoesNotAcceptFocus | NoDropShadowWindowHint` and a clear background, that maps the place to `x`, `y` and `screen`. macOS, Windows, X11, and Wayland with no layer shell.

The shell on Linux: `layer` when the platform is Wayland, the QML module `org.kde.layershell` loads and the compositor has `zwlr_layer_shell_v1`; else `plain`. `BELLWETHER_SHELL=plain|layer` forces one (for tests and for a person).

`Plain.qml` has no system call in it, so every behaviour test of the panel runs on it **on Linux**, off screen, with the same parametrized tests as the layer shell.

**As built in P2.**

- The shell file IS the panel window: `PanelShell.qml` is a `Window` (the place model, the Loader, the pointer handler, the hit test, no import of a window system), and each shell is a QML type derived from it (`PanelShell { … }`). So `engine.rootObjects()[0]` is the panel window for every shell, and every property and function that Python and the tests use stays on it with its name (`panel`, `openState`, `posX`, `posY`, `screenName`, `surfaceScreen`, `atDefault`, `refreshRate`, `screenSource`, `closedByCompositor`, `moveToNextScreen()`, …).
- One hook: `rehome()` (shared) finds the real screen and calls `showOn(target, x, y, real)` of the shell (`real`: the QScreen when the window must change its screen, else null); the shell calls `setPlace()` (shared: screen name, place, clamp) and does its window work. Layer: hide, `setPlace`, `screen`, `x`/`y` for the output, show (the code of before, in the same order); the margins are bound to the place, `requestUpdate()` on a margin change, anchors top|left, overlay layer, keyboard none, exclusion −1.
- The plain shell as built (fix round 1 of P2): the place of the panel in the whole desktop (its screen plus `posX`, `posY`), its size and its screen go to the window system in ONE request (`setGeometry`), after the step in which they changed (`Qt.callLater`; at once while the window is hidden, so it shows at its place). The screen first, then the geometry: a screen that is not part of the same desktop makes Qt make the window again, and the geometry must go to that window. A new size at the default corner is the same one request (size and x together: no frame past the right edge). When the window system puts the window somewhere else, the shell asks for the place again ONE time (not during a drag), then leaves it until the place changes; the model keeps the place of the panel. `placeRequests` counts the requests (tests).
- Where the window system places the window (`windowSystemPlaces`: Qt's platform plugin `wayland*` with the plain shell), a drag past the 6 px calls `startSystemMove()` (the compositor moves the window), and the panel neither changes nor saves its place. The log line of the rule says so: "the plain shell, a normal window: not above other windows, it can take the focus, the compositor places it, and a drag does not save its place".
- The registry read of the rule has a time limit (1 s, a `poll()` of the socket after `wl_display.sync`, not `wl_display_roundtrip`), opens `libwayland-client.so.0` by name (no `ldconfig`), and gives None on any error (no crash at the start).
- The rule (`platform/linux.py`, `shell()`): `BELLWETHER_SHELL=layer|plain` first (another non-empty value: one log line, ignored); then `plain` when the Qt platform is not `wayland*`; `plain` when `org.kde.layershell` does not load in the engine; `plain` when the compositor's registry has no `zwlr_layer_shell_v1` (read by `wayland_globals()`: `ctypes` on libwayland-client, a connection of its own, one round trip); else `layer`. When the registry cannot be read (no library, no compositor, `WAYLAND_SOCKET`), the module and the platform decide (the layer shell, as before). The log gets `shell: layer` or `shell: plain` at the start (`__main__.load_panel`).
- `QT_QPA_PLATFORM` defaults to `wayland;xcb`: the same plugin on a Wayland desktop, and Qt falls back to X11 when no Wayland compositor answers (the plain shell then; Qt writes two lines to stderr).
- A change of behaviour that the rule brings: on KDE with a Qt minor version that does not match the system module, the panel was not shown (an error line); now it shows in the plain shell with a warning line.

### 3. macOS

As sections 3 to 7 of the 2026-11-19 design: an accessory app (no Dock icon); the panel is an `NSPanel` at status level, on all Spaces, non-activating (through `pyobjc-framework-Cocoa`, a dependency only for `sys_platform == "darwin"`; without it a plain always-on-top window and one log line); the answer and options windows activate the app when they open; raise = activate the Herdr app (`open -a` as the second method); start = `open -a`; the watcher for the event child; the paths of the table.

New against that design: the process host (`psutil`, for `sys_platform != "linux"`). The check that a Claude Code session file is of the live process uses the start of the process; the form of `procStart` in that file on macOS is **not known** — the reader must compare only what it can prove and else give no model (the row then shows the time).

**As built in P3** (`bellwether/platform/macos.py`; nobody has run it on a Mac; the runner proves what it can):

- Folders: `~/Library/Application Support`, `~/Library/Logs`, `~/Library/Caches` (+ `bellwether`). The lock files are in `~/Library/Caches` (not `$TMPDIR`: a start by the Herdr app and one from a terminal can have a different `$TMPDIR`). The lock: `fcntl.flock` (`platform/posix.py`).
- Qt: no forced platform; the shell is always `plain` (`BELLWETHER_SHELL=layer` gets one log line). No native call when Qt's platform is not `cocoa` (off screen: the winId is no NSView).
- `prepare_environment`: with pyobjc, `QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM=1` (unless set): Qt 6.12 makes a program with no bundle a foreground app and activates it when it has started (`QCocoaIntegration`, `QCocoaApplicationDelegate.applicationDidFinishLaunching`), so each start took the keyboard from the app of the person (runner run 1: the app was active with only the panel shown). Without pyobjc Qt's way stays (a program that is neither foreground nor accessory has no windows).
- `prepare_app`: the accessory activation policy (no Dock icon). Without pyobjc: one log line (a Dock icon and a plain panel).
- The work area (all systems, the plain shell): `__main__.start_panel` gives the panel `reserved` (screen name → the part that the system keeps: the screen less its available geometry) and follows its changes; the default corner, the clamp and the rows that fit use the rest. The layer shell gets none (the compositor keeps its panels free): identical (0 different pixels, the same protocol trace). Runner run 1: the panel was at y 16 under the 31 px menu bar.
- The panel (`prepare_window(…, "panel")`): Qt 6.12 makes a `Qt::Tool` window a `QNSPanel` at the floating level and sets `hidesOnDeactivate` when it makes the native window, unless the QWindow has the property `_q_macAlwaysShowToolWindow` (`QCocoaWindow::createNSWindow`, `alwaysShowToolWindow()`; read only then). The panel is shown during its QML load, so the property comes too late for that native window: the program sets the property (for a later native window) and, through pyobjc, the level `NSStatusWindowLevel` (25), the collection behaviour `canJoinAllSpaces | fullScreenAuxiliary | stationary | ignoresCycle` (337, set as a whole: Qt's own value has `fullScreenPrimary`), the style mask bit `nonactivatingPanel` plus the private `_setPreventsActivation:` when the window has it (Wine found that the mask alone does not work after the window exists), `becomesKeyOnlyIfNeeded`, `hidesOnDeactivate = NO`, no shadow, not movable by the window server. Qt sets the level again only at a change of the flags or of the full-screen state of that window. With the status level, Qt's activation observer (which puts normal and floating windows to the normal level when the app resigns) leaves the panel alone. Without pyobjc (or when a call fails): the property, then hide, `destroy()`, show: Qt makes the native window again and reads the property (the panel shows when the app is not active; floating level, current Space only, and Qt's observer can lower it after the app was active).
- The answer and options windows: at each show the program asks for the activation of the app (`NSApp.activate`, else `activateIgnoringOtherApps:`) and makes the window key (`makeKeyAndOrderFront:`); when the app is still not active 300 ms later, `activateIgnoringOtherApps:` asks again — only when nothing changed: the same app in front (`NSWorkspace.frontmostApplication`, its pid at the request), the window still shown (P3 review: else the program could take the keyboard from an app the person went to; the fact `second_way_skipped`); without pyobjc Qt's `raise()`. The calls are a property of the window (`bellwetherActivation`) and a fact of the self-test. macOS 14 and later activate by cooperation: the system gives the activation to an app that asks while the person acts in it (in real use a click in the tray menu or on the panel opens these windows) and can refuse it otherwise. Runner run 2 (macOS 26.7.2): with no input of a person the app was not made active and the options window was not key (`can_become_key` true, so Qt with `QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM` and the accessory policy lets a normal window become key). What a runner can prove: that the calls are made and the windows can become key; not that the system gives the activation after a person's click.
- Raise: activate the running app by its bundle identifier (`NSRunningApplication`, `unhide` + `activateWithOptions:`), then always `open -b dev.herdr.app` (Launch Services reopens it: a minimized window shows); True when one worked. Start: `open -a <the .app of herdr-app>`, else `open -b dev.herdr.app`.
- Programs: `PATH`, then `~/.local/bin`, `/opt/homebrew/bin`, `/usr/local/bin`, `~/.local/share/mise/shims`, `/run/current-system/sw/bin`, `~/.nix-profile/bin`, `~/.cargo/bin` (the places where the Herdr app looks for herdr-core), and for herdr-app `Herdr.app/Contents/MacOS/Herdr` in `~/Applications`, `/Applications`. One log line says where each was found (a folder, never a path in the home folder).
- The event child: through the watcher `python -m bellwether.platform.guard <parent pid> <command…>` (`platform/guard.py`): the child inherits stdout; the watcher checks `getppid()` once a second and ends the child (SIGTERM, then SIGKILL after 2 s) and itself when the parent is gone; a SIGTERM to the watcher ends the child; it exits with the code of the child (128 + N for a signal). Linux keeps `prctl`.
- The process host: psutil (`create_time`, `children`, `cmdline`, `open_files`). `start_ticks` gives the start in the form of `LC_ALL=C TZ=UTC ps -o lstart=` ("Thu Nov  5 09:04:05 2026"), which is the form of `procStart` that Claude Code writes off Linux (open question 4). The rule of `sessions.py` is unchanged: a session file counts only when its `procStart` is exactly that text for the live process with its pid; any other form gives no model (the row shows the time). Without psutil: one log line and no models.
- The tray icon: the `.icns` that the `Info.plist` of the bundle names (`CFBundleIconFile`), in the bundle that `~/.local/bin/herdr-app` points to, then `Herdr.app` in `~/Applications` and `/Applications`; the largest image of the file (Qt's `qicns` plugin is in the PySide6 wheel; verified on Linux with the real `Herdr.icns` of 0.1.16: 8 images, 32 to 1024 px).
- `scripts/start.sh`: the log folder `~/Library/Logs/bellwether` on Darwin (`uname -s`), `nohup … &` where there is no `setsid`. It needs `readlink -f` (macOS 12.3 or later).
- Fonts: `"SF Pro", "Helvetica Neue"` and `"SF Mono", "Menlo"` at the end of each list (Linux: 0 different pixels in the five layouts and the options window).
- Dependencies: `pyobjc-framework-cocoa>=10.3; sys_platform == 'darwin'`, `psutil>=6; sys_platform != 'linux'` (the Linux install has neither).
- `python -m bellwether --self-test` (`bellwether/selftest.py`): made-up agents, no lock, no log file, settings in a temporary folder; the panel for 3 s, each layout and the options window (a line "self-test: shown <step>" on stderr before each wait), then ONE JSON object: the system, the Qt platform, the shell, the flags, frame, geometry and screen of the panel, whether it is active, the layouts, the options window, the tray, the native facts (`window_facts`) and the Qt warnings.
- The runner: `.github/workflows/platforms.yml`, job `macos` (since P4: by hand with the input `system`, or a push to `cross-platform` that changes code with `[ci macos]` or `[ci both]` in its head commit message; 6-minute limit, under 4 planned): `uv sync --locked`; the selected tests (the platform, macOS, watcher, client, state, sessions, settings, start script, events, self-test tests, and 23 named plain-shell cases of the panel tests, marker `runner`, `tests/conftest.py`: about 25 s on Linux; all plain cases took 313 s on the runner of run 1, about 5 times their time on Linux, evenly — no one cost); `scripts/ci/smoke.py` (start.sh with the made-up `scripts/ci/fake-herdr`, the log lines, a SIGKILL of the widget, the event child gone 3 s later); `scripts/ci/selftest.py` (the self-test, `screencapture` at each step, the checks of the facts); the facts, logs and pictures as an artifact for 3 days.

### 4. Windows

**As built in P4** (`bellwether/platform/windows.py`; nobody has run it on a Windows machine; the runner proves what
it can). The plan below is kept; where the two differ, this is right.

- Folders: settings `%APPDATA%\bellwether`; the log `%LOCALAPPDATA%\bellwether\Logs\bellwether\bellwether.log`
  (`state_home()` is `%LOCALAPPDATA%\bellwether\Logs`: Windows has no shared log folder, so the base is in the
  folder of the program and the program adds its name, as on the other systems); the icon cache in
  `%LOCALAPPDATA%\bellwether\Cache\bellwether`; the lock files in `%LOCALAPPDATA%\bellwether` (made when not
  there). An empty or relative variable: the default under the home folder.
- Lock: `msvcrt.locking(fd, LK_NBLCK, 1)` on the first byte of the lock file, opened without truncation ("a+");
  Windows gives the lock back when the file is closed or the process ends. Chosen over a named mutex: the same handle
  and `close()` as the other systems, and the same file a person can see.
- Qt: no forced platform (the windows plugin, aware of the scale of each monitor); the shell is always `plain`.
  `prepare_app`: one log line when the plugin is not `windows`; no native call then (off screen).
- The panel: Qt 6.12 (`qwindowswindow.cpp`: `WindowCreationData::fromWindow`, `initialize`, `show_sys`) gives
  `Qt::WindowDoesNotAcceptFocus` → `WS_EX_NOACTIVATE`, `Qt::Tool` → `WS_EX_TOOLWINDOW` (no taskbar button),
  `WindowStaysOnTopHint` → `SetWindowPos(HWND_TOPMOST, … SWP_NOACTIVATE)`, and shows a Tool window with
  `SW_SHOWNOACTIVATE`. `prepare_window(…, "panel")` reads the extended style and adds only what is missing (with
  `SetWindowPos(HWND_TOPMOST)`), one log line then; the property `bellwetherAdded` and the fact `added_by_program`.
- The answer and options windows: `SetForegroundWindow` at each show. Windows allows it to a process that got the last
  input (a click in the tray menu or on the panel); else it refuses and flashes the taskbar button: the window shows,
  one log line, the property `bellwetherActivation` = "SetForegroundWindow refused".
- Raise (on the main thread of Qt, as macOS): `EnumWindows`, the first unowned window that shows or is minimized of a
  process whose program is `herdr-app.exe` (`QueryFullProcessImageNameW`); `ShowWindow(SW_RESTORE)` when minimized;
  `SetForegroundWindow`. False with one log line when there is no such window or Windows refused. Start:
  `Popen([herdr-app], DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB)` (without the
  breakaway when a job of ours does not allow it), no handles, in the home folder; it returns 1 and starts nothing
  when a window of the Herdr app is there (a second start is no raise on Windows): so a refused raise shows the
  failure message of today.
- Programs: `PATH` (with PATHEXT), then `%LOCALAPPDATA%\Programs\herdr-app\herdr-app.exe`,
  `%LOCALAPPDATA%\Programs\herdr-core\herdr-core.exe`, `~\.cargo\bin\herdr-core.exe`; one log line with the
  places (variables, never a path of the person).
- The command without the caller variables: the argv and `os.environ` without the names (no case).
- The event child: a job object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK`,
  made once; the program holds its only handle, so the system ends the child when the program ends, also after a
  kill. The child joins the job just after `Popen` returns (`AssignProcessToJobObject` by its pid): a program killed
  in that short time leaves the child, which then ends at its next write into the pipe with no reader. A launcher
  that runs the real `herdr-core` as a child of its own (a shim of a package manager, the launcher of a Python
  environment) is the process in the job; the real stream is not (silent breakaway). When the launcher ends with the
  job, the stream keeps the write end of the pipe and ends at its next write after the program is gone (the next
  heartbeat, at most 15 s) — not seen on a runner: the release installs `herdr-core.exe` itself, with no launcher. Silent breakaway: a process that the child starts (the server of herdr-core, which runs every terminal) is
  not in the job and never ends with the panel (only the direct child, as `PR_SET_PDEATHSIG` on Linux). Chosen over
  the watcher: `terminate()` on Windows is `TerminateProcess`, which runs no handler, so a watcher that the program
  ends would leave its child; the job is proven on the runner with real processes. The child has no console
  (`CREATE_NO_WINDOW`). When the job cannot be made: one log line, the child runs.
- The process host: psutil (`PsutilHost`); `start_text` is the `create_time` of psutil as a text. Claude Code writes
  `procStartFt` on Windows, not `procStart`, and its form is not known here: no session file is taken, the row shows
  the time of the terminal, never a model it cannot prove. Codex: `%USERPROFILE%\.codex` (`Path.home()`); whether
  psutil lists a lock file that a process holds open is a test of the runner.
- The tray icon: `herdr-app.svg`, which the release archive puts beside `herdr-app.exe`; else the circle.
- Fonts: `"Segoe UI"` and `"Cascadia Mono", "Consolas"` at the end of each list (Linux: 0 different pixels).
- `scripts/start.cmd` runs `scripts\start_windows.py` with the `pythonw` of the checkout; that starts
  `pythonw -m bellwether` with no console, out of the group and the job of the caller (when allowed), with no handle
  of the caller (a caller that reads the output sees its end at once), and its output in `start.log` of the log
  folder (emptied above 1 MiB). The single-instance lock is the program's.
- The mod: not changed. To start the panel on Windows, `mod/main.js` must run `cmd.exe /c <…>\start.cmd` when
  `window().platform` is `"windows"` (the API has it), and the mod folder needs a way to reach the checkout: `start.sh`
  is a link that `readlink -f` follows; `%~dp0` of a `.cmd` in a linked folder is the link, not the checkout. Not
  done: it cannot be checked here (`herdr-app check` and the app on Windows), and Linux must stay identical.
- The start path, all systems: the reads of session files open with `O_BINARY` where it exists and read with
  `os.pread` or, without it (Windows), a seek and a read; the settings and the log are UTF-8; the log rotation that
  fails (Windows: a file that an other process has open cannot be renamed) keeps the file and writes the line.
- The answer and options windows draw an opaque body with the plain shell (`Backend.opaqueDialogs`, set by
  `__main__.start_panel` from the shell): runner run 1 showed the text of a console window through them (the panel
  colour has 94 % opacity). The panel keeps the opacity the person chose; the layer shell is as before (0 different
  pixels). Every text read and write names UTF-8 (a static test for the program): Windows uses cp1252 otherwise.
  Runner run 1 (Windows Server 2025): the program works (smoke run and self-test pass; Qt alone gives the panel
  `WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE`); psutil lists a file that a process holds
  open with a lock (so a Codex row can have a model, if Codex holds its thread lock open there as on Linux). Seen, not
  fixed then: the options window is wider than a 1024 px screen.
- The options window on a narrow screen (decision of the user, 2026-11-20, after run 1): before each show
  `options.py` gives it the width of the free part of its screen (`roomWidth`); the window is never wider than that
  less 32 px (and never narrower than 320). The five cards wrap (`Flow`): 4 + 1 at a free width of 1024, 3 + 2 at 800,
  2 + 2 + 1 at 640; Size and Text are side by side only when each column has room for its label, value, reset mark
  and 180 px of slider (at 1024: up to a text size below 140 %); the two groups of colours are one below the other
  below 1076, and a group has fewer colours in a row when it is wider than the window; the colour editor has a
  narrow form (the title and "Done" in a line, the palette in rows, the field, then the opacity) below the width of
  its wide form. Tab still goes in the order on the screen. After each show the options and the answer window are
  moved inside the free part of their screen when the system put them partly outside (Windows places a new window
  at a default place); no move when inside (Wayland). At the width of today: 0 different pixels. The answer window
  (600 px) fits a 640 px screen. The self-test checks that the options window is inside the free part of its screen.
- The wait for the event pipe (review of P4, m2): no polling. A thread of each pipe (`PipeWatch`) waits in the system
  with a read of no bytes (`ReadFile` of 0 bytes waits until a byte is there and takes none; libuv waits this way,
  `uv_pipe_zero_readfile_thread_proc`), then tells `readable` through a condition; after the reader took the data it
  waits again. Should a read of no bytes come back with no byte there, the pipe is looked at again after 50 ms (never a
  loop that does not wait). The end of the pipe stays ready. A file number that names a new pipe gets a new watch.
- The pipe watch after a restart of the event child (final review, F1): the next child's pipe can get the same file
  number and the same handle value; a watch whose pipe ended is told one time and then replaced, so the new pipe is
  asked of the system again. Proven with made-up pipes (the reviewer's probe as a test, and the quit after a
  restart), and on the runners by the smoke run: it kills the made-up `herdr-core events` once by pid, and the widget
  must log `events: lost` and later `events: connected` again (a stream after another one is announced after 20 s
  of life) with exactly one new event child. Not proven: a restart where the new pipe really gets the same handle
  value (Windows chooses it).
- On Wayland (final review, F2): Qt knows the screen of a window only after the compositor shows it; the options
  window takes the room of that screen when Qt tells it (`screenChanged`), so on two monitors the first frame can
  have the layout for the width of the other monitor for a moment. Where the program places windows (F6), the place
  and the lower height below the panel are given before the show: the first frame is the final one.
- Placement (review of P4, m1 and m8): the options and the answer window open on the screen of the panel (`setScreen`
  before the first show, where the program can place windows), get the free width of the screen that shows them
  (again after the show when the system chose an other one), and after each show go inside the free part of that
  screen and clear of the panel (left of it, below it, right of it, above it: the first that fits). When no side
  fits, the options window goes below the panel and is lower (at least 240 px: its sections scroll), so its close
  control is never under the panel (a 1024 × 768 screen); else they stay.
  No move where the compositor places the windows (Wayland). The options window lays its sections out from the size
  it asks for, not the size the window system gave so far, so a new room given before a show does not leave it
  scrolled (the first open on a narrow screen started scrolled down: runner run 3).
- With monitors of different scales (Windows, macOS) Qt 6 leaves gaps between the areas of the screens in its
  coordinates. The plain shell gives `desktopPoint(item, x, y)` (Qt's `mapToGlobal`, which maps a point by the screen
  under it); a drag keeps the point of the press under that pointer, so the panel crosses to the other monitor.
  The layer shell gives null and adds the move of the pointer as before (0 different pixels, the same protocol trace).
  The real mixed-scale mapping of Qt is proven nowhere: the test (`test_a_drag_crosses_the_gap_between_monitors_of_
  different_scales`) uses a model of `QWindow::mapToGlobal` written in the test, and the runners have one screen.

The plan before P4:

- The panel: `Plain.qml`; `prepare_window` sets `WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW` and topmost through `ctypes` (`user32`), so a click does not take the focus and the panel has no taskbar entry.
- Raise: find the top-level window of the Herdr process and call `SetForegroundWindow` (with `ShowWindow(SW_RESTORE)` for a minimized window). Windows can refuse this for a background process: then the failure message of today shows.
- Start: `subprocess.Popen` with `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`.
- No `env` program: the command gets an environment without the caller variables.
- Lock: `msvcrt.locking` on the lock file.
- Event child: the watcher of macOS (plain Python), or a job object with `KILL_ON_JOB_CLOSE`. The watcher first: one mechanism for two systems.
- Paths: `%APPDATA%\bellwether` (settings), `%LOCALAPPDATA%\bellwether\{Logs,Cache}`.
- Start: `scripts/start.cmd` runs `.venv\Scripts\pythonw.exe -m bellwether` detached.
- `signal.SIGTERM` handling and the log rotation must not assume POSIX (a rotated file that is open cannot be renamed on Windows).

### 5. Other Linux desktops

With the plain shell the panel runs on X11 and on Wayland desktops with no layer shell (GNOME). Limits to state, not to hide: on GNOME Wayland a program cannot ask for "always on top", and cannot place its window; the raise of the Herdr window has only the second method of today.

Limits found in the real runs of P2 (KDE Plasma 6, KWin, two monitors; scratch runs, made-up data):

- **Plain shell on Wayland (`BELLWETHER_SHELL=plain`, KWin)**: KWin treats the panel as a normal window. It places it by its own rule (at 1120,666 of the left monitor, not at the saved place), `keepAbove` is false (stays-on-top is not honoured), it has a taskbar entry (`skipTaskbar` false: `Qt.Tool` is not honoured), and it is the active window after its start (the flag "does not accept focus" has no Wayland protocol). Qt keeps the place it asked for as the geometry of the window. Since fix round 1 a drag asks the compositor to move the window (`startSystemMove`) and the place is not saved. This shell on a Wayland compositor is a fallback only: the panel shows and works by its tray and its clicks, but the compositor decides where it is and whether it is above other windows.
- **Plain shell on X11 (`QT_QPA_PLATFORM=xcb`, XWayland under KWin)**: the window is `_NET_WM_WINDOW_TYPE_UTILITY` with `_NET_WM_STATE_ABOVE` / `STAYS_ON_TOP`, `WM_HINTS` input false, frameless (`_MOTIF_WM_HINTS`), not the active window; the place is applied (2760,660 = DP-1 at 2560,360 + 200,300), and a move to the next screen moves the window. Fix round 1, with one request per place and the X server's own coordinates (`XTranslateCoordinates`): start, a place on the same monitor and the moves between the monitors are where asked (2760,660; 3060,760; 500,400 on HDMI-A-1; back), except a place above y 390: KWin keeps an X11 utility window inside the X11 work area, and `_NET_WORKAREA` here is ONE rectangle for the whole desktop, `0, 390, 4480, 1020` (y 390 = the top of DP-1, 360, plus its 30 px panel), so on HDMI-A-1 a place at y 300 gets y 390, also after the one ask again. A limit of EWMH with monitors of different places, not of the shell; a person should check the plain shell on a real X11 session.
- **During a drag across two screens** (plain shell, off screen with two screens) Qt gives the window the screen that holds its centre by itself; at the release the panel belongs to that screen.

## Proof

1. **Linux, full proof** (tasks P1, P2): Linux on KDE identical — every test, the pixel comparisons, the protocol trace of the layer surface, the running panel.
2. **Linux, logic proof** for the code of other systems: `Plain.qml` behaviour; `platform/macos.py` and `platform/windows.py` with fake `run`, fake paths and fake `ctypes`/`pyobjc` objects; the watcher; the start scripts.
3. **GitHub Actions**, real systems (`macos-latest`, `windows-latest`): a workflow started by hand and on pushes to this branch that touch code. `uv sync`, the test suite off screen, a smoke run with a made-up `herdr-app` and `herdr-core`, a self-test mode (`python -m bellwether --self-test`) that prints the facts of the real window as JSON (class, level or styles, focus rule, frame, screen, tray item), and a picture of the runner's own screen with made-up data as an artifact. Budget: the repository is private, so macOS minutes count 10 times and Windows minutes 2 times; one run under 10 minutes.
4. **Not provable from here**, to say in the README until a person checks it: the feel of the drag; a full-screen app; a real second monitor; the jump with the real Herdr app; the mod start; the sharpness on a Retina or scaled screen; the answer window with a real agent.

## Open questions (by research or on a runner, not by guess)

1. The name, the bundle identifier and the install places of the Herdr app, `herdr-app` and `herdr-core` on macOS and on Windows.
2. Does `herdr-app do agent.focus` alone bring the app to the front on those systems?
3. Does the mod's `exec` run the start script there, and with which `PATH`?
4. The form of `procStart` in a Claude Code session file on macOS and Windows.

Answers of P3 (2026-11-20), macOS:

1. **Found.** The release manifest `https://releases.herdr.dev/app/latest.json` (0.1.16) has `macos-aarch64` only (Intel Macs build from source). Its archive holds `Herdr.app`; `Contents/Info.plist`: `CFBundleIdentifier` `dev.herdr.app`, `CFBundleName` `Herdr`, `CFBundleExecutable` `Herdr`, `CFBundleIconFile` `Herdr` (`Resources/Herdr.icns`). The installer `https://releases.herdr.dev/app/install.sh` puts it in `~/Applications/Herdr.app` (it also knows `/Applications/Herdr.app`) and links `~/.local/bin/herdr-app` to `Herdr.app/Contents/MacOS/Herdr`; the app repairs that link at each launch (`~/.config/herdr-app/AGENTS.md`). herdr-core: `https://releases.herdr.dev/core/install.sh` puts `herdr-core` (and `hc`) in `~/.local/bin` (on macOS from a bundle `Herdr Core.app`, identifier `dev.herdr.core`); the app looks for it in PATH, the login shell's PATH, `~/.local/bin`, Homebrew, mise, Nix, cargo. Windows: P4.
2. **Not found.** Nothing in the documentation; it needs the real app on a Mac. The raise does not depend on it (activation and a reopen after the focus).
3. **Partly found.** `exec` runs a program "in the user's real environment" (AGENTS.md); a Finder launch of the app loads the login shell's PATH, with the usual install folders as a fallback; an unsigned bundle gets `LSEnvironment` PATH `~/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin` (install.sh). `start.sh` has a `#!/bin/sh` line and the x bit, so `exec` can run it. Not seen on a Mac.
4. **Found in the program, not seen on a Mac.** The code of Claude Code (the installed Linux build, read around the word `procStart`): on Linux field 22 of `/proc/<pid>/stat`; on the other branch the trimmed output of `LC_ALL=C TZ=UTC ps -o lstart= -p <pid>` (the same text in two helpers); on Windows a different key, `procStartFt`. The macOS host gives that text (`lstart()`); the runner test `test_on_a_mac_the_start_of_a_process_is_what_ps_lstart_prints` compares it with `ps` itself.

Answers of P4 (2026-11-20), Windows:

1. **Found.** The manifest `https://releases.herdr.dev/app/latest.json` (0.1.16) has `windows-x86_64`; the archive holds
   `herdr-app/herdr-app.exe` and `herdr-app.svg`. `app/install.ps1` puts the folder in
   `%LOCALAPPDATA%\Programs\herdr-app` (user PATH, Start menu `Herdr.lnk`); `core/install.ps1` puts `herdr-core.exe`
   (+ `conpty\`, `hc.exe`) in `%LOCALAPPDATA%\Programs\herdr-core` (user PATH). The exe names that folder and
   `.cargo/bin`, and `~/.config/herdr-app` as its home on every system. The window class of GPUI is `Zed::Window`.
2. **Not found** (needs the app on Windows).
3. **Partly found.** `exec` exists on Windows; `window().platform` tells the system to a mod. The mod is not changed
   (see section 4).
4. **Not found.** The installed build is the Linux build: the Windows branch of Claude Code is not in it; it writes
   `procStartFt` there and compares two number forms around 3e17. Windows: no model, the time.

Not verified by a person (P3): everything of section 4 of "Proof", and on macOS: the keyboard in the options and answer windows (the activation of the app after a click in the tray menu or on the panel); that a click on the panel leaves the keyboard in the other app (the style mask after creation, the private call); that `activateWithOptions:` from a background thread of the client is accepted (cooperative activation of macOS 14); that the panel shows over an app in full screen and on every Space; the menu bar item; the reopen of a minimized Herdr window; the watcher on a Mac before the runner run.

## Tasks (each: one implementer, a task review, fix rounds)

- **P1 — the platform package, pure move.** `platform/{__init__,linux}.py`; paths, lock, raise, start, clean environment, child spawn, process host, app icon, executables behind the interface; a static test that no module outside the package tests `sys.platform` or imports `fcntl`, `ctypes`, or names `prctl`, `/proc`, `busctl`, `systemd-run`, `XDG_`, `.desktop` (`tests/test_platform.py`, no exception); the Qt set-up of `__main__.py` behind `prepare_environment`, `prepare_app`, `prepare_engine`. Linux identical.
- **P2 — the shell split.** `PanelShell.qml`, `shells/Layer.qml`, `shells/Plain.qml`; the shell rule; the behaviour tests of the panel parametrized over both shells; the layer shell identical (pixels, protocol trace); a short real run of the plain shell on Linux (XWayland).
- **P3 — macOS.** `platform/macos.py`, the watcher, the start script, the font lists, `psutil`, `pyobjc`; the self-test mode; the workflow on a macOS runner; fix what the runner shows.
- **P4 — Windows.** `platform/windows.py`, `scripts/start.cmd`, the lock, the log rotation; the workflow on a Windows runner; fix what the runner shows. Also the fix round 1 of the review of P3 (the second activation of macOS only when nothing changed, the AppKit raise on the main thread, the watcher loop, the CI checks).
- **P5 — documents.** README (the support table, the install for each system, the "not verified by a person" list), the reference page, the notes.

## Error handling

- A missing optional part (`pyobjc`, `psutil`, the app bundle, the commands) gives one clear log line and the nearest working behaviour, never a crash at start.
- A raise that the system refuses is reported as today: the row shows the failure message for 3 seconds.

After the last run of the port (2026-11-21) the push rule with the commit-message markers was removed: the workflow starts by hand only (`workflow_dispatch`, default system Windows). `tests/test_workflow.py` holds it to that.
