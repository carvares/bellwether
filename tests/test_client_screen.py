"""The screen calls of the client with a fake runner: read the screen of one agent, press keys in it, send a text.
No test starts the real herdr-core. MARKER stands for the private text of a screen: it must be in no log record."""
import json
import logging
import os
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from bellwether import client as client_module
from bellwether.client import (
    PRESS_TIMEOUT, READ_TIMEOUT, SEND_TIMEOUT, TEXT_LIMIT, Failure, HerdrClient, Screen, text_problem, valid_address,
    valid_text)
from bellwether.platform import linux

CORE = "/fake/herdr-core"
MARKER = "MARKER-private-screen-text"
LIST = {"terminals": [
    {"address": "t1", "agent": "claude-code", "state": "live", "status": "blocked"},
    {"address": "t1c", "agent": "codex", "state": "live", "status": "working"},
    {"address": "box/t7", "agent": "claude-code", "state": "live", "status": "blocked"},
]}


@pytest.fixture(autouse=True)
def linux_system(monkeypatch):
    """The client with the Linux module of the platform, on every system: these tests check its command lines
    (the KWin raise, systemd-run, `env -u`). The client with the macOS module: tests/test_macos.py."""
    monkeypatch.setattr(client_module, "platform", linux)


def done(stdout=b"", returncode=0, stderr=b""):
    stdout = stdout if isinstance(stdout, bytes) else json.dumps(stdout).encode()
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class Runner:
    """Answers `ls` with LIST, `get <t> --json` with the terminal whose address is <t> (or `names[<t>]`: the address
    of the terminal that herdr-core finds for that text), and every other command with `answer` (an exception is
    raised). `calls` has the commands other than `ls` and `get`; `gets` has the `get` commands."""

    def __init__(self, answer=None, names=None):
        self.answer = answer
        self.names = names or {}
        self.calls: list[tuple[list[str], float]] = []
        self.gets: list[tuple[list[str], float]] = []

    def __call__(self, argv, timeout=2.0):
        if argv[1:] == ["ls", "--json"]:
            return done(LIST)
        if argv[1] == "get":
            self.gets.append((argv, timeout))
            found = self.names.get(argv[2], argv[2])
            if isinstance(found, Exception):
                raise found
            return found if not isinstance(found, str) else done({"address": found, "state": "live"})
        self.calls.append((argv, timeout))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class RunnerProcess:
    """A fake Popen for the `keys` command (it runs as a process that is not killed at its deadline): it ends as the
    runner says, at the first poll."""

    def __init__(self, runner, argv):
        self.runner, self.argv, self.returncode = runner, argv, None
        self.killed = False

    def communicate(self, timeout=None):
        if timeout is None:  # the wait after the deadline: the fake command ends well
            self.returncode = 0
            return b"", b""
        answer = self.runner(self.argv, timeout=timeout)
        self.returncode = answer.returncode
        return answer.stdout, answer.stderr

    def kill(self):
        self.killed = True


def spawn_with(runner):
    """`spawn` for a client: an OSError of the runner comes at the start, as from Popen."""
    def spawn(argv):
        if isinstance(runner.answer, (OSError, subprocess.SubprocessError)) and not isinstance(
                runner.answer, subprocess.TimeoutExpired):
            runner.calls.append((argv, PRESS_TIMEOUT))
            raise runner.answer
        return RunnerProcess(runner, argv)
    return spawn


def client_with(answer=None, core=CORE, listed=True, names=None) -> tuple[HerdrClient, Runner]:
    runner = Runner(answer, names)
    client = HerdrClient(None, core, run=runner, spawn=spawn_with(runner))
    if listed:
        client.list_agents()
    return client, runner


@pytest.fixture
def records(caplog):
    """The log records of the test, as a list that is read at each use."""
    caplog.set_level(logging.DEBUG, logger="bellwether")

    class Records:
        def __iter__(self):
            return iter(caplog.records)

        def __bool__(self):
            return bool(caplog.records)

        def clear(self):
            caplog.clear()

    return Records()


def no_marker(records) -> bool:
    return all(MARKER not in record.getMessage() and MARKER not in str(record.args) and record.exc_info is None
               for record in records)


# ----- the commands -----

def test_read_screen_runs_read_with_json_and_gives_the_text():
    client, runner = client_with(done({"complete": True, "how": "screen", "text": "line one\nline two"}))
    screen = client.read_screen("t1")
    assert screen == Screen("line one\nline two", True)
    assert runner.calls == [([CORE, "read", "t1", "--json"], READ_TIMEOUT)]


def test_read_screen_gives_the_complete_flag():
    client, _ = client_with(done({"complete": False, "how": "screen", "text": "x"}))
    assert client.read_screen("t1") == Screen("x", False)


def test_press_runs_keys_with_each_key_as_one_argument():
    client, runner = client_with(done({"status": "blocked", "turn": 1}))
    assert client.press("t1c", ["2"]) is None
    assert client.press("box/t7", ("1", "3")) is None
    assert runner.calls == [([CORE, "keys", "t1c", "2"], PRESS_TIMEOUT), ([CORE, "keys", "box/t7", "1", "3"], PRESS_TIMEOUT)]


def test_send_text_pastes_the_text_as_one_argument_with_no_caller_tag():
    """`herdr-core send` puts a tag with the address of the caller around the text when HC_TERMINAL_ID is set. The
    client takes the variables of the calling terminal away. `--` ends the options: a text can start with "-"."""
    client, runner = client_with(done({"started": True}))
    assert client.send_text("t1", "--force; rm -r x && $(echo \"é\") 'q'") is None
    assert runner.calls == [(
        ["env", "-u", "HC_TERMINAL_ID", "-u", "HC_SCOPE", "-u", "HC_TERMINAL_SOCKET",
         CORE, "send", "--force", "--", "t1", "--force; rm -r x && $(echo \"é\") 'q'"], SEND_TIMEOUT)]


def test_the_deadlines_are_above_the_holds_of_herdr_core():
    """herdr-core holds a key until 3 s after the last key that a person typed in the terminal, and a text while the
    person has a draft there, up to 60 s (measured with herdr-core 0.1.21). A deadline below that would end the
    command while the key or the text can still arrive."""
    assert READ_TIMEOUT <= 2.0 and 3.0 + 5.0 <= PRESS_TIMEOUT <= 15.0 and 60.0 + 3.0 <= SEND_TIMEOUT <= 70.0


# ----- a name that has the form of an address -----

@pytest.mark.parametrize("call", [
    lambda client: client.read_screen("t1"), lambda client: client.press("t1", ["1"]),
    lambda client: client.send_text("t1", "text"),
], ids=["read", "press", "send"])
def test_each_call_first_asks_herdr_core_which_terminal_the_address_names(call):
    client, runner = client_with(done({"complete": True, "text": "x"}))
    call(client)
    assert runner.gets == [([CORE, "get", "t1", "--json"], READ_TIMEOUT)] and len(runner.calls) == 1


@pytest.mark.parametrize("call", [
    lambda client: client.read_screen("t1"), lambda client: client.press("t1", ["1"]),
    lambda client: client.send_text("t1", "text"),
], ids=["read", "press", "send"])
def test_a_terminal_whose_name_is_the_address_of_an_other_one_gets_no_command(call, records):
    """A terminal can be NAMED "t1". When herdr-core takes the text "t1" for that terminal (its address is "t9"),
    the call does not run: it would read or press in a terminal that is not the agent of the row."""
    answers = [("t9", "not_this_terminal"), (done({"address": None}), "not_this_terminal"),
               (done({"address": 7}), "not_this_terminal"), (done(b"not json"), "not_this_terminal"),
               (done(b"[]"), "not_this_terminal"), (done({"state": "live"}), "not_this_terminal"),
               (done(MARKER.encode(), 3, json.dumps({"error": {"kind": "not_found", "message": MARKER}}).encode()),
                "herdr_not_found"),
               # The check itself did not work: nothing ran. Its own codes, so that no one reads "may still arrive".
               (subprocess.TimeoutExpired(["x"], 2.0, output=MARKER.encode()), "check_timeout"),
               (FileNotFoundError(MARKER), "check_failed"),
               (done(MARKER.encode(), 1, MARKER.encode()), "check_failed"),
               (done(b"", 3, json.dumps({"error": {"kind": "unavailable"}}).encode()), "check_failed")]
    for answer, code in answers:
        client, runner = client_with(done({"complete": True, "text": MARKER}), names={"t1": answer})
        assert call(client) == Failure(code), answer
        assert runner.calls == [] and len(runner.gets) == 1
    assert no_marker(records)


def test_the_screen_object_does_not_show_its_text():
    assert MARKER not in repr(Screen(MARKER, True)) and MARKER not in str(Screen(MARKER, True))


# ----- the address -----

@pytest.mark.parametrize("address", ["t1", "t1c", "t20", "box/t7", "my-box.1/t1b"])
def test_an_address_has_the_form_of_herdr(address):
    assert valid_address(address)


@pytest.mark.parametrize("address", [
    "", "t", "T1", "reviewer", "bw-name", "t1 ", " t1", "t1\n", "t1;ls", "--json", "-t1", "t1/t2/t3", "/t1", "box/",
    "box/reviewer", "t" + "1" * 9, "../t1", "t1 --force", None, 7, ["t1"]])
def test_a_name_or_any_other_text_is_not_an_address(address):
    """herdr-core takes the NAME of a terminal in the place of an address. The client does not."""
    assert not valid_address(address)


@pytest.mark.parametrize("call", [
    lambda client, address: client.read_screen(address),
    lambda client, address: client.press(address, ["1"]),
    lambda client, address: client.send_text(address, "text"),
], ids=["read", "press", "send"])
def test_no_command_runs_for_an_address_that_is_not_valid_or_not_in_the_list(call, records):
    client, runner = client_with(done({"complete": True, "text": MARKER}))
    for address in ("reviewer", "t1; rm", "--json", MARKER, "", None):
        assert call(client, address) == Failure("bad_address")
    for address in ("t2", "t9z", "other/t1"):  # the form is right, the list of agents does not have it
        assert call(client, address) == Failure("unknown_terminal")
    assert runner.calls == []
    assert no_marker(records)
    # The text of an address that is not valid is not in the log: it can be anything.
    assert all("; rm" not in record.getMessage() and "reviewer" not in record.getMessage() for record in records)


def test_before_the_first_list_no_address_is_known():
    client, runner = client_with(done({"complete": True, "text": "x"}), listed=False)
    assert client.read_screen("t1") == Failure("unknown_terminal")
    assert runner.calls == []


def test_an_address_that_left_the_list_is_not_known(monkeypatch):
    client, runner = client_with(done({"complete": True, "text": "x"}))
    assert client.read_screen("t1") == Screen("x", True)
    monkeypatch.setitem(LIST, "terminals", LIST["terminals"][1:])
    client.list_agents()
    assert client.read_screen("t1") == Failure("unknown_terminal")


def test_the_addresses_of_the_app_list_are_known():
    app_list = {"spaces": [{"name": "Main", "tabs": [{"name": "1", "terminals": [
        {"terminal": "t4", "status": "blocked", "app": "claude-code", "name": None, "sub_agents": [
            {"address": "t5", "status": "blocked", "agent": "claude-code", "state": "live"}]}]}]}]}
    calls = []

    def run(argv, timeout=2.0):
        calls.append(argv)
        if argv[1] == "get":
            return done({"address": argv[2]})
        return done(app_list if argv[0] == "/fake/herdr-app" else {"complete": True, "text": "x"})

    client = HerdrClient("/fake/herdr-app", CORE, run=run)
    client.list_agents()
    assert client.read_screen("t4") == Screen("x", True) and client.read_screen("t5") == Screen("x", True)
    assert client.read_screen("t1") == Failure("unknown_terminal")


# ----- the keys and the text -----

@pytest.mark.parametrize("keys", [
    [], ["0"], ["10"], ["enter"], ["y"], ["1", "enter"], ["ctrl+c"], ["esc"], ["1 2"], [""], ["--json"], "1", None,
    [1], ["1"] * 5, [MARKER]], ids=range(16))
def test_only_the_digits_of_the_options_are_keys(keys, records):
    client, runner = client_with(done({}))
    assert client.press("t1", keys) == Failure("bad_key")
    assert runner.calls == [] and no_marker(records)


@pytest.mark.parametrize("text", [
    "a", "yes, do it", "ação é ñ 日本語 ?", "--force", "-x", "x" * TEXT_LIMIT, "  padded  ",
    "a coder \U0001F469\u200D\U0001F4BB here",  # an emoji sequence with a zero-width joiner
    "\U0001F3F4\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F",  # a flag with tag characters
    "\u2764\ufe0f ok", "\U0001F44D\U0001F3FD",
    "\U0001F3F3\ufe0f\u200d\U0001F308 flag",  # a variation selector and a joiner inside one emoji
    "keycap 1\ufe0f\u20e3", "\U0001F468\U0001F3FD\u200d\U0001F4BB", "\u2764\ufe0f\u200d\U0001F525"])
def test_a_text_of_one_line_is_valid(text):
    assert valid_text(text) and text_problem(text) == ""


@pytest.mark.parametrize("text,problem", [
    ("", "text_empty"), ("   ", "text_empty"), (None, "text_empty"), (5, "text_empty"), (b"bytes", "text_empty"),
    ("x" * (TEXT_LIMIT + 1), "text_long"),
    ("two\nlines", "text_lines"), ("a\rb", "text_lines"), ("sep\u2028line", "text_lines"), ("p\u2029q", "text_lines"),
    ("a\x85b", "text_lines"), ("a\vb", "text_lines"),
    ("tab\there", "text_control"), ("bell\x07", "text_control"), ("esc\x1b[2J", "text_control"),
    ("paste end\x1b[201~", "text_control"), ("nul\x00", "text_control"), ("\x7f", "text_control"),
    ("c1\x9b", "text_control"), ("rm \u202eexe.txt", "text_control"), ("a\u2066b\u2069", "text_control"),
    ("a\u200fb", "text_control"),
    # Invisible characters that a model can read and a person cannot see: tag characters out of a flag, the language
    # tag, the zero-width space, the soft hyphen, the word joiner, and a joiner or a variation selector out of an emoji.
    ("ok\U000E0069\U000E0067\U000E006E\U000E006F\U000E0072\U000E0065", "text_control"),
    ("\U0001F3F4\U000E0069\U000E0067\U000E006E\U000E006F\U000E0072\U000E0065\U000E0020\U000E0061\U000E007F",
     "text_control"),  # a black flag with a long tag text
    ("\U0001F3F4\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074", "text_control"),  # no cancel tag at the end
    ("\U000E0001\U000E0065\U000E006E", "text_control"), ("a\u200bb", "text_control"), ("a\u00adb", "text_control"),
    ("a\u2060b", "text_control"), ("\ufeffa", "text_control"), ("a\u200db", "text_control"),
    ("\u200d\U0001F4BB", "text_control"), ("a\ufe0f", "text_control"), ("x\ufe00", "text_control"),
    ("\U0001F469\u200d", "text_control")])
def test_an_empty_long_or_control_text_is_not_valid(text, problem, records):
    assert not valid_text(text) and text_problem(text) == problem
    client, runner = client_with(done({}))
    assert client.send_text("t1", text) == Failure("bad_text")
    assert runner.calls == [] and runner.gets == []


# ----- errors are values, and no text of the screen is in a log -----

FAILURES = [
    (subprocess.TimeoutExpired(["x"], 2.0, output=MARKER.encode(), stderr=MARKER.encode()), "timeout"),
    (FileNotFoundError(MARKER), "no_run"),
    (PermissionError(MARKER), "no_run"),
    (subprocess.SubprocessError(MARKER), "no_run"),
    (done(MARKER.encode(), 3, json.dumps({"error": {"kind": "not_found", "message": MARKER}}).encode()),
     "herdr_not_found"),
    (done(MARKER.encode(), 3, json.dumps({"error": {"kind": "finished", "message": MARKER}}).encode()),
     "herdr_finished"),
    (done(MARKER.encode(), 1, MARKER.encode()), "exit_1"),
    (done(MARKER.encode(), 2, json.dumps({"error": {"kind": MARKER}}).encode()), "exit_2"),
    (done(MARKER.encode(), 2, json.dumps({"error": MARKER}).encode()), "exit_2"),
    (done(MARKER.encode(), 2, b"\xff\xfe not text"), "exit_2"),
]


@pytest.mark.parametrize("answer,code", FAILURES, ids=[f"{n}-{code}" for n, (_, code) in enumerate(FAILURES)])
def test_a_failed_command_is_a_value_with_a_reason_code_and_no_output_in_the_log(answer, code, records):
    for call in (lambda c: c.read_screen("t1"), lambda c: c.press("t1", ["1"]), lambda c: c.send_text("t1", "text")):
        client, runner = client_with(answer)
        records.clear()
        assert call(client) == Failure(code)
        assert len(runner.calls) == 1
        assert records and no_marker(records)
        assert any(f"code={code}" in record.getMessage() and "terminal=t1" in record.getMessage() for record in records)


@pytest.mark.parametrize("stdout", [
    b"", MARKER.encode(), b"[]", json.dumps({"text": MARKER}).encode(), json.dumps({"complete": True}).encode(),
    json.dumps({"complete": "yes", "text": MARKER}).encode(), json.dumps({"complete": True, "text": 5}).encode(),
    json.dumps({"complete": True, "text": [MARKER]}).encode(), b"\xff\xfe"], ids=range(9))
def test_a_read_reply_that_is_not_the_known_shape_is_a_value(stdout, records):
    client, _ = client_with(done(stdout))
    assert client.read_screen("t1") == Failure("bad_reply")
    assert records and no_marker(records)


def test_a_good_read_logs_nothing_of_the_screen(records):
    client, _ = client_with(done({"complete": True, "text": MARKER}))
    assert client.read_screen("t1") == Screen(MARKER, True)
    assert no_marker(records)


def test_a_press_and_a_send_log_the_address_and_the_keys_only(records):
    client, _ = client_with(done({"status": "blocked"}))
    records.clear()
    client.press("t1", ["2"])
    client.send_text("t1", MARKER)
    assert [record.getMessage() for record in records] == ["screen keys ok terminal=t1 keys=2", "screen send ok terminal=t1"]


def test_without_herdr_core_the_calls_are_values():
    client, runner = client_with(done({}), core=None, listed=False)
    client._known = frozenset({"t1"})
    assert client.read_screen("t1") == Failure("no_core")
    assert client.press("t1", ["1"]) == Failure("no_core")
    assert client.send_text("t1", "x") == Failure("no_core")
    assert runner.calls == []


# ----- a text that is held can be cancelled: its command is killed -----

class Process:
    """A fake Popen: it runs until `ends` (a number of polls) or forever, and records the kill and the wait."""

    def __init__(self, ends=None, returncode=0, stdout=b"{}", stderr=b""):
        self.ends, self.returncode, self.out, self.err = ends, returncode, stdout, stderr
        self.polls = 0
        self.killed = self.waited = False
        self.stdout = self.stderr = SimpleNamespace(close=lambda: None)

    def communicate(self, timeout=None):
        self.polls += 1
        if self.ends is None or self.polls < self.ends:
            raise subprocess.TimeoutExpired(["x"], timeout)
        return self.out, self.err

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.waited = True
        return -9


def cancellable_client(process, clock=None):
    runner = Runner(done({}))
    spawned = []
    client = HerdrClient(None, CORE, run=runner, spawn=lambda argv: spawned.append(argv) or process,
                         **({"clock": clock} if clock else {}))
    client.list_agents()
    return client, runner, spawned


def test_a_text_with_a_cancel_runs_as_a_process_that_is_watched():
    process = Process(ends=3)
    client, runner, spawned = cancellable_client(process)
    assert client.send_text("t1", "made-up text", cancel=threading.Event()) is None
    assert spawned == [["env", "-u", "HC_TERMINAL_ID", "-u", "HC_SCOPE", "-u", "HC_TERMINAL_SOCKET",
                        CORE, "send", "--force", "--", "t1", "made-up text"]]
    assert runner.gets == [([CORE, "get", "t1", "--json"], READ_TIMEOUT)] and not process.killed


def test_a_platform_that_gives_an_environment_runs_the_command_as_it_is_in_that_environment(monkeypatch):
    """A system with no `env` program (macOS, Windows): the platform gives the argv unchanged and an environment
    without the caller variables. The client gives it to the runner and to the process (with a cancel)."""
    made_up = {"PATH": "/made/up", "HOME": "/made/up/home"}
    asked = []

    def clean_environment(argv, names, commands):
        asked.append((list(argv), tuple(names), commands))
        return list(argv), dict(made_up)

    monkeypatch.setattr(client_module, "platform", SimpleNamespace(COMMANDS={}, clean_environment=clean_environment))
    calls = []
    runner = Runner(done({}))

    def run(argv, timeout=2.0, **options):
        calls.append((argv, options))
        return runner(argv, timeout)

    spawned = []
    process = Process(ends=1)
    client = HerdrClient(None, CORE, run=run, spawn=lambda argv, **options: spawned.append((argv, options)) or process)
    client.list_agents()
    assert client.send_text("t1", "made-up text") is None
    assert client.send_text("t1", "made-up text", cancel=threading.Event()) is None
    argv = [CORE, "send", "--force", "--", "t1", "made-up text"]
    assert asked == [(argv, ("HC_TERMINAL_ID", "HC_SCOPE", "HC_TERMINAL_SOCKET"), {})] * 2
    assert [call for call in calls if call[0][1] == "send"] == [(argv, {"env": made_up})]
    assert [call for call in calls if call[0][1] != "send"] == [([CORE, "ls", "--json"], {}),
                                                                  ([CORE, "get", "t1", "--json"], {}),
                                                                  ([CORE, "get", "t1", "--json"], {})]
    assert spawned == [(argv, {"env": made_up})]


def test_a_text_whose_cancel_is_set_is_killed_and_ends_after_the_process(records):
    """A held `send` that is killed is not typed (measured). The call returns only when the process has ended."""
    process = Process()
    cancel = threading.Event()
    client, _, _ = cancellable_client(process)
    original = process.communicate

    def communicate(timeout=None):
        if process.polls == 2:
            cancel.set()
        return original(timeout)

    process.communicate = communicate
    assert client.send_text("t1", MARKER, cancel=cancel) == Failure("cancelled")
    assert process.killed and process.waited
    assert no_marker(records)


def test_a_cancel_that_is_set_before_the_text_runs_nothing():
    process = Process(ends=1)
    cancel = threading.Event()
    cancel.set()
    client, runner, spawned = cancellable_client(process)
    assert client.send_text("t1", "text", cancel=cancel) == Failure("cancelled")
    assert spawned == [] and runner.calls == []


def test_a_watched_text_past_its_deadline_is_killed_with_the_timeout_code():
    now = [0.0]
    process = Process()

    def communicate(timeout=None):
        now[0] += 20.0
        raise subprocess.TimeoutExpired(["x"], timeout)

    process.communicate = communicate
    client, _, _ = cancellable_client(process, clock=lambda: now[0])
    assert client.send_text("t1", "text", cancel=threading.Event()) == Failure("timeout")
    assert process.killed and process.waited and SEND_TIMEOUT <= now[0] <= SEND_TIMEOUT + 20.0


def test_a_watched_text_that_herdr_refuses_has_the_error_kind():
    process = Process(ends=1, returncode=3, stdout=MARKER.encode(),
                      stderr=json.dumps({"error": {"kind": "not_found", "message": MARKER}}).encode())
    client, _, _ = cancellable_client(process)
    assert client.send_text("t1", "text", cancel=threading.Event()) == Failure("herdr_not_found")


@pytest.mark.skipif(sys.platform == "win32", reason="a POSIX shell script as herdr-core")
def test_a_real_process_is_killed_and_gone_when_the_call_returns(tmp_path):
    """With a real child process (a shell script in the place of herdr-core, not herdr-core): the cancel kills it,
    and the call returns after it ended."""
    script = tmp_path / "fake-core"
    pid_file = tmp_path / "pid"
    script.write_text(f"#!/bin/sh\necho $$ > {pid_file}\nexec sleep 30\n")
    script.chmod(0o755)
    runner = Runner(done({}))
    client = HerdrClient(None, str(script), run=runner)
    client._known = frozenset({"t1"})
    cancel = threading.Event()
    timer = threading.Timer(0.3, cancel.set)
    timer.start()
    began = time.monotonic()
    assert client.send_text("t1", "text", cancel=cancel) == Failure("cancelled")
    assert time.monotonic() - began < 3.0
    pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


# ----- a `keys` command is never killed: a killed `keys` still delivers, so a kill only loses the proof -----

class SlowProcess:
    """A fake Popen that does not end before the deadline. `end(returncode, stderr)` ends it."""

    def __init__(self):
        self.returncode = None
        self.killed = False
        self.stderr_bytes = b""
        self.ended = threading.Event()
        self.timeouts = []

    def communicate(self, timeout=None):
        self.timeouts.append(timeout)
        if timeout is not None:
            raise subprocess.TimeoutExpired(["x"], timeout)
        assert self.ended.wait(5)
        return MARKER.encode(), self.stderr_bytes

    def kill(self):
        self.killed = True

    def end(self, returncode, stderr=b""):
        self.returncode, self.stderr_bytes = returncode, stderr
        self.ended.set()


def slow_press(records=None):
    process = SlowProcess()
    client, _, spawned = cancellable_client(process)
    ends = []
    told = threading.Event()
    assert client.press("t1", ["2"], late=lambda failure: (ends.append(failure), told.set())) == Failure("timeout")
    assert spawned == [[CORE, "keys", "t1", "2"]] and process.timeouts[0] == PRESS_TIMEOUT
    assert not process.killed and ends == []
    return process, ends, told


def test_a_key_command_past_its_deadline_is_not_killed_and_its_good_end_is_told():
    process, ends, told = slow_press()
    process.end(0)
    assert told.wait(5) and ends == [None] and not process.killed


def test_a_key_command_that_ends_with_an_error_after_its_deadline_tells_the_code(records):
    process, ends, told = slow_press()
    process.end(3, json.dumps({"error": {"kind": "not_found", "message": MARKER}}).encode())
    assert told.wait(5) and ends == [Failure("herdr_not_found")] and no_marker(records)
    process, ends, told = slow_press()
    process.end(2, MARKER.encode())
    assert told.wait(5) and ends == [Failure("exit_2")]


def test_a_key_command_that_a_signal_ended_is_lost_and_not_a_proof():
    """A killed `keys` still delivers (measured): its end by a signal says nothing."""
    process, ends, told = slow_press()
    process.end(-9)
    assert told.wait(5) and ends == [Failure("lost")]


def test_a_key_command_with_no_listener_runs_on_too():
    process = SlowProcess()
    client, _, _ = cancellable_client(process)
    assert client.press("t1", ["2"]) == Failure("timeout") and not process.killed
    process.end(0)


@pytest.mark.skipif(sys.platform == "win32", reason="a POSIX shell script as herdr-core")
def test_a_real_key_process_lives_past_the_deadline_and_is_reaped(tmp_path, monkeypatch):
    """With a real child process (a shell script in the place of herdr-core): the call returns at the deadline, the
    process runs on, and its end is told."""
    monkeypatch.setattr("bellwether.client.PRESS_TIMEOUT", 0.2)
    script = tmp_path / "fake-core"
    script.write_text("#!/bin/sh\nsleep 0.8\nexit 0\n")
    script.chmod(0o755)
    client = HerdrClient(None, str(script), run=Runner(done({})))
    client._known = frozenset({"t1"})
    ends = []
    told = threading.Event()
    began = time.monotonic()
    assert client.press("t1", ["1"], late=lambda failure: (ends.append(failure), told.set())) == Failure("timeout")
    assert time.monotonic() - began < 0.7
    assert told.wait(5) and ends == [None] and time.monotonic() - began >= 0.7


# ----- the processes of one terminal, for the model and session-time line (task 26) -----

def terminal_client(names=None):
    runner = Runner(names=names)
    client = HerdrClient(None, CORE, run=runner)
    client.list_agents()
    return client, runner


def test_terminal_gives_the_processes_and_the_creation_time_with_one_get(caplog):
    from bellwether.client import Terminal
    caplog.set_level(logging.INFO, logger="bellwether")
    answer = {"address": "t1", "pid": 600, "created_ms": 1795015110521, "title": MARKER, "cwd": MARKER,
              "foreground": {"pid": 700, "name": "claude", "argv": [MARKER]}}
    client, runner = terminal_client({"t1": done(answer)})
    del caplog.records[:]
    found = client.terminal("t1")
    # The title is the name that a row shows when Herdr has no name: it is kept, but not in the text form.
    assert found == Terminal(600, 700, 1795015110521, MARKER)
    assert runner.gets == [([CORE, "get", "t1", "--json"], READ_TIMEOUT)] and runner.calls == []
    assert caplog.records == [] and MARKER not in repr(found)


@pytest.mark.parametrize("answer, expected", [
    ({"address": "t1"}, (0, 0, 0)),
    ({"address": "t1", "pid": "600", "created_ms": 1.5, "foreground": {"pid": True}}, (0, 0, 0)),
    ({"address": "t1", "pid": -4, "created_ms": 2 ** 60, "foreground": [700]}, (0, 0, 0)),
    ({"address": "t1", "pid": 600, "foreground": None}, (600, 0, 0)),
])
def test_terminal_takes_only_positive_whole_numbers(answer, expected):
    from bellwether.client import Terminal
    client, _ = terminal_client({"t1": done(answer)})
    assert client.terminal("t1") == Terminal(*expected)


@pytest.mark.parametrize("title, expected", [
    ("Made-up task", "Made-up task"),
    ("  two\nlines\tand \x1b[31m a mark\x07  ", "two lines and [31m a mark"),
    ("x" * 300, "x" * 80),
    ("", ""), (None, ""), (7, ""), (["a"], ""),
])
def test_terminal_gives_the_title_as_one_short_line_of_text(title, expected):
    client, _ = terminal_client({"t1": done({"address": "t1", "title": title})})
    assert client.terminal("t1").title == expected


@pytest.mark.parametrize("address, names, code", [
    ("t1; rm", None, "bad_address"),
    ("t9", None, "unknown_terminal"),
    ("t1", {"t1": "t5"}, "not_this_terminal"),
    ("t1", {"t1": done(b"not json " + MARKER.encode())}, "bad_answer"),
    ("t1", {"t1": done(b"[1]")}, "not_this_terminal"),
    ("t1", {"t1": subprocess.TimeoutExpired("x", 2)}, "timeout"),
    ("t1", {"t1": OSError(MARKER)}, "no_run"),
    ("t1", {"t1": done(MARKER.encode(), returncode=1, stderr=MARKER.encode())}, "exit_1"),
])
def test_terminal_fails_with_a_reason_code_and_no_log_line(caplog, address, names, code):
    caplog.set_level(logging.INFO, logger="bellwether")
    client, runner = terminal_client(names)
    del caplog.records[:]
    assert client.terminal(address) == Failure(code)
    assert caplog.records == [] and runner.calls == []
    assert len(runner.gets) == (0 if code in ("bad_address", "unknown_terminal") else 1)


def test_terminal_needs_herdr_core():
    client = HerdrClient(None, None)
    client._known = frozenset({"t1"})
    assert client.terminal("t1") == Failure("no_core")
