"""Real screens of narrow terminals (80 and 50 columns, Task 25; 84, 90 and 95 columns, fix round 1; made-up tasks,
sanitized: the folder layout, the user, the model and the plan are made-up text of the same length): how Claude Code
and Codex wrap their dialogs. Each gives the exact prompt. The rule: a screen never gives a prompt that shows less
than what is approved with an accept allowed."""
import re
from pathlib import Path

import pytest

from bellwether.prompts import parse

FIXTURES = Path(__file__).parent / "fixtures" / "prompts" / "narrow"
WORK = "/home/someuser/Workarea/Examples/madeupproj/.madeupnotes/run/2000-01-01-madeupproj/t00-test/work"
ALWAYS = f"Yes, and always allow access to {WORK} from this project"
ALWAYS_F = ALWAYS.replace("/t00-test/", "/t00f-test/")
TIP = 'Tip: auto mode handles these prompts for you — choose "switch to auto mode" below'
# The purpose of the Bash command of fix round 1: its first word is long, so it has no room after the tip.
PURPOSE = "Unconditionally create an empty made-up file in this folder"
AUTO = "Yes, and switch to auto mode · auto mode handles these prompts for you"
EDITS = "Yes, and switch to accept edits (auto-approve file edits and common file commands) for this session (shift+tab)"
CODEX_NO = "No, and tell Codex what to do differently (esc)"

# name -> (program, title, subtitle, question, the labels, the number of detail lines, a part of the first detail line)
EXPECTED = {
    # The header keeps every line as the screen shows it: the tip (wrapped or not), then the purpose.
    "80-claude-bash": ("claude-code", "Bash command",
                       TIP.replace(" below", "\nbelow") + "\nWrite test words to a file, then uppercase and count lines",
                       "Do you want to proceed?", ["Yes", ALWAYS, AUTO, "No"], 4, " │ echo made-up-alpha"),
    "50-claude-bash": ("claude-code", "Bash command",
                       TIP.replace(" choose", "\nchoose") + "\nCreate two empty placeholder files and print a\ndone message",
                       "Do you want to proceed?", ["Yes", ALWAYS, AUTO, "No"], 4, " │ touch made-up-file-alpha"),
    **{f"{width}-claude-bash": ("claude-code", "Bash command", f"{TIP}\n{PURPOSE}", "Do you want to proceed?",
                                ["Yes", ALWAYS_F, AUTO, "No"], 1, " touch made-up-empty-file.txt") for width in (84, 90, 95)},
    # No tip in an edit dialog (measured at 50, 80, 84, 90 and 95 columns).
    **{f"{width}-claude-edit": ("claude-code", "Edit file", "notes.txt", "Do you want to make this edit to notes.txt?",
                                ["Yes", EDITS, "No"], 4, " 1  made-up line one") for width in (84, 90, 95)},
    "80-claude-edit": ("claude-code", "Edit file", "notes.txt", "Do you want to make this edit to notes.txt?",
                       ["Yes", EDITS, "No"], 5, " 1  made-up line one"),
    "50-claude-edit": ("claude-code", "Edit file", "notes.txt", "Do you want to make this edit to notes.txt?",
                       ["Yes", EDITS, "No"], 6, " 1  made-up line one"),
    "80-claude-ask": ("claude-code", "Colour", "", "Which made-up colour scheme should the made-up widget use?",
                      ["Glimmerfrost Teal with soft Vellumshade borders and a bright Quillberry accent on hover states",
                       "Duskmoth Amber with deep Brindlewood panels and calm Oakmist text for long reading sessions",
                       "Zephyrine Violet with crisp Snowpetal backgrounds and sharp Coppervane highlights for key "
                       "status badges", "Type something.", "Chat about this"], 0, ""),
    "50-claude-ask": ("claude-code", "Colour", "",
                      "Which made-up colour scheme should the made-up widget use for all of its made-up panels and "
                      "made-up badges?",
                      ["Midnight Plumberry with glowing citrine edges and soft fogged lavender panel backgrounds "
                       "shown throughout",
                       "Seaglass Tangerine with pale mintwater panels and bright tangerine badges framed by "
                       "driftwood grey", "Type something.", "Chat about this"], 0, ""),
    "80-codex-command": ("codex", "Command approval", "", "Would you like to run the following command?",
                         ["Yes, proceed (y)",
                          "Yes, and don't ask again for commands that start with `touch made-up-alpha.txt "
                          "made-up-beta.txt made-up-gamma.txt made-up-delta.txt made-up-epsilon.txt made-up-zeta.txt "
                          "made-up-eta.txt made-up-theta.txt` (p)", CODEX_NO], 8, "  Environment: local"),
    "50-codex-command": ("codex", "Command approval", "", "Would you like to run the following command?",
                         ["Yes, proceed (y)",
                          "Yes, and don't ask again for commands that start with `touch "
                          "made-up-file-alpha-made-up-file-beta-made-up-file-gamma-made-up-file-delta-made-up-file-"
                          "epsilon.txt made-up-second.txt` (p)", CODEX_NO], 9, "  Environment: local"),
}
DESCRIPTIONS = {
    "80-claude-ask": "A cool palette built around the invented Glimmerfrost Teal. Borders use pale Vellumshade grey. "
                     "Buttons glow Quillberry red when the pointer moves over them, so actions stand out clearly.",
    "50-claude-ask": "Panels use a deep plumberry base with a faint lavender fog. Badges glow in citrine gold. The "
                     "scheme feels calm at night and keeps every made-up badge easy to spot.",
}


def test_every_narrow_screen_has_an_expected_result():
    assert {path.stem for path in FIXTURES.glob("*.txt")} == set(EXPECTED)


@pytest.mark.parametrize("name", list(EXPECTED))
def test_a_narrow_screen_gives_the_exact_prompt(name):
    app, title, subtitle, question, labels, lines, first = EXPECTED[name]
    prompt = parse(app, (FIXTURES / f"{name}.txt").read_text())
    assert prompt is not None and not prompt.cut and not prompt.blind
    assert (prompt.title, prompt.subtitle, prompt.question) == (title, subtitle, question)
    assert [option.label for option in prompt.options] == labels
    assert len(prompt.detail) == lines and (not lines or prompt.detail[0].startswith(first))
    if name in DESCRIPTIONS:
        assert prompt.options[0].description == DESCRIPTIONS[name]


def test_no_fixture_has_the_real_folder_layout_or_user():
    for path in FIXTURES.parent.rglob("*.txt"):
        text = path.read_text().lower()
        assert not [word for word in ("superpowers", "projects/personal", "bellwether", "carvares") if word in text], path.name


@pytest.mark.parametrize("name", [name for name in EXPECTED if "claude-bash" in name or "claude-edit" in name])
def test_every_line_of_the_header_is_in_the_title_or_the_subtitle_as_the_screen_shows_it(name):
    """Between the top rule and the detail: the title, then each line as it is (a tip too). Nothing is left out."""
    lines = (FIXTURES / f"{name}.txt").read_text().split("\n")
    top = max(place for place, line in enumerate(lines) if line.startswith("─" * 20))
    dashes = next(place for place, line in enumerate(lines) if line.startswith("╌" * 20))
    prompt = parse("claude-code", (FIXTURES / f"{name}.txt").read_text())
    assert [prompt.title, *prompt.subtitle.split("\n")] == [line[1:] for line in lines[top + 1:dashes]]


@pytest.mark.parametrize("name", [name for name in EXPECTED if "codex" in name])
def test_codex_wraps_a_command_behind_its_two_spaces_and_never_at_the_first_column(name):
    """The measurement behind the rule "a line of Codex at the first column cannot be drawn by a command": a command
    that is wider than the terminal, also one word that is wider, goes on behind two spaces."""
    lines = (FIXTURES / f"{name}.txt").read_text().split("\n")
    start = lines.index("  Would you like to run the following command?")
    end = next(place for place, line in enumerate(lines) if line.startswith("› 1. "))
    assert all(line == "" or line.startswith("  ") for line in lines[start:end])
    command = next(place for place in range(start, end) if lines[place].startswith("  $ "))
    assert re.match(r"  \S", lines[command + 1]) and max(len(line) for line in lines) in (50, 80)


def test_the_detail_of_a_narrow_dialog_has_every_line_of_the_wrapped_command():
    prompt = parse("codex", (FIXTURES / "50-codex-command.txt").read_text())
    assert list(prompt.detail)[-4:] == [
        "  $ touch", "  made-up-file-alpha-made-up-file-beta-made-up-f",
        "  ile-gamma-made-up-file-delta-made-up-file-epsi", "  lon.txt made-up-second.txt"]
    prompt = parse("claude-code", (FIXTURES / "50-claude-bash.txt").read_text())
    assert list(prompt.detail) == [
        " │ touch made-up-file-alpha-made-up-file-beta-mad", " │ e-up-file-gamma-made-up-file-delta-made-up-fil",
        " │ e-epsilon.txt made-up-second-argument.txt &&", " │ echo made-up-done"]
