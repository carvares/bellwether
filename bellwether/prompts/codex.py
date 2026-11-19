"""The dialogs of Codex (measured with version 0.170.0): the approval of a command and the approval of an edit.

Codex draws no frame, and it draws the lines of a command with the same two spaces as its own lines. So a command
can hold a line that looks like the first line of the dialog. The reader therefore wants that first line exactly one
time on the whole screen: with two, it reads nothing. The options are the last block of the screen, after two empty
lines that a command cannot be below.
"""
from __future__ import annotations

import re

from . import Option, Prompt, lines_of, numbered

APP = "codex"
HINT = "  Press enter to confirm or esc to cancel"
# The first line of each dialog -> (kind, title). Codex shows no title: these are the words of Bellwether.
HEADERS = {
    "  Would you like to run the following command?": ("command", "Command approval"),
    "  Would you like to make the following edits?": ("edit", "Edit approval"),
}
_OPTION = re.compile(r"(?P<cursor>›| ) (?P<key>\d+)\. (?P<label>\S.*)$")
_MORE = re.compile(r" {5}\S")


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
            options[-1] = Option(last.key, f"{last.label} {line.strip()}")
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
    return Prompt(APP, kind, title, lines[header].strip(), tuple(options), cursors[0], detail=tuple(detail))
