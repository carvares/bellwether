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

Not built yet, for later tasks: `prepare_window(window, role)` (P3/P4: native set-up after a window exists; `role`: `"panel"`, `"answer"`, `"options"`).

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
- One hook: `rehome()` (shared) finds the real screen and calls `showOn(target, x, y, real)` of the shell (`real`: the QScreen when the window must change its screen, else null); the shell calls `setPlace()` (shared: screen name, place, clamp) and does its window work. Layer: hide, `setPlace`, `screen`, `x`/`y` for the output, show (the code of before, in the same order); the margins are bound to the place, `requestUpdate()` on a margin change, anchors top|left, overlay layer, keyboard none, exclusion −1. Plain: `x`/`y` bound to the place in the whole desktop, `screen` set when it changes.
- The rule (`platform/linux.py`, `shell()`): `BELLWETHER_SHELL=layer|plain` first (another non-empty value: one log line, ignored); then `plain` when the Qt platform is not `wayland*`; `plain` when `org.kde.layershell` does not load in the engine; `plain` when the compositor's registry has no `zwlr_layer_shell_v1` (read by `wayland_globals()`: `ctypes` on libwayland-client, a connection of its own, one round trip); else `layer`. When the registry cannot be read (no library, no compositor, `WAYLAND_SOCKET`), the module and the platform decide (the layer shell, as before). The log gets `shell: layer` or `shell: plain` at the start (`__main__.load_panel`).
- `QT_QPA_PLATFORM` defaults to `wayland;xcb`: the same plugin on a Wayland desktop, and Qt falls back to X11 when no Wayland compositor answers (the plain shell then; Qt writes two lines to stderr).
- A change of behaviour that the rule brings: on KDE with a Qt minor version that does not match the system module, the panel was not shown (an error line); now it shows in the plain shell with a warning line.

### 3. macOS

As sections 3 to 7 of the 2026-11-19 design: an accessory app (no Dock icon); the panel is an `NSPanel` at status level, on all Spaces, non-activating (through `pyobjc-framework-Cocoa`, a dependency only for `sys_platform == "darwin"`; without it a plain always-on-top window and one log line); the answer and options windows activate the app when they open; raise = activate the Herdr app (`open -a` as the second method); start = `open -a`; the watcher for the event child; the paths of the table.

New against that design: the process host (`psutil`, for `sys_platform != "linux"`). The check that a Claude Code session file is of the live process uses the start of the process; the form of `procStart` in that file on macOS is **not known** — the reader must compare only what it can prove and else give no model (the row then shows the time).

### 4. Windows

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

- **Plain shell on Wayland (`BELLWETHER_SHELL=plain`, KWin)**: KWin treats the panel as a normal window. It places it by its own rule (at 1120,666 of the left monitor, not at the saved place), `keepAbove` is false (stays-on-top is not honoured), it has a taskbar entry (`skipTaskbar` false: `Qt.Tool` is not honoured), and it is the active window after its start (the flag "does not accept focus" has no Wayland protocol). Qt keeps the place it asked for as the geometry of the window, so the drag model and the window part: a drag moves the place of the panel, not the window. This shell on a Wayland compositor is a fallback only: the panel shows and works by its tray and its clicks, but the compositor decides where it is and whether it is above other windows.
- **Plain shell on X11 (`QT_QPA_PLATFORM=xcb`, XWayland under KWin)**: the window is `_NET_WM_WINDOW_TYPE_UTILITY` with `_NET_WM_STATE_ABOVE` / `STAYS_ON_TOP`, `WM_HINTS` input false, frameless (`_MOTIF_WM_HINTS`), not the active window; the place is applied (2760,660 = DP-1 at 2560,360 + 200,300), and a move to the next screen moves the window. One open fault: on the left monitor (HDMI-A-1 at 0,0) the window was sometimes 90 px lower than the place asked (y 390 for 300), and a later move put it at the right place again; the cause was not found (Qt's own geometry reports it, so it comes from the window manager or XWayland). A person should check the plain shell on a real X11 session.
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

## Tasks (each: one implementer, a task review, fix rounds)

- **P1 — the platform package, pure move.** `platform/{__init__,linux}.py`; paths, lock, raise, start, clean environment, child spawn, process host, app icon, executables behind the interface; a static test that no module outside the package tests `sys.platform` or imports `fcntl`, `ctypes`, or names `prctl`, `/proc`, `busctl`, `systemd-run`, `XDG_`, `.desktop` (`tests/test_platform.py`, no exception); the Qt set-up of `__main__.py` behind `prepare_environment`, `prepare_app`, `prepare_engine`. Linux identical.
- **P2 — the shell split.** `PanelShell.qml`, `shells/Layer.qml`, `shells/Plain.qml`; the shell rule; the behaviour tests of the panel parametrized over both shells; the layer shell identical (pixels, protocol trace); a short real run of the plain shell on Linux (XWayland).
- **P3 — macOS.** `platform/macos.py`, the watcher, the start script, the font lists, `psutil`, `pyobjc`; the self-test mode; the workflow on a macOS runner; fix what the runner shows.
- **P4 — Windows.** `platform/windows.py`, `scripts/start.cmd`, the lock, the log rotation; the workflow on a Windows runner; fix what the runner shows.
- **P5 — documents.** README (the support table, the install for each system, the "not verified by a person" list), the reference page, the notes.

## Error handling

- A missing optional part (`pyobjc`, `psutil`, the app bundle, the commands) gives one clear log line and the nearest working behaviour, never a crash at start.
- A raise that the system refuses is reported as today: the row shows the failure message for 3 seconds.
