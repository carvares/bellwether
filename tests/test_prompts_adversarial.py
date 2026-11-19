"""Hostile screens of the Task 24 review (made-up content, `tests/fixtures/prompts/adversarial/`): each gives nothing,
or a prompt that tells the truth about what it covers (`cut`, `blind`)."""
from pathlib import Path

import pytest

from bellwether.prompts import DECLINE, parse

FIXTURES = Path(__file__).parent / "fixtures" / "prompts" / "adversarial"

# name -> (program word, expected). None: no prompt. A dict: the values that the prompt must have.
EXPECTED = {
    "a01-old-dialog-above-normal-output": ("claude-code", None),
    "a02-dialog-quoted-in-agent-output": ("claude-code", None),
    "a03-dialog-in-user-input-box": ("claude-code", None),
    "a03b-dialog-in-input-box-no-status-line": ("claude-code", None),
    "a04-duplicated-number": ("claude-code", None),
    "a05-missing-number-3": ("claude-code", None),
    "a06-two-cursors": ("claude-code", None),
    "a07-hint-line-cut": ("claude-code", None),
    # A description line that reads "1. Yes": it stays a description, the keys are those of the real options.
    "a09-description-is-1-yes": ("claude-code", {"kind": "question", "title": "Colour", "blind": False,
                                                 "keys": ["1", "2", "3", "4", "5"]}),
    "a09b-extra-numbered-line": ("claude-code", None),
    "a10a-rule-lookalike-heavy": ("claude-code", None),
    "a10b-dash-lookalike": ("claude-code", None),
    "a10c-cursor-lookalike": ("claude-code", None),
    "a10d-hint-middot-lookalike": ("claude-code", None),
    "a10e-fullwidth-digit": ("claude-code", None),
    "a10f-codex-cursor-lookalike": ("codex", None),
    "a11a-claude-dialog-codex-reader": ("codex", None),
    "a11b-codex-dialog-claude-reader": ("claude-code", None),
    # A cut Bash dialog whose command draws a frame at the first column: the text line right above the rule shows
    # that the rule is not the top of a whole dialog.
    "a12-cut-bash-with-bare-fake-frame": ("claude-code", None),
    # The same frame behind one space (as Claude Code draws a command): a cut dialog, blind.
    "a12b-cut-bash-with-indented-fake-frame": ("claude-code", {"kind": "permission", "title": "", "cut": True,
                                                               "blind": True, "keys": ["1", "2", "3", "4"]}),
    # A tall plan whose text draws a header: a plan line right above the rule.
    "a13-tall-plan-with-fake-header": ("claude-code", None),
    # A cut plan with lines that are not plan lines (not behind three spaces) above it.
    "a13b-cut-plan-takes-any-text-above": ("claude-code", None),
    "a14-codex-old-dialog-composer-below": ("codex", None),
    "a15-codex-missing-blank-before-options": ("codex", None),
    # Only the Fetch dialog has no hint line.
    "a16-bash-no-hint-esc-label": ("claude-code", None),
    # The patch of a Codex edit is not in its dialog: blind.
    "a17-codex-edit-other-diff": ("codex", {"kind": "edit", "blind": True, "keys": ["1", "2", "3"]}),
    # The question text draws a rule and a header: two tops, so nothing (the title must not be replaced).
    "a19-question-text-with-rule-and-header": ("claude-code", None),
    # ----- the screens of the re-review of fix round 1 -----
    # The short hint below the tail of a cut dialog: blind, only "No".
    "r01-short-hint-cut-tail": ("claude-code", {"kind": "permission", "title": "", "cut": True, "blind": True,
                                                "keys": ["1", "2", "3"]}),
    "r02-short-hint-unknown-labels": ("claude-code", None),
    # A question whose answers read "No" and "Yes, and …": answers, not approvals.
    "r03-question-labels-no-yes": ("claude-code", {"kind": "question", "blind": False,
                                                   "effects": ["other", "other", "other", "other", "decline"]}),
    # A cut Bash dialog: a blank command line, then a frame at the first column. No line at the first column above
    # the rule shows that the rule is the top of a whole dialog.
    "r04-cut-bash-blank-then-bare-frame": ("claude-code", None),
    # A cut Codex command that draws the header: no line of Codex at the first column above it, so blind.
    "r05-codex-cut-command-fake-header": ("codex", {"kind": "command", "cut": True, "blind": True,
                                                    "keys": ["1", "2"]}),
    "r06-plan-unknown-option": ("claude-code", None),
    "r07-permission-unknown-option": ("claude-code", None),
    "r08-codex-edit-unknown-option": ("codex", None),
    "r09-codex-edit-with-command-header": ("codex", None),
    "r10-short-hint-cut-with-column0-text": ("claude-code", None),
    # A cut plan: a blank plan line, then a frame behind two spaces. No line at the first column above it.
    "r11-cut-plan-blank-then-fake-frame": ("claude-code", None),
    "r12-cut-no-hint-esc-label": ("claude-code", None),
    "r13-label-nothing": ("claude-code", None),
}


def test_every_adversarial_screen_has_an_expected_result():
    assert {path.stem for path in FIXTURES.glob("*.txt")} == set(EXPECTED)
    assert len(EXPECTED) == 27 + 13


@pytest.mark.parametrize("name", list(EXPECTED))
def test_an_adversarial_screen_gives_nothing_or_a_true_prompt(name):
    app, expected = EXPECTED[name]
    prompt = parse(app, (FIXTURES / f"{name}.txt").read_text())
    if expected is None:
        assert prompt is None
        return
    assert prompt is not None
    for attribute, value in expected.items():
        found = ([option.key for option in prompt.options] if attribute == "keys" else
                 [option.effect for option in prompt.options] if attribute == "effects" else getattr(prompt, attribute))
        assert found == value, attribute
    if prompt.blind:  # a blind prompt has an option that declines, and the window can offer only that one
        assert [option.key for option in prompt.options if prompt.allows(option.key)] == [
            option.key for option in prompt.options if option.effect == DECLINE] != []
