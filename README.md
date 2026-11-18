# herdr-float

A small always-on-top window that shows how many agents of the Herdr desktop app are in each state.
For KDE Plasma 6 on Wayland only.

The widget reads the Herdr desktop app (`herdr-app`) and its `herdr-core`.
It does not read the `herdr` 0.9 terminal program.

## Install

You need KDE Plasma 6 on Wayland and `uv`.
You also need the package `layer-shell-qt`. Plasma normally installs it.

    sudo pacman -S --needed layer-shell-qt

Then, in the repository folder:

    uv venv --python /usr/bin/python3
    uv sync

`uv sync` installs PySide6 from PyPI (`pyside6-essentials==6.12.*`).
You do not need a system PySide6 package.

### Version note

The widget loads the system QML module `org.kde.layershell` into the Qt of the PySide6 wheel.
This works while the system Qt and the wheel Qt have the same minor version (now 6.12).
A system upgrade to a new Qt minor version (for example 6.13) can stop the module from loading.
Then the widget does not show, and the log file names the missing module.
To fix it, change the pin in `pyproject.toml` to the new minor version (for example `pyside6-essentials==6.13.*`).
Then run `uv sync`.

## Start

Run this in the repository folder:

    ./scripts/start.sh

The widget starts in the background and stays on the screen until you log out or stop it.
It stays also after you close the Herdr app.
A second start does not open a second widget.

Stop the widget: right-click the tray icon, then click "Quit".
If there is no tray icon, stop the widget with this command:

    pkill -f -x '(.*/)?python[0-9.]* -m herdr_float'

To run the widget in the foreground:

    uv run python -m herdr_float

## Start with the Herdr app (optional)

The folder `mod/` is a small Herdr app mod. It runs `scripts/start.sh` each time the app starts a copy of the mod.
The documentation of the app says when that occurs: at the install, at the start of the app, in each window, after a change of layout, and after a save of a file of the mod.
So after "Quit" from the tray, the widget can come back before the next start of the app.
Repeated starts do no harm: only one widget runs at a time.
The mod runs a program on your machine (`start.sh`). It does not use the network.

Install it. Run this in the repository folder:

    ln -s "$PWD/mod" ~/.config/herdr-app/mods/herdr-float
    herdr-app check ~/.config/herdr-app/mods/herdr-float

The link must stay a link: the mod finds the repository through it.
Do not move the repository after this, or make the link again.

What is known and not known about the mod:

- `herdr-app check` passes for `mod/`.
- A mod starts only when the app shows it. The documentation of the app says that the app then puts a new mod into the window. `mod.json` asks for a block at the bottom, 1 pixel high. The mod draws nothing in it.
- A person has not yet installed the mod. These things are not checked: how the block looks, if the app accepts a linked mod folder, and if the app starts the mod again at each start.

Remove the automatic start:

    rm ~/.config/herdr-app/mods/herdr-float

If the empty block stays in the window after that, remove it from your layout in the app.

## Nothing shows?

- Read the log file `~/.local/state/herdr-float/herdr-float.log`. The line `source: app`, `source: core` or `source: none` shows where the counts come from.
- Read the start log `~/.local/state/herdr-float/start.log`. It holds the output of the widget process that `scripts/start.sh` starts, for example a Qt error before the log file opens.
- `scripts/start.sh` stops with exit code 1 and a message when `.venv/bin/python` does not exist. Then run `uv sync` in the repository folder.
- If the mod does not start the widget, run `herdr-app status` and read its `errors`.

## Use

- The panel is a dark box, 320 px wide, with text in a monospace font (Hack, or a different monospace font if Hack is not installed).
- The top line shows the number of all agents ("AGENTS 10") and, at the right, the most important state that has agents (for example "BLOCKED").
- The bar below it has one cell for each agent, in the colour of the state of the agent. The cells fill the width of the bar: 2 agents give 2 wide cells. With no agents, and offline, the bar is one empty outline. With more than 60 agents, the 60 cells show the share of each state, and a state with an agent keeps one cell or more.
- The panel shows four rows: Blocked, Done, Working, Idle. Each row shows the number of agents in that state with two digits ("03"). They are the states that the Herdr app shows. A row with 0 agents is dim.
- "Done" means that an agent finished while you did not look at it. It becomes "Idle" after you look at it in the app.
- A terminal that runs no agent (a plain shell) is not counted.
- Click a row to show its agents below it. Click the row again to hide them. Only one row is open at a time. A row with 0 agents does not open.
- Each agent line starts with the icon that the Herdr app shows for the program of the agent (for example Claude Code). The program name is not shown as text.
  - If the terminal has a name, the line shows the name, and the space at the right (with the tab name when the space has more than one tab).
  - If the terminal has no name, the line shows the space.
  - If two lines look the same, each one also shows its terminal address in brackets (for example `[t1c]`).
  - The lines of one row are in the order of the text that they show (A to Z).
  - A program that has no icon in the app gets the generic agent icon. If the widget cannot find the icons of the app, the line shows the program name as text.
- The four corner brackets of the panel and the word at the top right have the colour of the most important state that has agents. The order is: blocked (red), done (yellow), idle (green), working (blue). Idle is above working here, so green brackets tell you that an agent waits for you. With no agents ("NO AGENTS"), or offline, they are grey.
- An open row shows 8 agents at most. Turn the mouse wheel on the list to see the others. A line below the list shows which rows you see ("ROWS 01–08 / 12"), and marks at the right edge show the place in the list.
- Click an agent to go to it. The Herdr app window comes to the front and shows that agent:
  - If the window is behind other windows or minimized, the widget brings it to the front.
  - If the app is closed, the widget starts it. This takes about 1 second. The line shows "> opening…" during that time.
  - During a jump, more clicks on agents do nothing.
- If a jump fails, the line shows a short message in red, after a "!", for 3 seconds: "Herdr app did not start", "could not raise the window", "agent is gone", "Herdr is offline" or "jump failed" (an error that has no message of its own). If the agent has no line any more, the message shows at the bottom of the panel.
- Drag the panel to move it. You can start the drag on any row. The widget saves the position.
- With more than one monitor, you can move the panel to a different monitor in two ways:
  - Drag the panel across the edge where the two monitors touch, and release it there. The panel then belongs to the monitor that holds its middle, and it is fully on that monitor.
  - Right-click the tray icon, then click "Move to next screen". The panel keeps its distance to the nearer edges. The menu has this entry only when more than one monitor is connected.
- The widget saves the monitor with the position. At the next start the panel is on the same monitor at the same place. If that monitor is not connected, the panel shows at the top-right corner of a connected monitor.
- The tray icon is the Herdr app icon in one colour (the tile in the status colour, the ram cut out). If the widget cannot find or cannot use the Herdr app icon, the tray icon is a circle. The tray icon is the only icon of the widget: the widget has no application icon.
- Click the tray icon to hide or show the widget.
- Right-click the tray icon to open the menu: "Hide widget" or "Show widget", "Move to next screen" (with more than one monitor) and "Quit".
- The tray icon has the same colour as the corner brackets of the panel when at least one agent exists. With no agents, or offline, the two are grey (two different greys).

### When the Herdr app window is closed

Your agents continue to run in herdr-core. The widget then reads herdr-core:

- The counts can be different from the counts of the app. A "done" agent that you looked at before stays "done". Terminals that the app does not show are counted too.
- The agent lines show the program icon and the terminal address, with no terminal name and no space name.
- A click on an agent starts the Herdr app and shows that agent.

The panel shows "OFFLINE" when the app and herdr-core do not answer.
An open row closes when the widget goes offline.

### How the widget opens the app window

- The widget asks KWin (the window manager of Plasma) to restore and activate the window. It uses the program `busctl` for this.
- If KWin does not do it (for example, `busctl` is not installed), the widget runs plain `herdr-app`. The app then raises its own window. On this machine that worked with the default focus rules of KWin.
- The widget starts a closed app, and runs plain `herdr-app`, with `systemd-run --user`, as the desktop does. The app does not stop when the widget stops.
- When the widget starts the app, the output of the app goes to the user journal (`journalctl --user`), as when Plasma starts it.
- A jump ends 8 seconds after the click at the latest, with one of the messages above. During that time the line shows "opening…".

## Files

- Position: `~/.config/herdr-float/state.json` (`x` and `y` from the top-left corner of a monitor, and `screen`, the name of that monitor)
- Log: `~/.local/state/herdr-float/herdr-float.log`
- Start log (output of `scripts/start.sh` starts): `~/.local/state/herdr-float/start.log`
- Icon copies: `~/.cache/herdr-float/icons/`. The widget reads the icons from the folder of the app (`~/.config/herdr-app/icons/`, or `$HERDR_APP_HOME/icons/`) and does not change them. A one-colour icon is black, so the widget writes a light copy of it here. You can delete this folder.

## Tests

    uv run pytest

## Limits

- The widget reads the Herdr app that uses the default folder `~/.config/herdr-app`, and the default herdr-core.
- The widget looks for `herdr-app` and `herdr-core` one time, at its start. If you install one of them later, start the widget again.
- The widget finds the icon of a program by the file name. It tries, in this order: a short list of other names from the program table of the app (for example `github-copilot` gives `copilot.svg`), `icons/<program>.svg`, the part before the first `-` (`claude-code` gives `claude.svg`), `agent.svg`. A program name longer than 64 characters gets `agent.svg`. The app does not give its program table to other programs, so the widget does not read `programs.json`: an icon that you changed there does not show in the widget.
- The widget reads each icon one time. After an update of the app that changes an icon, start the widget again. If an icon file or the folder of icon copies is deleted, the widget finds or makes the file again at the next change of the list.
- The widget reads a new list one time each second. One read takes 3 to 14 ms.
- The panel redraws at most one time for each frame of your screen, and only when something changes. A drag moves the panel at most one time in two frames of the screen that the panel is on (240 Hz: each 8.3 ms, 144 Hz: each 13.9 ms, 60 Hz: each 20 ms). The second frame gives the compositor time to apply the last move before the next one is calculated.
- A drag across monitors: the panel goes only across an edge that two monitors share. Where a monitor has no neighbour (for example above a smaller monitor that starts lower), the panel stops at the edge. During the drag the panel can be on two monitors. At the release it goes fully to the monitor that holds its middle, and it can blink one time when it changes its monitor: the compositor needs a new surface for a different monitor.
- If the monitor of the panel is disconnected while the widget runs, the panel shows on a monitor that stays. This was tested with made-up screens only, not with a real cable. The saved monitor does not change, so after a later start with that monitor the panel is there again.
- A person has not yet dragged the panel to a different monitor with a real mouse. The checks used the same functions without a pointer, and the protocol trace of the compositor.
- The widget works on KDE Plasma on Wayland only.
- The jump was tested on 2026-11-18 on this machine (one virtual desktop): window behind a different window, window minimized, app closed. A window on a different virtual desktop was not tested.
- The jump needs `systemd-run` (a part of systemd). Without it the widget cannot start a closed app and has no second method to raise the window. `busctl` and KWin are the first method to raise the window; the jump also works without them (see "How the widget opens the app window").
- Known, not fixed: a failed agent in a group with more than 8 agents is not scrolled into view, so its message can be out of sight.
- Known, not fixed: the widget can start a second copy of the app in two cases. Case 1: you start the app by hand and click an agent before the app answers. Case 2: a jump started the app and failed at its time limit (8 seconds) while the app was still starting, and you click an agent again before the app answers.
- A jump to a "done" agent changes it to "idle", because you then look at it.
- Sub-agents (terminals that an agent starts with `hc run`) are read as the documentation of the app describes them. This was not checked with real data: no real sub-agent was available. If the real data has a different shape, sub-agents are not counted.
- An agent that reports "error" is counted as blocked, as in the agent list of the app.
- A person has not yet checked the look on the screen. The checks used an image of the widget's own window.
- A person has not yet dragged the panel or clicked its rows with a real mouse. The checks used synthesized pointer events. The drag can jitter.
- A person has not yet checked the widget above full-screen windows.
- When an open row makes the panel longer than the space below it, the panel moves up. It does not move back down when the row closes.
