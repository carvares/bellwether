# Bellwether: answer a blocked agent from the panel — design

Date: 2026-11-19. Branch: `unblock-agents` (from `build-widget` at `c259475`). Base spec: `2026-11-18-bellwether-design.md`.

## Request of the user

"this feature aims to allow the user to unblock agents faster … on the blocked agents list, let's add a button on each blocked agent that, if clicked, will open a window (or maybe expand the main one) with the questions and options for me to select."

Decisions of the user: the first version understands **Claude Code** and **Codex**; the question shows in **a small answer window** in the style of the active layout, which takes the keyboard; the design below was accepted ("go").

## Facts (measured on 2026-11-19 with test terminals)

- Herdr gives no structured question. Its API (`herdr-core schema`) has only the status `blocked`.
- `herdr-core read <terminal> --json` gives the screen text: `{"complete": bool, "how": "screen", "text": "…"}`.
- `herdr-core keys <terminal> <key>…` presses keys. `herdr-core send <terminal> <text>` pastes text and presses Enter.
- When the keys arrive (measured on 2026-11-19 with herdr-core 0.1.21 on own test terminals, fix round 1 of Task 24):
  - `keys` with no person typing in that terminal: the key arrives about 0.03 s after the start of the command, and the command ends about 0.06 s after its start. A terminal that prints all the time (a line each 0.2 s) does not delay it.
  - `keys` after a person typed in that terminal (in Herdr, or attached): herdr-core holds the key until 3.0 s after the person's last key. While the person goes on typing, the hold goes on (27 s measured, with a key each second). The command ends about 0.05 s after the key arrives.
  - A `keys` command that is killed while herdr-core holds its key does NOT cancel it: the key still arrives 3 s after the person's last key (measured with SIGKILL and SIGTERM, and live with the backend: the key arrived 5 s after the command was killed, and the agent went on).
  - `send` with no draft: the text arrives about 0.03 s after the start, Enter 0.2 s after the text. After the person sends their own line (Enter), at once.
  - `send` while the person has a draft (typed text with no Enter) in that terminal: herdr-core holds the text up to 60 s after the person's last key (60.2 s measured). A `send` that is killed while it holds the text IS cancelled: nothing was typed (checked 66 s later). `--force` only lets `send` type into a program that is blocked; it does not change the hold.
  - `read --lines N` gives the history above the screen only for a program that is not a full-screen program, or one that is not `working`, `blocked` or `error`. Claude Code and Codex are full-screen programs: while they are blocked, `read --lines N` gives only the screen, with `complete: false` and `why: "blocked"` (measured with N = 1, 10, 50, 100, 300). So a dialog taller than the screen, and the patch that Codex prints above its edit dialog, cannot be read whole while the agent waits.
  - A name of a terminal can have the form of an address ("1-32 of a-z 0-9 - _"). Which one herdr-core takes when a name is the address of another terminal was NOT measured: making such a name was refused by the permission system of the implementer. The client is safe either way (see "The client").
- Claude Code 2.1.322 dialogs: a title line ("Bash command", "Create file"), a detail block between dashed lines, a question ("Do you want to proceed?"), numbered options, the cursor marked `❯`, a hint line ("Esc to cancel · Tab to amend"). A question dialog (the AskUserQuestion tool) has a header ("☐ Colour"), the question, numbered options each with a description line, "N. Type something.", "N. Chat about this", and "Enter to select · ↑/↓ to navigate · Esc to cancel". **One digit key selects an option at once, with no Enter.**
- The "trust this folder" dialogs of both programs do not set the status `blocked`; Bellwether cannot show them.
- Codex 0.170.0: no approval dialog was obtained yet (the configuration of this machine runs commands without asking). Task 24 obtained them: see "The engine as built".

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

As built, an answer does not go through `loading` again: after the key the state stays `answering` while the backend reads, then it is `sent` (and `closed` one second later), `ready` with the next question, `unreadable`, `gone` or `failed`. See "The engine as built".

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
- A blind prompt (fix round 1): every option shows, the buttons of the options that are not `allowed` are off, and the `message` says to open Herdr to approve. `pending`: the question with its buttons off, the `message`, and "Open in Herdr". A `message` shows in every state that has one.

## Safety rules

1. No full recognition, no buttons.
2. Read again right before each key; press only on the same fingerprint. The fingerprint covers what the window shows: the program, the kind, the title, the subtitle, the question, the visible detail, the cut and blind flags, and each option (key, label, description, kind, effect). It does not cover what is not on the screen: the top of a dialog taller than the screen, and the patch of a Codex edit. Such a prompt is **blind**: only its options that decline can be answered from the window; to approve, the person opens Herdr.
3. One click, one key sequence, one terminal. Nothing automatic, no "answer all".
4. Only `herdr-core read` and `herdr-core keys` / `send` on the terminal of the row the user chose.
5. The screen text lives only in memory while the window shows it.

## Limits

- The readers depend on how each program draws its dialogs. After an update of a program the window may show "unreadable" until the reader is updated.
- A dialog larger than the screen shows only its visible part, and is blind (see Safety rule 2).
- The time from the check to the key. With no person typing in that terminal, the last read and the key are about 0.1 s apart (one `read`, one `get`, one `keys`). After a person typed in that terminal in the last 3 s, herdr-core holds the key until 3 s after their last key, with no limit while they go on typing, and a killed `keys` still delivers. In that time a person can answer the dialog in Herdr, and the held key then goes to whatever shows next. Bellwether cannot see the person's typing before the key. It sees it after: a key that took more than 1 s is "held", and the window says so ("check in Herdr"). A key that is not confirmed in 10 s is "pending": it may still arrive.
- The "trust this folder" dialog is not a blocked state in Herdr.

## Tasks

- **Task 24 — the engine:** readers for Claude Code and Codex with sample screens as test data (made-up content), the client calls, the backend state machine, the interface table for Task 25. Live proof on the implementer's own test terminals.
- **Task 25 — the interface:** the "Answer" control in five skins and the answer window; the documents.

## The engine as built (Task 24)

This part is the contract for Task 25. Code: `bellwether/prompts/`, `bellwether/client.py` (the screen calls), `bellwether/prompt_session.py` (the state machine, `PromptSession`), `bellwether/backend.py` (the names for QML, which forward to the session). Tests: `tests/test_prompts.py`, `tests/test_prompts_adversarial.py`, `tests/test_client_screen.py`, `tests/test_backend_prompt.py`, with real screens of made-up tasks in `tests/fixtures/prompts/`.

### The `Prompt` type (`bellwether/prompts/__init__.py`)

`parse(app, text, complete=True) -> Prompt | None`. `app` is the program word of the row. The registry has `claude-code`, `claude` (the word that `herdr-core run` gives) and `codex`. A screen with `complete` false is never read.

| Field | Type | Meaning |
|---|---|---|
| `app` | text | `claude-code` or `codex` (the word of the reader, not the alias) |
| `kind` | text | Claude Code: `permission`, `question`, `review`, `plan`. Codex: `command`, `edit` |
| `title` | text | "Bash command", "Create file", "Edit file", "Fetch · …"; the header of a question ("Drink"; with tabs "Pet · Seasoning"); "Review your answers"; "Ready to code?"; for Codex the words of Bellwether "Command approval" and "Edit approval". Empty when the dialog is cut |
| `subtitle` | text | The lines below the title: a file name, the purpose of a command. A "Tip:" line of Claude Code is left out |
| `question` | text | "Do you want to proceed?" and so on |
| `detail` | list of lines | The command, the diff, the plan, the answers to review: line for line as on the screen, with its first spaces |
| `cut` | yes/no | The dialog is taller than the screen: the detail has only the visible part, the title is empty |
| `blind` | yes/no | What the dialog approves is not all on the screen: a cut dialog, and every Codex edit. Only the options with the effect `decline` can be answered (`Prompt.allows(key)`) |
| `options` | list | Each: `key` (one digit, "1" to "9"), `label`, `description`, `kind`, `effect` |
| `cursor` | text | The key of the option with the cursor. It is not in the fingerprint |
| `fingerprint` | text | SHA-256 of the program, kind, title, subtitle, question, detail, cut flag, blind flag and options (with kind and effect). In memory only |
| `text_key` | text | The key of the option of the kind `text`, or empty |

The text form of a `Prompt` and an `Option` (`repr`, `str`) has no screen text: only the program, the kind, the number of options, the cursor, the flags, the start of the fingerprint, and for an option its key, kind and effect.

The effect of an option: `accept` (the agent does what the dialog shows), `decline` (it does not), `other` (neither: the answer to a question). The reader must know the effect of each option; a prompt with an option of no known effect is not read. Claude Code permission and plan, Codex: a label that starts with the word "Yes" accepts, with the word "No" declines; the plan's "Tell Claude what to change" (the text entry) declines. Claude Code question: each answer and "Type something." are `other`, "Chat about this" declines. Review: "Submit answers" accepts, "Cancel" declines.

The kinds of an option: `choice` (its key answers the dialog at once), `text` (its key moves the cursor to a text entry: "Type something." of a question, "Tell Claude what to change" of the plan dialog; only `answerText` uses it), `other` ("Chat about this": its key ends the question with no answer, and the agent then waits for a message in its terminal. It is safe to press; the window should show it apart from the answers).

What a reader wants before it gives a `Prompt`: the frame (Claude Code: the rule at the first column, the title lines, the two dashed lines; Codex: its first line exactly one time on the whole screen), the question, every option numbered from 1 in sequence with at most nine, exactly one cursor, the hint line, and nothing below the dialog (Claude Code: one rule with a session name on the last line of the screen is allowed, as the program draws it after the plan view). Not read, so `unreadable`: the check-box question of Claude Code (many answers), a question with a text typed in its entry, the "trust this folder" dialogs, a Codex dialog whose first line is not on the screen.

Checks added in fix round 1 (the adversarial screens of the review, `tests/fixtures/prompts/adversarial/`, 27 screens, each with its expected result in `tests/test_prompts_adversarial.py`):

- The top rule of a whole Claude Code permission or plan dialog has an empty line right above it (as Claude Code draws it). A text line there (a cut dialog whose detail draws a frame), or a rule on the first line of the screen: not read.
- A cut plan: each line of its visible part is behind the three spaces of the plan; else not read.
- A question or review dialog: exactly one "rule, then a header" pair above the options. A question text that draws a second one: not read (the title and the question shown could be the agent's).
- Only the Fetch dialog may have no hint line (its last label ends with "(esc)"). The permission hint is " Esc to cancel · Tab to amend", or " Esc to cancel" alone while the cursor is on an option that cannot be amended (measured: options 2 and 3 of a Bash dialog).

Known limit of the question dialog: a label that is too long for one line goes on in the next line with the same indent as a description. The reader puts that rest at the start of the description. The keys are right.

### The keys (measured on 2026-11-19, Claude Code 2.1.322, Codex 0.170.0)

| Program | Dialog | Keys |
|---|---|---|
| Claude Code | permission: Bash, Edit, Create, Fetch | the digit of the option; it acts at once, with no Enter |
| Claude Code | question, one choice (also one tab of many) | the digit; with tabs the next tab shows, and the backend shows it as the next question |
| Claude Code | review tab of many questions | `1` Submit answers, `2` Cancel |
| Claude Code | plan approval | `1`, `2` at once; `3` opens the text entry |
| Claude Code | "Chat about this" | its digit; the question ends with no answer |
| Claude Code | check-box question | a digit changes one box; "Submit" has no number. Not answered by Bellwether |
| Codex | command approval, edit approval | the digit; it acts at once. The letters in the labels ("(y)", "(p)", "(a)", "(esc)") are not used |
| both | "trust this folder" | Claude Code: arrows and Enter. Codex: Enter. Herdr does not call them blocked: no reader |

Free text (Claude Code question and plan): press the digit of the text option, read the screen until the cursor is on that option (the same fingerprint; four reads at the most, 0.25 s apart), then `herdr-core send --force -- <terminal> <text>`, which pastes the text and presses Enter. `herdr-core keys` cannot type a text: it makes capital letters small and refuses a whole call for a character with no key name. `send` puts a `<hc from="…">` tag around the text when the caller has `HC_TERMINAL_ID`; the client runs it through `env -u HC_TERMINAL_ID -u HC_SCOPE -u HC_TERMINAL_SOCKET`. A text is one line of 1 to 2000 visible characters.

To make Codex ask on this machine: `codex -a on-request -s read-only -c 'approvals_reviewer="user"'` (the user's `config.toml` has `approvals_reviewer = "auto_review"`, which answers for the person).

### The client (`HerdrClient`)

- `read_screen(terminal) -> Screen(text, complete) | Failure(code)`: `herdr-core read <t> --json`, 2 s.
- `press(terminal, keys) -> None | Failure(code)`: `herdr-core keys <t> <key>…`, 10 s (above the 3 s hold of herdr-core; see "Facts"). Keys: one to four digits "1"–"9", nothing else. A `timeout` does not mean that the key did not go: a killed `keys` still delivers.
- `send_text(terminal, text) -> None | Failure(code)`: `herdr-core send --force -- <t> <text>`, 65 s (above the 60 s draft hold). `--` ends the options: a text that starts with "-" is text.
- `text_problem(text) -> str`: "" for a text that can be sent, else `text_empty`, `text_long` (more than 2000 characters), `text_lines` (a line break of any kind) or `text_control` (a control character, an escape sequence, or a bidirectional control). Emoji sequences (zero-width joiner, variation selectors, tag characters) are fine. `valid_text(text)` is `text_problem(text) == ""`.
- A terminal must have the form of an address (`t7`, `t1c`, `machine/t7`) and be in the last list of agents. A NAME can have that form too, so each screen call first runs `herdr-core get <t> --json` (2 s) and goes on only when the `address` of the answer is the same text; else the code is `not_this_terminal` and no other command runs. Codes: `bad_address`, `unknown_terminal`, `not_this_terminal`, `bad_key`, `bad_text`, `no_core`, `timeout`, `no_run`, `bad_reply`, `herdr_<kind>` (the error kind of herdr-core, for example `herdr_not_found`), `exit_<n>`.
- The address of a row of `herdr-app ls` (`terminal`) is the address of `herdr-core` (`address`): the same text. `machine/t7` is from the help of herdr-core; no such row was there to test.

### The backend: slots, signal, values

| Name | Kind | Meaning |
|---|---|---|
| `openPrompt(key)` | slot | Open the prompt of the agent row `key`. An agent that is not blocked gives `gone`. It does NOTHING (no state change, no signal) for a key that is not in the list, after the program stopped, and while `answering` is true (states `answering` and `pending`): the window then keeps what it shows; it should not offer the action in those states |
| `answer(optionKey) -> bool` | slot | Press the key of an option of the kind `choice` or `other`. `true`: started. `false`: refused, nothing changes (the state is not `ready`, the prompt has no such option, it is the text option, or the prompt is blind and the option is not `allowed`) |
| `answerText(text) -> bool` | slot | Answer with a text. `false`: refused. When the state is `ready` and the text option is allowed but the text cannot be sent, the state stays `ready` and `reason` / `message` say why (`text_empty`, `text_long`, `text_lines`, `text_control`): this is the one way the window learns the reason. In the other cases (not `ready`, no text option, blind) nothing changes |
| `closePrompt()` | slot | Close, and drop the question and the screen text. A key that herdr-core has taken is NOT stopped: it can still arrive (a held key, or a worker that was past its last check). A text that herdr-core holds for a draft is cancelled only when the worker's `send` ends; a close does not end it |
| `prompt` | property (map), notify `promptChanged` | See below. Every key is always there |
| `answering` | property (yes/no), notify `promptChanged` | The state is `answering` or `pending` |
| `promptChanged()` | signal | `prompt` or `answering` is different |
| `canAnswer` | key of each agent row in `groups` | `true` for each blocked row whose key is a terminal address (top-level agents and sub-agents: a sub-agent row has its own terminal address in the list; this was read from the code, no real sub-agent was there to test). Also for a program with no reader: the window then shows the screen |

The `prompt` map:

| Key | Value |
|---|---|
| `state` | `closed`, `loading`, `ready`, `unreadable`, `gone`, `answering`, `pending`, `sent`, `failed` |
| `key`, `address` | the terminal address of the agent (the same text) |
| `label`, `icon`, `program` | the label and the icon of the agent row, and the program word |
| `kind`, `title`, `subtitle`, `question`, `detail`, `cut`, `blind`, `options`, `cursor` | the fields of the `Prompt`; empty (or false) when no question shows. `options`: a list of `{key, label, description, kind, effect, allowed}`; `allowed` false: the window shows the option but its button is off (an option that approves on a blind prompt) |
| `freeText` | the question has a text option and it is allowed: show the text field |
| `screen` | the text of the screen, only in the state `unreadable`; else empty |
| `reason` | a reason code, or empty |
| `message` | a short fixed text for the person, or empty. In `ready` with no reason and a blind prompt: "The full content is not visible here. Open it in Herdr to approve." |
| `changed` | `reason` is `changed`: the last answer was not sent because the screen was different ("The question changed. Nothing was sent.") |

The reason codes and their messages (fixed text, `bellwether/prompt_session.py: MESSAGES`):

| `reason` | State | `message` |
|---|---|---|
| `not_blocked` (also `unknown_terminal`, `herdr_not_found`, `herdr_finished`) | `gone` | "This agent is not blocked now." |
| `no_reader` / `not_recognised` / `incomplete` | `unreadable` | "Bellwether cannot read the questions of this program." / "Bellwether does not know this screen." / "Herdr could not read the whole screen." |
| `changed` | `ready`, `unreadable` | "The question changed. Nothing was sent." |
| `text_key_only` | `ready`, `unreadable` | "The text option was selected but the text was not sent. Check in Herdr." (the digit of the text option went, then the screen was different) |
| `held` | `ready` (the next question), `sent` | "Herdr held the key while someone typed in this terminal. Check in Herdr that it answered the question you saw." |
| `text_empty` / `text_long` / `text_lines` / `text_control` | `ready` | "Type a text first." / "The text is too long: at most 2000 characters." / "The text must be one line." / "The text has characters that cannot be sent (control or direction characters)." |
| `press_timeout`, `send_timeout` | `pending`, then `failed` | "Herdr did not confirm the answer. It may still arrive. Check in Herdr." |
| `unconfirmed` | `sent` | "The agent went on, but Herdr did not confirm the answer. Check in Herdr that it got yours." |
| `no_effect` | `failed` | "The answer was sent, but the question did not change." |
| `text_not_ready` | `failed` | "The text option was selected but its entry did not open. The text was not sent. Check in Herdr." |
| `error` | `failed` | "Bellwether had an error. Open the agent in Herdr." |
| `read_<code>` | `failed` | "The screen of the agent could not be read." |
| `press_<code>`, `send_<code>` (other codes) | `failed` | "The answer was not sent, or Herdr did not confirm it." |
| (none) | `sent` | "Sent." |

What each state has:

| State | Content | Next |
|---|---|---|
| `closed` | everything empty | `openPrompt` |
| `loading` | the agent (`key`, `label`, `icon`, `program`) | `ready`, `unreadable`, `gone`, `failed` |
| `ready` | the question and its options; a `reason` of a note (`changed`, `text_key_only`, `held`, `text_…`) with its `message` while the same question shows; for a blind prompt with no note, the blind `message` | `answer`, `answerText`, a tick (the same or a new question, `unreadable`, `gone`) |
| `answering` | the question stays, for buttons that are off | `sent`, `ready`, `unreadable`, `gone`, `failed`, `pending` |
| `pending` | the question stays, buttons off; `reason` `press_timeout` or `send_timeout`; `message` "… It may still arrive. Check in Herdr." The window should show "Open in Herdr" | `sent` (`unconfirmed`), `failed` (the same reason): see the transitions |
| `sent` | the agent; `message` "Sent." and `closed` after 1 s; with `reason` `held` or `unconfirmed` the `message` of that reason, and it stays until `closePrompt` | `closed` |
| `unreadable` | `screen`; `reason` and `message` set: `no_reader`, `not_recognised`, `incomplete`, or a note (`changed`, `text_key_only`) | a tick can give `ready` or `gone` |
| `gone` | the agent; `reason` `not_blocked`, `unknown_terminal` or a `herdr_…` code; `message` "This agent is not blocked now." | `closePrompt`, `openPrompt` |
| `failed` | the agent, no question; `reason`: `read_<code>`, `press_<code>`, `send_<code>`, `no_effect`, `text_not_ready`, `error`; `message` | `closePrompt`, `openPrompt` |

The transitions:

- `answer`: read the screen again. The same fingerprint: press the one key. A different screen: press nothing, show what is there (`ready` or `unreadable` with `changed`, or `gone`).
- After a key: the list of agents is read at once, and the screen after 0.2, 0.3, 0.5, 0.5, 0.75, 0.75, 1 and 1 s (5 s in all). The agent is not blocked: `sent`. A question with a different fingerprint: `ready`. At the end, the same question: `failed` / `no_effect`; a screen that no reader knows: `unreadable`. A key that took more than 1 s to go (herdr-core held it): the result has the note `held`, and a `sent` with that note stays open.
- A `press` or `send` that ends with `timeout`: `pending`. The reads go on for 25 s (the 5 s above, then each 2 s). The agent is not blocked: `sent` with `unconfirmed`. The same question: the reads go on; at the end `failed` with the timeout reason. Any other screen (a new question, a screen that no reader knows): `failed` with the timeout reason at once, with no buttons, because the held key can still arrive on that new question.
- A text answer: the digit of the text option, then the cursor check. A different screen after the digit: `ready` or `unreadable` with `text_key_only`, and the ticks go on.
- While `ready` or `unreadable`: each read of the list (the existing ticks and the changes of Herdr) reads the screen again, with at least 0.5 s from one read to the next. A read that fails changes nothing. No reads in the other states.
- Offline, the agent not in the list, the agent not blocked: `gone`, and the question is dropped.
- The result of one worker thread at a time counts: a new job, a close and a stop raise the serial number, and the result of an older worker is ignored. An older worker can still run to its end: one that is past its last check presses its key. The state is of the UI thread.
- Memory: the question and the screen text are dropped at `closePrompt`, when the program stops, and when the state changes to one that does not show them.
- Log lines have the terminal address, the program word, the state, the key and reason codes. Never a part of a screen.

### Not obtained, and limits

- A permission dialog of an MCP tool, and a dialog on a terminal narrower than 200 columns (the test terminals of herdr-core have 200 columns and 120 rows). The readers take a label on two lines when the second line starts below the label (as Claude Code does it in the question dialog); for the permission dialogs and Codex this is not measured.
- A Codex dialog taller than the screen, and Codex dialogs other than the two above (for example a question of the model).
- The edit approval of Codex shows only "Description" and "Destination": the diff is in the text above the dialog (Codex can show it in part, "+ Show details"), the reader cannot tie it to the dialog, and `read --lines` does not give it while Codex is blocked. So the prompt does not have it and is blind.
- Whether Claude Code shortens a long command or a long diff inside a dialog that fits the screen was not measured; such a dialog is read as whole.
- `machine/t7` addresses: no machine to test with.
