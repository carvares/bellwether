"""Readers of the question that a blocked agent shows on its screen: one module for each agent program.

`parse(app, text)` gives a `Prompt` only when the reader of the program knows the WHOLE dialog: its frame, the
question, every option numbered in sequence from 1, exactly one cursor, the hint line, and nothing after it on the
screen. Anything else is None: "no option buttons". The screen text is private: no reader logs it, saves it, or puts
it in an error.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field

log = logging.getLogger("bellwether")

# The kinds of an option. "choice": its key answers the dialog. "text": its key moves the cursor to a text entry,
# and the text that follows answers the dialog. "other": its key ends the dialog with no answer.
CHOICE, TEXT, OTHER = "choice", "text", "other"


@dataclass(frozen=True)
class Option:
    key: str  # The key name for `herdr-core keys`: one digit, "1" to "9".
    label: str
    description: str = ""
    kind: str = CHOICE


@dataclass(frozen=True)
class Prompt:
    app: str  # The program word of the reader: "claude-code" or "codex".
    kind: str  # "permission", "question", "review" or "plan" (Claude Code); "command" or "edit" (Codex).
    title: str
    question: str
    options: tuple[Option, ...]
    cursor: str  # The key of the option that the cursor is on. Not in the fingerprint.
    subtitle: str = ""  # What the dialog says below its title: a file name, the purpose of a command.
    detail: tuple[str, ...] = ()  # The command, the diff or the plan, line for line as the screen shows it.
    cut: bool = False  # The dialog is taller than the screen: the detail has only its visible part.
    fingerprint: str = field(init=False, compare=False, repr=False, default="")

    def __post_init__(self) -> None:
        parts = [self.app, self.kind, self.title, self.subtitle, self.question, list(self.detail), self.cut,
                 [[option.key, option.label, option.description, option.kind] for option in self.options]]
        digest = hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()
        object.__setattr__(self, "fingerprint", digest)

    @property
    def text_key(self) -> str:
        """The key of the option that takes free text. "" when the dialog has none."""
        return next((option.key for option in self.options if option.kind == TEXT), "")

    def option(self, key: str) -> Option | None:
        return next((option for option in self.options if option.key == key), None)


def numbered(options: list[Option]) -> bool:
    """True when the options have the keys "1", "2", … in sequence, and at most nine of them."""
    return 0 < len(options) <= 9 and [option.key for option in options] == [str(n + 1) for n in range(len(options))]


def lines_of(text: str) -> list[str]:
    """The lines of a screen with no spaces at their ends and no empty lines after the last text."""
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return lines


from . import claude, codex  # noqa: E402  (the readers use the types above)

# The reader of each program word that the agent rows carry. `herdr-core run` names Claude Code "claude".
READERS = {"claude-code": claude.read, "claude": claude.read, "codex": codex.read}


def has_reader(app: str) -> bool:
    return app in READERS


def parse(app: str, text: str, complete: bool = True) -> Prompt | None:
    """The question on the screen `text` of the program `app`, or None. A screen that Herdr did not read in whole
    (`complete` False) is never read."""
    reader = READERS.get(app)
    if reader is None or not complete or not isinstance(text, str):
        return None
    try:
        return reader(text)
    except Exception as exc:  # A reader with an error knows nothing. The class only: a message can hold the text.
        log.warning("prompt reader failed app=%s error=%s", app, type(exc).__name__)
        return None
