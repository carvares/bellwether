# Bellwether port to macOS (and the ground for Windows) — design

Date: 2026-11-19. Branch: `port-macos` (from `build-widget` at `c259475`). Base product spec: `2026-11-18-bellwether-design.md`.

## Request and decisions of the user

- "does this mods works on every OS? I mean Linux, Windows and macOS?" then "let's plan a port for windows and macOS, starting with macOS."
- The user has **no Mac**. Decision: (1) first split the system-specific parts from the rest, verified on Linux; (2) then the macOS code, proven only as far as a GitHub Actions macOS runner allows, and marked "not verified by a person".
- Install on macOS: **from source with uv**, as on Linux. No `.app` bundle.
- Scope: **full parity** with Linux.
- CI: a macOS runner is accepted **within the free minutes** (private repository: macOS minutes count 10 times; 2,000 free minutes = 200 macOS minutes each month).
- The port is made **on its own branch**.

## Goal

Bellwether runs on macOS with the same functions as on KDE: a floating panel above all windows that never takes the keyboard focus, five layouts, the options window, an icon in the menu bar in the status colour, a click that shows the agent in the Herdr app (also when the app is closed or minimized), a drag across monitors, the custom look, and the start with the Herdr app through the mod.

Linux must stay exactly as it is: the same pixels, the same protocol behaviour, all 729 tests.

## Facts

- The Herdr desktop app runs on macOS and Windows: its own documentation (`~/.config/herdr-app/AGENTS.md`, version 0.1.16) names both ("Cmd-click on macOS", "AltGr on Windows", "macOS keeps its window…"). Not seen on a Mac by us.
- Portable already: the data source (`herdr-app ls`, `herdr-core events --json`, `herdr-app do agent.focus`), the program icons (SVG files in the Herdr app home, `icons.py`), the settings file format, the QML skins, themes, controls and the options window, the tray through `QSystemTrayIcon`, the file lock (`fcntl.flock` exists on macOS).
- PySide6 6.12 has macOS wheels. The Qt platform plugin there is `cocoa`.

## What is tied to Linux today (the seams)

| # | Where | Today | On macOS |
|---|---|---|---|
| 1 | `ui/Main.qml:8,57-65`, `__main__.py:26,108-112` | A wlr-layer-shell surface (`org.kde.layershell`), placed with margins | A frameless plain window, always on top, on all Spaces, that never becomes the key window |
| 2 | `window.py`, `client.py:57,122` | Raise of the Herdr window with the KWin window runner over `busctl` | Activate the Herdr app (`NSRunningApplication` or `open -a`) |
| 3 | `client.py` (`systemd-run --user --slice=app.slice herdr-app`) | Start of a closed Herdr app outside our process tree | `open -a <Herdr app>` (launch services start it outside our tree) |
| 4 | `events.py:34-48` | `prctl(PR_SET_PDEATHSIG)` so the event child ends with us | No such call on macOS: a small watcher (see below) |
| 5 | `paths.py` | XDG folders | `~/Library/Application Support/bellwether`, `~/Library/Logs/bellwether`, `~/Library/Caches/bellwether` |
| 6 | `appicon.py:30-31` | The Herdr app icon from the `.desktop` file and the icon theme | The icon file of the app bundle (`.icns`) |
| 7 | `scripts/start.sh` | `setsid -f`, XDG state folder | No `setsid` on macOS: `nohup … &`, and the Logs folder |
| 8 | `skins/*Theme.qml` font lists | Linux families first | Add macOS families at the end of each list (Menlo/SF Mono; Helvetica Neue/SF) — no change on Linux, where the earlier names win |
| 9 | `tray.py` | A tray icon with a menu | The same class gives a menu bar item; check size and sharpness (22 pt, 2x) |

Everything else has no system call.

## Design

### 1. A platform package

`bellwether/platform/` with one module for each system and one small interface. `platform/__init__.py` picks the module from `sys.platform` one time. The rest of the program calls only the interface. No `if sys.platform` outside this package.

The interface (functions, all with injected `run` or paths where tests need it):

- `paths()` → config, state (log), cache and runtime folders.
- `shell_source()` → the QML file of the window shell (`ui/shells/Layer.qml` on Linux, `ui/shells/Plain.qml` on macOS), and `prepare_engine(engine)` (Linux: the import path of the layer-shell module and its clear error).
- `prepare_window(window)` → native set-up after the window exists (Linux: nothing; macOS: see 3).
- `prepare_app(app)` → process set-up before the first window (macOS: accessory activation policy, so no Dock icon and no menu bar of its own).
- `raise_app(run)` → bring the Herdr window to the front; True when it is visible and not minimized as far as the system can tell.
- `start_app(run)` → start a closed Herdr app outside our process tree.
- `child_guard()` → what `events.py` gives to `subprocess.Popen` so the child ends with us.
- `app_icon()` → the Herdr app icon file.
- `lock(path)` → the single-instance lock.

`platform/linux.py` gets the code that exists today, moved, not rewritten. Step 1 is a pure move.

### 2. Two window shells, one panel

`Main.qml` today mixes three things: (a) the layer-shell properties, (b) the place model (x, y, screen, clamp, default corner, drag, move to next screen, hot-plug), (c) the Loader, pointer handler and hit test. Split:

- `ui/PanelShell.qml` — (b) and (c): everything that does not name a window system. It knows a place (`posX`, `posY`, the screen) and asks its shell to apply it.
- `ui/shells/Layer.qml` — (a): the layer surface that maps the place to margins, `requestUpdate` on a margin change, hide / `setScreen` / show to change the output. Linux.
- `ui/shells/Plain.qml` — a frameless `Window` with the flags `Tool | FramelessWindowHint | WindowStaysOnTopHint | WindowDoesNotAcceptFocus | NoDropShadowWindowHint`, transparent background, that maps the place to `x`, `y` and `screen`. macOS, and later Windows. A drag sets `x`, `y` directly; the cross-monitor move needs no special case because the desktop is one coordinate space.

`Plain.qml` has no macOS call in it. So its place logic, clicks, drag, scale and layout switch are tested **on Linux** (off screen, and with a short real run under XWayland) with the same parametrized tests that run on the layer shell today. This is the largest part of the port that can be proven without a Mac.

### 3. The macOS window (the part that cannot be seen from here)

A Qt `Tool` window on macOS is an `NSPanel`. After it exists, `platform/macos.py` sets, through `pyobjc-framework-Cocoa` (a dependency only for `sys_platform == "darwin"`):

- level: `NSStatusWindowLevel` (above normal and floating windows);
- collection behaviour: `canJoinAllSpaces | fullScreenAuxiliary | stationary | ignoresCycle` (on every Space, also over a full-screen app, not in the window cycle or Mission Control);
- style mask with `nonactivatingPanel`, `becomesKeyOnlyIfNeeded`, and `hidesOnDeactivate = False` (a click on the panel does not take the focus from the app the user works in, and the panel does not vanish when Bellwether is not the active app);
- no shadow; movable only by our own drag.

The options window is a normal window. When it opens, the app must become active for the keyboard to work (`NSApp.activate`); an accessory app can do this.

If `pyobjc` cannot be loaded, the panel still runs as a plain always-on-top window (one log line), with the weaker behaviour: current Space only.

### 4. Jump to the agent

Unchanged: `herdr-app do agent.focus {"terminal": addr}`, one jump at a time, the 8 second deadline. Changed: the raise and the start.

- Raise: find the running Herdr app by its bundle identifier and activate it (`NSRunningApplication.activateWithOptions`); fallback `open -a`. `open -a` on a running app sends the "reopen" event, which shows a minimized window in most apps. It does not need the Accessibility permission. We do not use AppleScript window control or the Accessibility interface (both ask the user for a permission).
- Start: `open -a <app>`; then the same wait as on Linux until `herdr-app ls` answers.

### 5. The event child

macOS has no parent-death signal. The child is `herdr-core`, not our code. Design: start it through a tiny watcher (`python -m bellwether.platform.guard <parent pid> herdr-core events --json`) that starts the real child, copies nothing (the child inherits stdout), and polls the parent pid once a second; when the parent is gone it ends the child and itself. Linux keeps `prctl` (no change). The watcher is plain Python, so its logic is tested on Linux.

### 6. Paths, start script, mod

- Paths as in the table. No old folders to move on macOS.
- `scripts/start.sh` becomes correct on both systems with one branch: `setsid -f` where it exists, else `nohup … &`; the log folder from the platform rule (`$HOME/Library/Logs/bellwether` on Darwin). It stays POSIX `sh`.
- The mod (`mod/main.js`) needs no change if `exec` of a shell script works in the Herdr app on macOS. Open question 3.
- `herdr-app` and `herdr-core` must be found. A program started by the Herdr app on macOS may get a short `PATH`. The client looks in `PATH`, then in the known places (inside the app bundle, `/usr/local/bin`, `/opt/homebrew/bin`, `~/.local/bin`), and logs once where it found them.

### 7. Menu bar icon

`QSystemTrayIcon` gives a menu bar item with the same menu. The icon keeps the status colour (the user's request for the tray), so it is not a monochrome "template" image. Rendered at 22 pt with a 2x pixmap.

## Proof without a Mac

1. **Linux, full proof:** the platform move and the shell split leave Linux identical (729 tests, the pixel comparisons, a protocol trace of the layer surface, the running widget).
2. **Linux, logic proof for macOS code:** `Plain.qml` behaviour; `platform/macos.py` with fake `run` and fake paths (commands built, fallbacks, parsing); the watcher; the start script under a fake `uname`.
3. **GitHub Actions `macos-latest`, real macOS:** a workflow started by hand (`workflow_dispatch`) and on pushes to `port-macos` that touch code:
   - `uv sync`, the full test suite off screen, then the QML tests once more with the `cocoa` plugin;
   - a smoke run: Bellwether started with a made-up `herdr-app` and `herdr-core` on `PATH` (shell scripts that print made-up agents), for some seconds;
   - a self-test mode (`python -m bellwether --self-test`) that prints the facts of the real window as JSON: window class (`NSPanel`), level, collection behaviour, style mask, `canBecomeKeyWindow`, frame, screen, activation policy, the tray item's existence; the job asserts them;
   - a picture of the runner's own screen (`screencapture`) saved as an artifact, with the panel in each layout and the options window. A runner has a real window server. It is the runner's desktop, with made-up data: no private content.
   - Budget: one run under 10 minutes; not on every push to other branches.
4. **Not provable from here, stated in the README until a person checks it:** the feel of the drag; the panel over a real full-screen app and on a second Space; a real second monitor; the click with the real Herdr app (raise, minimized, closed); the mod start inside the real Herdr app; the Retina sharpness; macOS permission prompts.

## Open questions (answer by research or on the runner, not by guess)

1. The name and bundle identifier of the Herdr app on macOS, and where `herdr-app` / `herdr-core` are installed (the Herdr site and release files will say).
2. Does `herdr-app do agent.focus` alone bring the app to the front on macOS? If yes, the raise is only the fallback.
3. Does the mod's `exec` run a `sh` script on macOS, and with which `PATH`?
4. Can the Herdr app itself be installed on the runner for a real jump test (a download in CI)? If its licence and size allow, add it to the smoke run.

## Out of scope

- Windows (next; it reuses the platform package, `Plain.qml` and the watcher idea with a job object).
- A `.app` bundle, code signing, an installer.
- GNOME and X11 on Linux (the plain shell makes them possible later).
- Any change of the look or the functions.

## Tasks (each: implementer, task review, fix rounds; on `port-macos`)

- **P1 — the platform package, pure move.** `platform/{__init__,linux}.py`; `paths`, `window`, the start command, the child guard, the lock, the app icon move behind the interface. Linux identical (tests, pixels, running widget).
- **P2 — the shell split.** `PanelShell.qml`, `shells/Layer.qml`, `shells/Plain.qml`; the behaviour tests parametrized over both shells; Linux layer shell identical (pixels, protocol trace); a short real run of the plain shell on Linux.
- **P3 — macOS logic.** `platform/macos.py` (paths, raise, start, finding the commands, app icon), the watcher, the start script, the font lists, the answers to open questions 1–3 from research; all with fakes, on Linux.
- **P4 — the macOS window and the proof on the runner.** `prepare_app`, `prepare_window` with pyobjc, the self-test mode, the workflow, the screen pictures; fix what the runner shows, within the minute budget.
- **P5 — documents.** README (macOS install and limits, the "not verified by a person" list), the spec changes, the Obsidian notes.

## Error handling

- A missing optional part (pyobjc, the app bundle, the commands) gives one clear log line and the nearest working behaviour, never a crash at start.
- A raise that the system refuses is reported as today: the row shows the failure message for 3 seconds.
