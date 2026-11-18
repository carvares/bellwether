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

- The pill shows four counts: blocked, done, working, idle. They are the states that the Herdr app shows.
- "done" means that an agent finished while you did not look at it. It becomes "idle" after you look at it in the app.
- A terminal that runs no agent (a plain shell) is not counted.
- Click the pill to open the agent list. Click the pill again to close it.
- Each row shows the agent, its state, and its space (with the tab name when the space has more than one tab).
- Click an agent in the list to go to it in the Herdr app.
- Drag the pill to move it. The widget saves the position.
- Click the tray icon to hide or show the widget.
- Right-click the tray icon to open the menu with "Quit".
- The colour of the tray icon shows the most important state that has agents.

### When the Herdr app window is closed

Your agents continue to run in herdr-core. The widget then reads herdr-core:

- The counts can be different from the counts of the app. A "done" agent that you looked at before stays "done". Terminals that the app does not show are counted too.
- The rows show the program name only, with no space name.
- A click on a row shows "Herdr app is not open". Open the app to go to an agent.

The pill shows "offline" when the app and herdr-core do not answer.
The list closes when the widget goes offline, and a click on the pill does nothing then.

## Files

- Position: `~/.config/herdr-float/state.json`
- Log: `~/.local/state/herdr-float/herdr-float.log`
- Start log (output of `scripts/start.sh` starts): `~/.local/state/herdr-float/start.log`

## Tests

    uv run pytest

## Limits

- The widget reads the Herdr app that uses the default folder `~/.config/herdr-app`, and the default herdr-core.
- The widget looks for `herdr-app` and `herdr-core` one time, at its start. If you install one of them later, start the widget again.
- The widget reads a new list one time each second. One read takes 3 to 14 ms.
- The widget works on KDE Plasma on Wayland only.
- The jump shows the agent inside the Herdr app. It possibly does not raise the app window. This is not tested.
- The jump was run for real one time, to the agent that had the focus already. The app accepted the command. A jump to an agent in a different space or tab is not yet checked by a person.
- Sub-agents (terminals that an agent starts with `hc run`) are read as the documentation of the app describes them. This was not checked with real data: no real sub-agent was available. If the real data has a different shape, sub-agents are not counted.
- An agent that reports "error" is counted as blocked, as in the agent list of the app.
- The state when the app window is closed was tested with a simulation only (an empty app folder), not with the real window closed.
- A person has not yet checked the look on the screen. The checks used an image of the widget's own window.
- A person has not yet dragged the pill with a real mouse. The drag can jitter.
- A person has not yet checked the widget above full-screen windows.
