"""The dialogs of Claude Code (measured with version 2.1.322): a permission dialog (Bash, Edit, Create, Fetch), a
question of the AskUserQuestion tool (one question, or one tab of many), the review tab, and the plan approval.

Where the agent can write: the text above the dialog, the detail (always behind one space or a line number), the
question and the labels. A rule of the frame starts at the first column, so the detail cannot draw one. The
check-box question (many answers) has a "Submit" row with no number: it is not read.
"""
from __future__ import annotations

import re

from . import CHOICE, OTHER, TEXT, Option, Prompt, lines_of, numbered

APP = "claude-code"
RULE, DASH = "─", "╌"
PERMISSION_HINT = " Esc to cancel · Tab to amend"
TEXT_LABEL = "Type something."
CHAT_LABEL = "Chat about this"
PLAN_TEXT_LABEL = "Tell Claude what to change"
_NUMBER = r"(?P<cursor>❯| ) (?P<key>\d+)\. (?P<label>\S.*)$"
_PERMISSION_OPTION, _PERMISSION_MORE = re.compile(" " + _NUMBER), re.compile(r" {6}\S")
_QUESTION_OPTION, _QUESTION_MORE = re.compile(_NUMBER), re.compile(r" {5}\S")
_PLAN_OPTION, _PLAN_MORE = re.compile("   " + _NUMBER), re.compile(r" {8}\S")
_ONE_HEADER = re.compile(r" ☐ (?P<title>\S.*)$")
_TABS_HEADER = re.compile(r"←  (?P<tabs>\S.*\S)  ✔ Submit  →$")
_TAB = re.compile(r"[☐☒] (?P<name>\S.*)$")
_CHECK_BOX = re.compile(r"\[.\] ")


def _line(line: str, char: str, indent: int = 0) -> bool:
    """True for a line of the frame: `indent` spaces, then only `char`."""
    body = line[indent:]
    return line[:indent] == " " * indent and len(body) >= 20 and set(body) == {char}


def _rows(lines: list[str], start: re.Pattern, more: re.Pattern) -> list[dict] | None:
    """The option lines: {key, label, extra lines, cursor}. None when a line is not a line of an option, when the
    numbers are not 1, 2, … in sequence, or when the cursor is not on exactly one option."""
    rows: list[dict] = []
    for line in lines:
        match = start.match(line)
        if match:
            rows.append({"key": match["key"], "label": match["label"], "first": line, "extra": [],
                         "cursor": match["cursor"] == "❯"})
        elif rows and more.match(line):
            rows[-1]["extra"].append(line)
        else:
            return None
    if [row["key"] for row in rows] != [str(n + 1) for n in range(len(rows))]:
        return None
    return rows


def _cursor(rows: list[dict]) -> str | None:
    marked = [row["key"] for row in rows if row["cursor"]]
    return marked[0] if len(marked) == 1 else None


def _joined(row: dict) -> str:
    return " ".join([row["label"], *(line.strip() for line in row["extra"])])


def _stripped(lines: list[str]) -> list[str]:
    """The lines with no empty lines before the first text and after the last text."""
    first = next((place for place, line in enumerate(lines) if line), len(lines))
    last = next((place for place in range(len(lines), 0, -1) if lines[place - 1]), 0)
    return lines[first:last]


def _above(lines: list[str], place: int, char: str, indent: int = 0) -> int:
    """The place of the nearest frame line of `char` above `place`. -1 when there is none."""
    return next((at for at in range(place - 1, -1, -1) if _line(lines[at], char, indent)), -1)


def read(text: str) -> Prompt | None:
    lines = lines_of(text)
    if len(lines) < 4:
        return None
    for reader in (_permission, _question, _review, _plan):
        prompt = reader(lines)
        if prompt is not None and numbered(list(prompt.options)):
            return prompt
    return None


def _permission(lines: list[str]) -> Prompt | None:
    end = len(lines)
    hint = lines[-1] == PERMISSION_HINT
    if hint:
        if lines[-2] != "":
            return None
        end -= 2
    bottom = _above(lines, end, DASH)
    block = lines[bottom + 1:end]
    first = next((place for place, line in enumerate(block) if _PERMISSION_OPTION.match(line)), 0)
    question = block[:first]
    rows = _rows(block[first:], _PERMISSION_OPTION, _PERMISSION_MORE)
    if bottom < 0 or not question or not rows or len(rows) < 2 or _cursor(rows) is None:
        return None
    if not all(re.match(r" \S", line) for line in question) or not question[-1].endswith("?"):
        return None
    options = tuple(Option(row["key"], _joined(row)) for row in rows)
    # A dialog with no hint line has the Escape key in the label of its last option.
    if not hint and not options[-1].label.endswith("(esc)"):
        return None
    dashes = sum(_line(line, DASH) for line in lines)
    top = _above(lines, bottom, DASH)
    detail = lines[top + 1:bottom]
    if any(line and not line.startswith(" ") for line in detail) or not _stripped(detail):
        return None
    title, subtitle, cut = "", "", True
    header = []
    if top >= 0:
        place = top - 1
        while place >= 0 and re.match(r" \S", lines[place]):
            header.insert(0, lines[place].strip())
            place -= 1
        if place >= 0:
            # The whole dialog is on the screen: a rule, the title lines, and the two dashed lines of the detail.
            if not _line(lines[place], RULE) or not 1 <= len(header) <= 6:
                return None
            title, cut = header[0], False
            subtitle = " · ".join(line for line in header[1:] if not line.startswith("Tip: "))
    # A dashed line that is not of this frame: the screen is not what this reader knows.
    if dashes != (1 if top < 0 else 2):
        return None
    return Prompt(APP, "permission", title, " ".join(line.strip() for line in question), options, _cursor(rows),
                  subtitle=subtitle, detail=tuple(_stripped(detail)), cut=cut)


def _question(lines: list[str]) -> Prompt | None:
    hint = lines[-1]
    if not (hint.startswith("Enter to select · ") and hint.endswith(" · Esc to cancel")) or lines[-2] != "":
        return None
    inner = len(lines) - 4
    top = _above(lines, inner, RULE)
    if inner < 0 or not _line(lines[inner], RULE) or top < 0 or inner - top < 6:
        return None
    one, tabs = _ONE_HEADER.match(lines[top + 1]), _TABS_HEADER.match(lines[top + 1])
    if one:
        title = one["title"]
    elif tabs:
        names = [_TAB.match(tab) for tab in tabs["tabs"].split("  ")]
        if not all(names):
            return None
        title = " · ".join(name["name"] for name in names)
    else:
        return None
    body = lines[top + 2:inner]
    if body[0] != "":
        return None
    gap = body.index("", 1) if "" in body[1:] else 0
    question, block = body[1:gap], body[gap + 1:]
    if not question or any(not re.match(r"\S", line) or _QUESTION_OPTION.match(line) for line in question):
        return None
    rows = _rows([*block, lines[-3]], _QUESTION_OPTION, _QUESTION_MORE)
    if not rows or len(rows) < 3 or _cursor(rows) is None:
        return None
    chat, entry = rows[-1], rows[-2]
    if chat["label"] != CHAT_LABEL or chat["extra"] or not _QUESTION_OPTION.match(lines[-3]):
        return None
    # The option before the rule is the text entry. With a text typed in it, its label is that text: not read.
    if entry["label"] != TEXT_LABEL or entry["extra"] or ("ctrl+g to edit" in hint and not entry["cursor"]):
        return None
    options = []
    for row in rows[:-2]:
        if _CHECK_BOX.match(row["label"]):
            return None  # check boxes: a digit does not answer, it changes one box
        # The lines below a label are its description. A label that is too long for one line goes on in such a
        # line too: the screen does not tell the two apart, so the rest of that label is in the description.
        options.append(Option(row["key"], row["label"], " ".join(line.strip() for line in row["extra"])))
    options += [Option(entry["key"], TEXT_LABEL, kind=TEXT), Option(chat["key"], CHAT_LABEL, kind=OTHER)]
    return Prompt(APP, "question", title, " ".join(question), tuple(options), _cursor(rows))


def _review(lines: list[str]) -> Prompt | None:
    if len(lines) < 10 or lines[-5:-2] != ["", "Ready to submit your answers?", ""]:
        return None
    rows = _rows(lines[-2:], _QUESTION_OPTION, _QUESTION_MORE)
    top = _above(lines, len(lines) - 5, RULE)
    if not rows or [row["label"] for row in rows] != ["Submit answers", "Cancel"] or _cursor(rows) is None or top < 0:
        return None
    if not _TABS_HEADER.match(lines[top + 1]) or lines[top + 2:top + 5] != ["", "Review your answers", ""]:
        return None
    detail = lines[top + 5:-5]
    if not detail or any(not line.startswith(" ") for line in detail):
        return None
    options = tuple(Option(row["key"], row["label"]) for row in rows)
    return Prompt(APP, "review", "Review your answers", "Ready to submit your answers?", options, _cursor(rows),
                  detail=tuple(detail))


def _plan(lines: list[str]) -> Prompt | None:
    if not lines[-1].startswith("   ctrl+g to edit in ") or lines[-2] != "":
        return None
    low = _above(lines, len(lines) - 2, RULE, 2)
    if low < 0 or len(lines) - low < 7 or lines[low + 2] != "":
        return None
    question = lines[low + 1]
    if not re.match(r"   \S", question) or not question.endswith("Would you like to proceed?"):
        return None
    rows = _rows(lines[low + 3:-2], _PLAN_OPTION, _PLAN_MORE)
    if not rows or len(rows) < 2 or _cursor(rows) is None or rows[-1]["label"] != PLAN_TEXT_LABEL:
        return None
    options = [Option(row["key"], row["label"], " ".join(line.strip() for line in row["extra"])) for row in rows]
    last = options[-1]
    options[-1] = Option(last.key, last.label, last.description, TEXT)
    above = lines[:low]
    while above and not above[-1]:
        above.pop()
    dashes = [place for place, line in enumerate(above) if _line(line, DASH, 2)]
    top = _above(above, len(above), RULE, 2)
    title, subtitle, cut = "", "", True
    if top >= 0:
        # The whole dialog is on the screen: the rule, the two title lines, and the plan between two dashed lines.
        if above[top + 1:top + 4] != ["   Ready to code?", "", "   Here is Claude's plan:"]:
            return None
        if dashes != [top + 4, len(above) - 1]:
            return None
        title, subtitle, cut = "Ready to code?", "Here is Claude's plan:", False
        detail = above[top + 5:-1]
    else:
        # The plan is taller than the screen: what is on the screen above the question is the plan.
        if len(dashes) > 1 or (dashes and dashes != [len(above) - 1]):
            return None
        detail = above[:-1] if dashes else above
    if not _stripped(detail):
        return None
    return Prompt(APP, "plan", title, question.strip(), tuple(options), _cursor(rows), subtitle=subtitle,
                  detail=tuple(_stripped(detail)), cut=cut)
