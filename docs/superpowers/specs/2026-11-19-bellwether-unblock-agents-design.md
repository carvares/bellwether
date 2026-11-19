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
- A button is on only when its option is `allowed`, and the text field is there only when `freeText` is true. The engine sets `allowed` false on every option and `freeText` false in every state other than `ready` (also `answering` and `pending`), so a mistake of the window cannot send; the engine also refuses the slots then. The window should still use `answering` to show that an answer is on its way.

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
- A key that is not confirmed can arrive late: after the 25 s of reads, after a close of the window, and after Bellwether stops. Bellwether sends no second key or text to that terminal while its mark is there (see "The mark"). Since Task 25 the `keys` command is not killed at its deadline: it runs on, and the mark stays for as long as it runs, also while a person goes on typing in that terminal. The mark ends when the command ends. Only when the command is lost (a signal ended it) the older rule applies: the mark ends 4 s after Bellwether sees the agent leave the answered question, and a person who types for longer than that can make the held key land on what shows when they stop.
- The mark is in memory only. After Bellwether stops and starts again, it does not know of a key that may still arrive. At the stop it kills a text that herdr-core holds. It waits up to 1 s in all for the calls of answers that run (`PromptSession.finish`). A `keys` command that still runs then is NOT killed (a kill would not stop its key): it is left to end by itself, also after Bellwether has stopped, and it can deliver its key then.
- A late key, then the identical question (Task 25, plain words): when a key of Bellwether arrives late and the agent then shows a question with the same text again, Bellwether cannot tell the second question from the first. The window stays `pending` (`earlier`) with its buttons off until the person answers that question in Herdr. This is the safe side: no second key goes to a question that the first key may still reach.
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
| `subtitle` | text | The lines below the title: a file name, the purpose of a command, a "Tip:" line of Claude Code. Each line as the screen shows it, joined with a line break; none is left out and none is joined to an other (fix round 1 of Task 25) |
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

Checks added in fix round 2 (13 more screens of the re-review, `r01`–`r13`, 40 in all):

- Above that empty line, a line at the first column must be somewhere on the screen ("●", "❯", "✻", … of Claude Code). The detail of a cut dialog is behind a space and can have empty lines, so it can draw an empty line and a frame, but no line at the first column. None: not read (`r04`, `r11`).
- A Codex dialog is whole only when a line of Codex at the first column ("• …" its work, "› …" the message of the person) is above its first line. A command taller than the screen hides the real first line, and its lines (behind two spaces, with empty lines) can draw one. None: the prompt is `cut` and blind, so only "No" can be answered (`r05`).
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
- `press(terminal, keys, late=None) -> None | Failure(code)`: `herdr-core keys <t> <key>…`, 10 s (above the 3 s hold of herdr-core; see "Facts"). Keys: one to four digits "1"–"9", nothing else. A `timeout` does not mean that the key did not go. Since Task 25 the command is never killed (a killed `keys` still delivers, so a kill only loses the proof): after the 10 s the call returns `timeout`, the command runs on, and a thread of the client calls `late` when it ends: `late(None)` (exit 0: the key was delivered), `late(Failure(code))` (an error of herdr-core, `herdr_<kind>` or `exit_<n>`: nothing was sent), or `late(Failure("lost"))` (a signal ended the command, or its end could not be read: no proof).
- "An error code of `keys` means that nothing was sent" is measured for two kinds only (Task 25, own test terminal): `invalid_params` (exit 6, a key name that herdr-core does not know: the question was the same after it) and `finished` (exit 11, the terminal has ended). For every other `herdr_<kind>` and `exit_<n>` it is an assumption.
- `send_text(terminal, text, cancel=None) -> None | Failure(code)`: `herdr-core send --force -- <t> <text>`, 65 s (above the 60 s draft hold). `--` ends the options: a text that starts with "-" is text. With `cancel` (a `threading.Event`, the session always gives one), the command runs as a watched process: when `cancel` is set it is killed (herdr-core then does not type a held text, measured), and the call returns `cancelled` only after the process has ended. A `cancel` that is set before the start runs nothing.
- `text_problem(text) -> str`: "" for a text that can be sent, else `text_empty`, `text_long` (more than 2000 characters), `text_lines` (a line break of any kind) or `text_control` (a control character, an escape sequence, a bidirectional control, or any other invisible character: zero-width space, word joiner, soft hyphen, byte order mark, the language tag, tag characters, variation selectors). Inside emoji only: a zero-width joiner between two emoji, U+FE0E / U+FE0F after an emoji or a keycap base, and the tag characters of a region flag (U+1F3F4, then 2 to 6 tags of small letters or digits, then the cancel tag; for example the flag of Scotland). The text goes to a model: invisible characters could carry words that the person does not see. `valid_text(text)` is `text_problem(text) == ""`.
- A terminal must have the form of an address (`t7`, `t1c`, `machine/t7`) and be in the last list of agents. A NAME can have that form too, so each screen call first runs `herdr-core get <t> --json` (2 s) and goes on only when the `address` of the answer is the same text; else the code is `not_this_terminal` and no other command runs. When the `get` itself fails, nothing else runs either: `check_timeout` (its 2 s ended) or `check_failed` (any other failure), except `herdr_not_found` and `herdr_finished`, which say that the terminal is gone. So a press can take up to 12 s (2 s `get` + 10 s `keys`). Codes: `bad_address`, `unknown_terminal`, `not_this_terminal`, `check_timeout`, `check_failed`, `bad_key`, `bad_text`, `no_core`, `timeout`, `cancelled`, `no_run`, `bad_reply`, `herdr_<kind>` (the error kind of herdr-core, for example `herdr_not_found`), `exit_<n>`.
- The address of a row of `herdr-app ls` (`terminal`) is the address of `herdr-core` (`address`): the same text. `machine/t7` is from the help of herdr-core; no such row was there to test.

### The backend: slots, signal, values

| Name | Kind | Meaning |
|---|---|---|
| `openPrompt(key)` | slot | Open the prompt of the agent row `key`. An agent that is not blocked gives `gone`. A terminal with a mark (see "The mark") shows `pending` with `reason` `earlier`. It does NOTHING (no state change, no signal) for a key that is not in the list, after the program stopped, and while an answer of the open prompt is on its way (states `answering`, and `pending` with `press_timeout` / `send_timeout`): the window then keeps what it shows; it should not offer the action in those states. In `pending` with `earlier` it opens the row asked for |
| `answer(optionKey) -> bool` | slot | Press the key of an option of the kind `choice` or `other`. `true`: started. `false`: refused, nothing changes (the state is not `ready`, the prompt has no such option, it is the text option, or the prompt is blind and the option is not `allowed`). A terminal with a mark: refused, and the state becomes `pending` with `reason` `earlier` |
| `answerText(text) -> bool` | slot | Answer with a text. `false`: refused. When the state is `ready` and the text option is allowed but the text cannot be sent, the state stays `ready` and `reason` / `message` say why (`text_empty`, `text_long`, `text_lines`, `text_control`): this is the one way the window learns the reason. A terminal with a mark: `pending` with `earlier`, as for `answer`. In the other cases (not `ready`, no text option, blind) nothing changes |
| `detailSeen(shown)` | slot | (fix round 1) The answer window showed the last line of the detail of the question with the number `shown`. For that question `seen` becomes true and its options that approve can be `allowed`; `answer` refuses them before (nothing changes, log `reason=unseen`). A number of no question that shows does nothing |
| `showAnswer(key)` | slot | (Task 25) The "Answer" control of a row: `openPrompt(key)`, and then the signal `answerRequested()` when a prompt is open after it. `bellwether/answer.py` shows the answer window at that signal |
| `closePrompt()` | slot | Close, and drop the question and the screen text. A key that herdr-core has taken is NOT stopped: it can still arrive (a held key, or a worker that was past its last check). The `send` of a text that runs is killed (herdr-core then does not type it). The mark of the terminal stays: a reopen shows `pending` / `earlier` until it ends |
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
| `kind`, `title`, `subtitle`, `question`, `detail`, `cut`, `blind`, `options`, `cursor` | the fields of the `Prompt`; empty (or false) when no question shows. `options`: a list of `{key, label, description, kind, effect, allowed}`; `allowed` false: the window shows the option but its button is off (an option that approves on a blind prompt, an option that approves while `seen` is false, and every option in a state other than `ready`) |
| `freeText` | the state is `ready`, the question has a text option and it is allowed: show the text field |
| `screen` | the text of the screen, only in the state `unreadable`; else empty |
| `reason` | a reason code, or empty |
| `message` | a short fixed text for the person, or empty. In `ready` with no reason and a blind prompt: "The full content is not visible here. Open it in Herdr to approve." |
| `changed` | `reason` is `changed`: the last answer was not sent because the screen was different ("The question changed. Nothing was sent.") |
| `shown` | (Task 25) a number that is different for each question that shows, and 0 when no question shows. The same question keeps its number (a tick, a cursor move, a note, `answering`). The window starts its guard when it changes |
| `seen` | (fix round 1) true when the question has no detail, or when the window reported its detail seen to the last line (`detailSeen(shown)`). False when no question shows. A new question (a new `shown`) starts at false, also when an earlier question comes back |

Each option of `options` also has `wide` (Task 25): `true` for an option that approves more than the one thing that the dialog shows. The rule (`prompt_session.py: wide`): the effect is `accept` and the label, without a key hint at its end ("(y)"), is not one of "Yes", "Yes, proceed", "Yes, manually approve edits", "Submit answers". So "always allow …", "don't ask again …", "… auto mode", "accept edits … for this session" and every accept label that is not known are wide.

The reason codes and their messages (fixed text, `bellwether/prompt_session.py: MESSAGES`):

| `reason` | State | `message` |
|---|---|---|
| `not_blocked` (also `unknown_terminal`, `herdr_not_found`, `herdr_finished`) | `gone` | "This agent is not blocked now." |
| `no_reader` / `not_recognised` / `incomplete` | `unreadable` | "Bellwether cannot read the questions of this program." / "Bellwether does not know this screen." / "Herdr could not read the whole screen." |
| `changed` | `ready`, `unreadable` | "The question changed. Nothing was sent." |
| `text_key_only` | `ready`, `unreadable` | "The text option was selected but the text was not sent. Check in Herdr." (the digit of the text option went, then the screen was different) |
| `held` | `ready` (the next question), `sent` | "Herdr held the key while someone typed in this terminal. Check in Herdr that it answered the question you saw." |
| `text_empty` / `text_long` / `text_lines` / `text_control` | `ready` | "Type a text first." / "The text is too long: at most 2000 characters." / "The text must be one line." / "The text has characters that cannot be sent (control, direction or invisible characters)." |
| `press_timeout`, `send_timeout` | `pending`, then `failed` | "Herdr did not confirm the answer. It may still arrive. Check in Herdr." |
| `earlier` | `pending` | "An earlier answer to this agent may still arrive. Nothing more can be sent until it has arrived or can no longer arrive. Check in Herdr." (fix round 1: true for both ends of the mark, the end of a `keys` command that runs on, and the settle rule) |
| `check_timeout` / `check_failed` | `failed` | "Herdr did not answer the check of the terminal. Nothing was sent." / "Herdr could not check the terminal. Nothing was sent." (the `get` before the key failed: `keys` did not run) |
| `text_check` | `failed` | "The text option was selected, but Herdr could not check the terminal before the text. The text was not sent. Check in Herdr." |
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
| `pending` | the question stays, buttons off; `reason` `press_timeout` or `send_timeout`; `message` "… It may still arrive. Check in Herdr." The window should show "Open in Herdr" | `sent` (`unconfirmed`), `failed` (the same reason), `gone` (Herdr does not have the terminal): see the transitions |
| `pending` (`earlier`) | the question that shows now (it can be a new one), buttons off, no text field; `message` of `earlier` | `ready` / `unreadable` when the mark ends, `gone` (the agent is not blocked), `openPrompt`, `closePrompt` |
| `sent` | the agent; `message` "Sent." and `closed` after 1 s; with `reason` `held` or `unconfirmed` the `message` of that reason, and it stays until `closePrompt` | `closed` |
| `unreadable` | `screen`; `reason` and `message` set: `no_reader`, `not_recognised`, `incomplete`, or a note (`changed`, `text_key_only`) | a tick can give `ready` or `gone` |
| `gone` | the agent; `reason` `not_blocked`, `unknown_terminal` or a `herdr_…` code; `message` "This agent is not blocked now." | `closePrompt`, `openPrompt` |
| `failed` | the agent, no question; `reason`: `read_<code>`, `press_<code>`, `send_<code>`, `check_timeout`, `check_failed`, `text_check`, `no_effect`, `text_not_ready`, `error`; `message` | `closePrompt`, `openPrompt` |

The transitions:

- `answer`: read the screen again. The same fingerprint: press the one key. A different screen: press nothing, show what is there (`ready` or `unreadable` with `changed`, or `gone`).
- After a key: the list of agents is read at once, and the screen after 0.2, 0.3, 0.5, 0.5, 0.75, 0.75, 1 and 1 s (5 s in all). The agent is not blocked: `sent`. A question with a different fingerprint: `ready`. At the end, the same question: `failed` / `no_effect`; a screen that no reader knows: `unreadable`. A key that took more than 1 s to go (herdr-core held it): the result has the note `held`, and a `sent` with that note stays open.
- A `press` or `send` that ends with `timeout`: `pending`. The reads go on for 25 s (the 5 s above, then each 2 s). The agent is not blocked: `sent` with `unconfirmed`. The same question: the reads go on; at the end `failed` with the timeout reason. Any other screen (a new question, a screen that no reader knows): `failed` with the timeout reason at once, with no buttons, because the held key can still arrive on that new question.
- A text answer: the digit of the text option, then the cursor check. A different screen after the digit: `ready` or `unreadable` with `text_key_only`, and the ticks go on.
- While `ready`, `unreadable` or `pending` (`earlier`): each read of the list (the existing ticks and the changes of Herdr) reads the screen again, with at least 0.5 s from one read to the next (at once when a mark just ended). A read that fails changes nothing. No reads in the other states.
- Offline, the agent not in the list, the agent not blocked: `gone`, and the question is dropped.
- The result of one worker thread at a time counts: a new job, a close and a stop raise the serial number, and the result of an older worker is ignored. An older worker can still run to its end: one that is past its last check presses its key. The state is of the UI thread.
- Memory: the question and the screen text are dropped at `closePrompt`, when the program stops, and when the state changes to one that does not show them.

### The mark (fix round 2)

Bellwether sends no second key or text to a terminal while a first one may still be in the hold of herdr-core. The window state cannot hold that rule: a close (Esc) ends the state, and after `pending` comes `failed`. So the session keeps a **mark** per terminal address (`bellwether/prompt_session.py: Mark`), apart from the open prompt. A close does not end it.

- It is set when an answer starts (the read before the key, the key, the text).
- While it is there: `openPrompt` on that terminal shows `pending` with `reason` `earlier` (the question that shows now, no option `allowed`, no text field), `answer` and `answerText` are refused, for every look and after any close and reopen. Each terminal has its own mark.
- When the call of the answer returns, the mark ends at once when nothing of it can still arrive: the key or the text was confirmed; nothing was sent (a different screen, a failed read, a failed check, any error code of `keys` or `send` other than `timeout`); the key of the text option went but the text did not (`text_key_only`, `text_not_ready`, `text_check`); or a close killed the `send` (the kill is confirmed: the process ended; herdr-core does not type a killed held text, measured).
- A `send` killed at its 65 s deadline (`send_timeout`): the mark ends 4 s later, in case herdr-core was typing it at the kill.
- A `keys` command past its deadline (`press_timeout`; changed in Task 25): the command is not killed and runs on. The mark stays while it runs, with no limit and with no settle time. When it ends with exit 0, the key was delivered: the mark ends, and a prompt of that terminal that is `pending` or `failed` with `press_timeout` goes to `answering` and reads the screen as after any key, with the note `held` (then `sent`, `ready` with the next question, or `failed` / `no_effect`). When it ends with an error of herdr-core, nothing was sent: the mark ends, and that prompt is `failed` with `press_<code>`. A prompt that waits with `earlier` reads the screen at once in both cases. Log: `mark terminal=<t> cleared reason=delivered` or `reason=press_<code>`.
- Only a `keys` command that is lost (`late` gives `lost`; log `kept reason=lost`) has the older rule: a killed `keys` still delivers, and herdr-core holds it with no limit while a person types in that terminal. The mark then never ends by time alone while the answered question (the same fingerprint) shows. It ends 4 s (`SETTLE_SECONDS`: the measured 3.0 s hold after a person's last key, plus 1 s) after Bellwether first sees the agent leave that question: a read of the list shows the agent not blocked (offline is not a proof), or a read of its screen shows a question with a different fingerprint. A read that shows the answered question again starts it over. A screen that no reader knows proves nothing.
- At the stop of the program, a `send` that runs is killed, and the stop waits up to 1 s for the calls that run. A `keys` command that runs is not killed: it ends by itself, also after the program. The marks are in memory only (see Limits).
- Log lines: `mark terminal=<t> set`, `kept reason=<code>`, `cleared reason=<code>`; never screen text.
- Log lines have the terminal address, the program word, the state, the key and reason codes. Never a part of a screen.

### Not obtained, and limits

- A permission dialog of an MCP tool.
- Narrow terminals were measured in Task 25 (80 and 50 columns; see "The narrow-pane measurement" below). Not measured: a terminal narrower than 50 columns, and a real pane of the Herdr app that a person made narrow.
- A Codex dialog taller than the screen, and Codex dialogs other than the two above (for example a question of the model).
- The edit approval of Codex shows only "Description" and "Destination": the diff is in the text above the dialog (Codex can show it in part, "+ Show details"), the reader cannot tie it to the dialog, and `read --lines` does not give it while Codex is blocked. So the prompt does not have it and is blind.
- Whether Claude Code shortens a long command or a long diff inside a dialog that fits the screen was not measured; such a dialog is read as whole.
- `machine/t7` addresses: no machine to test with.

## Part 0 of Task 25: the narrow-pane measurement and the readers

How the width was set: `herdr-core run` has no size option. The program is started as `sh -c 'stty cols N rows 45; exec <program> …'`. The program then draws for N columns (every line of the read screen is at most N wide); Herdr names the agent after the `exec`. Measured with N = 80 and N = 50, Claude Code 2.1.322 and Codex 0.170.0, on own test terminals with made-up tasks. The screens are fixtures (`tests/fixtures/prompts/narrow/`, 8 files, sanitized), each with its exact expected prompt (`tests/test_prompts_narrow.py`).

- Codex, command approval: a command wider than the terminal goes on behind the same two spaces, at a space. A word longer than the line is cut and goes on behind two spaces. No line of a command starts at the first column. So the rule "a line of Codex at the first column above the first line of the dialog proves that the dialog is whole" holds, and the screens s1 and s2 of the second re-review (a wrapped tail at the first column) are not real. The screen s3 of that review is a fixture (blind). An option label wraps behind five spaces, at a space or after a hyphen: the reader joins a part that ends with "-" with no space.
- Claude Code, Bash permission: the command wraps inside its box, each line behind " │ ". The "Tip:" line and the purpose line wrap to a second line behind one space. A label wraps behind six spaces: at a space, or inside a word when the line is full (a long path).
- Claude Code, edit permission: a diff line wider than the terminal is cut at the width and goes on behind "   +".
- Claude Code, question: a question of more than one line has "│ " in front of each line. A label that wraps goes on with the indent of a description.
- The rule of the reader (`claude.py: _wraps`): a line goes on from the line before it when that line is full (as wide as the rule of the dialog), or when the first word of the line had no room at the end of the line before. With it: a label cut inside a word has no space there; a wrapped label of a question is whole and its description starts at the first line that does not go on (this also ends the old "known limit" of the 200-column question); the bars of a question are left out.
- Fix round 1: the header of a permission dialog is NOT joined and nothing is left out. Measured at 84, 90 and 95 columns (own test terminals, Claude Code 2.1.322; fixtures `narrow/84|90|95-claude-bash|edit`): the tip is one line of 82 characters and the purpose is the next line; a purpose whose first word is long had "no room" after the tip, so the join rule put the purpose into the tip and the tip filter dropped both. Now the subtitle is every line below the title as the screen shows it (the tip too). An edit dialog shows no tip (50, 80, 84, 90, 95 columns).
- Fix round 1: a Codex label that ends in a lone "-" (a space before it) goes on with a space, as on the screen; only a hyphen inside a word joins with no space.
- Fix round 1: a question label that fills its line, then a description whose first word has no room on that line, is the same screen as a longer label with no description (same indent, no colour in the read text). The reader takes the longer label (`test_a_full_label_line_and_a_description_cannot_be_told_apart_on_the_screen`); nothing is lost, and the effect of a question option is "other".
- Every one of the 8 screens gave a prompt with all its option keys, effects and every detail line before the change too: none showed less than the screen. The change makes the texts exact.
- Left: a label whose line is full by chance at a space joins with no space; a Codex word longer than the line and with no hyphen joins with a space. Keys and effects are right.

## The interface as built (Task 25)

Code: `bellwether/ui/AnswerControl.qml` (the control of a row), `bellwether/ui/Answer.qml` (the window), `bellwether/ui/controls/OptionButton.qml`, `TextView.qml`, `TextEntry.qml`, `bellwether/answer.py` (it shows the window), and the engine additions `showAnswer`, `answerRequested`, `shown`, `wide`. Tests: `tests/test_answer_control.py`, `tests/test_answer_window.py`.

### The "Answer" control

- The rule "which rows have it" is one line: `AgentRow.canAnswer` (`modelData.canAnswer === true`, from the backend). `AnswerControl` is visible only then.
- The control is a target of the one pointer handler of the panel: `hitRole: "answer"` with the key of the row. `Main.qml: hitAt` goes on inside an agent row and returns the control when the pointer is on it, else the row. A click on the control calls `PanelModel.answer(key)` (`backend.showAnswer(key)`), and the row does not jump. A click on the rest of the row jumps as before. A drag from the control moves the panel. While a jump runs, the control does nothing and is drawn at half opacity.
- The look: the word "Answer" in the accent colour of the theme, at the right end of the row; under the pointer the plate is the accent and the word has the ink that can be read on it (`inkOn`). Each skin gives its style: A a pill with an outline; B a soft plate with a corner of 6; C a square outline and capitals; D an outline with a corner of 6; E a soft pill. The status items have a pointer look and no pressed look, so the control has the same.
- Room: the control keeps its size. On a row with the control the detail (the workspace) is at most 72 px wide, and the label of the agent has the room first: the detail takes only what the whole label leaves (with a large text or a long label it is cut or it goes), and the label elides only when it is wider than the row (`AnswerControl.detailRoom`, `leftByLabel`; fix round 1). The message of a failed jump gives the control its width.
- The name for a screen reader: "Answer <label of the row>".
- With no row that can be answered, every layout draws the same pixels as before Task 25.

### The answer window

One window, made at the first use, 600 px wide, with no title bar of the system: the frame, the header and the tokens of the layout that shows, as the options window. It follows a change of the layout and of the custom look at once. Height: the content, from 220 px to the height of the screen less 80 px; a longer content scrolls between the header and the footer. A long detail takes all the height that the screen leaves free (at least 110 px) and then scrolls in its own view (fix round 1; before: at most 300 px). Place: the compositor chooses it (a Wayland client cannot place a toplevel); the header moves the window.

Header: the icon of the program, the label of the agent, the terminal address, a word for the state, the close control. Footer: the keys, and "Open in Herdr".

| State | What shows | State word | "Open in Herdr" |
|---|---|---|---|
| `loading` | "Reading the screen of the agent…" | Reading… | plain |
| `ready` | the title and subtitle, the detail, the question, one button for each option, the text field when `freeText`; a note of the engine at the top (`changed`, `held`, `text_key_only`); a refused text (`text_…`) at the field | none | plain |
| `ready`, blind | the same, the message of the engine at the top, the options that approve are off; "This is only the lower part …" when `cut` | Partly visible | main action |
| `unreadable` | the message; the screen as lines in a monospace view (only in this state) | Not readable | main action |
| `answering` | the question with every button off | Sending… | plain |
| `pending` (also `earlier`) | the message ("… Check in Herdr."), the question with every button off | Not confirmed | main action |
| `sent` | "Sent."; the engine closes the prompt after 1 s and the window goes away. With `held` or `unconfirmed` the message stays until the person closes | Sent | plain |
| `failed` | the message of the reason | Failed | main action |
| `gone` | "This agent is not blocked now." | Not blocked | main action |
| `closed` | the window is not on the screen | | |

Every message is the text of the engine (`MESSAGES`): the window has none of them in its file.

- The detail and the screen: plain text, a monospace font of the system, one item for each line of the screen with a thin mark at its left. A line wider than the view WRAPS (at a space, or inside a long word) and the next row has no new mark. Decision: wrap, not a sideways scroll. A sideways scroll hides the end of a command, and a person could approve a command without its end. The mark keeps a wrapped line apart from two lines.
- The options: the key in a cap, the label, the description below. Three looks that differ in shape and in colour: `accept` and not `wide`: a full cap in the accent; `wide`: an empty cap with a border of 2 px and a bar at the left, both in the warning colour (the colour of the status "blocked" of the custom look, or the ink when that colour cannot be told from the panel); `decline`: an empty cap, grey. An answer to a question (`other`): an empty cap in the text colour. "Chat about this" is below a line. An option that is not `allowed` is at 40 % opacity and does nothing. The window invents no label.
- The text option is the text field, at its place in the list, with its key and its label as the hint, and "Send". The field keeps its text when the engine refuses it.
- The end of the detail (fix round 1): while lines of the detail are out of view, a bar at the foot of its view says how many ("12 more lines below", "3 lines above"), in the text colour of the theme. The options that approve stay off, with the line "Scroll to the end of the text above to approve.", until the last line of the detail has been in view: by the wheel, a drag of the text or of the thumb, or the keys (Page Down, End, the arrows when the view has the keyboard; Page Down, Page Up, Home and End also from the window). The window then calls `backend.detailSeen(shown)`; a detail that fits is reported when the guard ends. Each new question (`shown`) puts the detail view and the content of the window back to their top in the same step that starts the guard, so a new command never shows at the scroll place of the one before, and its end is reported only when it came into view after that (fix round 2). The end counts only within 1 px of the foot of the view. On a low screen the content of the window scrolls too: the end must then also be in the window. While an option that approves is off for this reason (in either way), the line below the detail and the footer say "Scroll to the end of the text above to approve." (the footer is always in view; with the lock of the number keys too it says "Number keys off: click or press Tab. Scroll to the end of the text above to approve." with no "Esc closes.", for room). The engine refuses an option that approves while `seen` is false (log `result=refused reason=unseen`), so a fault of the window cannot skip the rule. Options that decline, the text field and "Open in Herdr" need nothing.
- The guards (fix round 1). Each time a question shows, and each time the window comes into a state where it can answer (also the same question, for example `pending` or `failed` to `ready`): a click and "Send" do nothing until 400 ms (`guardMs`, the double-click time of KDE) passed with no press of a key or of the pointer; a number key does nothing until 1000 ms (`keyQuietMs`) passed with no key press (a person who types presses a key each 0.1 to 0.3 s: one second with no key means the typing stopped). Each press while a guard runs starts it again. A new question has the mark "New question (no. N)" (N: the questions since the window opened) and a short light over the content; the field is empty again, and no option has the keyboard.
- The number keys: ONE rule (fix round 2; it replaces the conditions of round 1, "the field had the keyboard" and "a key in the last 2 s"). At each change of the question that shows (not at the first question after an open), the number keys are locked, except when all of these are true: the new question is the next question after an answer of the person sent from this window (the engine went from `answering` or `pending` to `ready` with a new question, with no reason or the reason `held`; the reason `changed`, "nothing was sent", does not count), the window is active at the change, and no key press reached the window since that answer was sent (`bellwether/answer.py` watches every key press of the window before any item gets it). A lock is sticky: only a press of the pointer in the window, Tab or Shift+Tab ends it; a later change of the question, of the state, of the keyboard focus or of the activation never ends it. The end of a lock starts the quiet time of the number keys again (1000 ms with no key). A close ends the lock; the next open starts as an open (the guards, then the number keys work). While the keys are locked and a question shows, the line "New question — the number keys are off. Click in the window or press Tab to turn them on." and the footer "Number keys off: click or press Tab. Esc closes." say so.
- Keys: a digit presses the option with that key when it is allowed (the digit of the text option puts the keyboard in the field); a digit typed in the field is text. Tab: the detail when it scrolls, the options and the field in their order, "Send", "Open in Herdr", close. Enter, Return and Space press the control that has the keyboard; at the open and after a new question no control has it. Esc closes.
- An option that approves more than this one thing has the words "Standing permission" under its label (fix round 1), so the look does not rest on the colour when the accent and the warning colour are close.
- Names for a screen reader: "Option 1, Yes, approves" (`approves`, `declines`, `answers`; ", standing permission" for a `wide` option; ", not available" when it is off); "Option 3, Type something., text"; "Send the text"; "Open the agent in Herdr"; "Close"; the detail when it scrolls: "What the agent asks for, 12 more lines below".
- "Open in Herdr" is `backend.focus(key)` and then the close of the window. It is off while a jump runs.
- Every way to close (Esc, the close control, the compositor, "Open in Herdr", the end of the engine) is a window that is not visible, and that calls `closePrompt`. The program hides and shows the window to bring it to the front when it is behind; the property `raising` tells the window that this is not a close.
- The window sends only through `choose()` (`backend.answer`) and `sendText()` (`backend.answerText`), each started by one act of the person, and only for an option that is `allowed` (a test spies on the call). It has two timers: the guard of the pointer and the quiet time of the number keys.
- Privacy: the window binds to `backend.prompt` and keeps no copy; the screen view exists only in the state `unreadable`; no `console.log`.
- Calmer rule for `sent`: the window does not stay for a pointer that enters it. "Sent." has nothing to act on, the engine drops the question at that time, and a sent with a note stays anyway.

Not verified in Task 25: the window on the real desktop (its place, the keyboard focus that KWin gives it, the look on the screen); the control and the window with a real mouse. The live proof ran off screen with the real herdr-core (see `task-25-report.md`).
