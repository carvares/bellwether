# Bellwether reference

The full description of how Bellwether works: each rule of the panel, the answer window, the options, the files and the known limits. The [README](../README.md) is the short version with pictures.

Contents: [Use](#use) · [The model and session-time line](#the-model-and-session-time-line) · [Options](#options) · [Custom look](#custom-look) · [When the Herdr app window is closed](#when-the-herdr-app-window-is-closed) · [How the widget opens the app window](#how-the-widget-opens-the-app-window) · [How the data stays fresh](#how-the-data-stays-fresh) · [Answer a blocked agent](#answer-a-blocked-agent) · [Files](#files) · [Limits](#limits) · [The window shell](#the-window-shell) · [Other systems](#other-systems) · [The Qt version rule](#the-qt-version-rule) · [Start with the Herdr app: the details](#start-with-the-herdr-app-the-details)

## Use

- The panel has a layout. You choose it in the options window (see "Options" below). The five layouts show the same data and work in the same way; only the look is different:
  - A, "Refined list": a list of the four statuses with a colour bar and a count badge. The agents of the open status show under its row.
  - B, "Tiles": four tiles with large numerals. The agents of the open tile show in a card below the tiles.
  - C, "Techno / HUD" (the default): monospace text, corner brackets and one cell for each agent.
  - D, "Signal strip": the number of all agents, the most important status as a badge, one bar with the share of each status, and the four statuses as tabs.
  - E, "Ring": a ring with the share of each status and the number of all agents in its centre, and a list of the four counts.
- In every layout, an agent in an open list has a second, smaller line below its name: the model that the agent runs and the age of its session, for example "Opus 5.5 · 2h 14m" (see "The model and session-time line").
- The name of an agent row: the name that the terminal has in Herdr. When it has none, the title that the program gave the terminal (Claude Code writes what the session is about). When it has none of the two, the space and the tab ("Integuru / Claude Code"). With a name or a title, the space and the tab show after it in smaller text. The answer window uses the same name. A title is cut at 80 characters, and Bellwether never writes a title to its log.
- Bellwether reads the title with `herdr-core get`: for an agent that is new in the list, when the status of the agent changes, when its process changes, and one time in 5 minutes. So a new title can be some minutes old. This read stays on when "Show model and session time" is off; only the session files are not read then.
- The answer window and the options window have an entry in the taskbar. Its icon is the Herdr mark in the colour of "blocked" (a circle when the Herdr icon is not found). This needs a desktop with the `xdg-toplevel-icon` protocol (Plasma 6.3 or later); an older desktop shows its generic icon.
- In every layout: click a status to show its agents, click it again to close it, click an agent to open the Herdr app on that agent. A status with no agents does nothing. A list shows 8 agents at the most; turn the mouse wheel for more. The frame (in Layout C: the corner brackets) has the colour of the most important status.
- The lines below describe Layout C.
- The panel is a dark box, 320 px wide, with text in a monospace font (Hack, or a different monospace font if Hack is not installed).
- The top line shows the name "BELLWETHER", the number of all agents ("AGENTS 10") and, at the right, the most important state that has agents (for example "BLOCKED").
- The bar below it has one cell for each agent, in the colour of the state of the agent. The cells fill the width of the bar: 2 agents give 2 wide cells. With no agents, and offline, the bar is one empty outline. With more than 60 agents, the 60 cells show the share of each state, and a state with an agent keeps one cell or more.
- The panel shows four rows: Blocked, Done, Working, Idle. Each row shows the number of agents in that state with two digits ("03"). They are the states that the Herdr app shows. A row with 0 agents is dim.
- A blocked agent has an "Answer" control in its row. It opens a small window with the question of the agent and its options (see "Answer a blocked agent").
- "Done" means that an agent finished while you did not look at it. It becomes "Idle" after you look at it in the app.
- A terminal that runs no agent (a plain shell) is not counted.
- Click a row to show its agents below it. Click the row again to hide them. Only one row is open at a time. A row with 0 agents does not open.
- Each agent line starts with the icon that the Herdr app shows for the program of the agent (for example Claude Code). The program name is not shown as text.
  - If the terminal has a name, the line shows the name, and the space at the right (with the tab name when the space has more than one tab).
  - If the terminal has no name, the line shows the space.
  - If two lines look the same, each one also shows its terminal address in brackets (for example `[t1c]`).
  - In an open row, the agents whose terminal has a name are first, in the order of the name (A to Z). The agents with no name are below them, in the order of the text that they show. Lines with the same text are in the order of the terminal address (`t2` is before `t10`).
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
- Right-click the tray icon to open the menu: "Options…", "Hide widget" or "Show widget", "Move to next screen" (with more than one monitor) and "Quit".
- The tray icon has the same colour as the corner brackets of the panel when at least one agent exists. With no agents, or offline, the two are grey (two different greys).

### The model and session-time line

- The line shows two things: a short name of the model ("Opus 5.5", "Fable 5.2", "Sonnet 5.5", "GPT-5.2-codex") and how long the session of the agent exists ("<1m", "14m", "2h 14m", "3d 2h").
- Where the model comes from:
  - Claude Code: Bellwether finds the Claude Code process of the terminal and reads its session file (`~/.claude/sessions/<pid>.json`) and the end of the transcript of that session (`~/.claude/projects/…`). The model of the last answer counts, so a change of the model during a session shows.
  - Codex: the Codex process of the terminal holds a lock file with the id of its session (`~/.codex/thread-writer-locks/<id>.lock`). Bellwether reads the model from the session file with that id (`~/.codex/sessions/…`), from the last turn, so a change of the model during a session shows. It also takes a session file that the process has open (older Codex versions). A session of a helper that Codex starts (a review, a sub-agent) does not count. Before the first turn of a session there is no session file: the line then shows the model of the Codex settings file (`~/.codex/config.toml`, key `model`), but not when the command line of Codex names a model, a profile or a setting (`-m`, `-p`, `-c`, `--oss`); then it shows the time only.
  - A different program: the line shows the time only.
- Where the time comes from: the start of the session in the files above. When there is none, the time when the terminal was made in Herdr.
- A part that Bellwether cannot read is not shown. Bellwether never guesses a model. A row with no part has no second line. When one row of an open list has the line, all rows of that list have the same, taller height.
- A model name that is too long for the row ends in "…". The time always shows in full.
- The model can be up to 30 seconds old: Bellwether reads the files of each agent one time in 30 seconds. Each 5 seconds it checks in `/proc` (no command) that the process of the agent still runs. When the process ended or is a different process, the row loses its model at once and Bellwether asks Herdr again (one `herdr-core get`). It also asks Herdr at once for an agent that is new in the list, and one time in 5 minutes for each agent as a safety net. The time text changes one time each minute.
- When Bellwether cannot tell which process is the agent (for example a shell with two Claude Code processes, or a Codex process with two session files open), the row shows the time only.
- Privacy: Bellwether takes only the model name and the time stamps from these files. It does not log, save or show any other content of a session or a transcript. It reads a transcript from its end, at most 4 MB in one read, and not again while the file did not change.
- A screen reader says the model and the age with the name of the row ("…, model Opus 5.5, session age 2 hours 14 minutes").
- To hide the line: clear "Show model and session time" in the options window. Bellwether then reads no session file and no transcript (it still asks Herdr for the title of each terminal, see "Use"). The file key is `showMeta` (see "Files").

### Options

- Right-click the tray icon, then click "Options…". The options window opens. It has the look of the layout that the panel shows: the same frame, font and colours. It has no title bar of the system; its own header shows "Bellwether — Options" and a close control (×) at the right.
- To move the window, press its header and move the pointer.
- A second click on "Options…" shows the same window again and brings it to the front.
- The section "Layout" shows the five designs as cards: A Refined list, B Tiles, C Techno / HUD, D Signal strip, E Ring. Each card has a small picture, the name and one line of text.
- The card of the layout that shows now has a blue border and the tag "SELECTED".
- Click a card to use that layout. The panel changes at once and stays at its place, on its monitor, with the same open row. The widget saves the layout.
- The window changes its look together with the panel. The cards stay at their places.
- All five layouts are built. If the file of a layout is missing, its card is dim, has the tag "COMING NEXT", and a click on it does nothing.
- In the line of the title "Layout", at the right, is the check box "Show model and session time" (on by default). It shows or hides the second line of the agent rows in all five layouts. The widget saves it.
- Below the cards are the sections "Size", "Text" and "Colours" (see "Custom look"), and at the bottom "Reset to defaults".
- On a low monitor the window is lower than its content. Turn the mouse wheel to move the sections. The header and the bottom line with "Reset to defaults" stay.
- Keyboard: Tab and Shift+Tab move through the controls in the order of the window: the cards, the sliders, the font, the colours, "Reset to defaults", the close control and "Show model and session time". Enter or Space presses a control. The arrow keys move a slider. The window moves its sections so that the control with the keyboard is on the screen.
- Esc closes what is open inside the window first (the colour editor, the list of fonts). Then Esc closes the window.
- Close the window with Esc or with the close control (×) in its header. The widget continues to run.

### Custom look

You can change the size of the panel, the size of the text, the font and eight colours. One set of values applies to all five layouts and to the options window. You change them in the options window. Each change applies at once, and the widget saves it a moment later.

**Size**

- "Panel size" is a slider from 75 % to 200 %, in steps of 5 %. The whole panel grows or shrinks while you move it. The options window keeps its size.
- "Reset" next to the value goes back to 100 %. A double click on the handle of the slider does the same. The small line on the slider shows where 100 % is.

**Text**

- "Text size" is a slider from 80 % to 140 %, in steps of 5 %. It changes every text of the panel and of the options window.
- "Font" shows the font in effect. Click it to open the list. "Layout default" is the first line: each layout then has its own font. Type some letters to see only the fonts with these letters in their name. Click a font, or move with the arrow keys and press Enter.

**Colours**

- There are two groups. "Status": Blocked, Done, Working, Idle. "Panel": Background, Text, Frame, Accent.
- Each colour shows a sample and its value. Click a colour to open the editor below the row.
- In the editor, click one of the 16 samples, or type a value such as `#8ab4f8` in the field "Hex". A valid value applies while you type. A value that is not a colour changes nothing, and the editor shows "Use a colour like #8ab4f8".
- The editor of "Background" also has the slider "Opacity", from 10 % to 100 %.
- A colour that you changed has the button "Reset". It gives back the colour of the layout.
- "Done" or Esc closes the editor.

**Reset to defaults**

- The button at the bottom right of the window resets the size, the text size, the font and all colours.
- You must click it two times. After the first click it shows "Click again to reset" for 3 seconds.
- You cannot click it when nothing is changed.
- You can always read this button and the close control (×), also when you chose a text colour that is the same as the background.

**The state file**

The widget keeps the values in `~/.config/bellwether/state.json`, beside `x`, `y`, `screen` and `layout`. You can also change the file by hand: stop the widget (tray menu, "Quit"), change the file, and start the widget again.

| Key | Value | What it does |
|---|---|---|
| `scale` | a number from 0.75 to 2.0 (1.0 when the key is not there) | The size of the whole panel: frame, rows, icons and text grow or shrink together. The top-left corner of the panel stays at its place, and the panel stays on its monitor. The options window does not change its size. |
| `fontScale` | a number from 0.8 to 1.4 (1.0 when the key is not there) | The size of every text, against the size that the layout gives it. With a larger text the rows get higher. The panel keeps its width, and a long text is cut with "…". |
| `fontFamily` | the name of a font of this system, for example `"DejaVu Sans"` (the font of the layout when the key is not there or is `""`) | The font of every text. Layout C is made for a monospace font: with a different font its columns are less even. |
| `colors` | an object with one or more of the keys below | Each value is a colour as `"#rrggbb"`. A key that is not there keeps the colour of the layout. |

The keys of `colors`:

- `blocked`, `done`, `working`, `idle`: the colour of that status, in the panel and in the tray icon. The frame of the panel (in Layout C: the corner brackets) has the colour of the most important status.
- `background`: the colour of the panel. `"#rrggbb"` keeps the opacity of the layout. `"#aarrggbb"` also sets the opacity (`aa` from `00`, clear, to `ff`, solid).
- `text`: the colour of the text. The dim texts, the thin guide lines and the one-colour program icons use the same colour, lighter.
- `frame`: the colour of the frame when no agent exists, and of the thin lines.
- `accent`: the colour of the selected card in the options window, and of "opening…" in an agent line.

Example:

```json
{"x": 1500, "y": 40, "screen": "DP-1", "layout": "A", "scale": 1.25, "fontScale": 1.1,
 "fontFamily": "DejaVu Sans", "colors": {"blocked": "#ff5c5c", "background": "#cc101418"}}
```

- A number out of its limits is set to the nearest limit.
- A value that the widget cannot use (a number as text, a colour in a different form, a font that this system does not have) is ignored: the default applies, and the log gets one line with the names of the keys. The other values of the file apply.
- To go back to the look of the layouts, use "Reset to defaults", or delete the four keys.
- A change in the options window writes only the value that you changed. The other keys of the file stay, also a font that this system does not have now.
- At a large scale a long list can be higher than the monitor. The list then shows fewer than 8 agents at a time, and you turn the mouse wheel for the others.
- The text on a filled badge (Layout A) and on a filled tile (Layout B) is dark on a light status colour and light on a dark one.
- A text size of 80 % makes the smallest texts of the options window 7 to 8 pixels high.

### When the Herdr app window is closed

Your agents continue to run in herdr-core. The widget then reads herdr-core:

- The counts can be different from the counts of the app. A "done" agent that you looked at before stays "done". Terminals that the app does not show are counted too.
- The agent lines show the program icon and the terminal address, with no terminal name and no space name.
- A click on an agent starts the Herdr app and shows that agent.

One read of the app that fails changes nothing: the widget keeps the last list of the app. After two failed reads one after the other, the widget reads herdr-core. It reads the app again at the first answer of the app.

The panel shows "OFFLINE" when the app and herdr-core do not answer.
An open row closes when the widget goes offline.

### How the widget opens the app window

This section is for Linux. For macOS and Windows, see [Other systems](#other-systems).

- The widget asks KWin (the window manager of Plasma) to restore and activate the window. It uses the program `busctl` for this.
- If KWin does not do it (for example, `busctl` is not installed), the widget runs plain `herdr-app`. The app then raises its own window. On this machine that worked with the default focus rules of KWin.
- The widget starts a closed app, and runs plain `herdr-app`, with `systemd-run --user`, as the desktop does. The app does not stop when the widget stops.
- When the widget starts the app, the output of the app goes to the user journal (`journalctl --user`), as when Plasma starts it.
- A jump ends 8 seconds after the click at the latest, with one of the messages above. During that time the line shows "opening…".

### How the data stays fresh

The widget follows the changes of herdr-core with one child process, `herdr-core events --json`. The widget reads `herdr-app ls` when herdr-core reports a change: usually a few milliseconds after the event, at most 0.25 s after it. A stream of changes gives about four to five reads each second at the most. The Herdr app itself sometimes shows a change 0.3 to 1.5 s after herdr-core reports it. So the widget reads again five times in the first 1.6 s after a change. While the stream works, the widget also reads one time each 2 seconds: a change that gives no event, or that the app shows later than 1.6 s, shows after at most 2 s. If herdr-core does not run, or the stream ends, the widget reads one time each second, as before, and tries to start the stream again after 1, 2, 5 and then each 10 seconds. The widget does not keep or log the text of a change. The child process ends with the widget, also when the widget is killed.

### Answer a blocked agent

A blocked agent waits for your answer in its terminal. You can give that answer from the panel, without the Herdr window.

1. Click the status "Blocked". Each blocked agent has an "Answer" control at the right end of its row. On a row with the model and session-time line, the control is at that second line, so the name of the agent keeps the full first line.
2. Click "Answer". The answer window opens with the question of that agent. A click on the rest of the row still shows the agent in Herdr.
3. Click an option, or press its number (1 to 9). The window sends that one key to that one terminal.

What the window shows:

- The agent (its icon, name and terminal address), the title of the dialog with every line below it as the dialog shows it (the purpose of a command, a file name, a tip of the program), and the detail: the command, the diff or the plan, line for line as on the screen of the agent. A long line goes on in the next row with no new mark at its left; nothing is hidden at the side.
- A long detail takes all the free height of the window. When it is still taller, a bar at its foot says how many lines are out of view ("12 more lines below").
- One button for each option, in the order of the dialog, with its number.
  - An option that approves only this one thing ("Yes") has a full number in the accent colour.
  - An option that approves more than this one thing ("always allow …", "don't ask again …", "auto mode", "accept edits for this session") has an empty number, a bar in the colour of the status "blocked", and the words "Standing permission". It never looks like the plain "Yes".
  - An option that declines ("No") is grey.
- A text field with "Send" when the question takes a free text. Type the text and press Enter. A text is one line of 1 to 2000 visible characters.
- "Open in Herdr" is always there. It shows the agent in the Herdr app and closes the answer window.

Keys: a number presses the option with that number (not while you type in the text field). Tab goes through the detail (when it scrolls), the options, the text field, "Send", "Open in Herdr" and the close control. Enter presses only the control that has the keyboard: no option is selected at the start. Page Down, Page Up, Home and End scroll the detail. Esc closes the window.

The programs: Claude Code (permission dialogs for a command, an edit, a new file and a fetch; a question with one choice, also with tabs and its review page; the plan approval) and Codex (the approval of a command and of an edit). For any other program, and for a screen that Bellwether does not know, the window shows the screen as text and "Open in Herdr".

Safety rules:

- Bellwether shows buttons only when it knows the whole dialog. Before each key it reads the screen again, and it sends nothing when the question is different ("The question changed. Nothing was sent.").
- One click or one key of yours is one answer. The window never sends anything by itself, and there is no "answer all".
- After a question shows (or can be answered again), a click does nothing until 0.4 seconds passed with no click and no key, and a number does nothing until 1 second passed with no key. Each press in that time starts the wait again. So a double click, or the next keys of your typing, cannot answer the next question.
- When the question in the window changes, the numbers go off until you click in the window or press Tab. Only one change keeps them on: the next question after your own answer from this window, when the window stayed active and you pressed no key since that answer. The window says so: "New question — the number keys are off. Click in the window or press Tab to turn them on." A later change does not turn them on again. A new question has the mark "New question" with its number, and the window lights up for a moment.
- The options that approve stay off until the last line of the detail was on the screen: "Scroll to the end of the text above to approve." A new command always shows from its first line, and its end counts only after its first line was on the screen. When the first line was not counted (for example, you scrolled while the question was still new), the window says "Scroll to the top, then to the end, to approve." Bellwether itself checks this, not only the window. "No" and "Open in Herdr" work at any time.
- "Partly visible": Bellwether cannot see all that the dialog approves (a dialog that is taller than the screen of the agent, and every edit of Codex: its patch is not in the dialog). You can only decline from the window. To approve, use "Open in Herdr".
- The text of a screen stays in memory only while the window shows it. It is never in the log and never in a file.

When Herdr does not confirm an answer:

- If you typed in that terminal in Herdr in the last 3 seconds, herdr-core holds the key of Bellwether until you stop. The window then says "Not confirmed … It may still arrive. Check in Herdr."
- While that key may still arrive, Bellwether sends nothing more to that terminal. You can close and open the window: it shows the question with its buttons off.
- This ends when herdr-core says that the key went (the window then shows what the agent shows now), or that it did not go.
- If the late key arrives and the agent then shows the identical question again, the buttons stay off until you answer that question in Herdr. Bellwether cannot tell the second question from the first.
- After you stop and start Bellwether, it does not know of a key that may still arrive. A key that herdr-core holds at the stop is not cancelled: it can still arrive.

Limits:

- The readers depend on how each program draws its dialogs. After an update of Claude Code or Codex, the window can show "Not readable" until Bellwether is updated.
- The "trust this folder" dialogs are not a blocked state in Herdr: the panel does not show them.
- The check-box question of Claude Code (many answers) is not answered from the window.
- The dialogs were measured on terminals of 200, 95, 90, 84, 80 and 50 columns. On a narrow terminal a label that wraps can differ from the screen by one space.
- On a blocked row the name of the agent has the room first: with a large text or a long name, the workspace text at its right is cut or goes away.
- The answer window is a normal window: the compositor chooses its place (KWin puts it near the middle of the screen or under the pointer, by its own rule). You can move it by its header.

## Files

- Position, layout and custom look: `~/.config/bellwether/state.json`. The keys are `x` and `y` (from the top-left corner of a monitor), `screen` (the name of that monitor), `layout` (the letter of the layout, `"C"` when the key is not there), `scale`, `fontScale`, `fontFamily` and `colors` (see "Custom look" above; a file without them has the look of the layouts), and `showMeta` (`false` hides the model and session-time line; the key is not there when the line shows; a value that is not `true` or `false` is ignored with one line in the log). A panel that is at its default corner (top right) has no `x` and `y`. A layout that the widget does not have gives Layout C and one line in the log.
- Log: `~/.local/state/bellwether/bellwether.log`
- Start log (output of `scripts/start.sh` starts): `~/.local/state/bellwether/start.log`
- Icon copies: `~/.cache/bellwether/icons/`. The widget reads the icons from the folder of the app (`~/.config/herdr-app/icons/`, or `$HERDR_APP_HOME/icons/`) and does not change them. A one-colour icon is black, so the widget writes a copy of it here, in a light colour or in your text colour (`colors.text`). You can delete this folder.

The widget uses `$XDG_CONFIG_HOME`, `$XDG_STATE_HOME` and `$XDG_CACHE_HOME` in place of `~/.config`, `~/.local/state` and `~/.cache` when you set them.

These are the folders of Linux. The folders of macOS and Windows are in [Other systems](#other-systems).

The widget had the name herdr-float before 2026-11-18. At its first start with the new name, it moves each folder `herdr-float` in these three places to the new name `bellwether`, with all files in it. It does not move a folder when a `bellwether` folder is already there. If a move fails, the widget starts with its default position and writes one line about it in the log. The widget does not try that move again at a later start. You can move the old folder by hand while the widget does not run. The three old folders are `~/.config/herdr-float`, `~/.local/state/herdr-float` and `~/.cache/herdr-float`; each gets the name `bellwether` in the same place (if a `bellwether` folder is there already, move the files of the old folder into it). The old log files stay in the moved folder with their old names. While a widget of the old name runs, a new widget does not start.

## Limits

- The widget reads the Herdr app that uses the default folder `~/.config/herdr-app`, and the default herdr-core.
- The widget looks for `herdr-app` and `herdr-core` one time, at its start. If you install one of them later, start the widget again.
- The widget finds the icon of a program by the file name. It tries, in this order: a short list of other names from the program table of the app (for example `github-copilot` gives `copilot.svg`), `icons/<program>.svg`, the part before the first `-` (`claude-code` gives `claude.svg`), `agent.svg`. A program name longer than 64 characters gets `agent.svg`. The app does not give its program table to other programs, so the widget does not read `programs.json`: an icon that you changed there does not show in the widget.
- The widget reads each icon one time. After an update of the app that changes an icon, start the widget again. If an icon file or the folder of icon copies is deleted, the widget finds or makes the file again at the next change of the list.
- The widget reads a new list when herdr-core tells of a change (see "How the data stays fresh"). One read takes 3 to 14 ms.
- The panel redraws at most one time for each frame of your screen, and only when something changes. A drag moves the panel at most one time in two frames of the screen that the panel is on (240 Hz: each 8.3 ms, 144 Hz: each 13.9 ms, 60 Hz: each 20 ms). The second frame gives the compositor time to apply the last move before the next one is calculated.
- The drag across monitors works because KWin shows a layer surface also on the neighbour monitor. A different compositor can cut the panel at the edge of its monitor during the drag. The tray entry "Move to next screen" always works.
- A drag across monitors: the panel goes only across an edge that two monitors share. Where a monitor has no neighbour (for example above a smaller monitor that starts lower), the panel stops at the edge. During the drag the panel can be on two monitors. At the release it goes fully to the monitor that holds its middle, and it can blink one time when it changes its monitor: the compositor needs a new surface for a different monitor.
- On Wayland with two monitors, the options window can show for a moment the layout for the width of the first monitor: Qt knows the monitor of a window only after the compositor shows it, and the window then takes the width of its own monitor.
- If the monitor of the panel is disconnected while the widget runs, the panel shows on a monitor that stays. This was tested with made-up screens only, not with a real cable. The saved monitor does not change, so after a later start with that monitor the panel is there again.
- A person has not yet dragged the panel to a different monitor with a real mouse. The checks used the same functions without a pointer, and the protocol trace of the compositor.
- The widget is made for KDE Plasma on Wayland (the layer shell, below). On other desktops it uses the plain shell, with the limits named there. macOS and Windows always use the plain shell (see "Other systems").
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
- A person has not yet opened the options window from the tray icon with a real mouse. The checks used the menu of the tray icon over D-Bus, synthesized keys and clicks, and the protocol trace of the compositor.
- A person has not yet looked at the layouts A, B, D and E, and at the options window in its new look, on the screen. The checks compared pictures of the real panel with the approved design pictures, and used synthesized keys and clicks and the protocol trace of the compositor.
- When an open row makes the panel longer than the space below it, the panel moves up. It does not move back down when the row closes.

## The window shell

On KDE Plasma on Wayland the panel is a layer surface (the layer shell): it stays above all windows, it never takes the keyboard, and the widget places it. The widget uses it when the Qt platform is Wayland, the QML module `org.kde.layershell` loads, and the compositor has the layer-shell protocol (`zwlr_layer_shell_v1`). Else it uses the plain shell: a frameless tool window that asks to stay on top and not to take the focus. On X11 the window manager gives that; on a Wayland desktop with no layer shell it is a normal window that the compositor places (it can be under other windows and take the focus at its start; a drag asks the compositor to move it, and its place is not saved). On X11 a window manager can keep the window inside its work area: then the widget asks for its place one more time and leaves it where the window manager put it. The first lines of the log say `shell: layer` or `shell: plain`. The environment variable `BELLWETHER_SHELL=layer` or `BELLWETHER_SHELL=plain` chooses the shell; another value is ignored with one line in the log. Without a Wayland compositor the widget starts on X11 (`QT_QPA_PLATFORM` is `wayland;xcb` unless you set it).

## Other systems

The widget runs on Linux, macOS and Windows from the same code. The [README](../README.md#will-it-run-on-my-machine) says how well each system is tested. Nobody has run the widget on a real Mac or a real Windows PC: GitHub CI machines ran it there (see "The CI workflow" below). The design of the port, with each decision and its source, is in `docs/superpowers/specs/2026-11-20-bellwether-cross-platform-design.md`.

### The platform package

- `bellwether/platform/` has all the code that is different for each system. No other module tests the system or imports a system library; a test checks this.
- At the start, `platform/__init__.py` picks one module by `sys.platform`: `linux.py`, `macos.py` or `windows.py`. On a different system the widget stops with a clear message.
- Each module gives the same members: the folders, the single-instance lock, the raise and the start of the Herdr app, the environment of a command, the event child, the process host, the icon of the Herdr app, the window shell, and the set-up of Qt and of each window.
- `tests/test_platform.py` has the table of these members. Each module must give all of them, with the same parameters.
- Shared parts: `posix.py` (the lock and the wait for a pipe, Linux and macOS), `host.py` (the process host on psutil, macOS and Windows), `guard.py` (the watcher of the event child, macOS) and `mainthread.py` (a call on the main thread of Qt).

### The two window shells

- The layer shell (`ui/shells/Layer.qml`): a layer surface. Only Linux has it (see "The window shell").
- The plain shell (`ui/shells/Plain.qml`): a frameless tool window that asks to stay above the other windows and not to take the focus.
- Both shells use the same panel (`ui/PanelShell.qml`): the place, the drag, the layout and the hit test.
- The rule: macOS and Windows always use the plain shell. Linux uses the layer shell when Qt runs on Wayland, the QML module `org.kde.layershell` loads, and the compositor has `zwlr_layer_shell_v1`. Else Linux uses the plain shell.
- `BELLWETHER_SHELL=layer` or `BELLWETHER_SHELL=plain` chooses the shell on Linux. On macOS and Windows, `layer` gives one line in the log, and the plain shell stays. The log says `shell: layer` or `shell: plain` at each start.

### The folders

| What | Linux | macOS | Windows |
|---|---|---|---|
| Settings (`state.json`) | `~/.config/bellwether/` | `~/Library/Application Support/bellwether/` | `%APPDATA%\bellwether\` |
| Log and start log | `~/.local/state/bellwether/` | `~/Library/Logs/bellwether/` | `%LOCALAPPDATA%\bellwether\Logs\bellwether\` |
| Icon copies | `~/.cache/bellwether/icons/` | `~/Library/Caches/bellwether/icons/` | `%LOCALAPPDATA%\bellwether\Cache\bellwether\icons\` |
| Lock files | `$XDG_RUNTIME_DIR`, else `/tmp` | `~/Library/Caches/` | `%LOCALAPPDATA%\bellwether\` |

- macOS keeps the lock files in `~/Library/Caches`, not in `$TMPDIR`: a start by the Herdr app and a start from a terminal can have a different `$TMPDIR`.
- Windows: when `%APPDATA%` or `%LOCALAPPDATA%` is empty or not a full path, the widget uses the default folder under your home folder.
- The settings file and the log are UTF-8 on every system.

### What is different on each system

All systems:

- With the plain shell (macOS, Windows, X11, Wayland without the layer shell), the answer window and the options window have an opaque body. So the text of a window behind them cannot show through them. The panel keeps the opacity that you chose. With the layer shell, the two windows have the opacity of the panel, as before.
- The plain shell keeps the panel out of the part of each screen that the system keeps: the macOS menu bar and Dock, the Windows taskbar, the panels of X11. The default corner, the clamp to the screen and the rows that fit use the rest.
- The options window fits a narrow screen, on every system. Before each show it takes the width of the free part of its screen less 32 px (at least 320 px). The five cards go into rows (4 + 1 at a free width of 1024 px, 3 + 2 at 800, 2 + 2 + 1 at 640). "Size" and "Text" go one below the other when they do not have room side by side. The two colour groups go one below the other below 1076 px. The colour editor has a narrow form. Tab still goes in the order on the screen. At a free width of 1108 px or more, the window is as before.
- After each show, the options window and the answer window move inside the free part of their screen when the system put them partly outside it (Windows puts a new window at a default place).
- With two monitors of different scales (macOS, Windows), a drag keeps the point that you pressed under the pointer, so the panel crosses to the other monitor. This is tested off screen only.

macOS:

- Bellwether is an accessory app: it has no Dock icon. Its tray icon is in the menu bar.
- The panel is a non-activating `NSPanel` at the status level (above the menu bar), set to show on every Space and beside an app in full screen. It cannot become the key window, so a click on it does not take the keyboard. These calls need pyobjc. Without pyobjc, the widget has a Dock icon and the panel is a plain window above the others on the current Space only; the log says so.
- When the options window or the answer window opens, the widget asks macOS to make it the active app and makes the window the key window. When the app is still not active 300 ms later, it asks one more time in an older way, but only when the same app is still in front and the window still shows. macOS 14 and later can refuse this when you did not just act in the widget.
- The raise of the Herdr window: activate the running Herdr app (`dev.herdr.app`), then `open -b dev.herdr.app`. The start of a closed app: `open -a` with the `Herdr.app` of `herdr-app`, else `open -b dev.herdr.app`.
- The programs: `PATH`, then `~/.local/bin`, `/opt/homebrew/bin`, `/usr/local/bin`, `~/.local/share/mise/shims`, `/run/current-system/sw/bin`, `~/.nix-profile/bin`, `~/.cargo/bin`. For `herdr-app` also `Herdr.app` in `~/Applications` and `/Applications`.
- The event child runs under a watcher (`python -m bellwether.platform.guard`). The watcher ends the child when the widget ends, also after a kill of the widget.
- The tray icon: the `.icns` file of the Herdr app bundle, else the circle.
- The model of Claude Code: the start of a process in the form of `LC_ALL=C TZ=UTC ps -o lstart=`, the form that Claude Code writes on macOS. A session file counts only when its `procStart` is exactly that text. Any other form gives no model.

Windows:

- The panel is a tool window (no taskbar button), topmost, with no activation. Qt gives these styles. The widget adds a style only when Qt did not give it, and writes one log line then.
- When the options window or the answer window opens, the widget asks Windows to bring it to the front. Windows allows that after an input in the widget (a click in the tray menu or on the panel). Else the window shows, its taskbar button flashes, and the log gets one line.
- The raise of the Herdr window: the first top-level window of `herdr-app.exe`, restored when it is minimized, then brought to the front. The start of a closed app: `herdr-app` as a detached process. When a Herdr window exists, the widget does not start a second app: a refused raise then shows "could not raise the window".
- The programs: `PATH`, then `%LOCALAPPDATA%\Programs\herdr-app`, `%LOCALAPPDATA%\Programs\herdr-core` and `~\.cargo\bin`. Each program that the widget runs gets no console window.
- The event child is in a job object that ends it when the widget ends, also after a kill. A process that the child starts (the herdr-core server) is not in the job and does not end with the widget.
- The wait for the event stream: Windows has no `select` for a pipe. A thread for each pipe waits in the system with a read of no bytes (as libuv does) and takes no byte; nothing wakes while no data comes.
- The options window and the answer window open on the screen of the panel, inside the free part of that screen, and clear of the panel when the screen has room at a side of it; on a small screen the options window goes below the panel and is lower (its sections scroll). macOS and X11 too; on Wayland the compositor places them.
- The tray icon: `herdr-app.svg` beside `herdr-app.exe`, else the circle.
- The model of Claude Code: none. Claude Code writes `procStartFt` on Windows, and its form is not known. The row shows the time. Codex: its folder is `%USERPROFILE%\.codex`.
- `scripts\start.cmd` runs `scripts\start_windows.py` with the `pythonw` of the checkout. It starts the widget with no console, out of the process group and the job of the caller, and writes its output to `start.log` in the log folder (emptied above 1 MiB).
- The log rotation can fail on Windows when a different process has the log open. The widget then keeps the file and writes the line.

Fonts: each layout's font list ends with fonts of macOS (`SF Pro`, `Helvetica Neue`; `SF Mono`, `Menlo`) and of Windows (`Segoe UI`; `Cascadia Mono`, `Consolas`). On Linux the look is the same as before.

### The self-test

    uv run python -m bellwether --self-test

- `--self-test` must be the only argument.
- It uses made-up agents. It takes no lock, writes no log file, and keeps its settings in a temporary folder.
- It shows the panel for about 3 seconds, then each layout, the options window and the answer window with a made-up question. Before each wait it writes `self-test: shown <step>` to stderr.
- Then it prints one JSON object with the facts of the real windows: the system, the Qt platform, the shell, the flags, the place and the screen of each window, the native facts of the system, the tray and the Qt warnings. It exits with 0, or with 1 when the panel did not load.
- `scripts/ci/selftest.py <out folder> <darwin | win32> [--pictures]` runs it on a CI machine. It takes a picture of the whole screen at each step (only when `CI` or `GITHUB_ACTIONS` is `true`, or with `--pictures`), writes the home folder as `~`, and prints each check: FAIL, or WARN for a fact that a CI machine may not give.

### The CI workflow

`.github/workflows/platforms.yml` has two jobs: `macos` (`macos-latest`, a limit of 6 minutes) and `windows` (`windows-latest`, a limit of 8 minutes). Each job:

1. Runs `uv sync --locked`.
2. Runs a selected set of tests: the platform package, the module of its system, the client, the state, the settings, the start scripts, the events, the self-test, and 23 cases of the panel tests on the plain shell (marker `runner`, `tests/conftest.py`).
3. Runs the smoke test `scripts/ci/smoke.py`: the start script with a made-up Herdr (`scripts/ci/fake-herdr/`), the log lines, a kill of the widget, and a check that the event child ends.
4. Runs the self-test with its checks.
5. Keeps the facts, the logs and the pictures as an artifact for 3 days.

How a job starts:

- By hand: `workflow_dispatch`, with the input `system` (`macos`, `windows` or `both`; the default is `windows`, so a run by hand spends no macOS minute unless macOS is chosen).
- Nothing else starts it: no push, no pull request and no schedule. During the port, a push to the branch of the port with a marker in the commit message (`[ci macos]`, `[ci windows]`, `[ci both]`) also started a job; that rule was removed before the merge.

Why: the repository is private. GitHub counts a macOS minute as 10 minutes and a Windows minute as 2 minutes of the free minutes. So a job runs only when it is asked for, and it runs a fast selected set of tests: the full suite takes about 11 minutes on Linux, and the panel tests of the plain shell took about 5 times as long on the macOS machine. The runs and their minutes are on the Actions page of the repository.

## The Qt version rule

The widget loads the system QML module `org.kde.layershell` into the Qt of the PySide6 wheel.
This works while the system Qt and the wheel Qt have the same minor version (now 6.12).
A system upgrade to a new Qt minor version (for example 6.13) can stop the module from loading.
Then the widget shows in the plain shell (see "The window shell"), and the log file names the missing module.
To fix it, change the pin in `pyproject.toml` to the new minor version (for example `pyside6-essentials==6.13.*`).
Then run `uv sync`.


## Start with the Herdr app: the details

The folder `mod/` is a small Herdr app mod. It runs `scripts/start.sh` each time the app starts a copy of the mod.
The documentation of the app says when that occurs: at the install, at the start of the app, in each window, after a change of layout, and after a save of a file of the mod.
So after "Quit" from the tray, the widget can come back before the next start of the app.
Repeated starts do no harm: only one widget runs at a time.
The mod runs a program on your machine (`start.sh`). It does not use the network.

Install it. Run this in the repository folder:

    ln -s "$PWD/mod" ~/.config/herdr-app/mods/bellwether
    herdr-app check ~/.config/herdr-app/mods/bellwether

The link must stay a link: the mod finds the repository through it.
Do not move the repository after this, or make the link again.

What is known and not known about the mod:

- `herdr-app check` passes for `mod/`.
- A mod starts only when the app shows it. The documentation of the app says that the app then puts a new mod into the window. `mod.json` asks for a block at the bottom, 1 pixel high. The mod draws nothing in it.
- A person has not yet installed the mod. These things are not checked: how the block looks, if the app accepts a linked mod folder, and if the app starts the mod again at each start.

Remove the automatic start:

    rm ~/.config/herdr-app/mods/bellwether

If the empty block stays in the window after that, remove it from your layout in the app.

