"""The answer to one blocked agent: the state machine behind the answer window.

States: closed -> loading -> ready | unreadable | gone | failed; ready -> answering -> sent -> closed, or -> ready (a
new question, or the screen was different and nothing went), unreadable, gone, failed; answering -> pending (Herdr
did not confirm the key or the text: it may still arrive) -> sent | failed | gone.

The mark: an answer to a terminal that may still arrive. It lives outside the open prompt (a close does not end it):
while it is there, the prompt of that terminal is `pending` (reason "earlier") and sends nothing. It ends when the
call of the answer returned and nothing of it can still arrive, or, for a key that herdr-core may still hold, only
when the agent left the answered question for SETTLE_SECONDS (see `Mark`).

The UI thread has the state. A worker thread does one job (a read, or a read and an answer) and gives its result
through a signal. The text of a screen is in memory only: no log line and no file has it.
"""
from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from . import prompts
from .client import Failure, text_problem, valid_address
from .state import Agent

log = logging.getLogger("bellwether")

# While a prompt is open, the screen of its agent is read again at each tick of the list and at each change of the
# agent, with at least this many seconds from one read to the next.
PROMPT_FLOOR = 0.5
# After a key: the waits before the reads that look for the result, in seconds. Then the reads end (5 seconds).
FOLLOW = (0.2, 0.3, 0.5, 0.5, 0.75, 0.75, 1.0, 1.0)
# After a key or a text that Herdr did not confirm: the reads go on longer (25 seconds), as the key can still arrive.
PENDING_FOLLOW = FOLLOW + (2.0,) * 10
# After the key that opens a text entry: this many reads, with this wait before each, look for the cursor in it.
ENTRY_TRIES = 4
ENTRY_WAIT = 0.25
# Seconds that the state "sent" shows before the prompt closes.
SENT_SECONDS = 1.0
# A key that took longer than this many seconds to go was held by herdr-core: a person typed in that terminal in the
# 3 seconds before. The key went to whatever dialog was there when it arrived. A key that is not held takes about
# 0.05 s (measured).
HELD_SECONDS = 1.0
# The terminals that herdr-core does not have any more, as the reason codes of the client.
GONE_CODES = frozenset({"herdr_not_found", "herdr_finished", "unknown_terminal"})
# A key or a text that herdr-core did not confirm before the deadline: it may still arrive.
UNCONFIRMED = frozenset({"press_timeout", "send_timeout"})
# After the agent left the question that a key answered (it is not blocked, or a read shows a different question),
# the mark of a key that herdr-core may still hold ends this many seconds later, if the same question did not come
# back. herdr-core gives a held key 3.0 s after the last key that a person typed in that terminal (measured).
SETTLE_SECONDS = 4.0
# At the stop of the program: the longest wait, in seconds, for the call of an answer that runs (a text is killed).
STOP_SECONDS = 1.0
# What the answer window says. Fixed text: never a part of a screen or of the output of a command.
MESSAGES = {
    "not_blocked": "This agent is not blocked now.",
    "no_reader": "Bellwether cannot read the questions of this program.",
    "not_recognised": "Bellwether does not know this screen.",
    "incomplete": "Herdr could not read the whole screen.",
    "changed": "The question changed. Nothing was sent.",
    "no_effect": "The answer was sent, but the question did not change.",
    "text_key_only": "The text option was selected but the text was not sent. Check in Herdr.",
    "text_not_ready": "The text option was selected but its entry did not open. The text was not sent. Check in Herdr.",
    "press_timeout": "Herdr did not confirm the answer. It may still arrive. Check in Herdr.",
    "send_timeout": "Herdr did not confirm the answer. It may still arrive. Check in Herdr.",
    "unconfirmed": "The agent went on, but Herdr did not confirm the answer. Check in Herdr that it got yours.",
    "held": ("Herdr held the key while someone typed in this terminal. Check in Herdr that it answered the question "
             "you saw."),
    "blind": "The full content is not visible here. Open it in Herdr to approve.",
    "text_empty": "Type a text first.",
    "text_long": "The text is too long: at most 2000 characters.",
    "text_lines": "The text must be one line.",
    "text_control": "The text has characters that cannot be sent (control, direction or invisible characters).",
    "text_check": ("The text option was selected, but Herdr could not check the terminal before the text. The text "
                   "was not sent. Check in Herdr."),
    "check_timeout": "Herdr did not answer the check of the terminal. Nothing was sent.",
    "check_failed": "Herdr could not check the terminal. Nothing was sent.",
    "earlier": ("An earlier answer to this agent may still arrive. Nothing more can be sent until the agent goes on "
                "or shows a different question. Check in Herdr."),
    "sent": "Sent.",
    "error": "Bellwether had an error. Open the agent in Herdr.",
    "read": "The screen of the agent could not be read.",
    "send": "The answer was not sent, or Herdr did not confirm it.",
}
# The notes that stay while the same question (or the same unknown screen) shows: a tick does not take them away.
NOTES = frozenset({"changed", "text_key_only", "held", "text_empty", "text_long", "text_lines", "text_control"})


class Outcome:
    """What one worker found. `kind`: "screen" (a read), "pressed" (the answer went to the terminal; `held`: herdr-core
    held it), "changed" (the screen was different: nothing went), "key_only" (the key of the text option went, then
    the screen was different: the text did not go), or "failed" with a reason code."""

    def __init__(self, kind: str, screen=None, prompt=None, reason: str = "", held: bool = False) -> None:
        self.kind = kind
        self.screen = screen  # a Screen, or None
        self.prompt = prompt  # the Prompt of the screen, or None
        self.reason = reason
        self.held = held


class Mark:
    """An answer to the terminal `key` that may still arrive. `running`: its call (the read, the key, the text) has
    not returned. `left_at`: the clock of the first read that showed the agent away from the answered question (not
    blocked, or a different question), after the call returned; None while the same question shows. `ended`: set by
    the worker when the call returned.

    The rule: a call that returned with the key or the text typed, or with nothing sent, or with a text whose command
    a close killed (herdr-core does not type it then, measured), ends the mark at once. A text whose command was
    killed at its deadline: the mark ends SETTLE_SECONDS later (`until`), in case herdr-core was typing it at the
    kill. A key whose `keys` command was killed (deadline) can still arrive at any time while a person types in that
    terminal: its mark ends only SETTLE_SECONDS after the agent left the answered question, never by time alone
    while that question shows."""

    def __init__(self, key: str, fingerprint: str) -> None:
        self.key = key
        self.fingerprint = fingerprint
        self.running = True
        self.left_at: float | None = None
        self.until: float | None = None  # the end of the mark by time (a killed text)
        self.ended = threading.Event()


class PromptSession(QObject):
    """The prompt of one agent at a time. `lookup(key)` gives the agent of the list with that key (None when the list
    does not have it), `blocked(key)` the same agent only while Herdr is online and the agent is blocked, `row(agent)`
    its row for QML (label, icon), `wake()` starts a read of the list now, `stopped()` is True after the program
    stops."""

    changed = Signal()  # the value or the flag `answering` is different
    _done = Signal(int, object)
    _call_ended = Signal(object, object)  # (Mark, Outcome): the call of an answer returned, also after a close

    def __init__(self, client, lookup, blocked, row, wake, stopped, clock, wait, floor: float = PROMPT_FLOOR,
                 follow: tuple[float, ...] = FOLLOW, pending_follow: tuple[float, ...] | None = None,
                 sent_seconds: float = SENT_SECONDS, parent=None) -> None:
        super().__init__(parent)
        self._client = client
        self._lookup, self._blocked, self._row, self._wake, self._stopped = lookup, blocked, row, wake, stopped
        self._clock = clock
        self._wait = wait  # wait(event, seconds): True when the event is set
        self._floor = floor
        self._follow = follow
        self._pending_follow = PENDING_FOLLOW if pending_follow is None else pending_follow
        self.state = "closed"
        self.agent: Agent | None = None  # the agent of the open prompt, as it was in the list
        self.prompt: prompts.Prompt | None = None  # the question that shows
        self._screen_text = ""  # the screen, only while the state is "unreadable"
        self._reason = ""
        self._note = ""  # a note of NOTES that stays while the same thing shows, or ""
        self._serial = 0  # the number of the last worker: the result of an older one is ignored
        self.busy = False  # the last worker runs
        self._cancel = threading.Event()  # set when the prompt of a worker closes: it then presses nothing
        self._read_at = float("-inf")  # the clock at the start of the last read
        self._follow_left: tuple[float, ...] = ()  # the waits of the reads after a key that are not done yet
        self._answered = ""  # the fingerprint of the question that the last key answered
        self._followed = False  # the key of the answer went to the terminal (or may go): the reads after it run
        self._held = False  # herdr-core held the last key
        self._unconfirmed = ""  # the reason code of a key or a text that Herdr did not confirm, or ""
        self._marks: dict[str, Mark] = {}  # the terminals that an earlier answer may still reach
        self._follow_timer = QTimer(self)
        self._follow_timer.setSingleShot(True)
        self._follow_timer.timeout.connect(self._follow_read)
        self._sent_timer = QTimer(self)
        self._sent_timer.setSingleShot(True)
        self._sent_timer.setInterval(int(sent_seconds * 1000))
        self._sent_timer.timeout.connect(self.close)
        self._done.connect(self._result)
        self._call_ended.connect(self._end_call)

    # ----- the value for QML -----

    def value(self) -> dict:
        """The open prompt for the answer window. Every key is always there."""
        agent, prompt, state, reason = self.agent, self.prompt, self.state, self._reason
        row = self._row(agent) if agent else {}
        if state == "gone":
            message = MESSAGES["not_blocked"]
        elif state == "sent":
            message = MESSAGES.get(reason) or MESSAGES["sent"]
        elif state == "failed":
            message = MESSAGES.get(reason) or MESSAGES["send" if reason.startswith(("press", "send")) else "read"]
        elif reason:
            message = MESSAGES.get(reason, "")
        else:
            message = MESSAGES["blind"] if state == "ready" and prompt is not None and prompt.blind else ""
        # An option can be clicked only while the prompt is ready: never while an answer is on its way or may still
        # arrive, whatever the window does.
        ready = state == "ready"
        return {
            "state": state,
            "key": agent.key if agent else "",
            "label": row.get("label", ""),
            "program": agent.app if agent else "",
            "icon": row.get("icon", ""),
            "address": agent.key if agent else "",
            "kind": prompt.kind if prompt else "",
            "title": prompt.title if prompt else "",
            "subtitle": prompt.subtitle if prompt else "",
            "question": prompt.question if prompt else "",
            "detail": list(prompt.detail) if prompt else [],
            "cut": prompt.cut if prompt else False,
            "blind": prompt.blind if prompt else False,
            "options": [{"key": o.key, "label": o.label, "description": o.description, "kind": o.kind,
                         "effect": o.effect, "allowed": ready and prompt.allows(o.key)} for o in prompt.options]
            if prompt else [],
            "cursor": prompt.cursor if prompt else "",
            "freeText": bool(ready and prompt and prompt.text_key and prompt.allows(prompt.text_key)),
            "screen": self._screen_text if state == "unreadable" else "",
            "reason": reason,
            "message": message,
            "changed": reason == "changed",
        }

    @property
    def answering(self) -> bool:
        """An answer is on its way (or may still arrive): a second one is ignored."""
        return self.state in ("answering", "pending")

    def _set(self, state: str, reason: str = "", prompt=None, screen_text: str = "", keep_agent: bool = True) -> None:
        """Set the state. What the new state does not show is dropped: the question, the screen."""
        before = (self.state, self.prompt, self._screen_text, self._reason, self.agent)
        self.state, self._reason = state, reason
        self._note = reason if reason in NOTES else ""
        self.prompt = prompt
        self._screen_text = screen_text if state == "unreadable" else ""
        if not keep_agent:
            self.agent = None
        if state not in ("answering", "pending"):
            self._follow_timer.stop()
            self._follow_left = ()
            self._followed = False
            self._held = False
            self._unconfirmed = ""
        if state != "sent":
            self._sent_timer.stop()
        after = (self.state, self.prompt, self._screen_text, self._reason, self.agent)
        if after != before:  # also the same question with the cursor on a different option
            if state != before[0] or reason != before[3]:
                log.info("prompt terminal=%s app=%s state=%s reason=%s", self.agent.key if self.agent else "-",
                         self.agent.app if self.agent else "-", state, reason or "-")
            self.changed.emit()

    def _end_workers(self) -> None:
        """No worker that runs now changes the prompt after this. One that is past its last check before the key
        still presses it (its subprocess runs to its end); only its result is ignored."""
        self._cancel.set()
        self._cancel = threading.Event()
        self._serial += 1
        self.busy = False

    # ----- actions -----

    def _earlier(self) -> bool:
        """The open prompt is pending because of the mark of an earlier answer (not of an answer of this prompt)."""
        return self.state == "pending" and self._reason == "earlier"

    def open(self, key: str) -> None:
        """Open the prompt of the agent row with this key. A key that is not in the list does nothing. While an
        answer of the open prompt is on its way (or may still arrive) it does nothing. A terminal with a mark shows
        `pending` (reason "earlier") until the mark ends."""
        agent = self._lookup(key)
        if agent is None or self._stopped() or (self.answering and not self._earlier()):
            return
        self._end_workers()
        self.agent = agent
        if self._blocked(key) is None or not valid_address(key):
            self._set("gone", "not_blocked")
            return
        self._set("loading")
        self._work(self._job_read)

    def close(self) -> None:
        """Close and drop the question and the screen text. A key that herdr-core has taken can still arrive (it is
        not cancelled); the command of a text that runs is killed, and herdr-core then does not type the text. The
        mark of the terminal stays: a reopen shows `pending` until it ends."""
        self._end_workers()
        self._set("closed", keep_agent=False)

    def finish(self, seconds: float = STOP_SECONDS) -> None:
        """Close at the stop of the program, and wait up to `seconds` for the calls of answers that run (the
        command of a text is killed): no command of Bellwether goes on after it."""
        self.close()
        deadline = self._clock() + seconds
        for mark in [mark for mark in self._marks.values() if mark.running]:
            mark.ended.wait(max(0.0, deadline - self._clock()))

    def answer(self, key: str) -> bool:
        """Press the key of one option of the shown prompt. True: the answer started. False: refused (no prompt is
        ready, the prompt has no such option, it is the text option, or the prompt is blind and the option does not
        decline)."""
        prompt = self.prompt
        option = prompt.option(key) if prompt and self.state == "ready" else None
        if option is None or option.kind == prompts.TEXT or not prompt.allows(key) or self._refused_by_mark():
            return False
        self._start_answer(self._job_answer, prompt, key)
        return True

    def _refused_by_mark(self) -> bool:
        """An earlier answer to this terminal may still arrive: the prompt is pending (reason "earlier")."""
        if not self._marked(self.agent.key):
            return False
        log.info("answer terminal=%s app=%s result=refused reason=earlier", self.agent.key, self.agent.app)
        self._set("pending", "earlier", prompt=self.prompt)
        return True

    def answer_text(self, text: str) -> bool:
        """Answer the shown prompt with a text, when it has a text entry. True: the answer started. False: refused.
        A text that cannot be sent leaves the prompt ready with a note (`reason` text_empty, text_long, text_lines or
        text_control, and its `message`)."""
        prompt = self.prompt
        if prompt is None or self.state != "ready" or not prompt.text_key or not prompt.allows(prompt.text_key):
            return False
        if self._refused_by_mark():
            return False
        problem = text_problem(text)
        if problem:
            self._set("ready", problem, prompt=prompt)
            return False
        self._start_answer(self._job_text, prompt, text)
        return True

    def tick(self) -> None:
        """After each read of the list: the prompt of an agent that is not blocked now is gone (after a key: it is
        sent). The screen of a prompt that shows is read again, with a pause from one read to the next."""
        self._scan_marks()
        state, agent = self.state, self.agent
        if agent is None or state not in ("loading", "ready", "unreadable", "answering", "pending"):
            return
        current = self._blocked(agent.key)
        if self._earlier():
            if current is None:
                self._end_workers()
                self._set("gone", "not_blocked")
            elif not self.busy and (not self._marked(agent.key) or self._clock() - self._read_at >= self._floor):
                self._work(self._job_read)  # each read can end the mark; a mark that ended: read now
            return
        if self.answering:
            if current is None and self._followed:
                self._end_workers()  # a read after the key that runs now has nothing more to say
                self._sent()
            return
        if current is None:
            self._end_workers()
            self._set("gone", "not_blocked")
            return
        if state != "loading" and not self.busy and self._clock() - self._read_at >= self._floor:
            self._work(self._job_read)

    def _start_answer(self, job, prompt, value: str) -> None:
        self._end_workers()  # a read of a tick that runs now is not needed: the answer reads again
        self._answered = prompt.fingerprint
        mark = self._marks[self.agent.key] = Mark(self.agent.key, prompt.fingerprint)
        log.info("mark terminal=%s set", mark.key)
        self._set("answering", prompt=prompt)
        self._work(job, prompt, value, mark=mark)

    def _work(self, job, *args, mark: Mark | None = None) -> None:
        """Start one worker. The result of a worker that started before it is ignored; the end of the call of an
        answer (`mark`) is not."""
        self._serial += 1
        self.busy = True
        self._read_at = self._clock()
        threading.Thread(target=self._run, name="herdr-prompt", daemon=True,
                         args=(self._serial, self._cancel, mark, job, self.agent, *args)).start()

    def _run(self, serial: int, cancel: threading.Event, mark: Mark | None, job, agent: Agent, *args) -> None:
        try:
            outcome = job(cancel, agent, *args)
        except Exception as exc:  # The class name only: the text of an error can hold a screen.
            log.warning("prompt failed terminal=%s error=%s", agent.key, type(exc).__name__)
            outcome = Outcome("failed", reason="error")
        if mark is not None:
            mark.ended.set()
            self._call_ended.emit(mark, outcome)  # before the result: the mark is right when the result comes
        self._done.emit(serial, outcome)

    # ----- the marks: on the UI thread -----

    @Slot(object, object)
    def _end_call(self, mark: Mark, outcome: Outcome) -> None:
        """The call of an answer returned. Its mark ends now, except for a key that herdr-core may still hold."""
        if self._marks.get(mark.key) is not mark:
            return
        mark.running = False
        if outcome.kind == "failed" and outcome.reason == "press_timeout":
            log.info("mark terminal=%s kept reason=press_timeout", mark.key)  # a killed `keys` still delivers
            return
        if outcome.kind == "failed" and outcome.reason == "send_timeout":
            mark.until = self._clock() + SETTLE_SECONDS
            log.info("mark terminal=%s kept reason=send_timeout", mark.key)
            return
        del self._marks[mark.key]
        log.info("mark terminal=%s cleared reason=%s", mark.key, outcome.reason or outcome.kind)
        if self._earlier() and self.agent is not None and self.agent.key == mark.key and not self.busy:
            self._work(self._job_read)  # the prompt that waited for this mark reads the screen now

    def _marked(self, key: str) -> bool:
        """An earlier answer may still reach the terminal `key`. A mark whose settle time has passed ends here."""
        mark = self._marks.get(key)
        if mark is None:
            return False
        now = self._clock()
        if mark.running or ((mark.left_at is None or now - mark.left_at < SETTLE_SECONDS)
                            and (mark.until is None or now < mark.until)):
            return True
        del self._marks[key]
        log.info("mark terminal=%s cleared reason=%s", key, "left" if mark.left_at is not None else "time")
        return False

    def _saw(self, key: str, prompt) -> None:
        """A read of the screen of `key` showed this question (or no question: that proves nothing)."""
        mark = self._marks.get(key)
        if mark is None or mark.running or prompt is None:
            return
        if prompt.fingerprint == mark.fingerprint:
            mark.left_at = None  # the answered question shows: the key may still come to it
        elif mark.left_at is None:
            mark.left_at = self._clock()

    def _scan_marks(self) -> None:
        """At each read of the list: an agent of the list that is not blocked has left the answered question."""
        for key, mark in list(self._marks.items()):
            listed = self._lookup(key) is not None  # offline, the list is empty: that proves nothing
            if not mark.running and mark.left_at is None and listed and self._blocked(key) is None:
                mark.left_at = self._clock()
            self._marked(key)

    # ----- the jobs: they run on the worker thread and do not touch the state -----

    def _read(self, agent: Agent) -> Outcome:
        screen = self._client.read_screen(agent.key)
        if isinstance(screen, Failure):
            return Outcome("failed", reason=f"read_{screen.code}" if screen.code not in GONE_CODES else screen.code)
        return Outcome("screen", screen, prompts.parse(agent.app, screen.text, screen.complete))

    def _job_read(self, cancel: threading.Event, agent: Agent) -> Outcome:
        return self._read(agent)

    def _same(self, cancel: threading.Event, agent: Agent, shown) -> Outcome | None:
        """Read the screen again, right before the key. None: it has the shown question, and the prompt is still
        open."""
        found = self._read(agent)
        if found.kind == "failed":
            return found
        if found.prompt is None or found.prompt.fingerprint != shown.fingerprint:
            log.info("answer terminal=%s app=%s result=changed", agent.key, agent.app)
            return Outcome("changed", found.screen, found.prompt)
        return Outcome("failed", reason="closed") if cancel.is_set() else None

    def _press(self, agent: Agent, key: str) -> Outcome:
        """Press one key and time it: a key that took long was held by herdr-core."""
        began = self._clock()
        failure = self._client.press(agent.key, [key])
        held = self._clock() - began > HELD_SECONDS
        log.info("answer terminal=%s app=%s key=%s result=%s held=%s", agent.key, agent.app, key,
                 failure.code if failure else "pressed", held)
        if failure is None:
            return Outcome("pressed", held=held)
        # A failed check of the address: `keys` did not run.
        return Outcome("failed", reason=failure.code if failure.code.startswith("check_") else f"press_{failure.code}")

    def _job_answer(self, cancel: threading.Event, agent: Agent, shown, key: str) -> Outcome:
        different = self._same(cancel, agent, shown)
        return different if different is not None else self._press(agent, key)

    def _job_text(self, cancel: threading.Event, agent: Agent, shown, text: str) -> Outcome:
        different = self._same(cancel, agent, shown)
        if different is not None:
            return different
        key = shown.text_key
        pressed = self._press(agent, key)
        if pressed.kind == "failed":
            return pressed
        # The key moves the cursor to the text entry. The text goes only when the screen shows the cursor there.
        for _ in range(ENTRY_TRIES):
            if self._wait(cancel, ENTRY_WAIT):
                return Outcome("failed", reason="closed")
            found = self._read(agent)
            if found.kind == "failed":
                return found
            if found.prompt is None or found.prompt.fingerprint != shown.fingerprint:
                log.info("answer terminal=%s app=%s result=key_only", agent.key, agent.app)
                return Outcome("key_only", found.screen, found.prompt)
            if found.prompt.cursor == key:
                break
        else:
            return Outcome("failed", reason="text_not_ready")
        failure = self._client.send_text(agent.key, text, cancel=cancel)  # a close kills it
        log.info("answer terminal=%s app=%s text result=%s", agent.key, agent.app, failure.code if failure else "sent")
        if failure is None:
            return Outcome("pressed", held=pressed.held)
        # A failed check of the address: `send` did not run. The key of the text option went.
        return Outcome("failed", reason="text_check" if failure.code.startswith("check_") else f"send_{failure.code}")

    # ----- the results: on the UI thread -----

    def _show_screen(self, outcome: Outcome, note: str = "") -> None:
        """Show what a read found: the question, or the screen that no reader knows. `note`: a reason of NOTES.
        While an earlier answer may still arrive, the prompt is pending: it shows the question with no option."""
        if self._marked(self.agent.key):
            self._set("pending", "earlier", prompt=outcome.prompt)
            return
        if outcome.prompt is not None:
            self._set("ready", note, prompt=outcome.prompt)
            return
        reason = note or ("no_reader" if not prompts.has_reader(self.agent.app) else
                          "not_recognised" if outcome.screen.complete else "incomplete")
        self._set("unreadable", reason, screen_text=outcome.screen.text)

    @Slot(int, object)
    def _result(self, serial: int, outcome: Outcome) -> None:
        if serial != self._serial:
            return  # A worker of a prompt that is closed, or an older read.
        self.busy = False
        state, agent = self.state, self.agent
        if state not in ("loading", "ready", "unreadable", "answering", "pending") or agent is None:
            return
        blocked = self._blocked(agent.key) is not None
        if outcome.kind == "screen":
            self._saw(agent.key, outcome.prompt)
        if outcome.kind == "failed" and outcome.reason in GONE_CODES:
            self._set("gone", outcome.reason)
        elif self._earlier():
            if outcome.kind == "screen":
                self._show_screen(outcome)  # pending while the mark is there, else the question
            # A read that fails changes nothing: the next tick reads again.
        elif self.answering:
            self._answer_done(outcome, blocked)
        elif outcome.kind == "failed":
            if state == "loading":
                self._set("failed", outcome.reason)
            # A later read that fails changes nothing: the next tick reads again.
        elif outcome.kind == "screen":
            # A note stays while the same thing shows.
            same = (outcome.prompt.fingerprint == self.prompt.fingerprint
                    if outcome.prompt is not None and self.prompt is not None
                    else outcome.prompt is None and state == "unreadable")
            self._show_screen(outcome, self._note if same else "")

    def _answer_done(self, outcome: Outcome, blocked: bool) -> None:
        """The result of a worker while an answer is on its way: of the answer, or of a read after its key."""
        if not self._followed:
            if outcome.kind == "pressed":
                # Read the list now, and the screen after a moment: the agent goes on, or it asks its next question.
                self._held = outcome.held
                self._start_follow(self._follow)
            elif outcome.kind == "failed" and outcome.reason in UNCONFIRMED:
                # herdr-core did not say that the key or the text went: it may still arrive. Read on, longer.
                self._set("pending", outcome.reason, prompt=self.prompt)
                self._unconfirmed = outcome.reason
                self._start_follow(self._pending_follow)
            elif outcome.kind == "failed":
                self._set("failed", outcome.reason)
            elif not blocked:
                self._set("gone", "not_blocked")
            elif outcome.kind == "key_only":
                self._show_screen(outcome, "text_key_only")  # The key went, the text did not. Say it.
            else:
                self._show_screen(outcome, "changed")  # Nothing went: the screen was different. Say it.
        elif not blocked:
            self._sent()
        elif self._unconfirmed:
            # Only the end of the block is sure. A different screen can be the effect of the key, or of a person in
            # Herdr with the key still on its way: the window shows no buttons, it says "check in Herdr".
            if outcome.kind == "failed" or (outcome.prompt is not None and outcome.prompt.fingerprint == self._answered):
                self._follow_next(self._unconfirmed)
            else:
                self._set("failed", self._unconfirmed)
        elif outcome.prompt is not None and outcome.prompt.fingerprint != self._answered:
            self._show_screen(outcome, "held" if self._held else "")  # the next question
        elif outcome.kind == "screen" and outcome.prompt is None and not self._follow_left:
            self._show_screen(outcome)  # the reads ended with a screen that no reader knows
        else:
            self._follow_next("no_effect" if outcome.kind == "screen" else outcome.reason)

    def _start_follow(self, waits: tuple[float, ...]) -> None:
        self._followed = True
        self._follow_left = waits
        self._wake()
        self._follow_next("no_effect")

    def _follow_next(self, reason: str) -> None:
        """Wait, then read the screen again. With no read left, the answer ends as failed with `reason`."""
        if not self._follow_left:
            self._set("failed", reason)
            return
        seconds, self._follow_left = self._follow_left[0], self._follow_left[1:]
        self._follow_timer.start(int(seconds * 1000))

    @Slot()
    def _follow_read(self) -> None:
        if self.answering and not self.busy:
            self._work(self._job_read)

    def _sent(self) -> None:
        """The agent is not blocked after the answer. With a note (a key that Herdr held or did not confirm) the
        window stays until the person closes it."""
        note = "unconfirmed" if self._unconfirmed else "held" if self._held else ""
        self._set("sent", note)
        if not note:
            self._sent_timer.start()
