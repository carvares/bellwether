"""The model and the start of a session: the text of the line, the readers of the session files, and the engine.
Every file is made up and is in a scratch home; /proc is a scratch folder too. No test reads a real session."""
import json
import logging
import os
import shutil
import threading
from types import SimpleNamespace

from datetime import datetime, timezone

import pytest

from bellwether import sessions
from bellwether.client import Failure, Terminal
from bellwether.platform import linux
from bellwether.platform.linux import Host
from bellwether.sessions import (
    BLOCK, SCAN_LIMIT, SessionFacts, SessionWatch, age_text, age_words, read_claude, read_codex, short_model)
from bellwether.state import Agent

MARKER = "MARKER-private-session-text"
SESSION = "0a1b2c3d-1111-2222-3333-444455556666"
OTHER_SESSION = "0a1b2c3d-9999-8888-7777-444455556666"
STARTED = 1_795_000_000_000


# ----- the text of the line -----

@pytest.mark.parametrize("raw, short", [
    ("claude-opus-5-5", "Opus 5.5"),
    ("claude-fable-5-2", "Fable 5.2"),
    ("claude-sonnet-5-5-20261001", "Sonnet 5.5"),
    ("claude-haiku-5", "Haiku 5"),
    ("claude-opus-4-20250514", "Opus 4"),
    ("claude-opus-4-1-20250805", "Opus 4.1"),
    ("claude-3-5-sonnet-20241022", "Sonnet 3.5"),
    ("claude-3-opus-latest", "Opus 3"),
    ("claude-opus-5-5[1m]", "Opus 5.5 1M"),
    ("claude-sonnet-5-5-20261001[1M]", "Sonnet 5.5 1M"),
    ("us.anthropic.claude-opus-4-1-20250805-v1:0", "Opus 4.1"),
    ("anthropic/claude-fable-5-2", "Fable 5.2"),
    ("claude-opus-4@20250514", "Opus 4"),
    ("CLAUDE-OPUS-5-5", "Opus 5.5"),
    ("gpt-5.2-codex", "GPT-5.2-codex"),
    ("gpt-5.6-terra", "GPT-5.6-terra"),
    ("o4-mini", "o4-mini"),
    ("made-up-model-9", "made-up-model-9"),
    ("claude-made-up", "claude-made-up"),
    ("  claude-opus-5-5  ", "Opus 5.5"),
    ("x" * 60, "x" * 31 + "…"),
    ("[1m]", "[1m] 1M"),
    ("", ""), ("   ", ""), (None, ""), (5, ""),
])
def test_the_short_form_of_a_model_id(raw, short):
    assert short_model(raw) == short


def test_a_model_id_is_never_empty_and_never_long():
    for raw in ("claude-", "claude-opus", "gpt-", "-", "a/b/", "anthropic.", "claude-opus-5-5-latest"):
        assert 0 < len(short_model(raw)) <= sessions.SHORT_LIMIT + 3, raw


MINUTE, HOUR, DAY = 60, 3600, 86400


@pytest.mark.parametrize("seconds, text, words", [
    (-5, "<1m", "less than 1 minute"),
    (0, "<1m", "less than 1 minute"),
    (59.9, "<1m", "less than 1 minute"),
    (MINUTE, "1m", "1 minute"),
    (14 * MINUTE + 59, "14m", "14 minutes"),
    (HOUR - 1, "59m", "59 minutes"),
    (HOUR, "1h", "1 hour"),
    (HOUR + MINUTE, "1h 1m", "1 hour 1 minute"),
    (2 * HOUR + 14 * MINUTE, "2h 14m", "2 hours 14 minutes"),
    (DAY - 1, "23h 59m", "23 hours 59 minutes"),
    (DAY, "1d", "1 day"),
    (DAY + 59 * MINUTE, "1d", "1 day"),
    (3 * DAY + 2 * HOUR + 30 * MINUTE, "3d 2h", "3 days 2 hours"),
    (400 * DAY + HOUR, "400d 1h", "400 days 1 hour"),
])
def test_the_age_of_a_session_in_short_and_in_words(seconds, text, words):
    assert age_text(seconds) == text and age_words(seconds) == words


# ----- a scratch home and a scratch /proc -----

def line(record):
    return json.dumps(record, separators=(",", ":")).encode() + b"\n"


def assistant(model, text=MARKER, **more):
    return line({"parentUuid": "p", "isSidechain": False, "type": "assistant",
                 "message": {"model": model, "role": "assistant", "content": [{"type": "text", "text": text}]},
                 **more})


def user(text=MARKER):
    return line({"type": "user", "message": {"role": "user", "content": text}})


class Machine:
    """A scratch home with session files and a scratch /proc with processes."""

    def __init__(self, tmp_path):
        self.home = tmp_path / "home"
        self.proc = tmp_path / "proc"
        self.home.mkdir()
        self.proc.mkdir()
        self.host = Host(self.home, self.proc)

    def process(self, pid, ticks=5000, children=(), files=()):
        folder = self.proc / str(pid)
        (folder / "task" / str(pid)).mkdir(parents=True, exist_ok=True)
        (folder / "stat").write_text(f"{pid} (made up) name) S " + " ".join(["0"] * 18) + f" {ticks} 0 0\n")
        (folder / "task" / str(pid) / "children").write_text(" ".join(map(str, children)))
        (folder / "fd").mkdir(exist_ok=True)
        for number, target in enumerate(files):
            os.symlink(target, folder / "fd" / str(number))

    def claude(self, pid, records=b"", ticks=5000, session=SESSION, folder="/made/up_folder.x", started=STARTED,
               **more):
        self.process(pid, ticks)
        sessions_folder = self.home / ".claude" / "sessions"
        sessions_folder.mkdir(parents=True, exist_ok=True)
        (sessions_folder / f"{pid}.json").write_text(json.dumps(
            {"pid": pid, "sessionId": session, "cwd": folder, "startedAt": started, "procStart": str(ticks),
             "name": MARKER, **more}))
        if records is None:
            return None
        return self.transcript(records, session, folder)

    def transcript(self, records, session=SESSION, folder="/made/up_folder.x"):
        path = self.home / ".claude" / "projects" / "-made-up-folder-x" / f"{session}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(records)
        return path

    def rollout(self, records, name="rollout-2026-11-19T16-38-25-01a1f551-426d-7d93-9568-9950011f5d54.jsonl"):
        path = self.home / ".codex" / "sessions" / "2026" / "11" / "19" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(records)
        return path


@pytest.fixture
def machine(tmp_path):
    return Machine(tmp_path)


# ----- Claude Code -----

def test_the_model_and_the_start_of_a_claude_session(machine):
    machine.claude(700, user() + assistant("claude-opus-5-5") + user())
    facts = read_claude(machine.host, [700])
    assert (facts.model, facts.started_ms, facts.reason, facts.pid) == ("claude-opus-5-5", STARTED, "ok", 700)


def test_the_last_record_of_the_assistant_counts_when_the_model_changed(machine):
    machine.claude(700, assistant("claude-opus-5-5") + user() + assistant("claude-fable-5-2") + user())
    assert read_claude(machine.host, [700]).model == "claude-fable-5-2"


def test_a_sub_agent_record_and_a_record_with_no_real_model_do_not_count(machine):
    machine.claude(700, assistant("claude-opus-5-5") + assistant("claude-haiku-5", isSidechain=True)
                   + assistant("<synthetic>") + assistant(MARKER + " not a model") + assistant(7)
                   + line({"type": "user", "message": {"model": "claude-fable-5-2"}}))
    assert read_claude(machine.host, [700]).model == "claude-opus-5-5"


def test_a_process_with_no_session_file_has_no_facts(machine):
    machine.process(700)
    facts = read_claude(machine.host, [700])
    assert (facts.model, facts.started_ms, facts.reason) == (None, None, "no_session")


def test_the_first_process_of_the_family_with_a_session_file_is_the_agent(machine):
    machine.process(600, children=[650, 700])
    machine.process(650)
    machine.claude(700, assistant("claude-opus-5-5"))
    facts = read_claude(machine.host, machine.host.family(600, 600))
    assert (facts.model, facts.pid) == ("claude-opus-5-5", 700)


def test_a_shell_with_two_live_claude_code_processes_gives_no_model_and_no_start(machine):
    """The shell has the terminal, and two Claude Code processes are its children (one stopped with Ctrl-Z): which one
    is the agent is not known, so neither is taken."""
    machine.claude(700, assistant("claude-opus-5-5"))
    machine.claude(701, assistant("claude-fable-5-2"), session=OTHER_SESSION, started=STARTED + 9)
    machine.process(600, children=[700, 701])
    facts = read_claude(machine.host, machine.host.family(600, 600))
    assert (facts.model, facts.started_ms, facts.reason, facts.pid) == (None, None, "several_sessions", 0)


def test_a_foreground_claude_code_process_is_the_agent_also_with_an_other_one_below_it(machine):
    machine.claude(701, assistant("claude-fable-5-2"), session=OTHER_SESSION)
    machine.claude(700, assistant("claude-opus-5-5"))
    machine.process(700, children=[701])
    machine.process(600, children=[700])
    assert read_claude(machine.host, machine.host.family(700, 600)).model == "claude-opus-5-5"


def test_the_child_processes_are_read_only_when_the_first_process_is_not_the_agent(machine):
    machine.claude(700, assistant("claude-opus-5-5"))
    machine.host.children = lambda pid: pytest.fail("the child processes were read")
    assert read_claude(machine.host, machine.host.family(700, 600)).pid == 700


def test_the_family_of_a_process_has_a_limit(machine):
    for pid in range(1, 80):
        machine.process(pid, children=[pid + 1])
    assert list(machine.host.family(1)) == list(range(1, linux.MAX_PROCESSES + 1))
    machine.process(200, children=[200, 201])  # a process that names itself
    machine.process(201, children=[200])
    assert list(machine.host.family(200, 0, -4)) == [200, 201]


def test_a_session_file_of_an_older_process_with_the_same_pid_is_not_used(machine):
    """The pid 700 was Claude Code; an other program has it now: /proc has an other start time."""
    machine.claude(700, assistant("claude-opus-5-5"), ticks=5000)
    machine.process(700, ticks=9000)
    facts = read_claude(machine.host, [700])
    assert (facts.model, facts.started_ms, facts.reason) == (None, None, "other_process")
    (machine.proc / "700" / "stat").unlink()  # the process is gone
    assert read_claude(machine.host, [700]).reason == "other_process"


def test_a_session_file_that_names_an_other_pid_is_not_used(machine):
    machine.claude(700, assistant("claude-opus-5-5"))
    file = machine.home / ".claude" / "sessions" / "700.json"
    file.write_text(file.read_text().replace('"pid": 700', '"pid": 701'))
    assert read_claude(machine.host, [700]).reason == "other_process"


@pytest.mark.parametrize("content", [b"", b"{", b"[1, 2]", b'"text"', b"\xff\xfe\x00", b"{" * 5000,
                                     b" " * (sessions.SMALL_FILE + 10)])
def test_a_broken_session_file_gives_no_facts_and_no_error(machine, content):
    machine.claude(700, assistant("claude-opus-5-5"))
    (machine.home / ".claude" / "sessions" / "700.json").write_bytes(content)
    assert read_claude(machine.host, [700]) == SessionFacts(reason="no_session")


@pytest.mark.parametrize("change", [{"sessionId": "../../made-up"}, {"sessionId": 5}, {"sessionId": None}])
def test_a_session_id_of_an_other_form_names_no_file(machine, change):
    machine.claude(700, assistant("claude-opus-5-5"), **change)
    (machine.home / "made-up.jsonl").write_bytes(assistant("claude-opus-5-5"))
    facts = read_claude(machine.host, [700])
    assert (facts.model, facts.started_ms, facts.reason) == (None, STARTED, "no_transcript")


def test_a_session_with_no_transcript_file_has_the_start_only(machine):
    machine.claude(700, None)
    facts = read_claude(machine.host, [700])
    assert (facts.model, facts.started_ms, facts.reason) == (None, STARTED, "no_transcript")


def test_a_session_with_no_record_of_the_assistant_yet_has_the_start_only(machine):
    machine.claude(700, user() + user())
    facts = read_claude(machine.host, [700])
    assert (facts.model, facts.started_ms, facts.reason) == (None, STARTED, "no_model")
    machine.claude(701, b"", session=OTHER_SESSION)
    assert read_claude(machine.host, [701]).reason == "no_model"


def test_a_start_that_is_not_a_number_is_no_start(machine):
    machine.claude(700, assistant("claude-opus-5-5"), started="yesterday")
    facts = read_claude(machine.host, [700])
    assert (facts.model, facts.started_ms) == ("claude-opus-5-5", None)


def test_the_transcript_is_found_by_its_session_id_when_the_folder_has_an_other_name(machine):
    path = machine.claude(700, assistant("claude-opus-5-5"))
    other = path.parent.parent / "-an-other-name"
    path.parent.rename(other)
    assert read_claude(machine.host, [700]).model == "claude-opus-5-5"


@pytest.mark.parametrize("records", [
    b"\n\n\n", b"{broken\n" * 50, b"\xff\xfe\x00\n", b"[]\n", b'{"type":"assistant"}\n',
    b'{"type":"assistant","message":5}\n', b'{"type":"assistant","message":{"model":{"a":1}}}\n',
    b'{"type":"assistant","message":{"model":"' + b"x" * 500 + b'"}}\n', b"[" * 100000 + b'"type":"assistant"\n',
])
def test_a_broken_transcript_gives_no_model_and_no_error(machine, records):
    machine.claude(700, records)
    facts = read_claude(machine.host, [700])
    assert (facts.model, facts.started_ms, facts.reason) == (None, STARTED, "no_model")


def test_a_broken_line_after_the_last_good_record_does_not_hide_it(machine):
    machine.claude(700, assistant("claude-opus-5-5") + b'{"type":"assistant","mess' + b"\n" + b"{half a line")
    assert read_claude(machine.host, [700]).model == "claude-opus-5-5"


def test_a_transcript_that_is_not_a_file_is_not_read(machine):
    path = machine.claude(700, assistant("claude-opus-5-5"))
    path.unlink()
    os.mkfifo(path)  # a read of it would never end
    assert read_claude(machine.host, [700]).reason == "no_transcript"


def test_of_a_huge_transcript_only_the_end_is_read(machine):
    filler = user("made-up " * 100) * 40000  # about 35 MB
    path = machine.claude(700, assistant("claude-opus-5-5") + filler + assistant("claude-fable-5-2") + user() * 20)
    assert path.stat().st_size > 30_000_000
    facts = read_claude(machine.host, [700])
    assert facts.model == "claude-fable-5-2" and machine.host.bytes_read == BLOCK


def test_a_scan_of_a_transcript_with_no_model_at_its_end_has_a_limit(machine):
    filler = user("made-up " * 100) * 10000  # about 9 MB after the last record of the assistant
    path = machine.claude(700, assistant("claude-opus-5-5") + filler)
    assert path.stat().st_size > 2 * SCAN_LIMIT
    facts = read_claude(machine.host, [700])
    assert (facts.model, facts.reason) == (None, "no_model") and machine.host.bytes_read == SCAN_LIMIT


def test_a_record_that_is_longer_than_one_block_is_read_in_whole(machine):
    machine.claude(700, user() + assistant("claude-opus-5-5", "made-up " * 40000) + user("made-up " * 30000))
    facts = read_claude(machine.host, [700])
    assert facts.model == "claude-opus-5-5" and BLOCK < machine.host.bytes_read < 12 * BLOCK


def test_a_transcript_that_did_not_change_is_not_read_again(machine):
    machine.claude(700, assistant("claude-opus-5-5") + user())
    first = read_claude(machine.host, [700])
    read = machine.host.bytes_read
    second = read_claude(machine.host, [700], first)
    assert second.model == "claude-opus-5-5" and machine.host.bytes_read == read


def test_of_a_transcript_that_grew_only_the_new_part_is_read(machine):
    path = machine.claude(700, assistant("claude-opus-5-5") + user() * 50)
    first = read_claude(machine.host, [700])
    read = machine.host.bytes_read
    with open(path, "ab") as file:
        file.write(user())
    second = read_claude(machine.host, [700], first)
    assert second.model == "claude-opus-5-5" and machine.host.bytes_read - read == len(user())
    read = machine.host.bytes_read
    with open(path, "ab") as file:
        file.write(assistant("claude-fable-5-2") + user())
    third = read_claude(machine.host, [700], second)
    assert third.model == "claude-fable-5-2"
    assert machine.host.bytes_read - read == len(assistant("claude-fable-5-2") + user())


def test_a_part_that_starts_in_the_middle_of_a_line_is_read_with_the_older_part(machine):
    """The file ended in the middle of a record at the first read: the record is whole at the second read."""
    record = assistant("claude-fable-5-2")
    path = machine.claude(700, assistant("claude-opus-5-5") + record[:40])
    first = read_claude(machine.host, [700])
    assert first.model == "claude-opus-5-5"
    with open(path, "ab") as file:
        file.write(record[40:])
    assert read_claude(machine.host, [700], first).model == "claude-fable-5-2"


def test_a_transcript_that_is_an_other_file_now_is_read_from_its_end_again(machine):
    path = machine.claude(700, assistant("claude-opus-5-5") + user() * 3)
    first = read_claude(machine.host, [700])
    path.rename(path.with_suffix(".old"))  # the first file stays: the new one cannot get its number
    # Longer, and an other file: its record is before the place where the first file ended.
    path.write_bytes(assistant("claude-fable-5-2") + user() * 30)
    assert read_claude(machine.host, [700], first).model == "claude-fable-5-2"
    path.write_bytes(assistant("claude-haiku-5"))  # the same file, shorter
    assert read_claude(machine.host, [700], first).model == "claude-haiku-5"


def test_an_other_file_at_the_same_path_is_read_in_whole_also_when_a_line_ends_where_the_first_file_ended(machine):
    """Only the number of the file tells the two files apart here: the new file is longer, a line of it ends at the
    place where the first file ended, and its record of the assistant is before that place."""
    path = machine.claude(700, assistant("claude-opus-5-5") + user() * 3)
    first = read_claude(machine.host, [700])
    size = first.mark.size
    path.rename(path.with_suffix(".old"))  # the first file stays: the new one cannot get its number
    head = assistant("claude-fable-5-2")
    head += user("x" * (size - len(head) - len(user(""))))
    assert len(head) == size and head.endswith(b"\n")
    path.write_bytes(head + user() * 3)
    assert read_claude(machine.host, [700], first).model == "claude-fable-5-2"


def run_briefly(call, fifo):
    """The value of call(), or a failure when it does not end in 2 s (a read that waits for a writer of the pipe)."""
    done = []
    thread = threading.Thread(target=lambda: done.append(call()), daemon=True)
    thread.start()
    thread.join(2)
    if not done:
        os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))  # lets the blocked read end
        thread.join(2)
        pytest.fail("the read blocked on a pipe")
    return done[0]


@pytest.mark.parametrize("kind", ["pipe", "device"])
def test_a_session_file_that_is_a_pipe_or_a_device_is_a_reason_code_and_never_blocks(machine, kind):
    machine.claude(700, assistant("claude-opus-5-5"))
    path = machine.home / ".claude" / "sessions" / "700.json"
    path.unlink()
    if kind == "pipe":
        os.mkfifo(path)
    else:
        os.symlink("/dev/null", path)
    facts = run_briefly(lambda: read_claude(machine.host, [700]), path)
    assert (facts.model, facts.started_ms, facts.reason) == (None, None, "not_regular")


def test_the_first_line_of_a_rollout_file_that_is_a_pipe_is_not_read(machine):
    path = machine.rollout(b"")
    path.unlink()
    os.mkfifo(path)
    assert run_briefly(lambda: sessions._first_stamp(machine.host, path), path) is None
    assert machine.host.bytes_read == 0


def test_a_new_session_of_the_same_process_keeps_the_model_until_its_first_answer(machine):
    """After "/clear" the process has a new session id and a transcript with no answer yet."""
    machine.claude(700, assistant("claude-opus-5-5"))
    first = read_claude(machine.host, [700])
    machine.claude(700, user(), session=OTHER_SESSION)
    second = read_claude(machine.host, [700], first)
    assert (second.model, second.reason) == ("claude-opus-5-5", "ok")
    machine.claude(800, user(), session=OTHER_SESSION)  # an other process: nothing is kept
    assert read_claude(machine.host, [800], first).model is None


# ----- Codex -----

def meta(stamp="2026-11-19T19:38:25.878Z"):
    return (b'{"timestamp":"' + stamp.encode() + b'","ordinal":0,"type":"session_meta","payload":{"cwd":"'
            + MARKER.encode() + b'"}}\n')


def turn(model):
    return line({"timestamp": "2026-11-19T19:40:00.000Z", "type": "turn_context",
                 "payload": {"cwd": MARKER, "model": model, "summary": MARKER}})


def test_the_model_and_the_start_of_a_codex_session_from_the_rollout_file_that_the_process_has_open(machine):
    path = machine.rollout(meta() + turn("gpt-5.2-codex") + user() + turn("gpt-5.6-terra") + user())
    machine.process(900, files=["/dev/null", str(machine.home / ".codex" / "logs_2.sqlite"), str(path)])
    facts = read_codex(machine.host, [900])
    assert (facts.model, facts.reason, facts.pid) == ("gpt-5.6-terra", "ok", 900)
    assert facts.started_ms == 1795117105878


def test_a_codex_process_with_no_open_rollout_file_has_no_facts(machine):
    """A rollout file of the same folder and the same time is not taken: only a file that the process has open."""
    machine.rollout(meta() + turn("gpt-5.2-codex"))
    machine.process(900, files=["/dev/null"])
    assert read_codex(machine.host, [900]) == SessionFacts(reason="no_session")
    assert read_codex(machine.host, [901]) == SessionFacts(reason="no_session")  # no such process


OTHER_ROLLOUT = "rollout-2026-11-19T17-00-00-02b2f662-537e-8e04-a679-a061122f6e65.jsonl"


def test_a_codex_process_with_two_open_rollout_files_has_no_model(machine):
    """Two rollout files open (a sub-agent, a second session): which one is the agent is not known."""
    first = machine.rollout(meta() + turn("gpt-5.2-codex"))
    second = machine.rollout(meta() + turn("made-up-sub-model"), name=OTHER_ROLLOUT)
    machine.process(900, files=[str(second), str(first)])
    assert read_codex(machine.host, [900]) == SessionFacts(reason="several_rollouts")
    assert machine.host.bytes_read == 0
    machine.process(901, files=[str(first), str(first)])  # one file open two times is one file
    assert read_codex(machine.host, [901]).model == "gpt-5.2-codex"


def test_rollout_files_of_two_child_processes_give_no_model_and_one_of_the_foreground_process_is_taken(machine):
    first = machine.rollout(meta() + turn("gpt-5.2-codex"))
    second = machine.rollout(meta() + turn("made-up-sub-model"), name=OTHER_ROLLOUT)
    machine.process(800, children=[900, 901])
    machine.process(900, files=[str(first)])
    machine.process(901, files=[str(second)])
    assert read_codex(machine.host, machine.host.family(800, 800)).reason == "several_rollouts"
    machine.process(902, children=[901], files=[str(first)])
    assert read_codex(machine.host, machine.host.family(902, 800)).model == "gpt-5.2-codex"


def test_a_file_that_is_not_a_rollout_file_of_the_home_is_not_read(machine, tmp_path):
    name = "rollout-2026-11-19T16-38-25-01a1f551-426d-7d93-9568-9950011f5d54.jsonl"
    outside = tmp_path / name
    outside.write_bytes(meta() + turn("gpt-5.2-codex"))
    inside = machine.rollout(meta() + turn("gpt-5.2-codex"), name="notes.jsonl")
    machine.process(900, files=[str(outside), str(inside), str(inside.parent / name)])
    assert read_codex(machine.host, [900]) == SessionFacts(reason="no_session")
    assert machine.host.bytes_read == 0


@pytest.mark.parametrize("records, model, started", [
    (meta(), None, 1795117105878),
    (b"", None, None),
    (b"{broken\n" + turn("gpt-5.2-codex"), "gpt-5.2-codex", None),
    (meta("2026-99-99T99:99:99Z") + turn("gpt-5.2-codex"), "gpt-5.2-codex", None),
    (meta() + b'{"type":"turn_context","payload":5}\n', None, 1795117105878),
])
def test_a_rollout_file_with_parts_missing_or_broken(machine, records, model, started):
    path = machine.rollout(records)
    machine.process(900, files=[str(path)])
    facts = read_codex(machine.host, [900])
    assert (facts.model, facts.started_ms, facts.reason) == (model, started, "ok" if model else "no_model")


# ----- the engine -----

class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Terminals:
    """A client that knows the terminals of the test: address -> Terminal or Failure."""

    def __init__(self, **terminals):
        self.terminals = terminals
        self.calls = []

    def terminal(self, address):
        self.calls.append(address)
        return self.terminals.get(address.replace("/", "_"), Failure("herdr_not_found"))


CREATED = 1_794_000_000_000
AGENTS = [Agent("t1", "working", "rev", "Main", "claude-code"), Agent("t2", "blocked", "dev", "Main", "codex")]


@pytest.fixture
def watched(machine):
    machine.claude(700, assistant("claude-opus-5-5"))
    machine.process(600, children=[700])
    machine.process(900)
    client = Terminals(t1=Terminal(600, 600, CREATED), t2=Terminal(900, 900, CREATED + 5))
    clock = Clock()
    return SimpleNamespace(machine=machine, client=client, clock=clock,
                           watch=SessionWatch(client, machine.host, clock=clock))


def test_the_engine_reads_each_agent_of_the_list_one_time(watched, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    assert watched.watch.facts() == {}
    assert watched.watch.step(AGENTS) is True
    assert watched.client.calls == ["t1", "t2"]
    # Codex with no open rollout file: no model, and the creation time of the terminal.
    assert watched.watch.facts() == {"t1": ("claude-opus-5-5", STARTED), "t2": (None, CREATED + 5)}
    assert [r.getMessage() for r in caplog.records] == [
        "session facts terminal=t1 app=claude-code reason=ok",
        "session facts terminal=t2 app=codex reason=no_session"]


def test_no_get_while_the_processes_of_an_agent_live_and_one_in_five_minutes_as_a_net(watched, caplog):
    """A step each CHECK seconds: the processes are checked in /proc, the files are read each 30 s, and Herdr is
    asked again only after GET_REFRESH."""
    caplog.set_level(logging.INFO, logger="bellwether")
    watched.watch.step(AGENTS)
    read = watched.machine.host.bytes_read
    watched.clock.now = 1000.0 + sessions.CHECK
    assert watched.watch.step(AGENTS) is False and watched.watch.wait() == sessions.CHECK
    for second in range(10, 300, 5):
        watched.clock.now = 1000.0 + second
        assert watched.watch.step(AGENTS) is False
    assert watched.client.calls == ["t1", "t2"]
    assert watched.machine.host.bytes_read == read  # the transcript did not change: it is not read again
    assert len(caplog.records) == 2  # a reason code that stays is logged one time
    watched.clock.now = 1000.0 + sessions.GET_REFRESH
    assert watched.watch.step(AGENTS) is False
    assert watched.client.calls == ["t1", "t2", "t1", "t2"]
    for second in range(305, 1200, 5):  # twenty minutes in all: 4 gets for each agent, the first one too
        watched.clock.now = 1000.0 + second
        watched.watch.step(AGENTS)
    assert len(watched.client.calls) == 2 * 4


def test_the_files_are_read_each_thirty_seconds_with_no_get(watched):
    watched.watch.step(AGENTS)
    with open(watched.machine.transcript(assistant("claude-opus-5-5")), "ab") as file:
        file.write(assistant("claude-fable-5-2"))
    watched.clock.now += 25
    assert watched.watch.step(AGENTS) is False and watched.watch.wait() == pytest.approx(5.0)
    watched.clock.now += 5
    assert watched.watch.step(AGENTS) is True and watched.watch.facts()["t1"][0] == "claude-fable-5-2"
    assert watched.client.calls == ["t1", "t2"]


def test_an_agent_that_ends_in_its_terminal_shows_no_old_model_after_the_next_step(watched):
    """Claude Code ends and the shell has the terminal again: the row has the time of the terminal at the next step.
    A new Claude Code in the same terminal shows at the next read of the files."""
    watched.watch.step(AGENTS)
    shutil.rmtree(watched.machine.proc / "700")
    watched.machine.process(600)
    watched.clock.now += sessions.CHECK
    assert watched.watch.step(AGENTS) is True
    assert watched.watch.facts()["t1"] == (None, CREATED) and watched.client.calls == ["t1", "t2", "t1"]
    watched.machine.claude(701, assistant("claude-fable-5-2"), session=OTHER_SESSION, started=STARTED + 9)
    watched.machine.process(600, children=[701])
    watched.clock.now += sessions.CHECK
    assert watched.watch.step(AGENTS) is False  # the shell lives: no get, and the files are not due
    watched.clock.now += sessions.REFRESH
    assert watched.watch.step(AGENTS) is True
    assert watched.watch.facts()["t1"] == ("claude-fable-5-2", STARTED + 9)
    assert watched.client.calls == ["t1", "t2", "t1"]


def test_a_new_process_with_the_same_pid_keeps_nothing_of_the_old_one(watched):
    """The pid came again with an other start: a new process, whose session has no answer yet. The model of the old
    process is not kept (it is kept only after "/clear" in the same process)."""
    watched.watch.step(AGENTS)
    watched.machine.claude(700, user(), ticks=6000, session=OTHER_SESSION, started=STARTED + 9)
    watched.clock.now += sessions.CHECK
    assert watched.watch.step(AGENTS) is True
    assert watched.watch.facts()["t1"] == (None, STARTED + 9) and watched.client.calls == ["t1", "t2", "t1"]


def test_the_net_finds_a_new_foreground_process_while_the_old_one_lives(watched):
    watched.watch.step(AGENTS)
    watched.machine.claude(702, assistant("claude-fable-5-2"), session=OTHER_SESSION, started=STARTED + 9)
    watched.client.terminals["t1"] = Terminal(600, 702, CREATED)  # 702 is not a child of the shell
    watched.clock.now += sessions.GET_REFRESH - sessions.CHECK
    watched.watch.step(AGENTS)
    assert watched.watch.facts()["t1"] == ("claude-opus-5-5", STARTED)
    watched.clock.now += sessions.CHECK
    assert watched.watch.step(AGENTS) is True
    assert watched.watch.facts()["t1"] == ("claude-fable-5-2", STARTED + 9)


def test_a_failed_get_is_asked_again_after_thirty_seconds(watched):
    watched.client.terminals["t1"] = Failure("timeout")
    watched.watch.step(AGENTS)
    watched.clock.now += sessions.REFRESH - 1
    watched.watch.step(AGENTS)
    assert watched.client.calls == ["t1", "t2"]
    watched.clock.now += 1
    watched.watch.step(AGENTS)
    assert watched.client.calls == ["t1", "t2", "t1"]


def test_a_shell_with_two_claude_code_processes_has_the_time_of_its_terminal(watched):
    watched.machine.claude(701, assistant("claude-fable-5-2"), session=OTHER_SESSION, started=STARTED + 9)
    watched.machine.process(600, children=[700, 701])
    watched.watch.step(AGENTS)
    assert watched.watch.facts()["t1"] == (None, CREATED)


def test_a_round_that_ends_stopped_keeps_nothing_of_it(watched):
    """The setting went off or the app quits while a round runs: what the round read is not kept."""
    watched.watch.step(AGENTS, stopped=lambda: len(watched.client.calls) >= 1)
    assert watched.client.calls == ["t1"] and watched.watch.facts() == {}


def test_a_model_that_changes_in_the_session_shows_at_the_next_read(watched):
    watched.watch.step(AGENTS)
    with open(watched.machine.transcript(assistant("claude-opus-5-5")), "ab") as file:
        file.write(assistant("claude-fable-5-2"))
    watched.clock.now += 10
    assert watched.watch.step(AGENTS) is False and watched.watch.facts()["t1"][0] == "claude-opus-5-5"
    watched.clock.now += 20
    assert watched.watch.step(AGENTS) is True and watched.watch.facts()["t1"][0] == "claude-fable-5-2"


def test_an_agent_that_is_new_in_the_list_is_read_at_once_and_one_that_left_is_dropped(watched):
    watched.watch.step(AGENTS[:1])
    assert watched.client.calls == ["t1"]
    watched.clock.now += 1
    assert watched.watch.step(AGENTS) is True and watched.client.calls == ["t1", "t2"]
    watched.clock.now += 1
    assert watched.watch.step(AGENTS[1:]) is True and watched.watch.facts() == {"t2": (None, CREATED + 5)}
    assert watched.client.calls == ["t1", "t2"]
    watched.clock.now += 1
    assert watched.watch.step(AGENTS) is True and watched.client.calls == ["t1", "t2", "t1"]  # back: read at once


def test_an_agent_with_a_new_process_gets_the_facts_of_that_process_at_its_next_read(watched):
    """The agent of the terminal was started again: an other pid, an other session, an other model."""
    watched.watch.step(AGENTS)
    watched.machine.claude(701, assistant("claude-fable-5-2"), session=OTHER_SESSION, started=STARTED + 9)
    watched.machine.process(600, children=[701])
    watched.clock.now += 30
    assert watched.watch.step(AGENTS) is True
    assert watched.watch.facts()["t1"] == ("claude-fable-5-2", STARTED + 9)


def test_an_other_program_in_the_same_terminal_is_read_at_once(watched):
    watched.watch.step(AGENTS)
    watched.clock.now += 1
    assert watched.watch.step([Agent("t1", "working", "rev", "Main", "codex"), AGENTS[1]]) is True
    assert watched.client.calls == ["t1", "t2", "t1"]
    assert watched.watch.facts()["t1"] == (None, CREATED)


def test_an_error_of_herdr_is_a_reason_code_and_the_row_has_no_facts(watched, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    watched.client.terminals["t1"] = Failure("timeout")
    watched.watch.step(AGENTS)
    assert watched.watch.facts()["t1"] == (None, None)
    watched.client.terminals["t1"] = Terminal(600, 600, CREATED)
    watched.clock.now += 30
    assert watched.watch.step(AGENTS) is True and watched.watch.facts()["t1"] == ("claude-opus-5-5", STARTED)
    assert [r.getMessage() for r in caplog.records if "t1" in r.getMessage()] == [
        "session facts terminal=t1 app=claude-code reason=timeout", "session facts terminal=t1 app=claude-code reason=ok"]


def test_a_reader_with_an_error_is_a_reason_code(watched, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")

    def broken(host, pids, known):
        raise RuntimeError(MARKER)

    watch = SessionWatch(watched.client, watched.machine.host, {"claude-code": broken}, watched.clock)
    watch.step(AGENTS)
    assert watch.facts() == {"t1": (None, CREATED), "t2": (None, CREATED + 5)}
    assert [r.getMessage() for r in caplog.records] == [
        "session facts terminal=t1 app=claude-code reason=reader_error",
        "session facts terminal=t2 app=codex reason=no_reader"]
    assert MARKER not in caplog.text


def test_an_agent_of_an_other_machine_has_the_time_of_its_terminal_and_no_local_file_is_read(watched):
    """The pid of an other machine can be the pid of a process here: it is not asked."""
    watched.client.terminals["box_t1"] = Terminal(700, 700, CREATED + 7)
    watched.machine.host.start_ticks = lambda pid: pytest.fail("a local process was asked")
    watched.watch.step([Agent("box/t1", "working", "rev", "Main", "claude-code"),
                        Agent("box/t9", "working", "rev", "Main", "claude-code")])
    assert watched.watch.facts() == {"box/t1": (None, CREATED + 7), "box/t9": (None, None)}
    assert watched.machine.host.bytes_read == 0


def test_a_row_with_no_terminal_address_is_not_asked(watched):
    watched.watch.step([Agent("not an address", "working", "", "", "claude-code"),
                        Agent("sub-agent-7", "idle", "", "", "claude-code"), Agent("", "idle", "", "", "codex")])
    assert watched.client.calls == [] and watched.watch.facts() == {}


def test_a_terminal_with_no_creation_time_and_no_session_has_no_facts(watched):
    watched.client.terminals["t2"] = Terminal(900, 900, 0)
    watched.watch.step(AGENTS)
    assert watched.watch.facts()["t2"] == (None, None)


def test_a_stop_ends_the_reads_and_clear_drops_the_facts(watched):
    watched.watch.step(AGENTS, stopped=lambda: True)
    assert watched.client.calls == [] and watched.watch.facts() == {}
    watched.watch.step(AGENTS)
    watched.watch.clear()
    assert watched.watch.facts() == {} and watched.watch.wait() == 30.0


# ----- privacy -----

def test_nothing_of_a_session_file_is_in_a_log_an_error_a_text_form_or_a_file(machine, caplog, tmp_path):
    """Session files, transcripts and rollout files with a marker in every text of theirs but the model: the whole
    engine runs; the marker is in no log record, in no text form of a value, and in no file that was written."""
    caplog.set_level(logging.DEBUG)
    machine.claude(700, user() + assistant("claude-opus-5-5") + user() + b'{"type":"assistant","' + MARKER.encode())
    machine.claude(701, assistant(MARKER + " as a model"), session=OTHER_SESSION, folder="/made/" + MARKER)
    rollout = machine.rollout(meta() + turn("gpt-5.2-codex") + user())
    machine.process(900, files=[str(rollout)])
    machine.claude(702, None)
    (machine.home / ".claude" / "sessions" / "702.json").write_text(MARKER)
    client = Terminals(t1=Terminal(700, 700, CREATED), t2=Terminal(900, 900, CREATED), t3=Terminal(701, 701, CREATED),
                       t4=Terminal(702, 702, CREATED))
    clock = Clock()
    watch = SessionWatch(client, machine.host, clock=clock)
    agents = AGENTS + [Agent("t3", "idle", MARKER, MARKER, "claude-code"), Agent("t4", "idle", "", "", "claude-code")]
    before = {path: path.stat().st_mtime_ns for path in tmp_path.rglob("*") if path.is_file()}
    values = []
    for _ in range(3):
        watch.step(agents)
        values.append(repr(watch.facts()) + repr(watch._entries))
        clock.now += 30
    assert watch.facts()["t1"] == ("claude-opus-5-5", STARTED) and watch.facts()["t2"][0] == "gpt-5.2-codex"
    assert watch.facts()["t3"] == (None, STARTED) and watch.facts()["t4"] == (None, CREATED)
    assert MARKER not in caplog.text and MARKER not in "".join(values)
    assert all(MARKER not in str(record.args) + record.getMessage() for record in caplog.records)
    after = {path: path.stat().st_mtime_ns for path in tmp_path.rglob("*") if path.is_file()}
    assert after == before  # no file was written or changed, in the home or anywhere else of the scratch folder


# ----- the title of the terminal: the name of an agent that has no name in Herdr -----

def titled(watched, **titles):
    for key, title in titles.items():
        old = watched.client.terminals[key]
        watched.client.terminals[key] = Terminal(old.pid, old.foreground, old.created_ms, title)


def test_the_engine_gives_the_title_of_each_terminal(watched, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    titled(watched, t1="Made-up task one")
    assert watched.watch.titles() == {}
    assert watched.watch.step(AGENTS) is True
    assert watched.watch.titles() == {"t1": "Made-up task one", "t2": ""}
    assert "Made-up" not in caplog.text and "Made-up" not in repr(watched.watch._entries)


def test_a_new_status_of_an_agent_is_one_get_and_a_new_title_tells_the_rows(watched):
    titled(watched, t1="Made-up task one")
    watched.watch.step(AGENTS)
    del watched.client.calls[:]
    titled(watched, t1="Made-up task two")
    watched.clock.now += sessions.CHECK
    assert watched.watch.step(AGENTS) is False and watched.client.calls == []  # the same status: Herdr is not asked
    blocked = [Agent("t1", "blocked", "rev", "Main", "claude-code"), AGENTS[1]]
    watched.clock.now += sessions.CHECK
    assert watched.watch.step(blocked) is True and watched.client.calls == ["t1"]
    assert watched.watch.titles()["t1"] == "Made-up task two"
    watched.clock.now += sessions.CHECK
    assert watched.watch.step(blocked) is False and watched.client.calls == ["t1"]


def test_a_get_that_fails_keeps_the_title_and_an_agent_that_left_has_none(watched):
    titled(watched, t1="Made-up task one", t2="Made-up task b")
    watched.watch.step(AGENTS)
    watched.client.terminals["t1"] = Failure("timeout")
    watched.clock.now += sessions.GET_REFRESH
    watched.watch.step(AGENTS)
    assert watched.watch.titles() == {"t1": "Made-up task one", "t2": "Made-up task b"}
    assert watched.watch.step(AGENTS[:1]) is True
    assert watched.watch.titles() == {"t1": "Made-up task one"}


def test_clear_drops_the_facts_and_keeps_the_titles(watched):
    titled(watched, t1="Made-up task one")
    watched.watch.step(AGENTS)
    watched.watch.clear()
    assert watched.watch.facts() == {} and watched.watch.titles()["t1"] == "Made-up task one"


def test_with_no_files_the_engine_asks_herdr_and_reads_no_file(watched):
    titled(watched, t1="Made-up task one")
    read = watched.machine.host.bytes_read
    assert watched.watch.step(AGENTS, files=False) is True
    assert watched.client.calls == ["t1", "t2"] and watched.machine.host.bytes_read == read
    assert watched.watch.titles()["t1"] == "Made-up task one"
    assert watched.watch.facts() == {"t1": (None, None), "t2": (None, None)}
    watched.clock.now += sessions.REFRESH
    watched.watch.step(AGENTS, files=False)
    assert watched.client.calls == ["t1", "t2"] and watched.machine.host.bytes_read == read


# ----- Codex 0.170: the process has no rollout file open; it holds a lock file with the id of its thread -----

THREAD_MS = 1_795_015_110_521  # the creation time that a thread id has in its first 12 hex digits


def thread_id(ms=THREAD_MS, tail="7d93-9568-9950011f5d54"):
    digits = f"{ms:012x}"
    return f"{digits[:8]}-{digits[8:]}-{tail}"


def thread_rollout(machine, records, thread, ms=THREAD_MS):
    day = datetime.fromtimestamp(ms / 1000)
    path = (machine.home / ".codex" / "sessions" / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}"
            / f"rollout-{day:%Y-%m-%dT%H-%M-%S}-{thread}.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(records)
    return path


def lock_of(machine, thread):
    return str(machine.home / ".codex" / "thread-writer-locks" / f"{thread}.lock")


def thread_meta(source="user"):
    return (b'{"timestamp":"2026-11-19T19:38:25.774Z","type":"session_meta","payload":{"id":"x","thread_source":"'
            + source.encode() + b'","base_instructions":"' + MARKER.encode() + b'"}}\n')


def config(machine, text):
    (machine.home / ".codex").mkdir(exist_ok=True)
    (machine.home / ".codex" / "config.toml").write_text(text)


def arguments(machine, pid, *words):
    (machine.proc / str(pid) / "cmdline").write_bytes(b"".join(word.encode() + b"\0" for word in words))


def test_the_model_of_a_codex_session_from_the_rollout_file_of_the_thread_that_the_process_locks(machine):
    thread = thread_id()
    path = thread_rollout(machine, thread_meta() + turn("gpt-5.2-codex") + user() + turn("gpt-5.6-terra"), thread)
    machine.process(900, files=["/dev/null", lock_of(machine, thread)])
    facts = read_codex(machine.host, [900])
    assert (facts.model, facts.reason, facts.pid) == ("gpt-5.6-terra", "ok", 900)
    assert facts.started_ms == int(datetime(2026, 11, 19, 19, 38, 25, 774000, timezone.utc).timestamp() * 1000)
    assert facts.mark.path == str(path)
    assert MARKER not in repr(facts)


def test_a_helper_thread_of_the_process_is_not_the_session(machine):
    """Codex also locks the threads of its review helpers: only a thread of the user counts."""
    mine, helper = thread_id(), thread_id(THREAD_MS + 5, "7fb2-ad05-f7e930c0ae87")
    thread_rollout(machine, thread_meta() + turn("gpt-5.6-terra"), mine)
    thread_rollout(machine, thread_meta("guardian_review") + turn("codex-auto-review"), helper, THREAD_MS + 5)
    machine.process(900, files=[lock_of(machine, helper), lock_of(machine, mine)])
    assert read_codex(machine.host, [900]).model == "gpt-5.6-terra"


def test_two_threads_of_the_user_in_one_process_give_no_model(machine):
    first, second = thread_id(), thread_id(THREAD_MS + 5, "7fb2-ad05-f7e930c0ae87")
    thread_rollout(machine, thread_meta() + turn("gpt-5.6-terra"), first)
    thread_rollout(machine, thread_meta() + turn("gpt-5.2-codex"), second, THREAD_MS + 5)
    machine.process(900, files=[lock_of(machine, first), lock_of(machine, second)])
    assert read_codex(machine.host, [900]) == SessionFacts(reason="several_rollouts")


def test_a_rollout_file_of_an_other_day_or_an_other_thread_is_not_taken(machine):
    thread = thread_id()
    thread_rollout(machine, thread_meta() + turn("gpt-5.2-codex"), thread_id(tail="0000-0000-000000000000"))
    thread_rollout(machine, thread_meta() + turn("gpt-5.2-codex"), thread, THREAD_MS + 40 * 86_400_000)
    machine.process(900, files=[lock_of(machine, thread)])
    assert read_codex(machine.host, [900]).model is None


@pytest.mark.parametrize("words, text, model, reason", [
    (("codex", "--no-daemon"), 'model = "gpt-5.6-terra"\nmodel_reasoning_effort = "medium"\n', "gpt-5.6-terra", "config_default"),
    (("codex",), 'other = 1\n', None, "no_session"),
    (("codex",), 'model = 7\n', None, "no_session"),
    (("codex",), 'model = "two words"\n', None, "no_session"),
    (("codex",), 'broken [[[\n', None, "no_session"),
    (("codex",), None, None, "no_session"),
    # An argument can name an other model, a profile or a setting: the file does not say what runs then.
    (("codex", "-m", "gpt-6-sol"), 'model = "gpt-5.6-terra"\n', None, "no_session"),
    (("codex", "--model=gpt-6-sol"), 'model = "gpt-5.6-terra"\n', None, "no_session"),
    (("codex", "-c", "model=x"), 'model = "gpt-5.6-terra"\n', None, "no_session"),
    (("codex", "--profile", "work"), 'model = "gpt-5.6-terra"\n', None, "no_session"),
    (("codex", "-p", "work"), 'model = "gpt-5.6-terra"\n', None, "no_session"),
    (("codex", "--oss"), 'model = "gpt-5.6-terra"\n', None, "no_session"),
    ((), 'model = "gpt-5.6-terra"\n', None, "no_session"),  # the arguments cannot be read
])
def test_a_codex_session_with_no_turn_yet_has_the_model_of_the_settings_file(machine, words, text, model, reason):
    """Before the first turn Codex has written no rollout file: the model is the one of its settings file, when
    no argument of the process can change it."""
    thread = thread_id()
    if text is not None:
        config(machine, text)
    machine.process(900, files=[lock_of(machine, thread)])
    if words:
        arguments(machine, 900, *words)
    facts = read_codex(machine.host, [900])
    assert (facts.model, facts.reason, facts.started_ms) == (model, reason, None)
    assert facts.pid == (900 if model else 0)


def test_the_lock_of_the_foreground_process_counts_before_those_of_its_children(machine):
    mine, other = thread_id(), thread_id(THREAD_MS + 5, "7fb2-ad05-f7e930c0ae87")
    thread_rollout(machine, thread_meta() + turn("gpt-5.6-terra"), mine)
    thread_rollout(machine, thread_meta() + turn("gpt-5.2-codex"), other, THREAD_MS + 5)
    machine.process(900, children=[901], files=[lock_of(machine, mine)])
    machine.process(901, files=[lock_of(machine, other)])
    machine.process(800, children=[900])
    assert read_codex(machine.host, machine.host.family(900, 800)).model == "gpt-5.6-terra"
    # A shell in front: the Codex processes below it both count, so the two threads give no model.
    assert read_codex(machine.host, machine.host.family(800, 800)).reason == "several_rollouts"


def test_a_lock_file_with_an_other_name_or_in_an_other_folder_is_not_a_thread(machine):
    thread = thread_id()
    thread_rollout(machine, thread_meta() + turn("gpt-5.6-terra"), thread)
    config(machine, 'model = "gpt-5.6-terra"\n')
    machine.process(900, files=[str(machine.home / ".codex" / "thread-writer-locks" / ".coordination.lock"),
                                str(machine.home / "other" / f"{thread}.lock")])
    arguments(machine, 900, "codex")
    assert read_codex(machine.host, [900]) == SessionFacts(reason="no_session")
