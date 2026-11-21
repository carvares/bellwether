"""The workflow of the CI runners (.github/workflows/platforms.yml), read as text: what it may start and spend. A
macOS minute counts 10 times and a Windows minute 2 times (a private repository)."""
import re
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "platforms.yml"
JOBS = {"macos": "macos-latest", "windows": "windows-latest"}
# The actions and their versions as they are pinned (a tag that exists: setup-uv has no tag of the major alone).
ACTIONS = {"actions/checkout@v7", "astral-sh/setup-uv@v10.4.0", "actions/upload-artifact@v7"}


def text():
    return WORKFLOW.read_text(encoding="utf-8")


def job(name):
    """The lines of the job `name` (from its line under `jobs:` to the next job or the end)."""
    lines = text().split("\n")
    start = lines.index(f"  {name}:")
    end = next((i for i in range(start + 1, len(lines)) if re.fullmatch(r"  [a-z]\w*:", lines[i])), len(lines))
    return "\n".join(lines[start:end])


def condition(name):
    """The `if:` of a job, as one line."""
    found = re.search(r"\n    if: >-\n((?:      .*\n)+)", job(name) + "\n")
    assert found, name
    return " ".join(found.group(1).split())


def test_the_workflow_starts_only_by_hand_or_by_a_push_and_never_by_a_schedule_or_a_pull_request():
    head = text().split("\njobs:")[0]
    assert "schedule" not in head and "pull_request" not in head
    assert re.search(r"\non:\n  workflow_dispatch:\n", head) and "\n  push:\n" in head


def test_a_run_by_hand_spends_no_macos_minute_unless_macos_is_chosen():
    inputs = text().split("workflow_dispatch:")[1].split("\n  push:")[0]
    assert re.search(r"options: \[macos, windows, both\]", inputs)
    assert re.search(r"\n        default: windows\b", inputs)


@pytest.mark.parametrize("name", JOBS)
def test_each_job_runs_only_when_it_is_asked_for_and_has_a_time_limit(name):
    assert condition(name) == (
        f"(github.event_name == 'workflow_dispatch' && (inputs.system == '{name}' || inputs.system == 'both')) "
        f"|| (github.event_name == 'push' && (contains(github.event.head_commit.message, '[ci {name}]') "
        f"|| contains(github.event.head_commit.message, '[ci both]')))")
    limit = re.search(r"\n    timeout-minutes: (\d+)\n", job(name))
    assert limit and int(limit.group(1)) <= 8
    assert f"\n    runs-on: {JOBS[name]}\n" in job(name)


def test_the_jobs_are_the_two_systems_and_the_actions_are_pinned():
    assert re.findall(r"\n  ([a-z]\w*):\n", text().split("\njobs:")[1]) == list(JOBS)
    assert set(re.findall(r"uses: (\S+)", text())) == ACTIONS


def test_the_check_of_the_condition_finds_an_inverted_marker(monkeypatch):
    """Mutation M7 of the review: the marker condition inverted must fail the test above."""
    changed = text().replace("(contains(github.event.head_commit.message, '[ci windows]')",
                             "(!contains(github.event.head_commit.message, '[ci windows]')")
    assert changed != text()
    monkeypatch.setattr(Path, "read_text", lambda self, encoding=None: changed)
    with pytest.raises(AssertionError):
        test_each_job_runs_only_when_it_is_asked_for_and_has_a_time_limit("windows")
