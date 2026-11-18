"""The client with a fake runner. No test starts the real herdr-app or herdr-core."""
import json
import logging
import subprocess
from types import SimpleNamespace

import pytest

from herdr_float import client as client_module
from herdr_float.client import HerdrClient, HerdrError, HerdrOffline, find_executables
from herdr_float.state import Agent

APP = "/fake/herdr-app"
CORE = "/fake/herdr-core"

APP_LIST = {
    "spaces": [
        {
            "id": "sp1",
            "name": "Main",
            "tabs": [
                {
                    "id": "tb1",
                    "name": "1",
                    "terminals": [
                        {"terminal": "t1", "pane": "p1", "status": "done", "app": "claude-code", "name": "reviewer", "sub_agents": []},
                        {"terminal": "t2", "pane": "p2", "status": None, "app": None, "name": None, "sub_agents": []},
                    ],
                }
            ],
        }
    ],
    "recent": [],
}
CORE_LIST = {
    "hidden_finished": 0,
    "terminals": [
        {"address": "t1", "agent": "claude-code", "state": "live", "status": "working"},
        {"address": "t2", "agent": "fish", "state": "live"},
    ],
}


def reply(data, returncode=0):
    stdout = data if isinstance(data, bytes) else json.dumps(data).encode()
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=b"")


class FakeRunner:
    """Answers by executable. A value that is an exception is raised."""

    def __init__(self, **answers):
        self.answers = {APP: answers.get("app"), CORE: answers.get("core")}
        self.calls = []

    def __call__(self, argv):
        self.calls.append(argv)
        answer = self.answers[argv[0]]
        if isinstance(answer, Exception):
            raise answer
        return answer


def make(**answers):
    runner = FakeRunner(**answers)
    return HerdrClient(APP, CORE, run=runner), runner


APP_DOWN = reply(b"", returncode=2)
TIMEOUT = subprocess.TimeoutExpired(cmd="x", timeout=2)


def test_list_reads_the_app(caplog):
    caplog.set_level(logging.INFO, logger="herdr_float")
    client, runner = make(app=reply(APP_LIST), core=reply(CORE_LIST))
    assert client.list_agents() == [Agent("t1", "done", "reviewer", "Main")]
    assert client.list_agents() == [Agent("t1", "done", "reviewer", "Main")]
    assert runner.calls == [[APP, "ls"], [APP, "ls"]]
    assert [r.getMessage() for r in caplog.records] == ["source: app"]


@pytest.mark.parametrize(
    "app_answer",
    [
        APP_DOWN,
        TIMEOUT,
        FileNotFoundError("gone"),
        reply(b"not json"),
        reply([1, 2]),
        reply({"spaces": "nope"}),
        reply({"error": "x"}),
    ],
)
def test_list_falls_back_to_the_core_when_the_app_does_not_answer(app_answer):
    client, runner = make(app=app_answer, core=reply(CORE_LIST))
    assert client.list_agents() == [Agent("t1", "working", "claude-code", "")]
    assert runner.calls == [[APP, "ls"], [CORE, "ls", "--json"]]


@pytest.mark.parametrize("core_answer", [reply(b"", returncode=1), TIMEOUT, reply(b"{"), reply({"terminals": None})])
def test_list_is_offline_when_the_app_and_the_core_do_not_answer(core_answer):
    client, _ = make(app=APP_DOWN, core=core_answer)
    with pytest.raises(HerdrOffline):
        client.list_agents()


def test_an_executable_that_was_not_found_is_not_run():
    runner = FakeRunner(core=reply(CORE_LIST))
    assert HerdrClient(None, CORE, run=runner).list_agents() == [Agent("t1", "working", "claude-code", "")]
    assert runner.calls == [[CORE, "ls", "--json"]]
    runner = FakeRunner()
    with pytest.raises(HerdrOffline):
        HerdrClient(None, None, run=runner).list_agents()
    assert runner.calls == []


def test_source_change_is_logged_one_time_for_each_change(caplog):
    caplog.set_level(logging.INFO, logger="herdr_float")
    client, runner = make(app=reply(APP_LIST), core=reply(CORE_LIST))
    client.list_agents()
    runner.answers[APP] = APP_DOWN
    client.list_agents()
    client.list_agents()
    runner.answers[CORE] = TIMEOUT
    with pytest.raises(HerdrOffline):
        client.list_agents()
    assert [r.getMessage() for r in caplog.records] == ["source: app", "source: core", "source: none"]


def test_focus_runs_agent_focus_with_the_terminal_address():
    client, runner = make(app=reply(APP_LIST))
    client.list_agents()
    runner.answers[APP] = reply(b"null\n")
    client.focus_agent("t1")
    assert runner.calls[-1] == [APP, "do", "agent.focus", '{"terminal": "t1"}']


def test_focus_error_reply_is_a_herdr_error_with_a_short_code():
    client, runner = make(app=reply(APP_LIST))
    client.list_agents()
    runner.answers[APP] = reply({"error": "text from the app"}, returncode=1)
    with pytest.raises(HerdrError) as failure:
        client.focus_agent("t9")
    assert failure.value.code == "exit_1"
    assert "text from the app" not in str(failure.value)
    runner.answers[APP] = reply({"error": "text from the app"})
    with pytest.raises(HerdrError) as failure:
        client.focus_agent("t9")
    assert failure.value.code == "error_reply"
    assert "text from the app" not in str(failure.value)


def test_focus_that_does_not_answer_is_offline():
    client, runner = make(app=reply(APP_LIST))
    client.list_agents()
    runner.answers[APP] = TIMEOUT
    with pytest.raises(HerdrOffline):
        client.focus_agent("t1")


def test_focus_does_not_run_a_command_when_the_app_is_not_the_source():
    client, runner = make(app=APP_DOWN, core=reply(CORE_LIST))
    with pytest.raises(HerdrError):
        client.focus_agent("t1")
    assert runner.calls == []
    client.list_agents()
    calls = list(runner.calls)
    with pytest.raises(HerdrError) as failure:
        client.focus_agent("t1")
    assert (failure.value.code, failure.value.message) == ("app_closed", "Herdr app is not open")
    assert runner.calls == calls


def test_default_runner_uses_no_shell_and_a_timeout(monkeypatch):
    seen = {}

    def fake_run(argv, **options):
        seen.update(options, argv=argv)
        return reply({})

    monkeypatch.setattr(subprocess, "run", fake_run)
    client_module._run(["/fake/herdr-app", "ls"])
    assert seen == {
        "argv": ["/fake/herdr-app", "ls"],
        "stdin": subprocess.DEVNULL,
        "capture_output": True,
        "timeout": 2.0,
    }


def test_find_executables(monkeypatch, tmp_path):
    monkeypatch.setattr(client_module.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(client_module.shutil, "which", lambda name: None)
    assert find_executables() == (None, None)
    local = tmp_path / ".local" / "bin" / "herdr-core"
    local.parent.mkdir(parents=True)
    local.write_text("")
    assert find_executables() == (None, str(local))
    monkeypatch.setattr(client_module.shutil, "which", lambda name: "/usr/bin/" + name)
    assert find_executables() == ("/usr/bin/herdr-app", "/usr/bin/herdr-core")
