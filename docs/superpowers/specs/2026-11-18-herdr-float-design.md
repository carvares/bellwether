# herdr-float: design

Date: 2026-11-18
Status: approved design, not built

## Goal

A small window that floats above all other applications.
It shows how many Herdr agents are in each state.
It lets the user jump to an agent.

## Decisions

| Topic | Decision |
|---|---|
| Form | Standalone program. A thin Herdr plugin starts it when Herdr starts. |
| Run time | From the Herdr start until desktop logout. The widget stays on the screen after the Herdr window closes. No start at desktop login. |
| Scope | The default local Herdr session only. |
| States | Five counters, one for each Herdr state: `idle`, `working`, `blocked`, `done`, `unknown`. No state is merged into another. |
| Attention | `blocked` and `done` use the attention colour. |
| Interaction | Compact counters. A click expands an agent list. A click on an agent focuses its pane. |
| Tray | A system tray icon. Left click hides or shows the widget. The menu has "Hide widget" / "Show widget" and "Quit". |
| Stack | Python, Qt6 (PySide6), KDE layer-shell library. PySide6 comes from PyPI (`pyside6-essentials`), pinned to the minor version of the system Qt (6.12), because `sudo` was not available to install the system package. The layer-shell library comes from the system package `layer-shell-qt`. A system Qt upgrade to a new minor version can break the load of the layer-shell QML module until the pin moves too. |
| Platform | Linux, KDE Plasma on Wayland. No other platform. |

## Why not a Herdr plugin only

Herdr plugin panes have these placements: `overlay`, `popup`, `split`, `tab`, `zoomed`.
All of them are inside the Herdr terminal.
None is an operating-system window, so a plugin cannot float above other applications.
A plugin can run a command at startup. The plugin uses that to start the widget.
The user decided on 2026-11-18 that a start with Herdr is sufficient. There is no systemd service.

## Facts from the Herdr API schema

Source: `herdr api schema`, Herdr 0.9.5, protocol 22.

- Socket path: `~/.config/herdr/herdr.sock`.
- `agent.list` returns `AgentInfo` rows. Required fields: `terminal_id`, `agent_status`, `workspace_id`, `tab_id`, `pane_id`, `focused`, `revision`. Optional fields include `name`, `display_agent`, `title`, `cwd`.
- `AgentStatus` values: `idle`, `working`, `blocked`, `done`, `unknown`.
- `events.subscribe` takes a list of subscriptions. Event kinds include `pane_agent_detected`, `pane_agent_status_changed`, `pane_closed`, `pane_exited`.
- `pane.agent_status_changed` carries `pane_id`, `workspace_id`, `agent_status`, and optional `agent`, `display_agent`, `title`.
- `agent.focus` focuses the pane of an agent. It also marks a `done` agent as viewed.
- A read (`agent.list`) does not change the viewed state.

## Verified on 2026-11-18

Tested against Herdr 0.9.5 (protocol 22) with `spike/wire.py` and a structure-only probe.

1. The socket wire format.
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

3. A method to raise the terminal window after a jump. This test needs the user and a live agent. If the test fails, the known limit stays.

## Parts

Each part has one job.

| Part | Job | Depends on |
|---|---|---|
| `herdr_float/state.py` | Hold the agent table. Apply a snapshot or an event. Return the five counts and a sorted agent list. Pure logic, no I/O. | nothing |
| `herdr_float/client.py` | Connect to the socket. Send one request. Return the reply or an error. | socket |
| `herdr_float/settings.py` | Save and load the window position. | nothing |
| `herdr_float/backend.py` | Qt object. Reads a snapshot each second. Gives counters and agents to the interface. | `client.py`, `state.py`, `settings.py` |
| `herdr_float/ui/Main.qml` | Layer-shell overlay window, compact pill, expanded list, drag. | `backend.py` |
| `herdr_float/tray.py` | System tray icon and menu. The one source of the state colours. | Qt, `backend.py` |
| `herdr_float/__main__.py` | Connect the parts. Start the Qt application. | all parts |
| `plugin/` | Herdr plugin manifest and start script. Starts the widget as an independent process. | Herdr |

## Data flow

Changed on 2026-11-18 after a second read of the schema.
The `pane.agent_status_changed` subscription needs a `pane_id`. There is no global status subscription.
So version 1 reads a snapshot one time each second and does not use events.

1. One time each second, open a connection and call `agent.list`.
2. Replace the full agent table with the result. Refresh the counters.
3. If the call fails, show "offline". The next read is 1 second later.
4. After a jump, read immediately.

Rules for `state.py`:

- The key of a row is `pane_id`.
- A pane with no agent is not a row.
- A snapshot replaces the full table.
- A row that is not valid is skipped. The other rows stay.
- A status that is not one of the five states counts as `unknown`.

Push updates (one subscription for each pane) are a later option, only if the 1-second delay is a problem.

## Interface

**Compact pill**

- Five counters in this order: `blocked`, `done`, `working`, `idle`, `unknown`.
- Each counter has a colour dot and a number.
- A counter with zero is dim.
- `blocked` and `done` use the attention colour when they are not zero.

**Expanded list**

- A click on the pill opens the list. A second click closes it.
- Each row shows the agent name (or agent kind if there is no name), the state, and the workspace.
- Sort order: `blocked`, `done`, `working`, `idle`, `unknown`. Then by name.
- A click on a row calls `agent.focus` for that pane. The list closes.
- With no agents, the list shows "No agents".

**Window**

- Always above other windows (layer-shell overlay layer).
- No title bar. The window does not take keyboard focus.
- Drag moves the widget. The widget changes its own margins.
- The position is saved to `~/.config/herdr-float/state.json` and loaded at start.
- If the saved position is outside the screen, the widget uses the top-right corner.

**System tray icon**

- The icon is a dot. Its colour is the colour of the first state, in display order, that has agents. With no agents or with Herdr offline it is grey.
- The tooltip gives the five counts.
- A left click hides the widget. A second left click shows it at the same position.
- A right click opens a menu: "Hide widget" or "Show widget", and "Quit".
- "Quit" stops the program. The plugin starts it again at the next Herdr start.
- The widget is always visible after a start. The hidden state is not saved.
- If the desktop has no system tray, the widget runs without an icon.

## Failure cases

| Case | Behaviour |
|---|---|
| Herdr is not running | The pill shows "offline" in grey. The widget reads again each second. |
| A reply is not valid | The pill shows "offline". The widget writes one log line when the condition starts. |
| `agent.focus` fails | The row shows a short error for 3 seconds. |
| A second widget starts | The second process exits. One widget only. |

Logs go to `~/.local/state/herdr-float/herdr-float.log`.
There is no Sentry. This is a local personal tool.
Logs contain IDs and states only. They do not contain pane text.

## Tests

- `state.py`: pytest unit tests. Zero, one and many agents. Rows that are not valid. Sort order. Each of the five states.
- `client.py`: pytest against a fake socket server. Normal flow, disconnect, invalid data, reconnect with a new snapshot.
- Live check on the desktop with real agents: each state, expand, jump, drag, restart, Herdr stopped and started.

## Known limits

- The jump focuses the pane inside Herdr. It possibly does not raise the terminal window, because Wayland blocks an application from activating another application's window. Step 1 tests a KWin method. If no method works, the limit stays.
- `agent.focus` marks a `done` agent as viewed. This is the expected Herdr behaviour.
- The drag can jitter. The pointer positions are relative to the surface, and the surface moves one frame late. A person has not yet seen this on the screen.
- The list closes when Herdr goes offline. Decision of 2026-11-18.

## Not in scope

- Other named Herdr sessions.
- SSH machines.
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
7. Herdr plugin wrapper.
8. Live check. Handoff notes in Obsidian.
