# herdr-float: design

Date: 2026-11-18
Status: built. The data source changed on 2026-11-18. The layout and the jump changed on 2026-11-18. Program icons and the status border were added on 2026-11-18 (see the next three sections; the newest is the last of the three).

## Change on 2026-11-18: data source is the Herdr desktop app

Root cause of the bug "all zeros with running agents":
this machine has two Herdr products, and the widget read the wrong one.
The widget read the `herdr` 0.9 terminal program (socket `~/.config/herdr/herdr.sock`), which had 0 agents.
The agents of the user are in the Herdr desktop app (`herdr-app`, the window) and `herdr-core` (it runs the terminals).

- **Source.** One time each second the widget runs `herdr-app ls` (argument list, no shell, 2 s timeout) and reads the JSON: spaces, tabs, terminals. Measured: 3 to 14 ms for each call, less than 1 % of one processor core.
- **Agent row.** A terminal with a status is an agent. A terminal with status `null` is a plain shell and is not a row. The key of a row is the terminal address (for example `t11`). The name is the terminal name, else the program (`app`), else the address. The place text is the space name, and the tab name when the space has more than one tab.
- **Sub-agents.** The entries in `sub_agents` are agents too (terminals that an agent started). They are rows. As in the agent list of the app, a sub-agent that reports `done` counts as `idle`. No real sub-agent was available on 2026-11-18, so the widget accepts two shapes for these entries: the fields of a terminal in `herdr-app ls` (`terminal`), and the fields of `herdr-core ls --json` (`address`, `state`; only `live` entries count). A terminal that is listed in a tab and also below a parent is one row with the sub-agent status. This is not verified with real data.
- **States.** Four: `blocked`, `done`, `working`, `idle`. `done` means that the agent finished while the person did not look; the app changes it to `idle` after the person looks. There is no `unknown` state. A program can report the raw word `error`; the widget counts it as `blocked`, as the agent list of the app does. A different word that is not known: the row is skipped and the word is logged one time.
- **Fallback.** When `herdr-app ls` gives no valid answer (window closed, app not installed, timeout), the widget runs `herdr-core ls --json`. A row is a terminal with `state` `live` and a status. Name: the `agent` field. No place text. A row with a `parent` is a sub-agent (`done` counts as `idle`). The status is the word of the program itself, so `done` shows also when the person saw the agent before. If herdr-core does not answer either, the panel shows "offline".
- **Jump.** `herdr-app do agent.focus {"terminal": "<address>"}`. The jump also starts a closed app and raises the window (see the next section).
- **Start.** `scripts/start.sh` starts the widget. The folder `mod/` is a Herdr app mod that runs this script when the app starts; the user installs it (see the README). The `plugin/` folder for the `herdr` 0.9 program is removed.

## Change on 2026-11-18: vertical status list and open-the-app click

Request of the user: a larger interface with a vertical list of the states and their counts, rows that expand to show their agents, and a click on an agent that opens the Herdr app also when it is closed or minimized.

**Interface (`ui/Main.qml`).**

- A panel 240 px wide. Four status rows (30 px), always visible, in the order Blocked, Done, Working, Idle: colour dot, name, count at the right edge. A row with 0 is dim. `blocked` and `done` show a coloured, bold count when they are not 0.
- A click on a row with agents opens it: its agents show below it (26 px each, indented): name at the left, space text at the right. A second click closes it. One row is open at a time. A row with 0 does nothing.
- An open group shows 8 agent rows at most. The mouse wheel scrolls the others. A thin bar at the right is the scroll indicator. The four group items are fixed, so the scroll position stays when the agents change.
- The open group closes when its count becomes 0, and when Herdr goes offline. Offline, the panel shows the one line "offline".
- One pointer handler covers the panel. A press that moves 6 px or more is a drag (the rules of the first design). A press that moves less is a click on the row below the pointer. So a drag can start on any row.
- The backend gives `groups`: for each state `{state, label, count, attention, agents: [{key, name, workspace}]}`. `counters` stays for the tray. The flat `agents` property is removed.
- Measured sizes (image of the widget's own window): closed 240 x 136; 3 agents open 240 x 214; 12 agents open 240 x 344; offline 240 x 46; with the error line + 24.

**Jump (`client.py`, `window.py`).** A click on an agent row does these steps on a worker thread:

1. `herdr-app ls`. If it does not answer, the app is closed: start it and ask again each 0.25 s, until it answers or the time of the jump ends. Failure: "Herdr app did not start".
2. `herdr-app do agent.focus`. A window that just started answers `ls` before it has its terminals, so after a start this step is tried 8 times (2 s of pauses), inside the time of the jump. The reply `no running terminal` gives "agent is gone".
3. Raise the window. Failure: "could not raise the window".

- **Time limit.** A jump has a deadline 8 s after the click (`JUMP_SECONDS`, monotonic clock). Each command gets the smaller of 2 s and the time that is left, and each pause is cut at the deadline. So a jump ends 8 s after the click at the latest, with the error of the step in progress: "Herdr app did not start", "agent is gone" (the last answer of a new window) or "Herdr is offline" (the show command gave no answer), "could not raise the window". Before fix round 1 the limit counted tries, and the worst case was about 90 s.
- **Start.** `systemd-run --user --quiet --collect --slice=app.slice -- <herdr-app>`. Plasma starts the app the same way (a unit of the user's systemd in `app.slice`, Exec `herdr-app` from `herdr-app.desktop`). The app gets the environment of the session and not that of the widget (a widget that was started from a Herdr terminal has `HC_*` variables). The app is not a child of the widget and has none of its files.
- **Raise.** KWin has the window runner of KRunner on D-Bus (`org.kde.KWin`, `/WindowsRunner`, `org.kde.krunner1`). `Match "herdr-app"` gives the windows; `getWindowInfo` (path `/KWin`) confirms the exact class `herdr-app`; `Run "0_<window id>"` restores the window from minimized and activates it (KWin possibly also goes to the desktop of the window: not tested, this machine has one desktop); a second `getWindowInfo` confirms `minimized: false`. The widget calls it with `busctl --user --json=short`. No KWin script and no file are necessary.
- A match that is not a window of the app, or that KWin cannot give, is skipped; the next match is tried.
- When the widget starts the app, the output of the app goes to the user journal, as when Plasma starts it.
- An error of a different kind in a jump shows "jump failed"; the log holds the class name of the error only.
- A failure message opens the group of its agent one time. After that the group follows the agent only when the agent goes to a different group, so the person can close or change the group.
- Known, not fixed: a failed agent in a group with more than 8 agents is not scrolled into view. A jump that races a start of the app by hand (the app does not answer yet) can start a second copy of the app.
- **Fallback for the raise.** If KWin did not raise the window, the widget runs plain `herdr-app` (the same start command). The app documentation says that this "opens or raises the window".
- While a jump runs, the backend property `opening` holds its terminal address. The row shows "opening…". More clicks on agents are ignored until the jump ends, so the app cannot start two times.
- A failed jump shows its message for 3 seconds in the agent row. If the agent changed its state, its new group opens. If the agent has no row (gone, or offline), the message shows in a line at the bottom of the panel.
- Logs: `jump agent=<address> step=<launch|wait|show|raise> ...` with exit codes. No command output.

**Measured on 2026-11-18** (KWin on Wayland, focus stealing prevention at its default "low", one virtual desktop, window state read from KWin with a read-only KWin script):

| Method | Window behind a different window | Window minimized | App closed |
|---|---|---|---|
| Plain `herdr-app` (no activation token) | raised and active, 2 of 2 | restored and active, 1 of 1 | starts the app; the new window is active |
| KWin window runner `Run` | raised and active in 8 ms | restored and active | not applicable (no window) |
| The real jump (`HerdrClient.focus_agent`) | ok, 0.03 s, 2 of 2 | ok, 0.03 s, 2 of 2 | ok, 0.6 s, 2 of 2 |

- Not tried: an xdg-activation token from the click on the widget (PySide6 has no public call for it), and a KWin script (the window runner does the same with no script file).
- Not tested: a window on a different virtual desktop (this machine has one desktop).
- KWin is the first method because its result can be read back and it does not depend on the focus rules of the desktop.
- The app window closed 3 times in the tests. The 5 live terminals of herdr-core stayed alive each time. After a restart the app showed the same space, tab and agent as before the close.

The sections below are the first design. Lines that the change made false are corrected.
Sections that describe the `herdr` 0.9 program are kept as history and say so.

## Change on 2026-11-18: program icons and status border

Request of the user: the icon that Herdr shows for the program in the place of the program word, and a panel border in the colour of the most important state, in the order blocked, done, idle, working.

- **What the app documents.** `~/.config/herdr-app/AGENTS.md` ("Programs: `programs.json`") and the `Program` type in `herdr.d.ts`: each terminal has a `program` from one table with `icon` (a path in the app folder, for example `icons/nvim.svg`) and `tint` (true: a one-colour glyph drawn in the text colour; false: a picture drawn as it is). `match` lists other names, also the `app` words of agents. The agent list of the app (`mods/agents/main.js`, function `icon`) draws it that way. The built-in table has 124 programs. `programs.json` changes entries; this machine has no such file.
- **What is not available from outside.** `herdr-app ls` and `herdr-core ls --json` give only the program word (`app` / `agent`, for example `claude-code`). No command and no file gives the table. The table is only inside the program file of the app.
- **Rule of the widget (inferred, then compared with the table).** `herdr_float/icons.py`, `find_icon`: a word that is not a plain program word (letters, digits, `.`, `_`, `+`, `-`) gets the generic icon. Else the first file that exists: the alias of the word (`ALIASES`: 5 agent words from the `match` lists that the next two steps do not find), `icons/<word>.svg`, `icons/<part before the first "-">.svg`, `icons/agent.svg`. No file: no icon, and the row shows the text of before. On 2026-11-18 the rule was compared with the table read from the program file (`strings`, read-only): the same file for all 124 keys and for all `match` words of agents, except the word `agent` (the table has both a key `agent` and a `match` of Cursor; the widget uses the key, the generic icon). 75 `match` words of programs that are not agents (for example `python3`) get the generic icon; such programs are not agent rows.
- **Glyph or picture (inferred, then compared).** `is_glyph`: an SVG whose `fill`, `stroke` and `stop-color` values are only `none`, `currentColor`, black or white is a glyph. The result is equal to the `tint` flag of the table for all 124 entries (8 pictures: amp, antigravity, claude, codex, crush, kimi, kiro, pig).
- **Colour of a glyph.** The Qt of the PyPI wheel reads SVG (`imageformats/libqsvg.so` is in the wheel), and `QtQuick.Effects` (`MultiEffect`) is there too. `MultiEffect` was not used: the software renderer (the off-screen tests and images) does not draw it, so it cannot be checked. The widget writes a copy of the glyph with the text colour `#e8eaed` in the place of `currentColor`, black and white (`tinted`) to `~/.cache/herdr-float/icons/<name>-<hash of the content>.svg` and gives QML that file. All 116 glyph files of the app were drawn from their copies: each one draws, and only in the text colour. A picture is given to QML as the file of the app. The files of the app are not copied into the repository and not changed.
- **Agent row.** `Agent` has a new field `app` (the program word); `name` is now only the name of the terminal. The backend builds each row: `icon` (file URL or ""), `label`, `detail`, `address`, `spoken`. With an icon: label = the terminal name, else the workspace text, else the address; detail (right) = the workspace text only when the row has a name. Without an icon: label = name, else program word, else address; detail = workspace (as before). Rows of one group with the same icon, label and detail get the address in a dim colour. The accessibility name says the program in words: "Go to claude-code in <workspace>", or "Go to <name>, claude-code in <workspace>".
- **Icon in QML.** An `Image` of 16 x 16 px at the left of the row, `sourceSize` 16 x 16 (Qt draws the SVG at the scale of the screen; checked at scale 1 and 2).
- **Border.** `state.py` has `PRIORITY = ("blocked", "done", "idle", "working")` and `top_state(online, counts)`: "offline", "none", or the first state of `PRIORITY` with an agent. Idle is above working: the user chose it. `STATES` (blocked, done, working, idle) is still the order of the rows. `Backend.topState` gives it to QML. The panel border is 2 px, drawn inside the panel (the panel size is the same: 240 x 136 closed), in the colour of `STATE_COLORS[topState]`; "none" and "offline" keep the grey `#3c4043`. The change has no animation.
- **Tray.** The tray dot uses `Backend.topState` too, so it has the colour of the border. The tooltip lists the counts in the order of `PRIORITY`.
- **Log.** One INFO line for each program word that has no icon of its own ("no icon for program 'x': the generic icon is used" or "...: the row shows text"). No paths.
- **Not done.** `programs.json` is not read. The icons are read one time for each word in the life of the process. A person did not yet look at the icons and the border on the screen: the checks used images of the widget's own window (off screen, software renderer).

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
| Interaction | A vertical list of the four states with counts. A click on a state shows its agents. A click on an agent opens the Herdr app on it. |
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

3. A method to raise the Herdr app window after a jump. Done on 2026-11-18: see "Change on 2026-11-18: vertical status list and open-the-app click".

## Parts

Each part has one job.

| Part | Job | Depends on |
|---|---|---|
| `herdr_float/state.py` | Convert the rows of `herdr-app ls` or `herdr-core ls --json` to a sorted agent list. Return the four counts. No reads of Herdr. | nothing |
| `herdr_float/client.py` | Run `herdr-app` (or `herdr-core` as the fallback). Return the agents or an error. Run the jump: start a closed app, show the agent, raise the window. | `state.py`, `window.py`, the two programs, `systemd-run` |
| `herdr_float/window.py` | Ask KWin to restore and activate the app window. | `busctl`, KWin |
| `herdr_float/settings.py` | Save and load the window position. | nothing |
| `herdr_float/backend.py` | Qt object. Reads a snapshot each second. Gives counters and status groups to the interface. Runs one jump at a time on a worker thread. | `client.py`, `state.py`, `settings.py` |
| `herdr_float/ui/Main.qml` | Layer-shell overlay window, status rows, agent rows of the open group, drag. | `backend.py` |
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

**Status list and agent rows**

The first design had a horizontal pill and one list below it. The section "Change on 2026-11-18: vertical status list and open-the-app click" describes the interface that replaced them.

- Sort order of the agents in a group: by name.

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
| The app window is closed | The widget shows the agents that herdr-core reports. A click on an agent starts the app and shows the agent. |
| The app and herdr-core do not answer | The panel shows "offline" in grey. The widget reads again each second. |
| A reply is not valid | The widget uses the next source, or shows "offline". It writes one log line when the source changes. |
| The jump fails | The agent row, or a line at the bottom of the panel, shows a short error for 3 seconds. |
| A second widget starts | The second process exits. One widget only. |

Logs go to `~/.local/state/herdr-float/herdr-float.log`.
There is no Sentry. This is a local personal tool.
Logs contain terminal addresses, states and counts only. They do not contain names, folders or terminal text.

## Tests

- `state.py`: pytest unit tests. Zero, one and many agents. Rows that are not valid. Sort order. Each of the four states. Sub-agents. Rows of herdr-core.
- `client.py`: pytest with a fake command runner. No test runs the real programs. Normal flow, fallback, offline, invalid data, and each branch of the jump: window visible, minimized, app closed, app does not start, raise fails, agent gone.
- `backend.py` and `Main.qml`: the groups, one jump at a time, and pointer clicks on the real QML off screen.
- Live check on the desktop with real agents: each state, expand, jump, drag, restart, Herdr stopped and started.

## Known limits

- The jump raises the app window through KWin, so it works on KDE Plasma only. A window on a different virtual desktop was not tested.
- After a jump the person looks at the agent, so the app changes `done` to `idle`. This is the expected Herdr behaviour.
- The drag can jitter. The pointer positions are relative to the surface, and the surface moves one frame late. A person has not yet seen this on the screen.
- The open group closes when Herdr goes offline. Decision of 2026-11-18.
- An open group can make the panel longer than the space below it. The panel then moves up and does not move back when the group closes.

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
