# Bellwether: answer a blocked agent from the panel — design

Date: 2026-11-19. Branch: `unblock-agents` (from `build-widget` at `c259475`). Base spec: `2026-11-18-bellwether-design.md`.

## Request of the user

"this feature aims to allow the user to unblock agents faster … on the blocked agents list, let's add a button on each blocked agent that, if clicked, will open a window (or maybe expand the main one) with the questions and options for me to select."

Decisions of the user: the first version understands **Claude Code** and **Codex**; the question shows in **a small answer window** in the style of the active layout, which takes the keyboard; the design below was accepted ("go").

## Facts (measured on 2026-11-19 with test terminals)

- Herdr gives no structured question. Its API (`herdr-core schema`) has only the status `blocked`.
- `herdr-core read <terminal> --json` gives the screen text: `{"complete": bool, "how": "screen", "text": "…"}`.
- `herdr-core keys <terminal> <key>…` presses keys. `herdr-core send <terminal> <text>` pastes text and presses Enter.
- Claude Code 2.1.322 dialogs: a title line ("Bash command", "Create file"), a detail block between dashed lines, a question ("Do you want to proceed?"), numbered options, the cursor marked `❯`, a hint line ("Esc to cancel · Tab to amend"). A question dialog (the AskUserQuestion tool) has a header ("☐ Colour"), the question, numbered options each with a description line, "N. Type something.", "N. Chat about this", and "Enter to select · ↑/↓ to navigate · Esc to cancel". **One digit key selects an option at once, with no Enter.**
- The "trust this folder" dialogs of both programs do not set the status `blocked`; Bellwether cannot show them.
- Codex 0.170.0: no approval dialog was obtained yet (the configuration of this machine runs commands without asking).

## Design

### Readers (`bellwether/prompts/`)

One module for each agent program, and one result type. `parse(app, text)` returns a `Prompt` or `None`.

A `Prompt` has: the program; a title; the question; the detail lines (the command, the file and its content, as shown); the options, each with the key to press, its label and its description; the key of a free-text option when there is one; a flag "the detail is cut" when the dialog does not fit the screen; and a **fingerprint** (a hash of the question, the detail and the options, in memory only).

A reader returns `None` unless it recognises the WHOLE dialog: its frame, the question, every option line in sequence from 1, and the hint line. A partial match is `None`. `None` means "no option buttons".

### Client

`read_screen(terminal)` and `press(terminal, keys)` beside the existing calls, with the same subprocess rules (deadline, no shell, errors as values). The screen text is never logged, never saved, and never part of an exception message or a test name.

### Backend

A small state machine for ONE open prompt (the answer window shows one agent at a time):

`closed → loading → ready | unreadable | gone → answering → (loading again) | failed`

- `openPrompt(agent key)`: reads the screen off the UI thread, parses it.
- `answer(option key)`: reads the screen AGAIN; only when the new fingerprint equals the shown one does it press the key; else it shows the new state and presses nothing.
- `answerText(text)`: the same check, then the free-text path of that program.
- After an answer it reads again until the agent is no longer blocked (the window then closes after a short "sent" state) or a new prompt shows (the window shows it).
- While the window is open, a change of the agent's status or a tick of the existing refresh reads the screen again (at most twice each second).
- One answer at a time; a second click while one is in flight is ignored.

### Interface

- An "Answer" control on each agent row of the **blocked** group in all five skins, through the shared row (`AgentRow.qml`) and the hit test (`hitRole: "answer"`). A click on the rest of the row still jumps to Herdr.
- `ui/Answer.qml`: a frameless window in the style of the active theme (the tokens and controls of the options window), an xdg toplevel that takes the keyboard. Content: the agent (icon, name, address); the title and question; the detail in the monospace font, scrollable, with a "cut" note; one button for each option with its number (keys 1–9 press them); a text field when there is a free-text option; "Open in Herdr" always; Esc closes.
- `unreadable`: the screen text (monospace, scrollable) and only "Open in Herdr". `gone`: "This agent is not blocked now."

## Safety rules

1. No full recognition, no buttons.
2. Read again before each key; press only on the same fingerprint.
3. One click, one key sequence, one terminal. Nothing automatic, no "answer all".
4. Only `herdr-core read` and `herdr-core keys` / `send` on the terminal of the row the user chose.
5. The screen text lives only in memory while the window shows it.

## Limits

- The readers depend on how each program draws its dialogs. After an update of a program the window may show "unreadable" until the reader is updated.
- A dialog larger than the screen shows only its visible part.
- The "trust this folder" dialog is not a blocked state in Herdr.

## Tasks

- **Task 24 — the engine:** readers for Claude Code and Codex with sample screens as test data (made-up content), the client calls, the backend state machine, the interface table for Task 25. Live proof on the implementer's own test terminals.
- **Task 25 — the interface:** the "Answer" control in five skins and the answer window; the documents.
