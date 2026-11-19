"""The readers of the dialogs of Claude Code and Codex. The fixtures are real screens with made-up content."""
import logging
import re
from pathlib import Path

import pytest

from bellwether.prompts import ACCEPT, CHOICE, DECLINE, OTHER, TEXT, Option, Prompt, has_reader, parse

FIXTURES = Path(__file__).parent / "fixtures" / "prompts"


def screen(name: str) -> str:
    return (FIXTURES / f"{name}.txt").read_text()


EFFECT = {"A": ACCEPT, "D": DECLINE, "O": OTHER}


def choices(*labels: str, effects: str) -> tuple[Option, ...]:
    """Options of the kind "choice" with the keys 1, 2, …; `effects` has one letter for each: A, D or O."""
    assert len(effects) == len(labels)
    return tuple(Option(str(place + 1), label, effect=EFFECT[letter])
                 for place, (label, letter) in enumerate(zip(labels, effects)))


def answer(key: str, label: str, description: str) -> Option:
    """An answer to a question of the AskUserQuestion tool."""
    return Option(key, label, description, effect=OTHER)


def entry(key: str) -> Option:
    return Option(key, "Type something.", kind=TEXT, effect=OTHER)


def chat(key: str) -> Option:
    return Option(key, "Chat about this", kind=OTHER, effect=DECLINE)


ACCEPT_EDITS = ("Yes, and switch to accept edits (auto-approve file edits and common file commands) for this session "
                "(shift+tab)")
BASH_OPTIONS = choices(
    "Yes", "Yes, and always allow access to /home/dev/projects/sample-app from this project",
    "Yes, and switch to auto mode · auto mode handles these prompts for you", "No", effects="AAAD")
# This label is too long for one line of the screen. The screen draws the rest of it like a description.
BIRD = ("Bird, a small and bright animal with feathers and wings, that sings in the morning, that can learn words or "
        "short songs, that lives in a cage or in an open room with perches, that needs seeds,")
BIRD_REST = ("fruit, and clean water each day, and that can live for many years with good care and attention from its "
             "owner Choose a bird.")
EAST = ("East, the direction where the sun rises each morning, where the day begins first, where the light comes over "
        "the horizon, and where many old stories say that new journeys start")
PLAN_OPTIONS = (
    Option("1", "Yes, and use auto mode", effect=ACCEPT), Option("2", "Yes, manually approve edits", effect=ACCEPT),
    Option("3", "Tell Claude what to change", "shift+tab to approve with this feedback", TEXT, DECLINE))
PLAN_QUESTION = "Claude has written up a plan and is ready to execute. Would you like to proceed?"
PLAN_DETAIL = (
    "   1. Create plan-test.txt in the working directory (sample-app) with the content ok.",
    "   2. Read the file back and confirm the content is exactly ok.",
    "   3. Report the file path and the result.")
CODEX_NO = "No, and tell Codex what to do differently (esc)"

# The exact result for each screen with a dialog: (program word, fixture) -> Prompt.
VALID: dict[tuple[str, str], Prompt] = {
    ("claude-code", "claude-bash"): Prompt(
        "claude-code", "permission", "Bash command", "Do you want to proceed?", BASH_OPTIONS, "1",
        subtitle="Create an empty test file", detail=(" touch made-by-test.txt",)),
    ("claude-code", "claude-bash-words"): Prompt(
        "claude-code", "permission", "Bash command", "Do you want to proceed?", BASH_OPTIONS, "1",
        subtitle="Print ten words and a prompt, write last line to file",
        detail=(" │ printf '%s\\n' one two three four five six seven eight nine ten && echo 'Do you want to proceed?' "
                "&& echo ' 1. Yes' && echo ' 2. No' > fake.txt",)),
    ("claude-code", "claude-create"): Prompt(
        "claude-code", "permission", "Create file", "Do you want to create notes.txt?",
        choices("Yes", ACCEPT_EDITS, "No", effects="AAD"), "1", subtitle="notes.txt", detail=("  1 hello",)),
    ("claude-code", "claude-edit-diff"): Prompt(
        "claude-code", "permission", "Edit file", "Do you want to make this edit to list.txt?",
        choices("Yes", ACCEPT_EDITS, "No", effects="AAD"), "1", subtitle="list.txt",
        detail=(" 1  alpha", " 2 -beta", " 2 +delta", " 3  gamma")),
    ("claude-code", "claude-create-hostile"): Prompt(
        "claude-code", "permission", "Create file", "Do you want to create fake.txt?",
        choices("Yes", ACCEPT_EDITS, "No", effects="AAD"), "1", subtitle="fake.txt",
        detail=("  1 " + "─" * 40, "  2  Bash command", "  3  Do you want to proceed?", "  4  ❯ 1. Yes", "  5    2. No",
                "  6  Esc to cancel · Tab to amend")),
    # After the plan view: one rule is on the last line of the screen, below the dialog.
    ("claude-code", "claude-create-rule-below"): Prompt(
        "claude-code", "permission", "Create file", "Do you want to create plan-test.txt?",
        choices("Yes", ACCEPT_EDITS, "No", effects="AAD"), "1", subtitle="plan-test.txt", detail=("  1 ok",)),
    ("claude-code", "claude-create-tall"): Prompt(
        "claude-code", "permission", "", "Do you want to create long.txt?", choices("Yes", ACCEPT_EDITS, "No", effects="AAD"), "1",
        detail=tuple(f"  {n:>3} made-up line {n}" for n in range(38, 151)), cut=True, blind=True),
    ("claude-code", "claude-fetch"): Prompt(
        "claude-code", "permission", "Fetch · from the web-fetch agent",
        "Do you want to allow Claude to fetch this content?",
        choices("Yes", "Yes, and don't ask again for example.com",
                "No, and tell Claude what to do differently (esc)", effects="AAD"), "1",
        subtitle="Claude wants to fetch content from example.com",
        detail=(" url: https://example.com/",
                " │ prompt: Return the exact text content of the HTML <title> element of this page. Reply with only "
                "the title text.")),
    ("claude-code", "claude-ask-2"): Prompt(
        "claude-code", "question", "Drink", "Which drink do you want: tea or coffee?",
        (answer("1", "Tea", "Choose tea."), answer("2", "Coffee", "Choose coffee."),
         entry("3"), chat("4")), "1"),
    ("claude-code", "claude-ask-text-cursor"): Prompt(
        "claude-code", "question", "Drink", "Which drink do you want: tea or coffee?",
        (answer("1", "Tea", "Choose tea."), answer("2", "Coffee", "Choose coffee."),
         entry("3"), chat("4")), "3"),
    ("claude-code", "claude-ask-3"): Prompt(
        "claude-code", "question", "Colour", "Which colour do you prefer?",
        (answer("1", "Red", "You prefer red."), answer("2", "Green", "You prefer green."),
         answer("3", "Blue", "You prefer blue."), entry("4"),
         chat("5")), "1"),
    ("claude-code", "claude-ask-4"): Prompt(
        "claude-code", "question", "Direction", "Which direction do you choose: North, South, East, or West?",
        (answer("1", "North", "Choose North."), answer("2", "South", "Choose South."),
         answer("3", EAST, "Choose East."), answer("4", "West", "Choose West."),
         entry("5"), chat("6")), "1"),
    ("claude-code", "claude-ask-tabs"): Prompt(
        "claude-code", "question", "Pet · Seasoning", "Which pet do you choose: Cat, Dog, or Bird?",
        (answer("1", "Cat", "Choose a cat."), answer("2", "Dog", "Choose a dog."),
         answer("3", BIRD, BIRD_REST), entry("4"),
         chat("5")), "1"),
    ("claude-code", "claude-ask-review"): Prompt(
        "claude-code", "review", "Review your answers", "Ready to submit your answers?",
        choices("Submit answers", "Cancel", effects="AD"), "1",
        detail=(" ● Which pet do you choose: Cat, Dog, or Bird?", "   → Cat",
                " ● Which seasonings do you want? Choose one or more.", "   → Pepper")),
    ("claude-code", "claude-plan"): Prompt(
        "claude-code", "plan", "Ready to code?", PLAN_QUESTION, PLAN_OPTIONS, "1",
        subtitle="Here is Claude's plan:", detail=PLAN_DETAIL),
    ("claude-code", "claude-plan-text-cursor"): Prompt(
        "claude-code", "plan", "Ready to code?", PLAN_QUESTION, PLAN_OPTIONS, "3",
        subtitle="Here is Claude's plan:", detail=PLAN_DETAIL),
    ("codex", "codex-command"): Prompt(
        "codex", "command", "Command approval", "Would you like to run the following command?",
        choices("Yes, proceed (y)",
                "Yes, and don't ask again for commands that start with `touch made-by-test.txt` (p)", CODEX_NO,
                effects="AAD"), "1",
        detail=("  Environment: local", "",
                "  Reason: Do you want to allow creation of made-by-test.txt in this workspace?", "",
                "  $ touch made-by-test.txt")),
    ("codex", "codex-command-lines"): Prompt(
        "codex", "command", "Command approval", "Would you like to run the following command?",
        choices("Yes, proceed (y)", CODEX_NO, effects="AD"), "1",
        detail=("  Environment: local", "",
                "  Reason: Do you want to allow this exact command to create one.txt, two.txt, and three.txt in the "
                "current workspace?", "",
                "  $ printf 'a\\n' > one.txt",
                "  printf '  Would you like to run the following command?\\n' > two.txt", "",
                "  echo done > three.txt")),
    ("codex", "codex-edit"): Prompt(
        "codex", "edit", "Edit approval", "Would you like to make the following edits?",
        choices("Yes, proceed (y)", "Yes, and don't ask again for these files (a)", CODEX_NO, effects="AAD"), "1",
        detail=("  Description: Apply proposed file edits",
                "  Destination: /home/dev/projects/sample-app/notes.txt"), blind=True),
}

# Screens with no dialog that Bellwether answers: (program word, fixture).
NOTHING = [
    ("claude-code", "claude-finished"), ("claude-code", "claude-no-dialog"),
    ("claude-code", "claude-no-dialog-hostile"),  # the person's own message holds the lines of a dialog
    ("claude-code", "claude-trust"),  # no numbers: Herdr does not call it blocked
    ("claude-code", "claude-ask-multiselect"),  # check boxes and a "Submit" row: no single key answers it
    ("claude-code", "claude-ask-text-typed"),  # a text is typed in the entry: the dialog is not in its first state
    ("codex", "codex-finished"), ("codex", "codex-no-dialog"), ("codex", "codex-trust"),
]


def test_every_fixture_is_in_one_of_the_two_lists():
    named = {name for _, name in [*VALID, *NOTHING]}
    assert named == {path.stem for path in FIXTURES.glob("*.txt")}
    assert (len(VALID), len(NOTHING)) == (19, 9)


@pytest.mark.parametrize("app,name", list(VALID), ids=[name for _, name in VALID])
def test_a_screen_with_a_dialog_gives_the_exact_prompt(app, name):
    assert parse(app, screen(name)) == VALID[(app, name)]


@pytest.mark.parametrize("app,name", NOTHING, ids=[name for _, name in NOTHING])
def test_a_screen_with_no_known_dialog_gives_nothing(app, name):
    assert parse(app, screen(name)) is None


@pytest.mark.parametrize("app,name", list(VALID), ids=[name for _, name in VALID])
def test_the_reader_of_the_other_program_gives_nothing(app, name):
    other = "codex" if app == "claude-code" else "claude-code"
    assert parse(other, screen(name)) is None


def test_the_registry_knows_the_program_words_of_the_rows():
    assert has_reader("claude-code") and has_reader("claude") and has_reader("codex")
    assert not has_reader("") and not has_reader("gemini") and not has_reader("Claude-Code")
    assert parse("claude", screen("claude-bash")) == VALID[("claude-code", "claude-bash")]
    assert parse("gemini", screen("claude-bash")) is None
    assert parse("", screen("claude-bash")) is None


def test_a_screen_that_is_not_complete_is_never_read():
    assert parse("claude-code", screen("claude-bash"), complete=False) is None
    assert parse("codex", screen("codex-command"), complete=False) is None


def test_empty_lines_and_spaces_after_the_dialog_change_nothing():
    for (app, name), prompt in VALID.items():
        assert parse(app, screen(name) + "\n\n   \n") == prompt, name


def test_text_after_the_dialog_gives_nothing():
    """The dialog must be the last thing on the screen: an old one higher in the history is not a question."""
    for app, name in VALID:
        for tail in ("\n\n❯ ", "\n  some later text", "\n" + "─" * 200 + "\n❯ \n" + "─" * 200):
            assert parse(app, screen(name) + tail) is None, name


def test_only_one_rule_with_nothing_below_it_can_be_after_a_dialog():
    text = screen("claude-bash")
    rule = "─" * 200
    assert parse("claude-code", text + "\n\n\n" + rule) == VALID[("claude-code", "claude-bash")]
    assert parse("claude-code", text + "\n\n" + "─" * 170 + " a-session-name ─") == VALID[("claude-code", "claude-bash")]
    for tail in ("\n" + rule, "\n\n" + rule + "\n" + rule, "\n\n" + rule + "\n\n" + rule, "\n\n" + rule + "\n❯",
                 "\n\n" + rule + "\n  text", "\n\n ─" + rule, "\n\n" + rule + " a-name", "\n\n─── a-name ─",
                 "\n\na-name " + rule):
        assert parse("claude-code", text + tail) is None, tail[-8:]
    assert parse("codex", screen("codex-command") + "\n\n" + rule) is None


def test_a_dialog_that_is_only_in_the_history_gives_nothing():
    old = screen("claude-bash")
    assert parse("claude-code", old + "\n\n" + screen("claude-no-dialog")) is None
    assert parse("codex", screen("codex-command") + "\n\n" + screen("codex-no-dialog")) is None


# ----- strictness: no line of the frame can be missing or different -----

OPTION_LINE = re.compile(r"(?P<before>\s*(?:[❯›] )?)(?P<key>\d)\. ")


def frame_lines(app: str, name: str) -> tuple[list[str], list[int]]:
    """The lines of the screen, and the places of the lines of the dialog that are not detail: the rules, the
    title, the question, the options and the hint."""
    lines = screen(name).split("\n")
    prompt = VALID[(app, name)]
    # The dialog starts at the lowest line that the reader needs for the same result.
    start = 0 if prompt.cut else max(
        place for place in range(len(lines)) if parse(app, "\n".join(lines[place:])) == prompt)
    if prompt.cut:
        start = max(place for place, line in enumerate(lines) if line in prompt.detail) + 1
    # A "Tip:" line below the title is an advertisement of the program: it is not in the prompt.
    places = [place for place in range(start, len(lines)) if lines[place].strip() and lines[place] not in prompt.detail
              and not lines[place].startswith(" Tip: ")]
    if name == "claude-create-rule-below":
        places.pop()  # the rule with the session name, below the dialog: the dialog is whole with no such line
    return lines, places


@pytest.mark.parametrize("app,name", list(VALID), ids=[name for _, name in VALID])
def test_a_frame_line_that_is_gone_or_different_never_gives_the_same_prompt(app, name):
    """Take away, or change, each line of the dialog that is not detail. The reader then gives nothing, or a prompt
    with a different fingerprint. It never gives the shown question with different options."""
    lines, places = frame_lines(app, name)
    prompt = VALID[(app, name)]
    assert len(places) >= 2 + len(prompt.options)  # a rule or a first line, the question, and each option
    for place in places:
        line = lines[place]
        # The hint of the plan dialog ends with the name of a file: the reader knows only how it starts.
        longer = [] if line.startswith("   ctrl+g to edit in ") else [[line + " and more"]]
        for changed in ([], ["x" + line[1:]], *longer):
            result = parse(app, "\n".join(lines[:place] + changed + lines[place + 1:]))
            if result is not None:
                assert result.fingerprint != prompt.fingerprint, (name, place)
                assert [option.key for option in result.options] == [str(n + 1) for n in range(len(result.options))]


@pytest.mark.parametrize("app,name", list(VALID), ids=[name for _, name in VALID])
def test_the_question_the_cursor_the_numbers_and_the_hint_are_required(app, name):
    lines, places = frame_lines(app, name)
    prompt = VALID[(app, name)]
    mark = "›" if app == "codex" else "❯"

    def with_line(place: int, *new: str) -> str:
        return "\n".join(lines[:place] + list(new) + lines[place + 1:])

    option_places = [place for place in places if OPTION_LINE.match(lines[place])]
    assert len(option_places) == len(prompt.options)
    cursor = next(place for place in option_places if mark in OPTION_LINE.match(lines[place])["before"])
    # No cursor, and two cursors.
    assert parse(app, with_line(cursor, lines[cursor].replace(mark, " ", 1))) is None
    other = next(place for place in option_places if place != cursor)
    digit = OPTION_LINE.match(lines[other]).start("key")
    assert parse(app, with_line(other, lines[other][:digit - 2] + mark + " " + lines[other][digit:])) is None
    # A number that is not the next number, for each option.
    for place in option_places:
        key = OPTION_LINE.match(lines[place])["key"]
        assert parse(app, with_line(place, lines[place].replace(f"{key}.", "8.", 1))) is None, (name, key)
    # An option that is gone and is not the last one.
    for place in option_places[:-1]:
        assert parse(app, with_line(place)) is None
    # No question.
    question = next(place for place in places if lines[place].strip() == prompt.question)
    assert parse(app, with_line(question)) is None
    # No hint line, for the dialogs that have one.
    last = places[-1]
    if last not in option_places:
        assert parse(app, with_line(last)) is None
        assert parse(app, with_line(last, lines[last].replace("to", "TO"))) is None


# ----- the fingerprint -----

def test_the_fingerprint_does_not_change_with_the_cursor():
    first = parse("claude-code", screen("claude-ask-2"))
    moved = parse("claude-code", screen("claude-ask-text-cursor"))
    assert (first.cursor, moved.cursor) == ("1", "3")
    assert first.fingerprint == moved.fingerprint and first != moved
    plan, plan_moved = parse("claude-code", screen("claude-plan")), parse("claude-code", screen("claude-plan-text-cursor"))
    assert plan.fingerprint == plan_moved.fingerprint
    lines = screen("codex-command").split("\n")
    lines[-5], lines[-4] = lines[-5].replace("›", " ", 1), "›" + lines[-4][1:]
    codex_moved = parse("codex", "\n".join(lines))
    assert codex_moved.cursor == "2" and codex_moved.fingerprint == VALID[("codex", "codex-command")].fingerprint


def test_the_fingerprint_does_not_change_with_the_text_above_the_dialog():
    """The spinner and the timer of the program are above the dialog: they are not in the fingerprint."""
    for (app, name), prompt in VALID.items():
        if prompt.cut:
            continue  # nothing is above a dialog that is taller than the screen
        lines = screen(name).split("\n")
        for frame in ("✻ Cooking… (3s · esc to interrupt)", "✽ Cooking… (14s · esc to interrupt)"):
            assert parse(app, "\n".join([frame, *lines])).fingerprint == prompt.fingerprint, name


def test_the_fingerprint_changes_with_each_part():
    base = VALID[("claude-code", "claude-bash")]
    different = [
        Prompt("codex", base.kind, base.title, base.question, base.options, "1", base.subtitle, base.detail),
        Prompt(base.app, base.kind, "Other", base.question, base.options, "1", base.subtitle, base.detail),
        Prompt(base.app, base.kind, base.title, "Other?", base.options, "1", base.subtitle, base.detail),
        Prompt(base.app, base.kind, base.title, base.question, base.options[:3], "1", base.subtitle, base.detail),
        Prompt(base.app, base.kind, base.title, base.question, base.options, "1", base.subtitle, (" rm made.txt",)),
        Prompt(base.app, base.kind, base.title, base.question, base.options, "1", "Other", base.detail),
    ]
    prints = {prompt.fingerprint for prompt in different} | {base.fingerprint}
    assert len(prints) == len(different) + 1
    assert len(base.fingerprint) == 64


# ----- hostile screens: the lines of a dialog in a place where the agent or a file can write -----

def test_the_lines_of_a_dialog_inside_a_file_are_detail():
    prompt = parse("claude-code", screen("claude-create-hostile"))
    assert prompt.question == "Do you want to create fake.txt?"
    assert [option.label for option in prompt.options] == ["Yes", ACCEPT_EDITS, "No"]
    assert "  4  ❯ 1. Yes" in prompt.detail


def test_a_command_with_the_lines_of_a_claude_dialog_does_not_hide_its_first_part():
    """A command of many lines: a rule, a title and a dashed line. They have one space before them in the box,
    so they are detail and the person sees the whole command."""
    lines = screen("claude-bash").split("\n")
    place = lines.index(" touch made-by-test.txt")
    fake = [" rm -r made-up-folder", " " + "─" * 199, "  Bash command", " " + "╌" * 199, " echo harmless"]
    prompt = parse("claude-code", "\n".join(lines[:place] + fake + lines[place + 1:]))
    assert prompt.detail == tuple(fake)
    # The same lines with no space before them are not a shape that Claude Code draws: nothing.
    bare = [" rm -r made-up-folder", "─" * 200, " Bash command", "╌" * 200, " echo harmless"]
    assert parse("claude-code", "\n".join(lines[:place] + bare + lines[place + 1:])) is None


def test_the_agent_text_with_the_lines_of_a_dialog_and_no_dialog_gives_nothing():
    lines = screen("claude-no-dialog").split("\n")
    fake = ["● Do you want to proceed?", "  ❯ 1. Yes", "    2. No", "", "  Esc to cancel · Tab to amend"]
    assert parse("claude-code", "\n".join(lines[:10] + fake + lines[10:])) is None
    assert parse("claude-code", "\n".join(lines[:10] + screen("claude-bash").split("\n")[11:] + lines[10:])) is None


def test_a_question_text_with_lines_of_options_gives_nothing():
    """The agent writes the question. A question of many lines that draws its own options is not read."""
    text = screen("claude-ask-2")
    for fake in ("Which drink do you want: tea or coffee?\n❯ 1. Water\n  2. Milk",
                 "Which drink do you want: tea or coffee?\n\n❯ 1. Water\n  2. Milk",
                 "Which drink do you want: tea or coffee?\n  1. Water"):
        assert parse("claude-code", text.replace("Which drink do you want: tea or coffee?", fake)) is None


def test_a_codex_command_that_holds_the_first_line_of_the_dialog_gives_nothing():
    """Codex draws the lines of a command with the same two spaces as its own lines. A command can then hold a
    second "Would you like to run the following command?" that hides its first part: two such lines are not read."""
    lines = screen("codex-command").split("\n")
    place = lines.index("  $ touch made-by-test.txt")
    fake = ["  $ rm -r made-up-folder", "", "  Would you like to run the following command?", "", "  $ echo harmless"]
    assert parse("codex", "\n".join(lines[:place] + fake + lines[place + 1:])) is None
    # In the text of the agent above the dialog too.
    above = ["• A note", "  Would you like to make the following edits?", ""]
    assert parse("codex", "\n".join(lines[:8] + above + lines[8:])) is None


def test_a_codex_command_with_lines_of_options_keeps_the_real_options():
    lines = screen("codex-command").split("\n")
    place = lines.index("  $ touch made-by-test.txt")
    fake = ["  $ echo one", "  1. Fake", "  2. Fake too"]
    prompt = parse("codex", "\n".join(lines[:place] + fake + lines[place + 1:]))
    assert prompt.detail[-3:] == tuple(fake)
    assert prompt.options == VALID[("codex", "codex-command")].options


def test_an_option_label_that_is_cut_or_empty_gives_nothing():
    text = screen("claude-bash")
    assert parse("claude-code", text.replace("   4. No", "   4.")) is None
    assert parse("claude-code", text.replace("   4. No", "   4. ")) is None
    assert parse("codex", screen("codex-command").replace("  3. No, and tell Codex what to do differently (esc)",
                                                           "  3.")) is None


def test_a_long_label_on_two_lines_is_one_label():
    """A narrow window: the label of an option goes on in the next line, below the start of the label."""
    text = screen("claude-bash").replace(
        "   2. Yes, and always allow access to /home/dev/projects/sample-app from this project",
        "   2. Yes, and always allow access to\n      /home/dev/projects/sample-app from this project")
    assert parse("claude-code", text) == VALID[("claude-code", "claude-bash")]
    codex = screen("codex-command").replace(
        "that start with `touch made-by-test.txt` (p)", "that start with\n     `touch made-by-test.txt` (p)")
    assert parse("codex", codex) == VALID[("codex", "codex-command")]


def test_more_than_nine_options_give_nothing():
    lines = screen("claude-ask-2").split("\n")
    place = lines.index("  3. Type something.")
    more = [f"  {n}. Choice {n}" for n in range(3, 10)] + ["  10. Type something."]
    text = "\n".join(lines[:place] + more + lines[place + 1:]).replace("  4. Chat about this", "  11. Chat about this")
    assert parse("claude-code", text) is None


def test_a_reader_that_fails_gives_nothing_and_logs_no_text(monkeypatch, caplog):
    from bellwether import prompts

    def broken(text):
        raise ValueError("MARKER " + text)

    monkeypatch.setitem(prompts.READERS, "claude-code", broken)
    with caplog.at_level(logging.DEBUG, logger="bellwether"):
        assert parse("claude-code", screen("claude-bash")) is None
    assert [record.getMessage() for record in caplog.records] == ["prompt reader failed app=claude-code error=ValueError"]


def test_the_kinds_of_the_options():
    ask = VALID[("claude-code", "claude-ask-3")]
    assert [option.kind for option in ask.options] == [CHOICE, CHOICE, CHOICE, TEXT, OTHER]
    assert ask.text_key == "4" and ask.option("5").label == "Chat about this" and ask.option("9") is None
    assert VALID[("claude-code", "claude-plan")].text_key == "3"
    assert VALID[("claude-code", "claude-bash")].text_key == "" and VALID[("codex", "codex-edit")].text_key == ""


# ----- what the fingerprint covers: the effect of each option, and the blind prompts -----

def test_each_option_has_its_effect():
    assert [o.effect for o in VALID[("claude-code", "claude-bash")].options] == [ACCEPT, ACCEPT, ACCEPT, DECLINE]
    assert [o.effect for o in VALID[("claude-code", "claude-ask-3")].options] == [OTHER, OTHER, OTHER, OTHER, DECLINE]
    assert [o.effect for o in VALID[("claude-code", "claude-ask-review")].options] == [ACCEPT, DECLINE]
    assert [o.effect for o in VALID[("claude-code", "claude-plan")].options] == [ACCEPT, ACCEPT, DECLINE]
    assert [o.effect for o in VALID[("codex", "codex-command")].options] == [ACCEPT, ACCEPT, DECLINE]


def test_an_option_whose_effect_is_not_known_gives_nothing():
    """The reader must know what each option does: a label that does not start with Yes or No is not read."""
    assert parse("claude-code", screen("claude-bash").replace("   4. No", "   4. Maybe later")) is None
    assert parse("claude-code", screen("claude-plan").replace("     2. Yes, manually", "     2. Perhaps, manually")) is None
    assert parse("codex", screen("codex-command").replace("  3. No, and tell", "  3. Later, and tell")) is None
    # A word that starts with "No" is not the word "No".
    assert parse("claude-code", screen("claude-bash").replace("   4. No", "   4. Nope")) is None


def test_a_cut_dialog_and_a_codex_edit_are_blind_and_allow_only_the_options_that_decline():
    for app, name in (("claude-code", "claude-create-tall"), ("codex", "codex-edit")):
        prompt = parse(app, screen(name))
        assert prompt.blind
        assert [option.key for option in prompt.options if prompt.allows(option.key)] == ["3"], name
    for (app, name), prompt in VALID.items():
        if not prompt.blind:
            assert all(prompt.allows(option.key) for option in prompt.options), name
            assert not prompt.cut and not (app == "codex" and prompt.kind == "edit")
    assert not VALID[("claude-code", "claude-bash")].allows("9")


def test_the_fingerprint_changes_with_the_blind_flag_and_the_effects():
    base = VALID[("claude-code", "claude-bash")]
    blind = Prompt(base.app, base.kind, base.title, base.question, base.options, "1", base.subtitle, base.detail,
                   blind=True)
    swapped = Prompt(base.app, base.kind, base.title, base.question,
                     base.options[:3] + (Option("4", "No", effect=ACCEPT),), "1", base.subtitle, base.detail)
    assert len({base.fingerprint, blind.fingerprint, swapped.fingerprint}) == 3


def test_a_whole_dialog_needs_an_empty_line_above_its_rule():
    """A text line right above the rule: the rule can be a line of a cut dialog, so nothing is read."""
    lines = screen("claude-bash").split("\n")
    rule = lines.index("─" * 200)
    assert lines[rule - 1] == ""
    assert parse("claude-code", "\n".join(lines[:rule - 1] + [" rm -rf made-up-dir"] + lines[rule:])) is None
    assert parse("claude-code", "\n".join(lines[rule:])) is None  # the rule on the first line of the screen
    plan = screen("claude-plan").split("\n")
    top = next(place for place, line in enumerate(plan) if line.startswith("  ─"))
    assert parse("claude-code", "\n".join(plan[:top - 1] + ["   0. a plan line"] + plan[top:])) is None


def test_the_text_form_of_a_prompt_has_no_screen_text():
    for prompt in VALID.values():
        text = repr(prompt) + str(prompt) + repr(prompt.options) + str(list(prompt.options))
        words = [prompt.title, prompt.subtitle, prompt.question, *prompt.detail,
                 *(part for option in prompt.options for part in (option.label, option.description))]
        assert not [word for word in words if word.strip() and word.strip() in text], prompt.kind
        assert prompt.fingerprint[:8] in text
