"""The dialogs of Codex (measured with version 0.170.0): the approval of a command and the approval of an edit.

Codex draws no frame, and it draws the lines of a command with the same two spaces as its own lines. So a command
can hold a line that looks like the first line of the dialog. The reader therefore wants that first line exactly one
time on the whole screen: with two, it reads nothing. A command taller than the screen hides the real first line:
the reader wants a line of Codex at the first column above it, or the prompt is cut and blind. The options are the
last block of the screen, after two empty lines that a command cannot be below.
"""
from __future__ import annotations

import re

from . import ACCEPT, DECLINE, Option, Prompt, lines_of, numbered

APP = "codex"
HINT = "  Press enter to confirm or esc to cancel"
# The first line of each dialog -> (kind, title). Codex shows no title: these are the words of Bellwether.
HEADERS = {
    "  Would you like to run the following command?": ("command", "Command approval"),
    "  Would you like to make the following edits?": ("edit", "Edit approval"),
}
_OPTION = re.compile(r"(?P<cursor>›| ) (?P<key>\d+)\. (?P<label>\S.*)$")
_MORE = re.compile(r" {5}\S")
_YES, _NO = re.compile(r"Yes\b"), re.compile(r"No\b")
_OWN = re.compile(r"[•›] \S")  # a line of Codex at the first column: its work ("•") or the message of the person ("›")


def _effect(label: str) -> str:
    """"Yes…" accepts, "No…" declines. "" for any other label: the prompt is then not read."""
    return ACCEPT if _YES.match(label) else DECLINE if _NO.match(label) else ""


def read(text: str) -> Prompt | None:
    lines = lines_of(text)
    if len(lines) < 8 or lines[-1] != HINT or lines[-2] != "":
        return None
    first = len(lines) - 2
    while first > 0 and lines[first - 1]:
        first -= 1
    options: list[Option] = []
    cursors = []
    for line in lines[first:-2]:
        match = _OPTION.match(line)
        if match:
            options.append(Option(match["key"], match["label"]))
            cursors += [match["key"]] if match["cursor"] == "›" else []
        elif options and _MORE.match(line):
            last = options[-1]
            # Codex wraps a label at a space, and inside a word after a hyphen (measured on 80 and 50 columns). Only
            # a hyphen after a letter or a digit is inside a word; after any other character ("--", "`-", a lone
            # "-") the hyphen ends a word, and the space after it stays, as on the screen.
            inside = re.search(r"[^\W_]-$", last.label) is not None
            options[-1] = Option(last.key, last.label + ("" if inside else " ") + line.strip())
        else:
            return None
    if len(options) < 2 or not numbered(options) or len(cursors) != 1:
        return None
    headers = [place for place, line in enumerate(lines) if line in HEADERS]
    if len(headers) != 1 or first < 4 or lines[first - 2:first] != ["", ""]:
        return None
    header = headers[0]
    detail = lines[header + 2:first - 2]
    if (header and lines[header - 1]) or lines[header + 1] != "" or header + 2 >= first - 2:
        return None
    if not detail[0] or not detail[-1] or any(line and not line.startswith("  ") for line in detail):
        return None
    kind, title = HEADERS[lines[header]]
    options = [Option(option.key, option.label, effect=_effect(option.label)) for option in options]
    # A command taller than the screen hides the real header, and its lines (behind two spaces, with empty lines)
    # can draw one. A line of Codex at the first column above the header ("• Running …", "› the message") shows that
    # the header is the real one: a command cannot draw it. With none, the dialog is cut and blind.
    cut = not any(_OWN.match(line) for line in lines[:header])
    # The edit dialog shows only where the edit goes. The patch is in the text above it, which Codex can show in
    # part ("+ Show details") and which the reader cannot tie to the dialog: the prompt is blind.
    return Prompt(APP, kind, title, lines[header].strip(), tuple(options), cursors[0], detail=tuple(detail),
                  cut=cut, blind=cut or kind == "edit")
