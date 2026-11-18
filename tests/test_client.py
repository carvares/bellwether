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


# ----- the jump: show the agent, start the app when it is closed, bring the window to the front -----

BUSCTL = "/fake/busctl"
SYSTEMD_RUN = "/fake/systemd-run"
WINDOW = "{11111111-2222-3333-4444-555555555555}"
FOCUS_T1 = [APP, "do", "agent.focus", '{"terminal": "t1"}']
START = [SYSTEMD_RUN, "--user", "--quiet", "--collect", "--slice=app.slice", "--", APP]


class Desk:
    """A fake desktop: the app, its window as KWin reports it, and the launcher. It records every command."""

    def __init__(self, running=True, minimized=False, window_class="herdr-app", launcher_exit=0,
                 answers_after=2, raise_works=True, focus_answer=None, busctl_error=None):
        self.running = running
        self.minimized = minimized
        self.window_class = window_class
        self.launcher_exit = launcher_exit
        self.answers_after = answers_after  # number of `ls` calls after the start until the app answers
        self.raise_works = raise_works
        self.focus_answer = focus_answer
        self.busctl_error = busctl_error
        self.started = False
        self.calls = []
        self.sleeps = []

    def names(self):
        """The commands in a short form: one word for each call."""
        return [c[1] if c[0] == APP else "start" if c[0] == SYSTEMD_RUN else c[7] for c in self.calls]

    def sleep(self, seconds):
        self.sleeps.append(seconds)

    def __call__(self, argv):
        self.calls.append(argv)
        if argv[0] == SYSTEMD_RUN:
            self.started = self.launcher_exit == 0
            return reply(b"", returncode=self.launcher_exit)
        if argv[0] == BUSCTL:
            return self._kwin(argv)
        if argv[1] == "ls":
            if self.started and not self.running:
                self.answers_after -= 1
                self.running = self.answers_after <= 0
            return reply(APP_LIST) if self.running else APP_DOWN
        assert argv[1:3] == ["do", "agent.focus"]
        if isinstance(self.focus_answer, Exception):
            raise self.focus_answer
        if self.focus_answer is not None:
            return self.focus_answer
        if json.loads(argv[3])["terminal"] == "t1":
            return reply(b"null\n")
        return reply({"error": 'no running terminal "t9"'}, returncode=1)

    def _kwin(self, argv):
        if self.busctl_error:
            raise self.busctl_error
        assert argv[1:5] == ["--user", "--json=short", "call", "org.kde.KWin"]
        method, arguments = argv[7], argv[9:]
        if method == "Match":
            assert arguments == ["herdr-app"]
            rows = [["0_" + WINDOW, "a caption", "icon", 100, 0.8, {}]] if self.running else []
            return reply({"type": "a(sssuda{sv})", "data": [rows]})
        if method == "getWindowInfo":
            assert arguments == [WINDOW]
            return reply({"type": "a{sv}", "data": [{
                "resourceClass": {"type": "s", "data": self.window_class},
                "minimized": {"type": "b", "data": self.minimized},
            }]})
        assert (method, arguments) == ("Run", ["0_" + WINDOW, ""])
        if self.raise_works:
            self.minimized = False
        return reply({"type": "", "data": []})


def jump(key="t1", **desk_options):
    desk = Desk(**desk_options)
    client = HerdrClient(APP, CORE, run=desk, sleep=desk.sleep, busctl=BUSCTL, systemd_run=SYSTEMD_RUN)
    return client, desk


def test_focus_with_a_visible_window_shows_the_agent_and_raises_the_window():
    client, desk = jump()
    client.focus_agent("t1")
    assert desk.names() == ["ls", "do", "Match", "getWindowInfo", "Run", "getWindowInfo"]
    assert desk.calls[1] == FOCUS_T1
    assert desk.sleeps == []


def test_focus_with_a_minimized_window_restores_it():
    client, desk = jump(minimized=True)
    client.focus_agent("t1")
    assert desk.minimized is False
    assert "start" not in desk.names()


def test_focus_with_the_app_closed_starts_it_one_time_and_waits_for_its_answer():
    client, desk = jump(running=False, answers_after=3)
    client.focus_agent("t1")
    assert desk.names() == ["ls", "start", "ls", "ls", "ls", "do", "Match", "getWindowInfo", "Run", "getWindowInfo"]
    assert desk.calls[1] == START
    assert desk.sleeps == [0.25, 0.25, 0.25]


def test_focus_fails_when_the_launcher_fails():
    for options in ({"launcher_exit": 1}, {"launcher_exit": 0, "answers_after": 10_000}):
        client, desk = jump(running=False, **options)
        with pytest.raises(HerdrError) as failure:
            client.focus_agent("t1")
        assert (failure.value.code, failure.value.message) == ("no_start", "Herdr app did not start")
        assert desk.names().count("start") == 1
        assert "do" not in desk.names() and "Run" not in desk.names()
    assert sum(desk.sleeps) == pytest.approx(6.0)  # the wait for an app that starts but does not answer


def test_focus_fails_when_the_launcher_is_not_found():
    client, desk = jump(running=False)
    client._systemd_run = "/fake/herdr-app-missing"
    desk_call = desk.__call__

    def run(argv):
        if argv[0] == "/fake/herdr-app-missing":
            raise FileNotFoundError(argv[0])
        return desk_call(argv)

    client._run = run
    with pytest.raises(HerdrError) as failure:
        client.focus_agent("t1")
    assert failure.value.code == "no_start"


@pytest.mark.parametrize(
    "options",
    [
        {"minimized": True, "raise_works": False},
        {"window_class": "herdr-app-other"},
        {"busctl_error": FileNotFoundError("busctl")},
        {"busctl_error": TIMEOUT},
    ],
)
def test_focus_says_when_the_window_was_not_raised(options):
    client, desk = jump(**options)
    with pytest.raises(HerdrError) as failure:
        client.focus_agent("t1")
    assert (failure.value.code, failure.value.message) == ("no_raise", "could not raise the window")
    assert FOCUS_T1 in desk.calls  # the agent is shown before the raise
    if options.get("window_class"):
        assert "Run" not in desk.names()  # a window of a different class is not touched


def test_focus_says_when_the_agent_is_gone_and_does_not_raise_the_window():
    client, desk = jump()
    with pytest.raises(HerdrError) as failure:
        client.focus_agent("t9")
    assert (failure.value.code, failure.value.message) == ("agent_gone", "agent is gone")
    assert desk.names() == ["ls", "do"]


def test_focus_error_reply_is_a_herdr_error_with_a_short_code():
    client, desk = jump(focus_answer=reply({"error": "text from the app"}, returncode=1))
    with pytest.raises(HerdrError) as failure:
        client.focus_agent("t1")
    assert failure.value.code == "exit_1"
    assert "text from the app" not in str(failure.value)
    desk.focus_answer = reply({"error": "text from the app"})
    with pytest.raises(HerdrError) as failure:
        client.focus_agent("t1")
    assert failure.value.code == "error_reply"
    assert "text from the app" not in str(failure.value)


def test_focus_that_does_not_answer_is_offline():
    client, _ = jump(focus_answer=TIMEOUT)
    with pytest.raises(HerdrOffline):
        client.focus_agent("t1")


def test_focus_without_the_app_program_runs_nothing():
    desk = Desk()
    client = HerdrClient(None, CORE, run=desk, sleep=desk.sleep, busctl=BUSCTL, systemd_run=SYSTEMD_RUN)
    with pytest.raises(HerdrError) as failure:
        client.focus_agent("t1")
    assert (failure.value.code, failure.value.message) == ("no_app", "Herdr app is not installed")
    assert desk.calls == []


def test_focus_logs_steps_and_exit_codes_only(caplog):
    caplog.set_level(logging.INFO, logger="herdr_float")
    client, _ = jump(running=False, minimized=True)
    client.focus_agent("t1")
    client, _ = jump()
    with pytest.raises(HerdrError):
        client.focus_agent("t9")
    assert [r.getMessage() for r in caplog.records] == [
        "jump agent=t1 step=start exit=0",
        "jump agent=t1 step=wait answered=True",
        "jump agent=t1 step=show exit=0",
        "jump agent=t1 step=raise ok=True",
        "jump agent=t9 step=show exit=1",
    ]
    assert "caption" not in caplog.text and "no running terminal" not in caplog.text


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
