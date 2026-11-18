# herdr-float: design

Date: 2026-11-18
Status: built. The data source changed on 2026-11-18 (see the next section).

## Change on 2026-11-18: data source is the Herdr desktop app

Root cause of the bug "all zeros with running agents":
this machine has two Herdr products, and the widget read the wrong one.
The widget read the `herdr` 0.9 terminal program (socket `~/.config/herdr/herdr.sock`), which had 0 agents.
The agents of the user are in the Herdr desktop app (`herdr-app`, the window) and `herdr-core` (it runs the terminals).

- **Source.** One time each second the widget runs `herdr-app ls` (argument list, no shell, 2 s timeout) and reads the JSON: spaces, tabs, terminals. Measured: 3 to 14 ms for each call, less than 1 % of one processor core.
- **Agent row.** A terminal with a status is an agent. A terminal with status `null` is a plain shell and is not a row. The key of a row is the terminal address (for example `t11`). The name is the terminal name, else the program (`app`), else the address. The place text is the space name, and the tab name when the space has more than one tab.
- **Sub-agents.** The entries in `sub_agents` are agents too (terminals that an agent started). They are rows. As in the agent list of the app, a sub-agent that reports `done` counts as `idle`. No real sub-agent was available on 2026-11-18, so the widget accepts two shapes for these entries: the fields of a terminal in `herdr-app ls` (`terminal`), and the fields of `herdr-core ls --json` (`address`, `state`; only `live` entries count). A terminal that is listed in a tab and also below a parent is one row with the sub-agent status. This is not verified with real data.
- **States.** Four: `blocked`, `done`, `working`, `idle`. `done` means that the agent finished while the person did not look; the app changes it to `idle` after the person looks. There is no `unknown` state. A program can report the raw word `error`; the widget counts it as `blocked`, as the agent list of the app does. A different word that is not known: the row is skipped and the word is logged one time.
- **Fallback.** When `herdr-app ls` gives no valid answer (window closed, app not installed, timeout), the widget runs `herdr-core ls --json`. A row is a terminal with `state` `live` and a status. Name: the `agent` field. No place text. A row with a `parent` is a sub-agent (`done` counts as `idle`). The status is the word of the program itself, so `done` shows also when the person saw the agent before. If herdr-core does not answer either, the pill shows "offline".
- **Jump.** `herdr-app do agent.focus {"terminal": "<address>"}`. With herdr-core as the source there is no window: the row shows "Herdr app is not open" and no command runs.
- **Start.** `scripts/start.sh` starts the widget. The folder `mod/` is a Herdr app mod that runs this script when the app starts; the user installs it (see the README). The `plugin/` folder for the `herdr` 0.9 program is removed.

The sections below are the first design. Lines that the change made false are corrected.
Sections that describe the `herdr` 0.9 program are kept as history and say so.

## Goal

A small window that floats above all other applications.
It shows how many Herdr agents are in each state.
It lets the user jump to an agent.

## Decisions

| Topic | Decision |
|---|---|
| Form | Standalone program. A small Herdr app mod can start it when the app starts. |
| Run time | From the Herdr start until desktop logout. The widget stays on the screen after the Herdr window closes. No start at desktop login. |
| Scope | The Herdr desktop app that uses the default folder `~/.config/herdr-app`, and the default herdr-core. |
| States | Four counters, one for each state of the app: `blocked`, `done`, `working`, `idle`. No state is merged into another. |
| Attention | `blocked` and `done` use the attention colour. |
| Interaction | Compact counters. A click expands an agent list. A click on an agent shows it in the Herdr app. |
| Tray | A system tray icon. Left click hides or shows the widget. The menu has "Hide widget" / "Show widget" and "Quit". |
| Stack | Python, Qt6 (PySide6), KDE layer-shell library. PySide6 comes from PyPI (`pyside6-essentials`), pinned to the minor version of the system Qt (6.12), because `sudo` was not available to install the system package. The layer-shell library comes from the system package `layer-shell-qt`. A system Qt upgrade to a new minor version can break the load of the layer-shell QML module until the pin moves too. |
| Platform | Linux, KDE Plasma on Wayland. No other platform. |

## Why not a Herdr plugin only

This section is about the `herdr` 0.9 terminal program. It is history.
The same reason applies to the desktop app: a mod draws inside the app window only.

Herdr plugin panes have these placements: `overlay`, `popup`, `split`, `tab`, `zoomed`.
All of them are inside the Herdr terminal.
None is an operating-system window, so a plugin cannot float above other applications.
A plugin can run a command at startup. The plugin uses that to start the widget.
The user decided on 2026-11-18 that a start with Herdr is sufficient. There is no systemd service.

## Facts from the Herdr API schema

**This section applies to the `herdr` 0.9 terminal product. The widget does not use it any more.**

Source: `herdr api schema`, Herdr 0.9.5, protocol 22.

- Socket path: `~/.config/herdr/herdr.sock`.
- `agent.list` returns `AgentInfo` rows. Required fields: `terminal_id`, `agent_status`, `workspace_id`, `tab_id`, `pane_id`, `focused`, `revision`. Optional fields include `name`, `display_agent`, `title`, `cwd`.
- `AgentStatus` values: `idle`, `working`, `blocked`, `done`, `unknown`.
- `events.subscribe` takes a list of subscriptions. Event kinds include `pane_agent_detected`, `pane_agent_status_changed`, `pane_closed`, `pane_exited`.
- `pane.agent_status_changed` carries `pane_id`, `workspace_id`, `agent_status`, and optional `agent`, `display_agent`, `title`.
- `agent.focus` focuses the pane of an agent. It also marks a `done` agent as viewed.
- A read (`agent.list`) does not change the viewed state.

## Verified on 2026-11-18

The spike files named in this section were removed after the tests. They are in the git history (commits 6e42551, 937bf36, 9c3175c).

Tested against Herdr 0.9.5 (protocol 22) with `spike/wire.py` and a structure-only probe.

1. The socket wire format. (This item is about the `herdr` 0.9 terminal product. The widget does not use it any more.)
   - Request: one JSON object and `\n`: `{"id", "method", "params"}`.
   - Reply: one line of JSON that ends with `\n`. No bytes follow the `\n`. Envelope: `{"id", "result"}`. For `agent.list`, `result` is `{"type": "agent_list", "agents": [...]}`.
   - The server closes the connection after the reply. A second read gets 0 bytes at once. A second request on the same connection fails with a broken pipe. So use one connection for each request.
   - `agent.list` does not return panes that have no agent. In the test, `pane.list` gave 17 panes, all with `agent_status` `unknown` and no `agent` field. `agent.list` gave 0 rows.
   - Agent rows: no live row was available in the test. The bundled schema (`herdr api schema --json`, `AgentInfo`) gives `agent`, `display_agent` and `name` as string or null. They are not in the required list. In `pane.list` rows the server leaves out `agent` and `display_agent` when there is no agent, and does not send `null`. So read these three fields as optional: missing or `null` means "no value".

2. The layer-shell overlay on this KDE desktop with PySide6.
   Tested with `spike/overlay.py` and `spike/Overlay.qml`: `pyside6-essentials` 6.12.0 from PyPI, system `qt6-base` 6.12.0, system `layer-shell-qt` 6.8.2, KWin on Wayland.
   The check was a Wayland protocol trace (`WAYLAND_DEBUG=1`) only. The visual result (position on the screen, stays above full-screen windows, no focus steal) still needs a look by the user.
   - Result 1, overlay surface: yes. The QML loads. The client sends `zwlr_layer_shell_v1.get_layer_surface(..., 3, "herdr-float-spike")` (3 = overlay) and the compositor replies with `zwlr_layer_surface_v1.configure(serial, 220, 48)`. The trace has no `xdg_surface` and no `xdg_toplevel`.
   - Result 2, QML lines: the lines below work. The test used them as written, with one difference: the scope in the test was `"herdr-float-spike"`. The trace shows `set_anchor(5)` (top + left), `set_exclusive_zone(-1)`, `set_margin(120, 0, 0, 200)` (order: top, right, bottom, left) and `set_keyboard_interactivity(0)`.
     ```qml
     import org.kde.layershell as LayerShell

     Window {
         id: root
         flags: Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
         property int posX: 200
         property int posY: 120
         LayerShell.Window.scope: "herdr-float"
         LayerShell.Window.layer: LayerShell.Window.LayerOverlay
         LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft
         LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
         LayerShell.Window.exclusionZone: -1
         LayerShell.Window.margins.left: root.posX
         LayerShell.Window.margins.top: root.posY
         LayerShell.Window.onMarginsChanged: root.requestUpdate()
     }
     ```
   - Result 2, margins: the grouped form `LayerShell.Window.margins.left: <binding>` works. A change of the bound property at run time (`root.posX += 10` from a `Timer`) sends a new `set_margin` on the same surface. A direct write from JavaScript also sends it: `root.LayerShell.Window.margins.left += 40`. Do not use `Qt.margins(...)`: it does not exist in QML and gives a `TypeError`.
   - Result 2, margin commit: a frame commit is needed after a margin change. In wlr-layer-shell the compositor applies `set_margin` only on the next `wl_surface.commit`. Qt sends no commit for a margin change alone: with 5 changes 200 ms apart and nothing else on the screen changing, no commit came after the first 4 changes (800 ms). So without help the surface does not move until some other repaint occurs. Use this line in the window: `LayerShell.Window.onMarginsChanged: root.requestUpdate()`. With it, a `wl_surface.frame`, `attach` and `commit` followed each of the 5 `set_margin` requests in less than 1 ms. A call to `root.requestUpdate()` or `root.update()` in the code that changes the margin gives the same result. The signal handler is the preferred form because it covers each margin change.
   - Result 3, `QT_WAYLAND_SHELL_INTEGRATION`: not necessary, and do not set it. The attached property alone gives the layer surface; in that run the client binds `xdg_wm_base` as usual and binds `zwlr_layer_shell_v1` only when the window shows. With the variable set to `layer-shell` (and the system plugin `liblayer-shell.so` on the plugin path), the client binds `zwlr_layer_shell_v1` at start-up and never binds `xdg_wm_base`. So the variable loads a second system binary into the Qt of the wheel and turns off xdg-shell for all windows of the program. Without the variable, of the Qt libraries in the process, only `libLayerShellQtQml.so` and `/usr/lib/libLayerShellQtInterface.so.6` come from the system; the system plugin is not loaded.
   - Result 4, hide and show: `visible = false` sends `zwlr_layer_surface_v1.destroy()`. `visible = true` sends a new `get_layer_surface` on the overlay layer with the same scope, anchors and the last margins (`set_margin(120, 0, 0, 240)`), and a new `configure` comes back.
   - Result 5, `QApplication`: the trace is the same as with `QGuiApplication`. `QSystemTrayIcon.isSystemTrayAvailable()` returns `True`. `pyside6-essentials` has QtWidgets, QtQml, QtQuick and the Wayland platform plugin, so the PyPI `pyside6` meta-package is not necessary.
   - Result 6, start-up recipe. The bundled Qt does not find `org.kde.layershell` by default (`module "org.kde.layershell" is not installed`). Give it an import directory that holds only a symlink to the system module. Do not add `/usr/lib/qt6/qml` as an import path: that mixes other system Qt modules into the bundled Qt.
     ```python
     os.environ.setdefault("QT_QPA_PLATFORM", "wayland")  # before the application object

     bridge = tempfile.TemporaryDirectory(prefix="herdr-float-qml-")  # keep a reference until exit
     (Path(bridge.name) / "org" / "kde").mkdir(parents=True)
     (Path(bridge.name) / "org" / "kde" / "layershell").symlink_to("/usr/lib/qt6/qml/org/kde/layershell")

     app = QApplication(sys.argv)
     engine = QQmlApplicationEngine()
     engine.addImportPath(bridge.name)  # before engine.load()
     engine.load(...)
     ```
     No other environment variable, library path or plugin path is necessary. In a test run with `QT_QPA_PLATFORM` not set at all, the platform was also `wayland` and the layer surface was made. Note that `setdefault` keeps an inherited value: with `QT_QPA_PLATFORM=xcb` in the environment the program uses X11 and gets no layer surface. If that must not occur, assign the variable and do not use `setdefault`.
   - Limit: the system libraries bind to the Qt libraries of the wheel at load time. They ask for the symbol versions `Qt_6`, `Qt_6.12` and `Qt_6_PRIVATE_API` (private Qt Wayland API). So the wheel must have the same Qt minor version as the system Qt. The pin is `pyside6-essentials==6.12.*` in `pyproject.toml`.

## Not verified

3. A method to raise the Herdr app window after a jump. This test needs the user and a live agent. If the test fails, the known limit stays.

## Parts

Each part has one job.

| Part | Job | Depends on |
|---|---|---|
| `herdr_float/state.py` | Convert the rows of `herdr-app ls` or `herdr-core ls --json` to a sorted agent list. Return the four counts. No reads of Herdr. | nothing |
| `herdr_float/client.py` | Run `herdr-app` (or `herdr-core` as the fallback). Return the agents or an error. Run the jump command. | `state.py`, the two programs |
| `herdr_float/settings.py` | Save and load the window position. | nothing |
| `herdr_float/backend.py` | Qt object. Reads a snapshot each second. Gives counters and agents to the interface. | `client.py`, `state.py`, `settings.py` |
| `herdr_float/ui/Main.qml` | Layer-shell overlay window, compact pill, expanded list, drag. | `backend.py` |
| `herdr_float/tray.py` | System tray icon and menu. The one source of the state colours. | Qt, `backend.py` |
| `herdr_float/__main__.py` | Connect the parts. Start the Qt application. | all parts |
| `scripts/start.sh` | Starts the widget as an independent process. | nothing |
| `mod/` | Herdr app mod. Runs `scripts/start.sh` when the app starts. | Herdr app |

## Data flow

The widget reads a snapshot one time each second and does not use events.

1. One time each second, run `herdr-app ls`. If it gives no valid answer, run `herdr-core ls --json`.
2. Replace the full agent table with the result. Refresh the counters.
3. If the two commands fail, show "offline". The next read is 1 second later.
4. After a jump, read immediately.

Rules for `state.py`:

- The key of a row is the terminal address.
- A terminal with no status is not a row.
- A snapshot replaces the full table.
- A row that is not valid is skipped. The other rows stay.
- The raw word `error` counts as `blocked`. A row with a different status word that is not one of the four states is skipped, and the word is logged one time.

Push updates (`herdr-core` has an event stream) are a later option, only if the 1-second delay is a problem.

## Interface

**Compact pill**

- Four counters in this order: `blocked`, `done`, `working`, `idle`.
- Each counter has a colour dot and a number.
- A counter with zero is dim.
- `blocked` and `done` use the attention colour when they are not zero.

**Expanded list**

- A click on the pill opens the list. A second click closes it.
- Each row shows the agent name (or the program if there is no name), the state, and the space (with the tab name when the space has more than one tab).
- Sort order: `blocked`, `done`, `working`, `idle`. Then by name.
- A click on a row runs `herdr-app do agent.focus` for that terminal. The list closes.
- With no agents, the list shows "No agents".

**Window**

- Always above other windows (layer-shell overlay layer).
- No title bar. The window does not take keyboard focus.
- Drag moves the widget. The widget changes its own margins.
- The position is saved to `~/.config/herdr-float/state.json` and loaded at start.
- If the saved position is outside the screen, the widget uses the top-right corner.

**System tray icon**

- The icon is a dot. Its colour is the colour of the first state, in display order, that has agents. With no agents or with Herdr offline it is grey.
- The tooltip gives the four counts.
- A left click hides the widget. A second left click shows it at the same position.
- A right click opens a menu: "Hide widget" or "Show widget", and "Quit".
- "Quit" stops the program. `scripts/start.sh` starts it again (by hand, or from the mod at the next start of the app).
- The widget is always visible after a start. The hidden state is not saved.
- If the desktop has no system tray, the widget runs without an icon.

## Failure cases

| Case | Behaviour |
|---|---|
| The app window is closed | The widget shows the agents that herdr-core reports. A click on a row shows "Herdr app is not open". |
| The app and herdr-core do not answer | The pill shows "offline" in grey. The widget reads again each second. |
| A reply is not valid | The widget uses the next source, or shows "offline". It writes one log line when the source changes. |
| The jump command fails | The row shows a short error for 3 seconds. |
| A second widget starts | The second process exits. One widget only. |

Logs go to `~/.local/state/herdr-float/herdr-float.log`.
There is no Sentry. This is a local personal tool.
Logs contain terminal addresses, states and counts only. They do not contain names, folders or terminal text.

## Tests

- `state.py`: pytest unit tests. Zero, one and many agents. Rows that are not valid. Sort order. Each of the four states. Sub-agents. Rows of herdr-core.
- `client.py`: pytest with a fake command runner. No test runs the real programs. Normal flow, fallback, offline, invalid data, the jump argument list and its errors.
- Live check on the desktop with real agents: each state, expand, jump, drag, restart, Herdr stopped and started.

## Known limits

- The jump shows the agent inside the Herdr app. It possibly does not raise the app window, because Wayland blocks an application from activating another application's window.
- After a jump the person looks at the agent, so the app changes `done` to `idle`. This is the expected Herdr behaviour.
- The drag can jitter. The pointer positions are relative to the surface, and the surface moves one frame late. A person has not yet seen this on the screen.
- The list closes when Herdr goes offline. Decision of 2026-11-18.

## Not in scope

- A second app folder (`HERDR_APP_HOME`).
- A test of agents on other machines (the app lists them; the widget shows what the app lists).
- Sounds and desktop notifications.
- A settings screen.
- Platforms other than KDE on Wayland.

## Build order

1. Short test of the three items that were not verified. Record the results in this file. Items 1 and 2 are done (see "Verified on 2026-11-18"). Item 3 stays in "Not verified".
2. `state.py` with tests.
3. `client.py` with tests.
4. Window and compact pill.
5. Expanded list and jump.
6. System tray icon.
7. Herdr plugin wrapper. (Replaced on 2026-11-18 by `scripts/start.sh` and `mod/`.)
8. Live check. Handoff notes in Obsidian.
