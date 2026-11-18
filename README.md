# herdr-float

A small always-on-top window that shows the states of your Herdr agents.
For KDE Plasma 6 on Wayland only.

## Install

You need KDE Plasma 6 on Wayland and `uv`.
You also need the package `layer-shell-qt`. Plasma normally installs it.

    sudo pacman -S --needed layer-shell-qt

Then, in the repository folder:

    uv venv --system-site-packages --python /usr/bin/python3
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

## Start with Herdr

Link the plugin one time. Run this in the repository folder:

    herdr plugin link "$PWD/plugin"
    herdr plugin list --plugin carvares.herdr-float

The plugin starts the widget when Herdr starts.
The widget stays on the screen after you close Herdr.
A second start does not open a second widget.
Stop the widget: right-click the tray icon, then click "Quit".
Remove the automatic start:

    herdr plugin unlink carvares.herdr-float

Not yet tested: Herdr possibly runs the start command only when the Herdr server starts.
If the widget does not show when you open Herdr, restart the Herdr server.

## Start manually

    uv run python -m herdr_float

## Use

- The pill shows five counts: blocked, done, working, idle, unknown.
- Click the pill to open the agent list. Click the pill again to close it.
- Click an agent in the list to go to its pane in Herdr.
- Drag the pill to move it. The widget saves the position.
- Click the tray icon to hide or show the widget.
- Right-click the tray icon to open the menu with "Quit".
- The colour of the tray icon shows the most important state that has agents.
- The pill shows "offline" when the Herdr server does not answer.
- The list closes when Herdr goes offline.
- A click on the pill does nothing while Herdr is offline.

## Files

- Position: `~/.config/herdr-float/state.json`
- Log: `~/.local/state/herdr-float/herdr-float.log`

## Tests

    uv run pytest

## Limits

- The widget reads the default local Herdr session only.
- The widget works on KDE Plasma on Wayland only.
- The jump focuses the pane inside Herdr. It possibly does not raise the terminal window. This is not tested.
- All checks so far are automated: protocol traces, D-Bus, and the window image of the widget.
- A person has not yet checked the look on the screen.
- A person has not yet dragged the pill with a real mouse. The drag can jitter.
- A person has not yet checked the widget above full-screen windows.
- The counts were only seen with 0 real agents.
