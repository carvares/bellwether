"""The answer to one blocked agent: the state machine behind the answer window.

States: closed -> loading -> ready | unreadable | gone | failed; ready -> answering -> sent -> closed, or -> ready (a
new question, or the screen was different and nothing went), unreadable, gone, failed; answering -> pending (Herdr
did not confirm the key or the text: it may still arrive) -> sent | failed.

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
    "text_control": "The text has characters that cannot be sent (control or direction characters).",
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


class PromptSession(QObject):
    """The prompt of one agent at a time. `lookup(key)` gives the agent of the list with that key (None when the list
    does not have it), `blocked(key)` the same agent only while Herdr is online and the agent is blocked, `row(agent)`
    its row for QML (label, icon), `wake()` starts a read of the list now, `stopped()` is True after the program
    stops."""

    changed = Signal()  # the value or the flag `answering` is different
    _done = Signal(int, object)

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
        self._follow_timer = QTimer(self)
        self._follow_timer.setSingleShot(True)
        self._follow_timer.timeout.connect(self._follow_read)
        self._sent_timer = QTimer(self)
        self._sent_timer.setSingleShot(True)
        self._sent_timer.setInterval(int(sent_seconds * 1000))
        self._sent_timer.timeout.connect(self.close)
        self._done.connect(self._result)

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
                         "effect": o.effect, "allowed": prompt.allows(o.key)} for o in prompt.options] if prompt else [],
            "cursor": prompt.cursor if prompt else "",
            "freeText": bool(prompt and prompt.text_key and prompt.allows(prompt.text_key)),
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

    def open(self, key: str) -> None:
        """Open the prompt of the agent row with this key. A key that is not in the list does nothing. While an
        answer is on its way (or may still arrive) it does nothing."""
        agent = self._lookup(key)
        if agent is None or self._stopped() or self.answering:
            return
        self._end_workers()
        self.agent = agent
        if self._blocked(key) is None or not valid_address(key):
            self._set("gone", "not_blocked")
            return
        self._set("loading")
        self._work(self._job_read)

    def close(self) -> None:
        """Close and drop the question and the screen text. A key or a text that herdr-core has taken can still
        arrive: a key is not cancelled, a text is cancelled only when herdr-core has not typed it yet."""
        self._end_workers()
        self._set("closed", keep_agent=False)

    def answer(self, key: str) -> bool:
        """Press the key of one option of the shown prompt. True: the answer started. False: refused (no prompt is
        ready, the prompt has no such option, it is the text option, or the prompt is blind and the option does not
        decline)."""
        prompt = self.prompt
        option = prompt.option(key) if prompt and self.state == "ready" else None
        if option is None or option.kind == prompts.TEXT or not prompt.allows(key):
            return False
        self._start_answer(self._job_answer, prompt, key)
        return True

    def answer_text(self, text: str) -> bool:
        """Answer the shown prompt with a text, when it has a text entry. True: the answer started. False: refused.
        A text that cannot be sent leaves the prompt ready with a note (`reason` text_empty, text_long, text_lines or
        text_control, and its `message`)."""
        prompt = self.prompt
        if prompt is None or self.state != "ready" or not prompt.text_key or not prompt.allows(prompt.text_key):
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
        state, agent = self.state, self.agent
        if agent is None or state not in ("loading", "ready", "unreadable", "answering", "pending"):
            return
        current = self._blocked(agent.key)
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
        self._set("answering", prompt=prompt)
        self._work(job, prompt, value)

    def _work(self, job, *args) -> None:
        """Start one worker. The result of a worker that started before it is ignored."""
        self._serial += 1
        self.busy = True
        self._read_at = self._clock()
        threading.Thread(target=self._run, name="herdr-prompt", daemon=True,
                         args=(self._serial, self._cancel, job, self.agent, *args)).start()

    def _run(self, serial: int, cancel: threading.Event, job, agent: Agent, *args) -> None:
        try:
            outcome = job(cancel, agent, *args)
        except Exception as exc:  # The class name only: the text of an error can hold a screen.
            log.warning("prompt failed terminal=%s error=%s", agent.key, type(exc).__name__)
            outcome = Outcome("failed", reason="error")
        self._done.emit(serial, outcome)

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
        return Outcome("failed", reason=f"press_{failure.code}") if failure else Outcome("pressed", held=held)

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
        failure = self._client.send_text(agent.key, text)
        log.info("answer terminal=%s app=%s text result=%s", agent.key, agent.app, failure.code if failure else "sent")
        return Outcome("failed", reason=f"send_{failure.code}") if failure else Outcome("pressed", held=pressed.held)

    # ----- the results: on the UI thread -----

    def _show_screen(self, outcome: Outcome, note: str = "") -> None:
        """Show what a read found: the question, or the screen that no reader knows. `note`: a reason of NOTES."""
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
        if outcome.kind == "failed" and outcome.reason in GONE_CODES:
            self._set("gone", outcome.reason)
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
