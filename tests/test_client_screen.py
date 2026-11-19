"""The screen calls of the client with a fake runner: read the screen of one agent, press keys in it, send a text.
No test starts the real herdr-core. MARKER stands for the private text of a screen: it must be in no log record."""
import json
import logging
import subprocess
from types import SimpleNamespace

import pytest

from bellwether.client import (
    PRESS_TIMEOUT, READ_TIMEOUT, SEND_TIMEOUT, TEXT_LIMIT, Failure, HerdrClient, Screen, valid_address, valid_text)

CORE = "/fake/herdr-core"
MARKER = "MARKER-private-screen-text"
LIST = {"terminals": [
    {"address": "t1", "agent": "claude-code", "state": "live", "status": "blocked"},
    {"address": "t1c", "agent": "codex", "state": "live", "status": "working"},
    {"address": "box/t7", "agent": "claude-code", "state": "live", "status": "blocked"},
]}


def done(stdout=b"", returncode=0, stderr=b""):
    stdout = stdout if isinstance(stdout, bytes) else json.dumps(stdout).encode()
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class Runner:
    """Answers `ls` with LIST and every other command with `answer` (an exception is raised)."""

    def __init__(self, answer=None):
        self.answer = answer
        self.calls: list[tuple[list[str], float]] = []

    def __call__(self, argv, timeout=2.0):
        if argv[1:] == ["ls", "--json"]:
            return done(LIST)
        self.calls.append((argv, timeout))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def client_with(answer=None, core=CORE, listed=True) -> tuple[HerdrClient, Runner]:
    runner = Runner(answer)
    client = HerdrClient(None, core, run=runner)
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


def test_the_deadlines_are_short():
    assert READ_TIMEOUT <= 2.0 and PRESS_TIMEOUT <= 5.0 and SEND_TIMEOUT <= 8.0


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


@pytest.mark.parametrize("text", ["a", "yes, do it", "ação é ñ 日本語 ?", "--force", "x" * TEXT_LIMIT, "  padded  "])
def test_a_text_of_one_line_is_valid(text):
    assert valid_text(text)


@pytest.mark.parametrize("text", [
    "", "   ", "two\nlines", "a\rb", "tab\there", "bell\x07", "esc\x1b[2J", "x" * (TEXT_LIMIT + 1), "nul\x00", "\x7f",
    "c1\x9b", "sep line", None, 5, b"bytes"])
def test_an_empty_long_or_control_text_is_not_valid(text, records):
    assert not valid_text(text)
    client, runner = client_with(done({}))
    assert client.send_text("t1", text) == Failure("bad_text")
    assert runner.calls == []


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
