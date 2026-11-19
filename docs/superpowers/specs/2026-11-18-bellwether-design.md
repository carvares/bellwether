# Bellwether: design

Renamed from herdr-float to Bellwether on 2026-11-18. The "Verified on 2026-11-18" records keep the old name where they quote what was run then.

Date: 2026-11-18
Status: built. The data source changed on 2026-11-18. The layout and the jump changed on 2026-11-18. Program icons and the status border were added on 2026-11-18. The panel became Layout C (Techno / HUD) on 2026-11-18 (see the next sections; the section on Layout C is the newest and it replaces the sizes, colours and the border of the sections before it).

## Change on 2026-11-18: the name is Bellwether

- The tool is Bellwether: the Python package `bellwether` (`python -m bellwether`), the logger `bellwether`, the Qt application name and the layer-shell scope `bellwether`, the tray tooltip "Bellwether: …", the mod folder `mods/bellwether` in the folder of the app, and "BELLWETHER" at the left of the panel header. The names of the Herdr product, of its two programs and of its folder do not change.
- Folders: `bellwether` in `$XDG_CONFIG_HOME` (state.json), `$XDG_STATE_HOME` (bellwether.log, start.log) and `$XDG_CACHE_HOME` (icons), with the defaults `~/.config`, `~/.local/state` and `~/.cache`. The lock is `bellwether.lock` in `$XDG_RUNTIME_DIR` (else `/tmp`).
- Move of the old folders (`bellwether/paths.py`, `move_old_folders`): at start, after the lock and before anything reads or makes a folder, each folder `herdr-float` in the three places gets the name `bellwether` when no `bellwether` folder is there. An existing new folder is never replaced, and the old one then stays as it is. A move that fails does not stop the start: one log line with the error class, and the widget uses its defaults. The log lines are written when the log file is open (the log folder is one of the folders that move). Old log files keep their old names in the moved folder.
- An old and a new widget never run together: the widget also takes the old lock `herdr-float.lock`. If a widget of either name holds a lock, the start exits before it moves or makes a folder. `scripts/start.sh` writes start.log into the old state folder when only that one exists, so that the widget can still move it.
- The header text is longer, so "AGENTS nn" now follows the name with a 12 px gap (it was at x 52). In the widest case ("AGENTS 121" and "BLOCKED") the parts do not touch in 292 px.

## Change on 2026-11-18: data source is the Herdr desktop app

Root cause of the bug "all zeros with running agents":
this machine has two Herdr products, and the widget read the wrong one.
The widget read the `herdr` 0.9 terminal program (socket `~/.config/herdr/herdr.sock`), which had 0 agents.
The agents of the user are in the Herdr desktop app (`herdr-app`, the window) and `herdr-core` (it runs the terminals).

- **Source.** The widget runs `herdr-app ls` (at first one time each second; since the change "push events and row order" below: at each change that herdr-core tells of) (argument list, no shell, 2 s timeout) and reads the JSON: spaces, tabs, terminals. Measured: 3 to 14 ms for each call, less than 1 % of one processor core.
- **Agent row.** A terminal with a status is an agent. A terminal with status `null` is a plain shell and is not a row. The key of a row is the terminal address (for example `t11`). The name is the terminal name ("" when the terminal has none; before Task 13 the program word or the address took its place). The program word (`app`) is a field of its own. The place text is the space name, and the tab name when the space has more than one tab.
- **Sub-agents.** The entries in `sub_agents` are agents too (terminals that an agent started). They are rows. As in the agent list of the app, a sub-agent that reports `done` counts as `idle`. No real sub-agent was available on 2026-11-18, so the widget accepts two shapes for these entries: the fields of a terminal in `herdr-app ls` (`terminal`), and the fields of `herdr-core ls --json` (`address`, `state`; only `live` entries count). A terminal that is listed in a tab and also below a parent is one row with the sub-agent status. This is not verified with real data.
- **States.** Four: `blocked`, `done`, `working`, `idle`. `done` means that the agent finished while the person did not look; the app changes it to `idle` after the person looks. There is no `unknown` state. A program can report the raw word `error`; the widget counts it as `blocked`, as the agent list of the app does. A different word that is not known: the row is skipped and the word is logged one time.
- **Fallback.** When `herdr-app ls` gives no valid answer (window closed, app not installed, timeout), the widget runs `herdr-core ls --json`. A row is a terminal with `state` `live` and a status. Name: the `agent` field. No place text. A row with a `parent` is a sub-agent (`done` counts as `idle`). The status is the word of the program itself, so `done` shows also when the person saw the agent before. If herdr-core does not answer either, the panel shows "offline".
- **Jump.** `herdr-app do agent.focus {"terminal": "<address>"}`. The jump also starts a closed app and raises the window (see the next section).
- **Start.** `scripts/start.sh` starts the widget. The folder `mod/` is a Herdr app mod that runs this script when the app starts; the user installs it (see the README). The `plugin/` folder for the `herdr` 0.9 program is removed.

## Change on 2026-11-18: vertical status list and open-the-app click

Request of the user: a larger interface with a vertical list of the states and their counts, rows that expand to show their agents, and a click on an agent that opens the Herdr app also when it is closed or minimized.

**Interface (`ui/Main.qml`).**

- (Sizes and look replaced by Layout C, see that section.) A panel 240 px wide. Four status rows (30 px), always visible, in the order Blocked, Done, Working, Idle: colour dot, name, count at the right edge. A row with 0 is dim. `blocked` and `done` show a coloured, bold count when they are not 0.
- A click on a row with agents opens it: its agents show below it (26 px each, indented): name at the left, space text at the right. A second click closes it. One row is open at a time. A row with 0 does nothing.
- An open group shows 8 agent rows at most. The mouse wheel scrolls the others. A thin bar at the right is the scroll indicator. The four group items are fixed, so the scroll position stays when the agents change.
- The open group closes when its count becomes 0, and when Herdr goes offline. Offline, the panel shows the one line "offline".
- One pointer handler covers the panel. A press that moves 6 px or more is a drag (the rules of the first design). A press that moves less is a click on the row below the pointer. So a drag can start on any row.
- The backend gives `groups`: for each state `{state, label, count, attention, agents: [{key, icon, label, detail, address, spoken}]}` (before Task 13: `{key, name, workspace}`; see the section on program icons). `counters` stays for the tray. The flat `agents` property is removed.
- (Replaced by Layout C.) Measured sizes (image of the widget's own window): closed 240 x 136; 3 agents open 240 x 214; 12 agents open 240 x 344; offline 240 x 46; with the error line + 24.

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
- **Rule of the widget (inferred, then compared with the table).** `bellwether/icons.py`, `find_icon`: a word that is not a plain program word (letters, digits, `.`, `_`, `+`, `-`) gets the generic icon. Else the first file that exists: the alias of the word (`ALIASES`: 5 agent words from the `match` lists that the next two steps do not find), `icons/<word>.svg`, `icons/<part before the first "-">.svg`, `icons/agent.svg`. No file: no icon, and the row shows the text of before. On 2026-11-18 the rule was compared with the table read from the program file (`strings`, read-only): the same file for all 124 keys and for all `match` words of agents, except the word `agent` (the table has both a key `agent` and a `match` of Cursor; the widget uses the key, the generic icon). 75 `match` words of programs that are not agents (for example `python3`) get the generic icon; such programs are not agent rows.
- **Glyph or picture (inferred, then compared).** `is_glyph`: an SVG whose `fill`, `stroke` and `stop-color` values are only `none`, `currentColor`, black or white is a glyph. The result is equal to the `tint` flag of the table for all 124 entries (8 pictures: amp, antigravity, claude, codex, crush, kimi, kiro, pig).
- **Colour of a glyph.** The Qt of the PyPI wheel reads SVG (`imageformats/libqsvg.so` is in the wheel), and `QtQuick.Effects` (`MultiEffect`) is there too. `MultiEffect` was not used: the software renderer (the off-screen tests and images) does not draw it, so it cannot be checked. The widget writes a copy of the glyph with the text colour `#e8eaed` in the place of `currentColor`, black and white (`tinted`) to `~/.cache/bellwether/icons/<name>-<hash of the content>.svg` and gives QML that file. All 116 glyph files of the app were drawn from their copies: each one draws, and only in the text colour. A picture is given to QML as the file of the app. The files of the app are not copied into the repository and not changed.
- **Agent row.** `Agent` has a new field `app` (the program word); `name` is now only the name of the terminal. The backend builds each row: `icon` (file URL or ""), `label`, `detail`, `address`, `spoken`. With an icon: label = the terminal name, else the workspace text, else the address; detail (right) = the workspace text only when the row has a name. Without an icon: label = name, else program word, else address; detail = workspace (as before). Rows of one group with the same icon, label and detail get the address in a dim colour. The accessibility name says the program in words: "Go to claude-code in <workspace>", or "Go to <name>, claude-code in <workspace>".
- **Icon in QML.** An `Image` of 16 x 16 px at the left of the row, `sourceSize` 16 x 16 (Qt draws the SVG at the scale of the screen; checked at scale 1 and 2).
- **Border (the 2 px border is replaced by the corner brackets of Layout C; the rule for the state is the same).** `state.py` has `PRIORITY = ("blocked", "done", "idle", "working")` and `top_state(online, counts)`: "offline", "none", or the first state of `PRIORITY` with an agent. Idle is above working: the user chose it. `STATES` (blocked, done, working, idle) is still the order of the rows. `Backend.topState` gives it to QML. The panel border is 2 px, drawn inside the panel (the panel size is the same: 240 x 136 closed), in the colour of `STATE_COLORS[topState]`; "none" and "offline" keep the grey `#3c4043`. The change has no animation.
- **Tray.** The tray dot uses `Backend.topState` too, so it has the colour of the border. The tooltip lists the counts in the order of `PRIORITY`.
- **Log.** One INFO line for each program word that has no icon of its own ("no icon for program 'x': the generic icon is used" or "...: the row shows text"). No paths.
- **Fix round 1 (2026-11-18).** The lookup accepts a program word of 64 characters at most and treats a file system error as "no such file" (the result is kept, so the error does not repeat each second). The rows of a group are sorted in the backend by the label that shows, then by the address (changed later the same day: agents with a name first, see "push events and row order"); `state.py` sorts only by state and address. `Icons.url` checks that the file it gave still exists and finds or makes it again if not. An icon that does not load in QML is hidden, and the row uses the layout without an icon.
- **Not done.** `programs.json` is not read. The icons are read one time for each word in the life of the process (and again when the file is gone). A person did not yet look at the icons and the border on the screen: the checks used images of the widget's own window (off screen, software renderer).

## Change on 2026-11-18: Layout C (Techno / HUD)

Decisions of the user, after the five design options: the floating panel is Layout C; the tray icon stays as it is (the Herdr ram tile in the status colour); the widget has no standalone application icon (the five icon concepts in `design/icons/` are an archive, nothing uses them).

- **Visual reference.** `design/layouts/c-hud.qml` and its six frames `design/out/herdr-float-layout-c-*.png`. `ui/Main.qml` takes its sizes, spacings, colours and font sizes from that file. The real panel with the data of the mock-up scenes was compared with the mock-up, pixel by pixel at scale 2: the closed scene (10 agents) is equal. The scenes with an open group differ only in the order of the agent rows (the real rows are sorted by their text). The scenes with fewer than 10 agents and the offline scene differ only in the cell bar (see below: no empty cells).
- **Panel.** 320 px wide, `#0b0e11` at 94 % opacity, a 1 px frame `#2b333b`, four corner brackets (14 px long, 2 px thick, inside the panel). Monospace font: Hack; if it is not installed, the first of JetBrains Mono, DejaVu Sans Mono, Liberation Mono, Noto Sans Mono, else the system `monospace`.
- **Header (22 px).** "BELLWETHER" (until the rename: "HERDR"), then "AGENTS nn" (the sum of the four counts, computed in QML from `groups`; "NO LINK" offline), and at the right a 6 px lamp and the top state in capitals ("NO AGENTS" for none, "OFFLINE" offline).
- **Top status.** The brackets, the lamp and the word have the colour of `STATE_COLORS[backend.topState]`; "none" and "offline" are `#6b747d`. The frame line and every size stay the same for each state.
- **Cell bar (20 px).** One cell (8 px high) for each agent in the row order blocked, done, working, idle; the number of cells is the number of agents and the cells fill the width (the user asked for this after the first build: the mock-up had 10 cells at least, with empty outlines; the approved frames with fewer than 10 agents, and the offline frame, are different in this one point); the cell width is `(292 - gap x (n - 1)) / n`, as in the mock-up, so the last cell ends at the right edge; the gap is 2 px, and 1 px with more than 24 cells. More than 60 agents: 60 cells are shared in proportion, a state with an agent has one cell or more (the difference from rounding goes to the biggest state). Offline and with no agents: one empty outline across the width.
- **Status rows (32 px).** An 8 px marker (filled; an outline for a count of 0), the name in capitals, a dotted leader, and the count with two digits where a zero at the front is dim. `blocked` and `done` counts have the state colour. A row with 0 is dim and does nothing. The open row has a plate in the state colour at 10 % and a 2 px accent at the left. Not in the mock-up: the row below the pointer has a lighter plate (6 %; an agent row has a faint plate), so a person sees what a click does.
- **Agent rows (28 px).** A tree line at the left, the 16 px program icon at 20 px, the label at 44 px (at 20 px without an icon), the address in dim brackets, and the detail text at the right (120 px at most). "> opening…" in blue during a jump. A failure shows as "! <message>" in red (200 px at most) and hides the address. Under a list: 4 px, or the 20 px hint line.
- **Long groups.** 8 rows show. The hint line reads "ROWS 01–08 / 12  ▼ SCROLL" with the rows on the screen ("▲ SCROLL" at the end of the list). The scroll track at the right edge has one tick for each agent, bright for the rows on the screen; with more than 72 agents a tick would be thinner than 1 px, so the track is then one bar with a bright part. The track is not a target of the pointer. One wheel step scrolls 2 rows (56 px).
- **Failure line.** When the failed agent has no row (gone, or offline), "! <message>" shows in a 24 px line at the bottom of the panel.
- **Offline.** The header, the empty outline of the bar and a hatched plate with the word "OFFLINE": 320 x 108.
- **Sizes (image of the widget's own window).** Closed 320 x 192; an open group adds 28 px for each row and 4 px (3 agents: 320 x 280); 12 agents: 320 x 436; the failure line + 24.
- **Kept without change.** The layer-shell properties and `onMarginsChanged: requestUpdate()`, the position logic, the one pointer handler (6 px threshold, drag from any row, save at release), the rules for the open group, the failure message rules (`failedShownIn`), no keyboard focus, the accessibility names.
- **Drag rate.** The shortest time between two margin changes of a drag was 16 ms. It is now one frame of the screen of the window: `minMoveMs = 1000 / refreshRate`, from 4 ms to 20 ms, and 16 ms when the rate is not known. QML does not have the refresh rate of a screen, so `__main__.follow_refresh_rate` sets the window property `refreshRate` from `QScreen.refreshRate()` at start and when the window changes its screen. On this machine: 240 Hz (step 4.2 ms) and 144 Hz (step 6.9 ms). (Changed later on the same day to two frames: see "Change on 2026-11-18: more than one monitor".) The panel has no animation, and no `Timer` moves a visual. The agent data is read one time each second, as before.
- **Not done.** No transition when a group opens: an animated height changes the size of the layer surface and the clamp in each frame, and a fade alone would show only at the open. A person did not yet look at the new panel on the screen.

## Change on 2026-11-18: tray icon is the Herdr icon

Request of the user: the tray icon is the Herdr app icon, in the status colour, with the same behaviour as the tray dot.

- **Where the icon comes from.** `bellwether/appicon.py`, `find_app_icon`, at each start: the `Icon=` entry of the first `herdr-app.desktop` in the XDG `applications` folders, then that name in the XDG `icons/hicolor` folders (`scalable/apps/` SVG first, else the largest PNG of `<size>/apps/`) and in `pixmaps`. An absolute `Icon=` path is accepted only when it is an existing `.svg` or `.png` file. A name with an extension (`herdr-app.svg`) is read as the name without it. An SVG in a size folder (`hicolor/48x48/apps/`) is found too, after `scalable/apps/`. On this machine: `herdr-app.svg` in `hicolor/scalable/apps` (package `herdr-app-desktop-bin`). The file is not copied into the repository.
- **The icon.** An opaque ivory rounded tile with a charcoal ram (curled horn, a terminal prompt as the eye). Qt does not apply `clip-path`, so the widget clips the drawing with each used `clipPath` that is one `<rect>`. A plain silhouette is a blank rounded square, so `mark` keeps the plate (the most frequent tone in a thin band at the outer edge of the tile), cuts the picture out as transparent, and adds a thin outline (`max(1.5, size / 16)` px) that keeps the tile edge closed where the ram touches it. An icon that is a glyph on transparency gets its plain alpha silhouette.
- **Chosen by eye at 22 px** on a dark and a light panel (off screen) from: plain silhouette, plate with ram cut out, the same with outline, ram only, plate with a dark ram. The outlined plate stays one colour and keeps the tile shape on both panels; on a dark panel it looks like the app icon. The plate with a dark ram was close, but it has two colours.
- **Tray.** `TrayIcons` makes each shape one time (sizes 16, 22, 24, 32, 44, 48, 64) and each colour one time (at most 5 icons). `STATE_COLORS`, `PRIORITY`, the tooltip, the click, the menu and the rule for when the icon changes are the same.
- **Fallback.** No icon or an icon that does not load: the circle of before, and one INFO line at start without a path.
- **Robustness (Task 16).** `TrayIcons.load` has one broad guard around the lookup, the load and the making of the mark: any error gives the circle and one INFO line with the class name of the error only. `appicon.shapes` checks the 64 px mark: it must cover from 3 % to 97 % of its square, and on a plate the picture that is cut out must be 2 % of the square or more; else the circle and one INFO line. The rectangle clips of an SVG are applied only when the clipped drawing keeps 50 % or more (10 % before Task 17) of the opaque area of the drawing without the clip (a clip for the tile); else the drawing stays as Qt draws it (a clip for one detail). A PNG larger than 256 px is scaled down to 256 px before the work on each pixel: a 1024 px PNG took 607 ms and a 2048 px PNG 2440 ms from the lookup to the finished icons; now 43 ms and 51 ms. The look of the tray icon did not change: the 22 px mark is equal, pixel for pixel, to the one of before.
- **Not done.** A person did not yet look at the icon in the real panel.

## Change on 2026-11-18: more than one monitor

Request of the user: "I can't drag the window to the other monitor, I need to have this feature."

Measured on this machine (KWin 6.8.2, layer-shell-qt 6.8.2, PySide6 6.12; DP-1 1920x1080 at (2560,360), 144 Hz; HDMI-A-1 2560x1440 at (0,0), 240 Hz; traces `t17-trace-*.txt` in the workspace):

- **How a layer surface gets its output.** layer-shell-qt gives `get_layer_surface` the `wl_output` of `QWindow.screen()` at the time the surface is made. `QWindow.setScreen()` on a visible window changes only the Qt property: no request goes to the compositor (all Wayland screens are siblings, so Qt does not make the window again). Hide, `setScreen`, show makes a new surface on the other output. The attached property `LayerShell.Window.screen` cannot be set from QML (`Cannot assign QObject* to QScreen*`: QML has screen descriptions, not `QScreen` objects).
- **Margins outside the output.** KWin does not keep a layer surface inside its output. A left or top margin larger than the output, or a negative one, puts the surface on the neighbour monitor: the trace shows `wl_surface.leave` for the old output and `wl_surface.enter` for the other, with no new surface. Qt then also changes `QWindow.screen()`.
- **So the drag needs no new surface.** During a drag the surface stays on its output and only the margins change, as before. The implicit pointer grab stays with the same surface. What happens to a grab when the surface is destroyed during a drag was not measured (it needs a real pointer), and the design does not depend on it.

Design:

- **Position model.** `screenName` is the screen that holds the panel; `posX` and `posY` are from its top-left corner; `home` is that screen as a rectangle in the desktop. `state.json` has `x`, `y` and `screen`. A file without `screen` (older version) is read as before: the position is for the screen that Qt gives the window. A saved screen that is not connected: the screen of the window and the default corner. The clamp, the default corner (16 px) and the bottom clamp of an open group use `home`.
- **Drag.** `dragPlace` gives the nearest place to the wanted one where the four corners of the panel are on a screen. So the panel crosses an edge that two screens share and stops at an edge with nothing behind it. At the release, `settle` gives the panel to the screen that holds its centre, clamps it into that screen and saves. When that screen is a different one, `rehome` hides the window, sets its screen, and shows it: a new layer surface on the new output, at the same place of the desktop.
- **Tray.** "Move to next screen" (only with more than one screen) calls `moveToNextScreen`: the next screen of the list, the same distance to the nearer side edge and to the nearer of the top and bottom edges, clamped, saved.
- **Hot-plug.** When layer-shell-qt closes the window (the compositor closed the surface) or the list of screens changes, `recover` runs 200 ms later: a panel whose screen is gone goes to the screen that the window has now, and a window that the compositor closed shows again. A window that the user hid stays hidden. Nothing is saved, and nothing moves when a monitor is added. Tested with made-up screens and with `QWindow.close()`; not with a real cable.
- **Drag rate.** The shortest time between two margin changes is now two frames of the current screen: `minMoveMs = 2000 / refreshRate`, from 4 ms to 20 ms, 16 ms when not known (240 Hz: 8.3 ms, 144 Hz: 13.9 ms, 60 Hz: 20 ms). Reason: Qt sends the commit with a new margin only after the frame callback of the frame before, so a pointer event can come one frame after a move and still be relative to the old place. `follow_refresh_rate` follows the screen of the window and also `refreshRateChanged` of that screen. Only a drag with a real mouse can confirm the feel.
- **Not verified.** A drag across the monitors with a real mouse. The blink at the release when the panel changes its monitor. A monitor that is disconnected by its cable.

## Change on 2026-11-18: push events and row order

Request of the user: "use push events, and named agents first." Before, a new status showed up to one second late.

- **The stream.** `herdr-core events --json` (the API method `events.subscribe` with no filter) writes one JSON object in each line. The first line is the answer of the subscription (`channel`, `seq`, `terminals`: all terminals, 21 to 24 kB here). Each later line is a notification: `method` is `event` (`params`: `type`, `seq`, `terminal`, `data`) or `heartbeat` (each 15 s, `params.seq` only). Types seen with the user's agents: `status`, `turn`, `title`, `labels`, `doc`, `foreground`, `created`, `finished`, `size`. Measured: 0.24 and 0.26 lines each second in 120 s and 180 s (heartbeats included); in a 300 s run, some seconds with about 10 `title` events each second while an agent worked.
- **An event is a trigger, not data.** `bellwether/events.py` runs the one child process and reads its output in a thread. It looks only for the end of a line and for the fixed start of a heartbeat line. It does not parse, keep or log a line: the lines hold terminal titles and folders. Each line that is not a heartbeat sets the wake of the poll thread, and that thread reads `herdr-app ls` now. Many events during one read start one more read, never a queue. A read that an event starts begins 0.25 s after the start of the read before it at the least (`FLOOR`), so a stream of title changes gives about four to five reads each second at the most (the events start four, 240 in 60 s on the made-up clock of the tests, and the reads of the schedule come between them). An event that comes alone is read usually a few milliseconds after the event, at most 0.25 s after it. The brief asked for 30 to 50 ms; the title bursts are the reason for 0.25 s (first 0.1 s, changed in fix round 1).
- **The app is later than herdr-core for some changes.** Measured for 9 changes: `herdr-app ls` showed the new status 4, 19, 31, 40, 116, 342, 490, 497 and 1495 ms after the event. So one read at the event is not sufficient. After a wake the poll thread reads again 0.15, 0.4, 0.55, 1.0 and 1.6 s later (`AFTER`); a new event starts this list again. A status that the app holds back shows when the app has it, not a few milliseconds after the event.
- **The read by time stays, slower.** With a healthy stream: one read each 2 s (`SLOW_INTERVAL`), so a change that gives no event, or that the app shows later than 1.6 s after its event, shows after 2 s at the most. In 300 s, no change of `herdr-app ls` came without an event in the 2 s before it, and the change from done to idle after the person looked at the agent came with a `labels` event of that terminal. But that was seen one time only, so the interval is 2 s and not 5 s (5 s in the first version, changed in fix round 1). With no healthy stream: one read each second, as before.
- **Health and retries.** The stream is healthy from the first line of a child to the end of that child. The backoff starts again at 1 s only after a stream that lived 20 s (`MIN_LIFE`): a child that writes one line and ends at each start (for example an error line) is tried after 1, 2, 5 and then each 10 seconds, and "events: connected" is then written only when a child has lived 20 s. An error at the start of the child (also between fork and exec) is a failed start with the same backoff. The child ends, its pipe closes, or no byte comes for 45 s (three heartbeats): the stream is not healthy at once, the poll thread is woken and reads each second, and the next child starts after 1, 2, 5 and then each 10 seconds. A new stream starts a read at once (its first line). The log gets "events: connected", "events: lost (exit code N)" and "events: retry in Ns"; a long time with no stream writes each of these one time. One thread starts and reaps the child, so there is never more than one.
- **The child does not outlive the widget.** `Backend.stop()` (the existing `aboutToQuit` path) stops the event thread, which sends SIGTERM to the child (SIGKILL after 2 s) and reaps it. The child is started with `prctl(PR_SET_PDEATHSIG, SIGTERM)`, so the kernel ends it when the widget is killed. Its input is `/dev/null`, its error output is discarded, there is no shell.
- **Measured with the real app and core (a scratch program with no window).** The numbers of this point are from the first version (floor 0.1 s, read by time each 5 s). Event to applied snapshot: median 3.9 ms, largest 103 ms (the floor), 8 events. Reads: 18 in a quiet minute, 40 in a minute with 7 events, 60 with the old polling. With the values of fix round 1 (floor 0.25 s, each 2 s): 30 reads in a quiet minute. Processor time of the process and its children in 60 s: 0.19 s quiet and 0.47 s with events, 0.40 to 0.44 s with the old polling. So the widget does less work when nothing changes, and about the same while agents change.
- **Not verified.** What the stream does when herdr-core stops or restarts (the core of the user was not stopped). The code handles an exit, a closed pipe and a silent stream. The notification `missed` of the API was not seen; it is a line as the others, so it starts a read.
- **Row order.** In an open group: first the agents whose terminal has a name, in the order of the name; then the agents with no name, in the order of the label that shows; both without regard to capital letters. Rows with the same text are in the natural order of the address (`t2` before `t10`). The rule "rows that look the same also show the address" is applied after the sort. Made-up example: names "Mid" and "zed", and no name in the spaces "alpha", "Beta", "zeta" give Mid, zed, alpha, Beta, zeta.

## Change on 2026-11-18: options window and layout skins

Request of the user: "we need a options menu for it. this option menu must be open by the system tray and it must let us chosse the UI version." The UI versions are the five approved designs in `design/layouts/`: A Refined list, B Tiles, C Techno / HUD, D Signal strip, E Ring. Step 1 separated the behaviour of the panel from its look, made the options window, and made the layout a saved value that changes while the widget runs, with Layout C as the only skin. Step 2 (Task 21, the subsection "Step 2" at the end of this section) built the skins A, B, D and E against the contract of this section, and gave the options window the look of the layout that shows.

### The parts

| File | Owns |
|---|---|
| `bellwether/ui/Main.qml` | The window: layer-shell properties, place and screen (`posX`, `posY`, `screenName`, `rehome`, `settle`, `moveToNextScreen`, `recover`), `clampPosition`, the one pointer handler (click or drag, hover, wheel), the drag step `minMoveMs`. It shows the skin in a `Loader` and has the size of the skin. No drawing. |
| `bellwether/ui/PanelModel.qml` | The controller: the state and the rules that every skin uses (the list below). The only QML file other than `Main.qml` and `Options.qml` that reads `backend` (since 2026-11-19 also `skins/ThemeBase.qml`: see "Change on 2026-11-19: custom look"). |
| `bellwether/ui/AgentList.qml` | The agent rows of one group: at most 8 rows on the screen, scroll with the wheel, the scroll position stays when new data comes. The skin gives the look of a row and an optional decoration. |
| `bellwether/ui/AgentRow.qml` | The base of one agent row: its size, its click target, its states (`failed`, `opening`, `hovered`, `last`) and its name for a screen reader. |
| `bellwether/ui/skins/<letter>.qml` | One skin: only drawing. `A.qml`, `B.qml`, `C.qml`, `D.qml`, `E.qml`. |
| `bellwether/ui/skins/<letter>Theme.qml` | The theme tokens of that skin: the values that the skin and the options window share. |
| `bellwether/ui/Options.qml` | The options window. |
| `bellwether/ui/previews/<letter>.png` | One picture of each design for the options window (360 px wide, shown 180 px wide). Made by `design/previews.py` from the real skins: the real panel, closed, with the counts 1, 2, 3 and 4, on a dark background. Run that script again after a change of a skin. |
| `bellwether/layouts.py` | The catalogue of the five designs (letter, name, one line), the default (`"C"`), and `built_skins()`: a design is built when `ui/skins/<letter>.qml` exists. |
| `bellwether/options.py` | `Options(engine).open()`: makes the options window at the first call, and shows the same window at each later call. |
| `bellwether/settings.py` | The state file. Each save reads the file and changes only its own keys. |
| `bellwether/backend.py` | New for QML: `layout`, `skinSource`, `themeSource` (the theme file of the layout that shows, for the options window), `layouts`, `setLayout(letter)`, `skinFailed()`, `saveScreen(name)`, signal `layoutChanged`. |

The controller is a QML object, not a Python object. Reasons: its rules were QML already (bindings to `backend.groups`, a `Timer`, a `Connections`), so they moved with no change of their text and the existing QML tests still check them; the values that a skin reads are bindings, so a skin needs no signal code; and Python keeps one job in the interface, the data (`backend`). The layout name and its file are in Python, because Python owns the settings file.

### The controller: what a skin can read (`PanelModel.qml`)

A skin gets the controller as its property `panel`. All of these are read-only for a skin, except the two functions.

- `online` (bool).
- `groups`: always four objects in the display order blocked, done, working, idle. Each has `state`, `label` ("Blocked"), `count`, `attention` (the state is blocked or done), `alert` (`attention` and `count > 0`: the mock-ups call this `attention`), `color` ("#rrggbb"), `share` (`count / total`, 0 to 1, for a share bar or a ring), `start` (the sum of the shares of the groups before it in this order: where its part of a ring or a strip starts; a group with no agents has it too, for example 1 for idle when idle is the last group and has no agents; 0 for every group when there are no agents and offline) and `agents` (the rows, sorted by the backend: `key`, `icon`, `label`, `detail`, `address`, `spoken`). Offline every count is 0. A skin that must keep its items when the data changes uses `Repeater { model: 4 }` and `panel.groups[index]`, as `C.qml` does.
- `total` (0 offline), `parts` (the number of states with an agent).
- `topState` ("blocked", "done", "idle", "working", "none", "offline"), `quiet` (true for "none" and "offline": the skin then uses its own neutral colour), `topColor`, `topLabel` ("Blocked", "No agents", "Offline"), `topCount`, `topBadge` ("1 blocked", "No agents", "Offline").
- `cells`: the states of the lit cells of a cell bar (one for each agent up to `cellLimit` = 60, then shares, and a state with an agent keeps one cell). Empty with no agents and offline.
- `stateColors`: the colours by state name (since 2026-11-19 from `backend.stateColors`: the user can change four of them).
- `pixelScale` (since 2026-11-19): `max(1, scale of the custom look)`, for a part of a skin that is made of pixels (the `sourceSize` of an icon, a canvas).
- `openState` ("" or a state): one group is open at a time. `openGroup`, `openLabel`, `openColor`, `agents` (the rows of the open group), `maxAgentRows` (8, read-only also for a test: a test makes a second controller with a different cap through an initial property; since 2026-11-19 it is `min(rowLimit, rowRoom)`: fewer than 8 when 8 rows make the panel taller than its screen), `shown` (rows on the screen), `scrolls` (the open group has more rows). `rowsFor(count)` is the one place that applies the cap of 8 rows: the controller and `AgentList` both use it.
- `opening`: the key of the agent that a jump goes to now, or "".
- `failedColor` (`#f28b82`) and `openingColor` (`#8ab4f8`): the colours of a failure message and of "opening…", the same in every layout (since 2026-11-19: the colour of the status blocked, and the accent of the custom look).
- `failedKey`, `failedMessage`: the last failed jump, for 3 seconds. `failedAlone`: true when the failed agent has no row (it is gone, or Herdr is offline).
- `hoverItem`: the status item or agent row under the pointer (the window gives it with `hover(item)`). It is null for a status item that cannot open, so a skin needs no check of its own: `panel.hoverItem === item` is the whole rule for the pointer look.
- `canOpen(state)`: true when a click opens the group (Herdr answers and the state has an agent). For a skin that draws an affordance (a chevron, a cursor). A status item that cannot open is inert: no pointer look, no change on a click.
- `toggle(state)`: open the group, or close it when it is open. It does nothing for a group with no agents and offline.
- `jump(key)`: show the agent in the Herdr app. One jump at a time: the backend ignores a call while a jump runs.
- Helpers: `groupOf(state)`, `countOf(state)`, `stateOf(key)`, `spokenStatus(group)` ("Blocked, 1 agent"), `pad2(n)`, `faded(hex, alpha)` (a colour value), `tint(hex, alpha)` (the text "#aarrggbb" with an 8-bit alpha, as the mock-ups make it: use it where a picture must be equal to a mock-up).
- `strip(width, gap, minimum)`: the parts of a share strip, one `{x, width}` for each group. In proportion to the counts; a group with an agent is never narrower than `minimum`; a group with no agents has no width and no gap.
- `ring(gap, minimum)`: the arcs of a share ring, one `{start, sweep}` in radians for each group, `start` from the top, clockwise. The arcs and the gaps fill the circle; a group with an agent is never shorter than `minimum`; one group alone is the full circle.

Rules that the controller applies with no help of the skin: the open group closes when its count goes to 0 and when Herdr goes offline; a failed jump opens the group of its agent one time, and again only when that agent goes to a different group (`failedShownIn`); the message ends after 3 seconds.

### The skin contract

A skin is one file `bellwether/ui/skins/<letter>.qml`. The file name is the letter of the design in `layouts.py`. When the file exists, the design is built: the options window lets the user choose it. No list has to change.

A skin must:

1. Have an `Item` as its root, with `import ".."` and `required property PanelModel panel`.
2. Set `implicitWidth` and `implicitHeight` to the size of the panel that it draws, for every state. The window takes this size. The size must never be 0.
3. Mark its click targets with the property `hitRole` (the one hit-test convention):
   - a status row, tile, tab or legend row: `readonly property string hitRole: "status"` and `readonly property string stateName` (the state). A click calls `panel.toggle(stateName)`.
   - an agent row: use `AgentRow` (it has `hitRole: "agent"` and `key`). A click calls `panel.jump(key)`.
   - the list that scrolls: use `AgentList` (its `Flickable` has `hitRole: "scroll"`). The wheel calls `scrollBy`.
4. Show the agents of the open group with `AgentList`, and give it a `delegate` that is an `AgentRow` with `view` set to the list. Two ways: one list for the open group (the default `stateName: panel.openState`; for the skins that show the agents below or beside the statuses: B, D, E), or one list in each group with `stateName` set to the state of that group (A, C). A group that opens starts at its first row, in both ways: a list that closes loses its rows and its scroll position, and one list that gets a different group goes to the top.
5. Show the note of each row in the place of its detail: `noteText` of the `AgentRow` (the failure message, "opening…", or the detail), in `panel.failedColor` when `note` is "failed" and in `panel.openingColor` when it is "opening". The rule (a failure comes before "opening") is in `AgentRow`; the skin chooses only the colour of the detail, the place and the font. Show `panel.failedMessage` in a line of its own while `panel.failedAlone` is true. Show a scroll hint while `longer` of the list is true. Show the offline state and the state with no agents. The mock-ups have no line for `failedAlone` and no look for the row under the pointer (`hovered` of an `AgentRow`, `panel.hoverItem === item` for a status item): the skin adds them in its own style.
6. Give each status item `Accessible.role: Accessible.Button`, `Accessible.name: panel.spokenStatus(group)` and `Accessible.onPressAction: panel.toggle(stateName)`. `AgentRow` has its own.

A skin must not: read `backend`; have a `Timer`, a `Connections` or other code for rules (a handler that only draws is allowed: `Canvas.onPaint`, and `onXChanged: canvas.requestPaint()`); have a `MouseArea` or other pointer handler; change the place or the size of the window; keep state that must stay when the skin changes (that state is in the controller).

How the window finds a target: from the root of the skin it takes `childAt(x, y)` again and again, and stops at the first item whose `hitRole` is one that it looks for ("status" and "agent" for a click and for the hover; "scroll" for the wheel). So `childAt` decides: at each level it is the top visible child with a size that holds the point. An item that lies over a target and is not its child takes the click away. Put a decoration over the rows (a scroll track, a fade) in the `overlay` of the `AgentList`: its parent has no size, so the search does not find it, and the click or wheel turn goes to the row below it. For the same reason the overlay cannot use anchors to its parent or `parent.width`: it is at (0, 0) of the list, and it takes its place and size from the `width` and `height` of the list (`x: agentList.width - 3`).

`AgentList` (an `Item`): in `panel` (required), `stateName`, `rowHeight` (default 28), `delegate`, `overlay`. Out: `group`, `open`, `count`, `shown`, `longer`, `first` (the number of the first row on the screen, from 0), `atEnd`, `contentY`, `contentHeight`. Its `implicitHeight` is `shown * rowHeight`. The skin sets its width.
`AgentRow` (an `Item`): in `view` (required, the list), and `modelData` and `index` from the list. Out: `key`, `failed`, `opening`, `note` ("failed", "opening" or ""), `noteText` (the text for that place), `hovered`, `last`. Its size is the width of the list and `rowHeight`. The skin puts the drawing in it as children.

The example of a second skin is `tests/skins/T.qml` (40 lines, used only by the tests): four status rows and one list for the open group. The tests of the layout change in `tests/test_qml.py` use it.

### Changing the layout

- `backend.setLayout(letter)` sets `backend.layout`, tells `layoutChanged`, and saves the key `"layout"` in `state.json`. A letter with no skin file is ignored.
- `Main.qml` then loads the new skin in the same `Loader` (`setSource` with `panel`). The window is the same window: it is not hidden, the layer surface is the same, and the place, the screen, the open group and the online state stay (they are in the window and in the controller). The window takes the new size with one `setGeometry` call: the trace has one `zwlr_layer_surface_v1.set_size` and then one commit for each change of the layout. `clampPosition` then keeps the panel on its screen, and a panel at the default corner stays at the corner with its new width.
- The window is not visible until the first skin is there: a layer surface must not have the size 0. So the start makes one surface, with its size, its margins and its output (before this change the window showed first and got its place after).
- A skin that does not load (an error in its file): `backend.skinFailed(reason)` writes one line to the log (the letter and the status of the loader, no path) and shows Layout C now, in memory only. The saved layout is not changed, so the next start tries it again. When the user then chooses a layout in the options window, also C, that choice is saved.
- When `skins/C.qml` itself is missing at the start, the log has one line: "the skin file of the default layout C is missing: the panel cannot show".
- The window ignores a skin size of 0 or less (`takeSize`): the layer surface keeps its last size.
- At the start: no `"layout"` key (a file of an older version) gives C with no log line. A value that is not text, a letter with no skin file, or an unknown letter gives C with one log line ("the saved layout is not available: the layout is C"); the file is not changed.
- `state.json` now has `x`, `y`, `screen` and `layout`. Saving one of them keeps the others, and keeps keys that this version does not know.

### The options window

- The tray menu has "Options…" above "Hide widget". It opens one window. A second click shows the same window: when it is behind a different window, the widget hides it and shows it again, because on Wayland a program cannot raise its window without a click in one of its own windows, and a window that shows again comes to the front.
- It is a normal window: `Options.qml` has no `LayerShell` properties, and it is loaded with the same engine (`engine.load`). Trace on this machine (Task 21, `t21-trace.txt`): `xdg_surface.get_toplevel`, `set_title("Bellwether — Options")`, `set_min_size` and `set_max_size` with the same size (1076 × 344), and no decoration request: the window is frameless and draws its own header (see "Theme tokens and the look of the options window"); the panel stays the one `zwlr_layer_surface_v1`. The window takes the keyboard focus (`active` true); the panel never does. `QT_WAYLAND_SHELL_INTEGRATION` is not set.
- Esc and the close control in the header of the window hide the window. The widget continues (`setQuitOnLastWindowClosed(False)`).
- Content: a column of sections. The first section is "Layout" (since 2026-11-19 the sections "Size", "Text" and "Colours" follow, see "The controls in the options window"): five cards in a row. A card has the picture, the letter and name ("C — Techno / HUD"), one line of text, and a tag: "SELECTED" (the card also has a blue border), or "COMING NEXT" for a design that is not built (the card is dim and cannot be chosen).
- A click on a built card applies the layout at once and saves it.
- Keyboard: Tab and Shift+Tab move between the built cards (a white ring shows the focus), Enter, Return and Space select, Esc closes. At each open the focus is on the selected card. Each card has a name for a screen reader: "Layout C, Techno / HUD, selected", "Layout A, Refined list, coming next".

### Review findings that this change fixes

- Data source: one failed read of `herdr-app ls` no longer changes the source. The client returns the last list of the app (no read of herdr-core, not offline). Two failed reads one after the other change the source to herdr-core; the first answer of the app changes it back and starts the count again. With no list of the app yet (the start with the app closed), the first failed read goes to herdr-core at once.
- "events: connected" is now also written for a later stream that lived 20 s and then ended, or was silent, before its next line.
- The read rate, stated more exactly: a read that an event starts comes usually a few milliseconds after the event and at most 0.25 s after it; a stream of events gives about four to five reads each second at the most (four that the events start, and the reads of the schedule between them).
- A start that ends because a widget runs already writes "bellwether: already running" to its error output, so `start.log` has the line also when no log folder exists.
- "Move to next screen" for a panel at its default corner saves only the screen (`backend.saveScreen`): the file then has no `x` and `y`, so at the next start the panel is at the default corner of that screen and follows the width of the screen and of the layout.
- Not done: the reads of the schedule still start after the first line of a new event stream (the answer of the subscription). The first line is also the wake that starts the read of a new stream, and three tests state that contract; a change needs a second kind of wake between `events.py` and `backend.py`.

### Step 2 (Task 21): the skins A, B, D and E

Each skin was built from its mock-up `design/layouts/<letter>-*.qml` and checked against it: the real panel (real `Main.qml`, real backend, made-up data) and the mock-up, rendered off screen at scale 2 in the ten scenes of the six approved frames, compared pixel by pixel. Result for each of A, B, D and E: 0 different pixels in 9 scenes. The scene with 12 idle agents is different only in the order of the rows (decision of the user: agents with a name first). Layout C stayed pixel-identical to step 1 in 25 states.

What every skin adds to its mock-up (the mock-ups are static): a lighter plate under the pointer for a status item that can open and for an agent row; a line for a failed jump whose agent has no row; a scroll hint that follows the scroll position; the row layout with no icon.

- **A, Refined list** (`A.qml`, 296 px wide; 168 px high closed, 54 px offline). One `AgentList` in each group, under its status row. Count badge: filled in the colour of the status for `group.alert`. Scroll hint: a thumb at the right and a fade over the last row while more rows are below, both in the `overlay`. Controller values: `groups`, `openState`, `topColor`, `quiet`, `failedAlone`.
- **B, Tiles** (`B.qml`, 304 × 176; offline 206). Four tiles in a grid; a tile is solid for `group.alert`. One `AgentList` in a card below the grid; the card header shows `openLabel` and the number of agents ("3 agents"), or the rows on the screen for a long group ("1–8 of 12", from `first`, `shown` and `count` of the list). The open tile has a border and a chevron; on a solid tile they are dark (in the mock-up they have the colour of the tile and cannot be seen). Offline the tiles stay, with "–" for the counts.
- **D, Signal strip** (`D.qml`, 320 × 122, the same offline). Headline: `total` and `topBadge` ("1 blocked", "No agents"). Strip: `strip(296, 3, 8)`; with no agents and offline one neutral track; the segments of the other statuses go dim while a status is open. Four tabs with the numerals; a lamp for `group.alert`. One `AgentList` below; its scroll hint is a footer under the rows: "4 more ↓", and "4 above ↑" at the end.
- **E, Ring** (`E.qml`, 312 × 128, the same offline). A `Canvas` draws the ring from `ring(0.07, 0.10)` (its handlers only draw: `onPaint`, and `requestPaint()` when the arcs, the open status or `online` change). The open status has a thicker arc and the others go dim. Centre: `total` (the numeral gets smaller above 99 and above 999), or "off". With no agents one grey ring; offline a ring of dashes. The legend rows are the status items. One `AgentList` below, with a thumb and a fade as in A. The mock-up shows 8 px of the ninth row under the fade; the shared list shows exactly 8 rows.

A long group fits a screen of 1080 px in every skin: the highest panel is B with 460 px.

### Theme tokens and the look of the options window (Task 21, Part 3)

Request of the user: "remember that this option windows should have the same window style as the main one".

- Each skin has a file `skins/<letter>Theme.qml`, a `QtObject` (since 2026-11-19 a `ThemeBase`) with the tokens of the list `THEME_TOKENS` in `bellwether/layouts.py`: `panelColor`, `frameColor` (the neutral frame), `frameWidth`, `radius`, `itemRadius`, `lineColor`, `textColor`, `dimColor`, `faintColor`, `accentColor`, `selectedColor`, `hoverColor`, `fontFamily`, `titleSize`, `bodySize`, `smallSize`, `letterSpacing`, `uppercaseTitles`, and `decoration` (a `Component` for a frame ornament that fills its parent and has a colour property `tone`, or null; Layout C: the four corner brackets). A test fails when a theme file does not have a token.
- The skin makes one instance (`CTheme { id: theme }`) and uses the tokens where a value is the same thing. A value that only that design has stays in the skin. A skin reads the token for its status title (`titleSize`), its agent label (`bodySize`), its small texts and the detail (`smallSize`), and its colours of panel, frame, text, dim and faint text, and of the plate under the pointer; a test with other token values in a copy of the theme (`tests/test_skins.py`) finds a text that keeps a literal. Exceptions, each a size of that design: the tab labels of D (11 px; the `titleSize` of D, 13, is used only by the options window) and the detail of C (11 px; the `smallSize` of C, 10, is its header). (Since 2026-11-19 these two have tokens too, `labelSize` and `detailSize`, and no skin has a text size of its own.) The rule that picks the font family is in `skins/fonts.js` (`first(wanted, fallback)`), one copy for the five theme files. Layout C also has `neutralColor` (`#6b747d`): its corner brackets and its header with no agents and offline, and the brackets of its options window. A new skin needs its theme file; a skin with no theme file gets the tokens of Layout C in the options window.
- `backend.themeSource` is the theme file of the layout that shows. `Options.qml` loads it and reads only tokens: frame, header, fonts, colours, the selected and the hover look of a card, the focus ring. The frame has `frameColor`, never the colour of a status: the options window does not show a status. In Layout C the window and the selected card have the corner brackets.
- The window has no title bar of the system: `Qt.Window | Qt.FramelessWindowHint`, transparent background (round corners stay clean). It is still an `xdg_toplevel`; the trace has no decoration request for it, it gets the keyboard focus (`wl_keyboard.enter` on its surface), and the panel stays the one layer surface. Its header draws the title (capitals when `uppercaseTitles`) and a close control. A press in the header that moves 6 px or more sends `systemMoveRequested`, which calls `startSystemMove()`: the compositor moves the window, and the widget has no position code for it.
- The size of the window (1076 × 344) and the places and sizes of the cards are the same in every theme, so a card stays under the pointer when a click changes the theme.

### Not verified

- A person has not yet opened the options window from the tray icon with a real mouse, has not yet moved it by its header, and has not yet looked at it on the screen in its new look. The checks used the window's own image, synthesized keys and clicks, and the protocol trace.
- A person has not yet looked at the layouts A, B, D and E on the screen. The checks compared images of the real panel with the mock-ups.
- The options windows of A, B, D and E look much alike (round frame, the same font and colours; the radius and the title size are different): these four designs share their colours and their font. Only Layout C has a different font, capitals and an ornament.
- The options window has the application name of the Python program ("python") and no icon of its own in the task bar.

## Change on 2026-11-19: custom look

Request of the user: "now let's include more customization options in the settings. like changing the window size, font size, font family and colors". Decisions of the user: the window size is one scale from 75 % to 200 % for the whole panel; one set of values for all five layouts; the colours that can change are the four status colours, the background, the text, the frame and the accent; one "Reset to defaults".

The work has two steps. Step 1 (Task 22, this section) is the engine: the saved values, the interface of the backend, and the panel, the tray icon and the options window that follow the values while the widget runs. Step 2 (Task 23) adds the controls to `Options.qml` (see "The controls in the options window") and fixes the review findings of step 1; the text below has those corrections. A person can also change the look in `state.json` (and restart the widget).

### The saved values

`~/.config/bellwether/state.json` has four more keys, beside `x`, `y`, `screen` and `layout`:

| Key | Type | Default | Valid |
|---|---|---|---|
| `scale` | number | 1.0 | 0.75 to 2.0. A number out of the limits is clamped. |
| `fontScale` | number | 1.0 | 0.8 to 1.4. A number out of the limits is clamped. |
| `fontFamily` | text | "" (the font of each layout) | A family of the list `backend.fontFamilies`. |
| `colors` | object | {} | Keys: `blocked`, `done`, `working`, `idle`, `background`, `text`, `frame`, `accent`. Values: `#rrggbb`; for `background` also `#aarrggbb`. A role with no key has the colour of the layout. |

Rules (`bellwether/settings.py`: `load_look`, `save_look`, `valid_color`, `clamped`):

- A file without these keys works as before this change.
- The two numbers have two decimal places.
- A value that is not valid is ignored, and its default applies: a value of the wrong type (a number as text, `true`, `null`, NaN), a colour that is not `#rrggbb` (or `#aarrggbb` for the background), a role that is not one of the eight, a font family that this system does not have. The valid values of the same file apply. The log gets ONE line for the file, with the keys only: "the saved custom look has values that cannot be used: scale, colors.text, colors, fontFamily". A colour is named `colors.<role>`; a role that is not one of the eight is named `colors` (its name is not written: a file that a person changed can hold anything). A start does not change the file.
- A value at its default has no key in the file. So after "reset everything" the file has none of the four keys.
- Saving the look keeps `x`, `y`, `screen`, `layout` and the keys of a later version, and the reverse.
- A save writes only what changed (`save_look(look, path, changed)`; the backend keeps the names of the changed values until the save: `scale`, `fontScale`, `fontFamily`, `colors.<role>`). Everything else in the file stays as it is: a `fontFamily` that this system does not have now (it applies again when the font is installed), a colour role of a later version, a value that was not valid at the start. "Reset everything" (`resetLook`) is the one exception: it removes the four keys with all that they hold. A save that changes nothing does not write the file and does not make it.

### What each value does

**scale.** The window shell applies it one time for every skin (`Main.qml`): the `Loader` of the skin has a `Scale` transform from its top-left corner, and the layer surface has the size `ceil(implicit size of the skin × scale)` (`scaled()`; 320 × 1.1 is 352, not 353). A skin does not know the scale: its sizes are the pixels of the design.

- The pointer handler works in pixels of the screen: the press must move 6 px of the screen to be a drag, and the panel moves as far as the pointer. For the hit test the handler maps the point to the skin (`mapFromItem`), so the transform is in the map.
- The saved place is the top-left corner. After a change of the scale `clampPosition` keeps the panel on its screen; a panel at the default corner stays at the corner. A change of the scale is one new size: the trace has one `zwlr_layer_surface_v1.set_size` and one commit.
- Sharp at every scale: a text is drawn from its outlines at the scale (the default text rendering of Qt Quick; no skin sets `renderType`). A part that is made of pixels needs more pixels above the scale 1: `panel.pixelScale` is `max(1, scale)`; a program icon loads `16 × pixelScale` pixels (`sourceSize`), and the ring of Layout E draws on a canvas of `100 × pixelScale` pixels that is shown `1 / pixelScale` times smaller. Rectangles are drawn by the renderer at the scale.
- The scale does not apply to the options window.
- A panel is never taller than its screen. One rule, `fitRows()` in `Main.qml`: the lists show only the rows that fit: `panel.rowRoom` = (height of the screen ÷ scale − height of the skin without its rows) ÷ height of a row, from 1 to `panel.rowLimit` (8). `panel.maxAgentRows` is `min(rowLimit, rowRoom)`, and the group scrolls. `AgentList` gives the height of a row to the controller (`panel.rowHeight`). The rule runs before each frame (`onAfterAnimating`), when the items of the skin have their final places, so the height of the skin and the number of rows belong together; the same rule gives the rows back when they have room again. `takeSize()` does not give the window a size that is taller than the screen while a list can show fewer rows. On a screen of 1080 px, 8 rows fit at scale 2.0 in every layout with the font scale 1 (the highest panel is B with 920 px). With scale 2.0 and font scale 1.4 the lists show 7 (A), 5 (B), 6 (C), 7 (D) and 8 (E) rows.
- One new size for each change. The size of a skin can change two times and more in one step: with one list in each group (A, C) the list of the new group opens before the list of the old group closes, and a new font changes many heights one after the other. Before this change the window took each of these sizes, and a size on the way that was taller than the room below the panel moved the panel up for good. Now a new size of the skin calls `takeSize()` after the step, one time (`sizeLater()`, `Qt.callLater`). The trace has one `set_size` for a change of the scale, of the open group and of the font scale. Two sizes in one step are left in one case only: an OPEN list gets rows back (for example the font scale goes from 1.4 to 1.0 at scale 2.0 while the group shows): the window first takes the size with the fewer rows, and the size with all rows one frame later. A closed panel holds nothing back: when no list shows rows, `fitRows()` sets `rowRoom` to `rowLimit` again, so a group that opens after a change of the scale, the font, the screen or the layout gets one size (Task 23, M1: before, the low `rowRoom` of a large scale stayed while the group was closed, and the next open had two sizes in every layout; test `test_a_group_opens_with_one_new_size_after_a_change_of_the_look_while_it_was_closed`).

**fontScale.** Every text size of every skin is a theme token, and a theme token is `size(pixels of the design)`: `round(pixels × fontScale)`. A test fails when a skin has a number after `pixelSize:` (`tests/test_look_qml.py`), and a second test checks every text on the screen against its size at the font scale 1.

- New tokens for the sizes that only some designs have (in the theme file of the design): `numeralSize` (A 15, B 34, C 20, D 20, E 15), `labelSize` (B 12: the title of the card; D 11: the tab label), `detailSize` (B 11, C 11, D 11), `markSize` (B 14), `noticeSize` (C 13: "OFFLINE"; D 17: "Offline"; E 15: "off"), `headlineSize` (D 24; E 26, with `headlineMidSize` 21 above 99 agents and `headlineSmallSize` 16 above 999), `unitSize` (D 13, E 10: the word "agents"), `badgeSize` (D 12). This closes the two exceptions of Task 21 (the tab label of D and the detail of C).
- Boxes grow with a larger font and stay with a smaller one: `fit(pixels)` is `round(pixels × max(1, fontScale))`. The skins use it for the heights that hold text: status rows, agent rows, tiles, badges, tabs, the headline, the footer, the line of a failed jump. The width of a panel never changes; a long text elides. In Layout E the ring grows half as much as the rows (`(100 + fit(100)) / 2`), and the name in a legend row elides before it touches a large count. In Layout C the header drops the word "BELLWETHER" when the three parts do not fit, and then the total elides.
- The options window uses the same tokens, and `size()` and `fit()` for its own sizes: with a larger font its cards and the window get taller (344 px high at the font scale 1 before the controls of step 2, 647 px with them; the width stays 1076).

**fontFamily.** `family(font of the design)` in each theme file: the family of the user when it is set, in every layout and in the options window. Layout C is made for a monospace font: with a proportional font its columns are less even. Nothing is cut or over a different text (the tests check each layout with a proportional and a monospace family, also at the font scale 1.4).

**colors.**

- `blocked`, `done`, `working`, `idle`: `backend.stateColors`, which `panel.stateColors` gives to the skins (`groups[n].color`, `topColor`, `openColor`), and the tray icon. `offline` and `none` (`#5f6368`) do not change. `panel.failedColor` is the colour of `blocked` (as before: the same value).
- `background`: `panelColor`. `#rrggbb` keeps the opacity of the layout, `#aarrggbb` sets it. A plate inside the panel (the card of B, the footer of D: `insetColor`) is the custom background made darker (`Qt.darker`, 1.2).
- `text`: `textColor`, and every grey of a design, by one rule: **with a custom text colour a grey is that colour at a fixed opacity**. `dimColor` 62 %, `faintColor` 45 %, `hoverColor` the opacity of the design (8 %), and the greys that only one design has through `tone(colour of the design, opacity)`: `ghostColor` 35 % (the outline of an empty mark, a count of 0), C `markColor` 35 %, `guideColor` 28 %, `dotColor` 22 %, `hatchColor` 10 %, B `separatorColor` 12 %, D `trackColor` 15 % and `mutedColor` 80 %. So the user sets one colour. The glyph icons of the programs (one colour, drawn in the text colour) follow it too (see "The program icons").
- `frame`: `frameColor` and `lineColor` (and `neutralColor` of Layout C: its brackets with no agents).
- `accent`: `accentColor`; `selectedColor` is the accent at the opacity of the theme; `panel.openingColor` is `backend.colors.accent` (the controller has no colour rule and no colour value of its own).
- The ink on a solid plate. A text, a mark or a border on a solid plate of a status colour or of the accent is not text on the panel. `ThemeBase.inkOn(plate, dark, light)` gives it the dark ink (`darkInk`, `#202124`) or the light ink (`lightInk`, `#f1f3f4`): the one with the larger contrast to the plate (WCAG 2 relative luminance; the change is near a luminance of 0.2). Every status colour of the designs is light, so the designs keep their dark ink and their pixels. Users: the count in a filled badge of A; the label, the count, the mark and the border of a solid tile of B (`tile.ink`); the tag on the accent in `Options.qml` (its own dark ink, `#0b0e11`, as the second argument); the border of the preset in effect in the colour editor. C, D and E draw no text on a solid status or accent plate (their plates are tints, and the text on them has the status colour).
- Colour values that are not one of the roles, and stay: `#24ffffff`, the white veil under the pointer on a solid tile of B; in `Options.qml` `#05070a`, the backdrop of the pictures of the designs, and `#0b0e11`, the dark ink of the tag; in `ThemeBase.qml` the two inks; in `controls/ColorEditor.qml` the 16 presets. No other colour value is in a skin or a control.

### One mechanism: `skins/ThemeBase.qml`

Every theme file is a `ThemeBase` (before: a `QtObject`). A theme file states only the values of its design, each inside the helper of its kind; with no custom look a helper returns the value of the design, not changed:

```qml
ThemeBase {
    readonly property color panelColor: background("#f21f2023")
    readonly property color dimColor: dim("#9aa0a6")
    readonly property string fontFamily: family(Fonts.first([...], fallback))
    readonly property int titleSize: size(15)
}
```

| Helper | Returns, with a custom look |
|---|---|
| `size(pixels)` | `round(pixels × backend.fontScale)` |
| `fit(pixels)` | `round(pixels × max(1, backend.fontScale))` |
| `family(design)` | `backend.fontFamily`, when it is not "" |
| `background(design)` | the custom background; `#rrggbb` with the opacity of `design` |
| `inset(design)` | the custom background, darker by 1.2 |
| `text(design)`, `frame(design)`, `accent(design)` | the custom colour of the role, with the opacity of `design` |
| `dim(design)`, `faint(design)` | the custom text colour at 62 % and at 45 % |
| `tone(design, opacity)` | the custom text colour at `opacity` |
| `inkOn(plate, dark, light)` | (no role) `dark` or `light`, the one with more contrast to `plate` |
| `readable(wanted, plate)` | (no role) `wanted` when its contrast to `plate` is 3 or more, else `inkOn(plate)`. A `wanted` with an opacity is judged as it is drawn: mixed with the plate. |
| `solid(colour)` | (no role) the colour without its opacity |

New sentence of the skin contract: **`ThemeBase.qml` reads `backend` (the font scale, the font family, `colorOverrides`); a skin still reads only its `panel` and its theme.** A skin calls `theme.fit()` for a length that holds text. The files that read `backend` are now `Main.qml`, `Options.qml`, `PanelModel.qml` and `skins/ThemeBase.qml`. The context property `stateColors_` is gone: the controller reads `backend.stateColors`.

`bellwether/layouts.py` `theme_colors(file)` reads the default colours of the roles background, text, frame and accent from the text of a theme file (the tokens `panelColor`, `textColor`, `frameColor`, `accentColor`, each written as a colour text, alone or in the helper of its role), for `backend.defaultColors`. The background always has its alpha (`#aarrggbb`). The loaded QML theme is the truth: `test_the_default_colours_of_the_backend_are_the_colours_of_the_loaded_theme` loads each of the five theme files with no custom look and compares the four tokens with `theme_colors`. Only a file that cannot be read gives the colours of Layout C. A file that can be read and has a token with no colour text raises `ThemeColorError` (the name of the token): the function never gives the colour of a different layout in silence. The backend catches it, writes one error line for the file ("the theme file BTheme.qml has no colour that can be read for textColor") and then gives the options window the colours of Layout C, so the window still works; the test of the five real files fails on such a file. (Before Task 23 a token that could not be read took the colour of Layout C with no line and no failing test.)

### The interface of the backend (for the controls of step 2)

Properties (`backend.<name>` in QML):

| Member | Type | Signal | Meaning |
|---|---|---|---|
| `scale` | real | `scaleChanged` | The scale that applies now. |
| `scaleMin`, `scaleMax`, `scaleDefault`, `scaleStep` | real | constant | 0.75, 2.0, 1.0; the step of the slider, 0.05. |
| `fontScale` | real | `fontScaleChanged` | The font scale that applies now. |
| `fontScaleMin`, `fontScaleMax`, `fontScaleDefault`, `fontScaleStep` | real | constant | 0.8, 1.4, 1.0; the step of the slider, 0.05. |
| `opacityMin`, `opacityMax`, `opacityStep` | real | constant | 0.1, 1.0, 0.05: the limits and the step of the opacity slider of the background in the options window. A file can hold any opacity. |
| `lookIsCustom` | bool | `lookIsCustomChanged` | A value of the look is not its default: "Reset to defaults" has something to do. |
| `fontFamily` | string | `fontFamilyChanged` | The family of the user. "": each layout has its own font. |
| `fontFamilies` | list of strings | constant | The families that can be chosen: sorted with no regard to capitals, each one time. The fonts of the system that are not private, can have any size (no bitmap font) and have the Latin letters (so no symbol or emoji font). Read at the first use. |
| `colorRoles` | list of strings | constant | `blocked`, `done`, `working`, `idle`, `background`, `text`, `frame`, `accent`, in this order. |
| `colors` | map role → colour | `colorsChanged` | The colour of each of the eight roles AS IT IS DRAWN now: the custom colour, or the default of the layout that shows. `#rrggbb`. `background` is always `#aarrggbb`: a custom `#rrggbb` has the alpha of the layout that shows (custom `#102030` in Layout C: `#f0102030`; in Layout A: `#f2102030`). |
| `colorOverrides` | map role → colour | `colorsChanged` | Only the roles that the user changed, AS THEY ARE SAVED. A role is changed when it is a key of this map. `background` is `#rrggbb` (no opacity of its own: it keeps the opacity of each layout) or `#aarrggbb` (its own opacity in every layout). |
| `defaultColors` | map role → colour | `colorsChanged` | The colour of each of the eight roles with no custom look, for the layout that shows now. `background` is `#aarrggbb`, with the opacity of the layout (C `#f00b0e11`, A `#f21f2023`). |
| `stateColors` | map state → colour | `colorsChanged` | The six colours by state (`offline` and `none` too), for the controller and the tray. |

`colorsChanged` also comes after a change of the layout: the default colours are those of the layout that shows.

Slots:

| Member | Returns | Meaning |
|---|---|---|
| `setScale(real)` | bool | A number out of the limits is clamped. Two decimal places. |
| `setFontScale(real)` | bool | The same. |
| `setFontFamily(string)` | bool | A family of `fontFamilies`, or "" for the font of each layout. |
| `setColor(role, colour)` | bool | A role of `colorRoles` and `#rrggbb` (the background also `#aarrggbb`). Capitals are accepted and saved as small letters. |
| `resetColor(role)` | bool | One colour back to the default of the layout. |
| `resetLook()` | nothing | The scale, the font scale, the font family and every colour back to the defaults. With nothing custom it does nothing. The save then removes the four keys from the file. |

Each slot checks its value. A value that is not valid changes nothing, sends no signal, and the slot returns `false` (NaN and infinity; a family that is not in the list; a role that is not one of the eight; a colour of a different form). A valid value returns `true`, also when it is the value that applies already (then no signal and no save). A valid new value applies at once to the running panel, to the tray icon and to the options window, with its signal one time. A change of the layout keeps the custom look.

The save: 0.4 s after the last change (`LOOK_SAVE_DELAY`, one `QTimer` that starts again with each change), so a slider that moves writes the file one time, with the last value. `backend.stop()` (the program calls it before it ends: `aboutToQuit`) saves a change that waits. A process that is killed (SIGTERM, SIGKILL) can lose the changes of the last 0.4 s. A look that cannot be saved still applies, and the log gets "the custom look was not saved".

### The tray icon and the program icons

- The tray icon has `backend.stateColors[topState]`, and it changes with `colorsChanged`. The tray keeps at most 16 icons in its memory (a new colour makes a new icon).
- The program icons: the copy of a glyph icon in the cache (`~/.cache/bellwether/icons`) has the hash of its content in its name, and the colour is in the content. So a new text colour is a new file, never an old picture. `Icons.set_color()` forgets the file of each program, removes the copies that this run made in the old colour (the cache does not grow while the user tries colours), and the backend sends `changed`, so the rows get the new files. With no custom text colour the glyph icons are `#e8eaed` in every layout, as before.

### Not verified, and limits

- A person has not yet looked at the panel on the screen at a scale, with a different font or with custom colours. The checks used the window's own picture (off screen, and one picture from the real compositor at scale 2), the tests and the protocol trace.
- A person has not yet used the controls of the options window with a real mouse and keyboard, and has not yet looked at them on the screen. The checks used the window's own picture (60 sheets: five layouts in twelve states), synthesized pointer and key events, and the text audit.
- Layout E, a long group: the fade over the last row had square bottom corners that showed outside the round corner of the frame (also with the colours of the design, on a light wallpaper). Fixed in Task 23 (M6): the fade has the bottom corners of the inside of the frame (`bottomLeftRadius`, `bottomRightRadius` = `radius − frameWidth`). This is the one change against the approved pictures: 387 pixels in the two bottom corner areas of the long-list scene at scale 2.
- A failure message in a row with a large font takes the room of the name of that row (the name elides to nothing in A for the 3 seconds of the message).

### The controls in the options window (step 2, Task 23)

The window keeps the section "Layout" and has three more, and a footer. Its width stays 1076. Its height is the height of its content (647 px with the font scale 1 and nothing open; more with the colour editor or the list of fonts open, and with a larger font), and at most the height of the screen less 80 px (`roomHeight`, the height of the screen; a test gives its own). On a lower screen the sections scroll between the header and the footer (`scroller`, a `Flickable` that the wheel, a drag of the pointer or a finger, and the keyboard move; a thin thumb at the right shows the place, and a drag on it (a 16 px wide grip) scrolls too; a slider keeps its own drag). The header with the close control and the footer never scroll. The scale of the panel does not apply to the window; the font scale, the font family and the colours do, through the theme tokens.

The controls are components in `bellwether/ui/controls/`. They use plain Qt Quick items only (no `QtQuick.Controls`), read only theme tokens, and have every text size from `theme.size()`. They do not read `backend`: `Options.qml` binds their values to the backend and calls its slots. A static test keeps every text size of these files and of `Options.qml` to the forms of the skin rule (a token, `theme.size(n)`, a token + 1, the smaller of two, one of two by a flag), and every colour to a theme token, except the 16 presets and the documented literals (the `"#000000"` placeholders, the example of the hint, the tag ink and the preview plate of a card).

| File | What it is |
|---|---|
| `LookSlider.qml` | A track, the part up to the value in `accentColor`, a mark at the default value, a handle. The value comes from outside; the slider asks for a new value in whole steps (`moved`). A press on the track takes the value of that place, a drag follows the pointer, a double click asks for the default (`resetRequested`). Keys: arrows one step, Page Up and Page Down four steps, Home and End the ends. From a value between two steps the first step goes to the next step in that direction (94 % and Right: 95 %). |
| `SliderRow.qml` | One row of "Size" or "Text": the label, a `LookSlider`, the value in percent and the small "Reset" while the value is not the default. `Options.qml` gives the limits and the value from the backend. |
| `LayoutCard.qml` | One card of the section "Layout": the preview, the name, the description and the tag. It gets its layout and `selected`, and says `chosen`; `Options.qml` calls `setLayout`. |
| `LookButton.qml` | A text on a plate. Enter, Return and Space press it. `small` for the reset marks. |
| `ColorSwatch.qml` | One colour: a chip with the colour in effect, the name, the value (`#rrggbb`, and the opacity in percent for the background), and the button "Reset" only while the colour is custom. The swatch of the open editor has the selected look. |
| `ColorEditor.qml` | Inside the window, below the row of swatches: a palette of 16 presets (one stop of the Tab key; the arrows move, Enter and Space choose), the field "Hex", and for the background the slider "Opacity" (`backend.opacityMin`, `opacityMax`, `opacityStep`: 10 % to 100 %, steps of 5 %). "Done" closes it. |
| `FontChooser.qml` | A button with the family in effect. It opens, below it and inside the window, a filter field and a list of six rows: "Layout default" first, then `backend.fontFamilies`. Each family shows in its own typeface; the list makes only the rows on the screen. |
| `SectionTitle.qml`, `FocusRing.qml` | The title of a section or of a group, and the ring of the keyboard focus. |

The sections:

- **Size** (left column): the slider "Panel size", with `backend.scaleMin`, `scaleMax`, `scaleStep`, `scaleDefault` and `scale`; the value ("125 %"); the button "Reset" while the value is not the default. The panel changes while the slider moves; the backend saves at the end of the burst.
- **Text** (right column): the slider "Text size" (the `fontScale` members), and "Font" (the chooser). Typing in the filter field shows the families with that text in their name (capitals do not matter). Down and Up move the mark, Enter chooses the marked row, a click chooses a row. With a filter that no family matches, Enter chooses nothing.
- **Colours**: one row of eight swatches in two groups, "Status" (the first four of `backend.colorRoles`) and "Panel" (the other four). A swatch opens the editor for its role (`options.editingRole`); the swatch of the open editor closes it; a different swatch moves the editor to its colour.
  - A preset or a valid text in "Hex" calls `setColor` at once. The field takes `#rrggbb` and `rrggbb`, in capitals too. While the text can still become a colour (`#12`), nothing is shown. A text that cannot become a colour, or a text that is not a colour when the user presses Enter, changes nothing and shows "Use a colour like #8ab4f8" under the field. The field shows the colour in effect again when the keyboard leaves it.
  - The background: without a choice of the opacity a new colour is saved as `#rrggbb` (it keeps the opacity of each layout). After the user moved "Opacity" the colour is `#aarrggbb`, and a later preset or text keeps that opacity (`ownOpacity`: the saved override has 9 letters).
- **Footer**: a note, and "Reset to defaults" (`resetLook`). It is disabled while `backend.lookIsCustom` is false. The first press arms it: the label is "Click again to reset" for 3 seconds (also until the keyboard leaves it); the second press resets. No dialog.

The keyboard:

- The Tab order is the order of the window: the cards that can be chosen, "Panel size", its "Reset" (when shown), "Text size", its "Reset", "Font" (and the filter field while the list is open), the eight swatches (each followed by its "Reset" when it is custom), the editor when open (the palette, "Hex", "Opacity" for the background, "Done"), "Reset to defaults" (when enabled), "Close". The close control is the last item of the frame for this reason.
- The control that gets the keyboard comes on the screen when the sections scroll (`scroller.reveal`).
- Esc (one `Shortcut` for the window) closes the colour editor when it is open, else the list of fonts when it is open, else the window. A text field takes every other key as text (a space in a field presses no control).
- Names for a screen reader: "Panel size, 125 percent"; "Reset the panel size to 100 percent"; "Font, Layout default"; "Filter the fonts, 4 of 312"; "Blocked colour, custom, #ff5555"; "Background colour, default, #0b0e11, 94 percent opacity"; "Reset Blocked colour"; "Presets for the Blocked colour, #f28b82"; "Blocked colour as hex, #f28b82"; "Background opacity, 90 percent"; "Close the colour editor"; "Reset to defaults" ("Reset to defaults, press again to reset" while armed); "Close".

A look that cannot be read. The user can choose any colours, also a text in the colour of the panel, and a panel with 10 % opacity. Two controls must stay usable so that the user can undo this: the close control and "Reset to defaults". The rule: each has a solid plate (`safePlate`: the panel colour without its opacity, so what is behind the window does not matter), and its ink is `theme.readable(text colour, safePlate)`: the text colour of the user while its contrast to the plate is 3 or more, else the dark or the light ink for that plate. The idle marks of the close control have `theme.readable(dimColor, safePlate)` (`closeInk`). "Reset to defaults" always has its plate (it is a button). The close control shows its plate only when it is needed (`closePlated`): an ink of its marks is not the colour of the layout, or the panel has less opacity than the layout gives it. With the colours of the designs nothing changes: the header is the header of before, pixel for pixel. A test sets the four panel colours to one colour (dark, white, grey, red) at 10 % opacity in each layout, and then counts the pixels of the two controls that have a contrast of 3 or more to their plate, and uses the two controls.

What the controls needed from the backend, and got in this task: `scaleStep`, `fontScaleStep`, `opacityMin`, `opacityMax`, `opacityStep`, `lookIsCustom` (with `lookIsCustomChanged`), and `colors.background` as the colour that is drawn.

Limits: at a text size of 80 % the smallest texts of the window (the reset marks, the values of the colours, the tag) are 7 to 8 pixels high. A double click on the track of "Text size" away from its handle changes the text size with its first click, the window moves its rows, and the second click can miss the slider: the double click is for the handle, and "Reset" next to the value is the sure way. The window scrolls with the wheel, with a drag of the pointer or a finger, with a drag of the thumb, and with the keyboard.

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
| `bellwether/state.py` | Convert the rows of `herdr-app ls` or `herdr-core ls --json` to a sorted agent list. Return the four counts. No reads of Herdr. | nothing |
| `bellwether/client.py` | Run `herdr-app` (or `herdr-core` as the fallback). Return the agents or an error. Run the jump: start a closed app, show the agent, raise the window. | `state.py`, `window.py`, the two programs, `systemd-run` |
| `bellwether/window.py` | Ask KWin to restore and activate the app window. | `busctl`, KWin |
| `bellwether/settings.py` | Save and load the state file: the window position and the layout. | nothing |
| `bellwether/layouts.py` | The five designs and which of them are built. | nothing |
| `bellwether/options.py` | Open the options window. | the QML engine |
| `bellwether/paths.py` | The XDG folders of the widget. At start, move the folders of the old name herdr-float to the new name. | nothing |
| `bellwether/events.py` | One child process `herdr-core events --json` and one thread. Each line of the child starts a read now. Keeps and logs no text of a line. | herdr-core |
| `bellwether/backend.py` | Qt object. Reads a snapshot at each event of `events.py`, and by time as a safety net (each 2 s with a healthy stream, each second without one). Gives counters and status groups to the interface. Runs one jump at a time on a worker thread. | `client.py`, `state.py`, `settings.py` |
| `bellwether/ui/Main.qml` | Layer-shell overlay window, place and screen, drag, the pointer handler. Shows one skin. | `backend.py`, `PanelModel.qml` |
| `bellwether/ui/PanelModel.qml`, `AgentList.qml`, `AgentRow.qml` | The state and the rules of the panel, and the agent list, for every skin. | `backend.py` |
| `bellwether/ui/skins/C.qml` | The drawing of Layout C. | `PanelModel.qml`, `AgentList.qml` |
| `bellwether/ui/Options.qml` | The options window: the layout choice. | `backend.py` |
| `bellwether/tray.py` | System tray icon and menu. The one source of the state colours. | Qt, `backend.py` |
| `bellwether/__main__.py` | Connect the parts. Start the Qt application. | all parts |
| `scripts/start.sh` | Starts the widget as an independent process. | nothing |
| `mod/` | Herdr app mod. Runs `scripts/start.sh` when the app starts. | Herdr app |

## Data flow

The widget reads a snapshot when herdr-core tells of a change. An event is only a trigger: the data comes from the read. With no healthy event stream the widget reads one time each second.

1. At each event of the stream (and each 2 seconds; with no healthy stream: each second), run `herdr-app ls`. If it gives no valid answer, run `herdr-core ls --json`.
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
- The position is saved to `~/.config/bellwether/state.json` and loaded at start.
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
| herdr-core does not run, or the event stream ends | The stream is not healthy: the widget reads one time each second, and starts the stream again after 1, 2, 5 and then each 10 seconds. The log gets "events: lost (exit code N)" and "events: retry in Ns" one time each. |
| A reply is not valid | The widget uses the next source, or shows "offline". It writes one log line when the source changes. |
| The jump fails | The agent row, or a line at the bottom of the panel, shows a short error for 3 seconds. |
| A second widget starts | The second process exits. One widget only. A widget of the old name herdr-float counts as a widget. |
| A folder of the old name cannot be moved | One log line with the error class. The widget starts with its defaults. |

Logs go to `~/.local/state/bellwether/bellwether.log`.
There is no Sentry. This is a local personal tool.
Logs contain terminal addresses, states and counts only. They do not contain names, folders or terminal text.

## Tests

- `state.py`: pytest unit tests. Zero, one and many agents. Rows that are not valid. Sort order. Each of the four states. Sub-agents. Rows of herdr-core.
- `client.py`: pytest with a fake command runner. No test runs the real programs. Normal flow, fallback, offline, invalid data, and each branch of the jump: window visible, minimized, app closed, app does not start, raise fails, agent gone.
- `backend.py` and `Main.qml`: the groups, one jump at a time, and pointer clicks on the real QML off screen.
- Live check on the desktop with real agents: each state, expand, jump, drag, restart, Herdr stopped and started.

## Known limits

- The jump raises the app window through KWin first. Without KWin or `busctl` it runs plain `herdr-app`, and the app raises its own window, so the jump itself does not need KDE Plasma. Only the overlay panel (layer-shell) needs KDE Plasma on Wayland. A window on a different virtual desktop was not tested.
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
