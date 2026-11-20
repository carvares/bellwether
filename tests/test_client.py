"""The client with a fake runner. No test starts the real herdr-app or herdr-core."""
import json
import logging
import subprocess
from types import SimpleNamespace

import pytest

from bellwether import client as client_module
from bellwether.client import HerdrClient, HerdrError, HerdrOffline, find_executables
from bellwether.state import Agent

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

    def __call__(self, argv, timeout=2.0):
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
    caplog.set_level(logging.INFO, logger="bellwether")
    client, runner = make(app=reply(APP_LIST), core=reply(CORE_LIST))
    assert client.list_agents() == [Agent("t1", "done", "reviewer", "Main", "claude-code")]
    assert client.list_agents() == [Agent("t1", "done", "reviewer", "Main", "claude-code")]
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
    assert client.list_agents() == [Agent("t1", "working", "", "", "claude-code")]
    assert runner.calls == [[APP, "ls"], [CORE, "ls", "--json"]]


@pytest.mark.parametrize("core_answer", [reply(b"", returncode=1), TIMEOUT, reply(b"{"), reply({"terminals": None})])
def test_list_is_offline_when_the_app_and_the_core_do_not_answer(core_answer):
    client, _ = make(app=APP_DOWN, core=core_answer)
    with pytest.raises(HerdrOffline):
        client.list_agents()


def test_an_executable_that_was_not_found_is_not_run():
    runner = FakeRunner(core=reply(CORE_LIST))
    assert HerdrClient(None, CORE, run=runner).list_agents() == [Agent("t1", "working", "", "", "claude-code")]
    assert runner.calls == [[CORE, "ls", "--json"]]
    runner = FakeRunner()
    with pytest.raises(HerdrOffline):
        HerdrClient(None, None, run=runner).list_agents()
    assert runner.calls == []


def test_source_change_is_logged_one_time_for_each_change(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    client, runner = make(app=reply(APP_LIST), core=reply(CORE_LIST))
    client.list_agents()
    runner.answers[APP] = APP_DOWN
    client.list_agents()
    client.list_agents()
    runner.answers[CORE] = TIMEOUT
    with pytest.raises(HerdrOffline):
        client.list_agents()
    assert [r.getMessage() for r in caplog.records] == ["source: app", "source: core", "source: none"]


# ----- one read of the app that fails does not change the source -----

APP_AGENTS = [Agent("t1", "done", "reviewer", "Main", "claude-code")]
CORE_AGENTS = [Agent("t1", "working", "", "", "claude-code")]


def test_one_failed_read_of_the_app_keeps_the_last_list_and_the_source(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    client, runner = make(app=reply(APP_LIST), core=reply(CORE_LIST))
    assert client.list_agents() == APP_AGENTS
    runner.answers[APP] = APP_DOWN
    assert client.list_agents() == APP_AGENTS  # the last good list: not the core, not offline
    runner.answers[APP] = reply(APP_LIST)
    assert client.list_agents() == APP_AGENTS
    assert runner.calls == [[APP, "ls"]] * 3  # no read of the core
    assert [r.getMessage() for r in caplog.records] == ["source: app"]  # no line for the one failure


def test_two_failed_reads_of_the_app_one_after_the_other_change_the_source_to_the_core(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    client, runner = make(app=reply(APP_LIST), core=reply(CORE_LIST))
    client.list_agents()
    runner.answers[APP] = TIMEOUT
    assert client.list_agents() == APP_AGENTS
    assert client.list_agents() == CORE_AGENTS
    assert client.list_agents() == CORE_AGENTS  # the app is asked first each time, and the core answers
    assert runner.calls == [[APP, "ls"], [APP, "ls"], [APP, "ls"], [CORE, "ls", "--json"], [APP, "ls"], [CORE, "ls", "--json"]]
    assert [r.getMessage() for r in caplog.records] == ["source: app", "source: core"]


def test_the_app_is_the_source_again_at_its_first_answer_and_the_count_of_failures_starts_again(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    client, runner = make(app=reply(APP_LIST), core=reply(CORE_LIST))
    client.list_agents()
    runner.answers[APP] = APP_DOWN
    client.list_agents()
    assert client.list_agents() == CORE_AGENTS
    renamed = json.loads(json.dumps(APP_LIST))
    renamed["spaces"][0]["tabs"][0]["terminals"][0]["name"] = "builder"
    runner.answers[APP] = reply(renamed)
    new_list = [Agent("t1", "done", "builder", "Main", "claude-code")]
    assert client.list_agents() == new_list  # recovery at the first answer
    del runner.calls[:]
    for _ in range(3):  # a failure, an answer, a failure: never two failures one after the other
        runner.answers[APP] = APP_DOWN
        assert client.list_agents() == new_list  # the last good list is the new one
        runner.answers[APP] = reply(renamed)
        assert client.list_agents() == new_list
    assert runner.calls == [[APP, "ls"]] * 6
    assert [r.getMessage() for r in caplog.records] == ["source: app", "source: core", "source: app"]


def test_with_no_list_of_the_app_yet_the_first_failed_read_goes_to_the_core(caplog):
    """At the start with the app window closed: the widget is not offline for one read."""
    caplog.set_level(logging.INFO, logger="bellwether")
    client, runner = make(app=APP_DOWN, core=reply(CORE_LIST))
    assert client.list_agents() == CORE_AGENTS
    assert runner.calls == [[APP, "ls"], [CORE, "ls", "--json"]]
    assert [r.getMessage() for r in caplog.records] == ["source: core"]


def test_the_last_list_of_the_app_is_a_copy_that_the_caller_cannot_change():
    client, runner = make(app=reply(APP_LIST), core=reply(CORE_LIST))
    client.list_agents().clear()
    runner.answers[APP] = APP_DOWN
    assert client.list_agents() == APP_AGENTS


# ----- the jump: show the agent, start the app when it is closed, bring the window to the front -----

BUSCTL = "/fake/busctl"
SYSTEMD_RUN = "/fake/systemd-run"
WINDOW = "{11111111-2222-3333-4444-555555555555}"
FOCUS_T1 = [APP, "do", "agent.focus", '{"terminal": "t1"}']
START = [SYSTEMD_RUN, "--user", "--quiet", "--collect", "--slice=app.slice", "--", APP]


class Desk:
    """A fake desktop: the app, its window as KWin reports it, and the launcher. It records every command."""

    def __init__(self, running=True, minimized=False, window_class="herdr-app", launcher_exit=0,
                 answers_after=2, raise_works=True, focus_answer=None, busctl_error=None,
                 not_ready=0, others_first=(), no_window=False, hang=(), cost=0.0,
                 clock_at=None, tick=0.0, match_reply=None):
        self.running = running
        self.minimized = minimized
        self.window_class = window_class
        self.launcher_exit = launcher_exit
        self.answers_after = answers_after  # number of `ls` calls after the start until the app answers
        self.raise_works = raise_works
        self.focus_answer = focus_answer
        self.busctl_error = busctl_error
        self.not_ready = not_ready  # number of agent.focus calls that a new window refuses: no terminals yet
        self.others_first = others_first  # classes of windows that KWin lists before the app window
        self.no_window = no_window
        self.hang = hang  # names of commands (see names()) that use their full timeout and give no answer
        self.cost = cost  # seconds that each command takes
        self.clock_at = dict(clock_at or {})  # {command name: time}: the clock is at that time after its first run
        self.tick = tick  # seconds that the clock moves at each read
        self.match_reply = match_reply  # the reply of KWin to "Match", when it must have a different shape
        self.started = False
        self.now = 0.0  # the clock of this desktop: commands and sleeps move it
        self.calls = []
        self.timeouts = []
        self.sleeps = []

    def names(self):
        """The commands in a short form: one word for each call."""
        return [c[1] if c[0] == APP else "start" if c[0] == SYSTEMD_RUN else c[7] for c in self.calls]

    def clock(self):
        self.now += self.tick
        return self.now

    def sleep(self, seconds):
        if seconds < 0:
            raise ValueError("sleep length must be non-negative")  # as time.sleep does
        self.sleeps.append(seconds)
        assert len(self.sleeps) <= 100, "the jump does not end: more than 100 pauses"
        self.now += seconds

    def __call__(self, argv, timeout=2.0):
        self.calls.append(argv)
        self.timeouts.append(timeout)
        assert len(self.calls) <= 100, "the jump does not end: more than 100 commands"
        assert 0 < timeout <= 2.0
        if self.hang == "all" or self.names()[-1] in self.hang or self.cost > timeout:
            self.now += timeout  # the real runner stops a command at its timeout
            raise subprocess.TimeoutExpired(cmd="x", timeout=timeout)
        self.now = max(self.now + self.cost, self.clock_at.pop(self.names()[-1], 0.0))
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
        self.not_ready -= 1
        if json.loads(argv[3])["terminal"] == "t1" and self.not_ready < 0:
            return reply(b"null\n")
        return reply({"error": 'no running terminal "t9"'}, returncode=1)

    def _kwin(self, argv):
        if self.busctl_error:
            raise self.busctl_error
        assert argv[1:5] == ["--user", "--json=short", "call", "org.kde.KWin"]
        method, arguments = argv[7], argv[9:]
        if method == "Match":
            assert arguments == ["herdr-app"]
            if self.match_reply is not None:
                return reply(self.match_reply)
            rows = [["0_" + WINDOW, "a caption", "icon", 100, 0.8, {}]] if self.running and not self.no_window else []
            others = [[f"0_{{other-{n}}}", "herdr-app in a caption", "icon", 100, 0.8, {}] for n in range(len(self.others_first))]
            return reply({"type": "a(sssuda{sv})", "data": [others + rows]})
        if method == "getWindowInfo" and arguments != [WINDOW]:
            kind = self.others_first[int(arguments[0][7:-1])]
            if kind is None:
                return reply(b"", returncode=1)  # KWin does not know this window
            return reply({"type": "a{sv}", "data": [{"resourceClass": {"type": "s", "data": kind}}]})
        if method == "getWindowInfo":
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
    client = HerdrClient(APP, CORE, run=desk, sleep=desk.sleep, clock=desk.clock,
                         busctl=BUSCTL, systemd_run=SYSTEMD_RUN)
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


def test_focus_waits_for_the_terminals_of_a_window_that_just_started():
    client, desk = jump(running=False, answers_after=1, not_ready=2)
    client.focus_agent("t1")
    assert desk.names() == ["ls", "start", "ls", "do", "do", "do", "Match", "getWindowInfo", "Run", "getWindowInfo"]
    assert desk.sleeps == [0.25, 0.25, 0.25]


def test_focus_says_agent_is_gone_when_a_new_window_never_has_the_terminal():
    client, desk = jump(running=False, answers_after=1, not_ready=10_000)
    with pytest.raises(HerdrError) as failure:
        client.focus_agent("t1")
    assert failure.value.code == "agent_gone"
    assert desk.names().count("do") == 8 and "Run" not in desk.names()
    assert sum(desk.sleeps) == pytest.approx(0.25 + 7 * 0.25)


def test_focus_fails_when_the_launcher_fails():
    for options in ({"launcher_exit": 1}, {"launcher_exit": 0, "answers_after": 10_000}):
        client, desk = jump(running=False, **options)
        with pytest.raises(HerdrError) as failure:
            client.focus_agent("t1")
        assert (failure.value.code, failure.value.message) == ("no_start", "Herdr app did not start")
        assert desk.names().count("start") == 1
        assert "do" not in desk.names() and "Run" not in desk.names()
    assert sum(desk.sleeps) == pytest.approx(8.0)  # the wait for an app that starts but does not answer
    assert desk.now == pytest.approx(8.0)


def test_a_jump_where_every_command_hangs_ends_with_the_right_error():
    client, desk = jump(hang="all")
    with pytest.raises(HerdrError) as failure:
        client.focus_agent("t1")
    assert failure.value.code == "no_start"  # `ls` and then the launcher gave no answer
    assert desk.names() == ["ls", "start"] and desk.now == pytest.approx(4.0)


@pytest.mark.parametrize(
    "options, code, error",
    [
        # The app is closed and, after the launch, `ls` never answers: each try uses its timeout.
        ({"running": False, "answers_after": 10_000, "cost": 0.75}, "no_start", HerdrError),
        ({"running": False, "hang": ("ls",)}, "no_start", HerdrError),
        # The new window never has the terminal, and each command is slow.
        ({"running": False, "answers_after": 1, "not_ready": 10_000, "cost": 0.9}, "agent_gone", HerdrError),
        # The agent shows, then KWin and the launcher give no answer.
        ({"hang": ("Match", "start")}, "no_raise", HerdrError),
        ({"cost": 1.9, "minimized": True, "raise_works": False, "launcher_exit": 1}, "no_raise", HerdrError),
        # The command that shows the agent gives no answer.
        ({"hang": ("do",)}, None, HerdrOffline),
        ({"running": False, "answers_after": 1, "cost": 1.5, "hang": ("do",)}, None, HerdrOffline),
    ],
)
def test_a_jump_ends_at_its_deadline_with_the_error_of_the_step_in_progress(options, code, error):
    client, desk = jump(**options)
    with pytest.raises(error) as failure:
        client.focus_agent("t1")
    assert getattr(failure.value, "code", None) == code
    assert desk.now <= 8.0 + 1e-9  # no command and no pause goes past the deadline
    assert len(desk.calls) <= 34  # 8 s of tries each 0.25 s, the first `ls` and the launch
    assert all(0 < t <= 2.0 for t in desk.timeouts)


@pytest.mark.parametrize(
    "options, code",
    [
        # The launch ends 0.05 s before the deadline: the pause of the wait for the app is cut to 0.05 s.
        ({"running": False, "answers_after": 10_000, "clock_at": {"start": 7.95}}, "no_start"),
        # The new window refuses the agent 0.05 s before the deadline: the pause before the next try is cut.
        ({"running": False, "answers_after": 1, "not_ready": 10_000, "clock_at": {"do": 7.95}}, "agent_gone"),
    ],
)
def test_a_pause_that_is_longer_than_the_time_left_is_cut_at_the_deadline(options, code):
    client, desk = jump(**options)
    with pytest.raises(HerdrError) as failure:
        client.focus_agent("t1")
    assert failure.value.code == code
    assert desk.sleeps[-1] == pytest.approx(0.05)
    assert desk.now == pytest.approx(8.0) and desk.now <= 8.0 + 1e-9


@pytest.mark.parametrize(
    "options, code",
    [
        ({"running": False, "answers_after": 10_000, "clock_at": {"start": 8.0}}, "no_start"),
        ({"running": False, "answers_after": 1, "not_ready": 10_000, "clock_at": {"do": 8.0}}, "agent_gone"),
    ],
)
def test_a_step_that_ends_at_the_deadline_has_no_pause_and_no_command_after_it(options, code):
    client, desk = jump(**options)
    with pytest.raises(HerdrError) as failure:
        client.focus_agent("t1")
    assert failure.value.code == code
    calls = len(desk.calls)
    assert desk.now == pytest.approx(8.0) and all(pause > 0 for pause in desk.sleeps)
    assert desk.names()[calls - 1] in ("start", "do")  # the step at the deadline was the last command


@pytest.mark.parametrize(
    "options, code",
    [
        ({"running": False, "answers_after": 10_000, "clock_at": {"start": 7.999}}, "no_start"),
        ({"running": False, "answers_after": 1, "not_ready": 10_000, "clock_at": {"do": 7.999}}, "agent_gone"),
    ],
)
def test_a_deadline_that_falls_between_two_reads_of_the_clock_gives_no_negative_pause(options, code):
    # The clock moves 4 ms at each read, so the deadline is at 8.004: one read is before it and the next is after it.
    client, desk = jump(tick=0.004, **options)
    with pytest.raises(HerdrError) as failure:
        client.focus_agent("t1")
    assert failure.value.code == code


@pytest.mark.parametrize("data", [[None], [7], None, [], {"x": 1}, [[None]], [[7]]])
def test_focus_asks_the_app_when_the_reply_of_kwin_has_a_different_shape(data):
    client, desk = jump(match_reply={"type": "?", "data": data})
    client.focus_agent("t1")
    assert desk.calls[-1] == START  # plain `herdr-app` raises the window


def test_a_command_near_the_deadline_gets_only_the_time_that_is_left():
    client, desk = jump(running=False, answers_after=10_000, cost=0.7)
    with pytest.raises(HerdrError):
        client.focus_agent("t1")
    assert desk.timeouts[0] == 2.0
    assert desk.timeouts[-1] < 0.7  # less than the command needs: only the time that was left
    assert desk.now == pytest.approx(8.0)


def test_a_slow_start_that_ends_before_the_deadline_is_a_good_jump():
    client, desk = jump(running=False, minimized=True, answers_after=3, not_ready=2, cost=0.5)
    client.focus_agent("t1")
    assert desk.minimized is False
    assert 6.0 < desk.now <= 8.0
    assert desk.names().count("start") == 1


def test_focus_raises_the_app_window_when_kwin_lists_other_windows_first():
    # A caption that holds "herdr-app", a window that KWin does not know any more, then the app window.
    client, desk = jump(minimized=True, others_first=("konsole", None, "herdr-app-helper"))
    client.focus_agent("t1")
    assert desk.minimized is False
    runs = [c[9:] for c in desk.calls if c[0] == BUSCTL and c[7] == "Run"]
    assert runs == [["0_" + WINDOW, ""]]  # only the app window was activated
    assert "start" not in desk.names()


def test_focus_asks_the_app_when_kwin_finds_no_window():
    client, desk = jump(no_window=True)
    client.focus_agent("t1")
    assert desk.names() == ["ls", "do", "Match", "start"]
    assert desk.calls[-1] == START


def test_focus_fails_when_the_launcher_is_not_found():
    client, desk = jump(running=False)
    client._systemd_run = "/fake/herdr-app-missing"
    desk_call = desk.__call__

    def run(argv, timeout=2.0):
        if argv[0] == "/fake/herdr-app-missing":
            raise FileNotFoundError(argv[0])
        return desk_call(argv, timeout)

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
def test_focus_asks_the_app_to_raise_its_window_when_kwin_did_not(options):
    client, desk = jump(**options)
    client.focus_agent("t1")
    assert FOCUS_T1 in desk.calls
    assert desk.calls[-1] == START  # plain `herdr-app` opens or raises the window
    if options.get("window_class"):
        assert "Run" not in desk.names()  # a window of a different class is not touched


def test_focus_says_when_the_window_was_not_raised():
    client, desk = jump(busctl_error=TIMEOUT, launcher_exit=1)
    with pytest.raises(HerdrError) as failure:
        client.focus_agent("t1")
    assert (failure.value.code, failure.value.message) == ("no_raise", "could not raise the window")
    assert desk.names() == ["ls", "do", "Match", "start"]  # the agent is shown before the raise


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
    client = HerdrClient(None, CORE, run=desk, sleep=desk.sleep, clock=lambda: desk.now,
                         busctl=BUSCTL, systemd_run=SYSTEMD_RUN)
    with pytest.raises(HerdrError) as failure:
        client.focus_agent("t1")
    assert (failure.value.code, failure.value.message) == ("no_app", "Herdr app is not installed")
    assert desk.calls == []


def test_focus_logs_steps_and_exit_codes_only(caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    client, _ = jump(running=False, minimized=True)
    client.focus_agent("t1")
    client, _ = jump()
    with pytest.raises(HerdrError):
        client.focus_agent("t9")
    assert [r.getMessage() for r in caplog.records] == [
        "jump agent=t1 step=launch exit=0",
        "jump agent=t1 step=wait answered=True",
        "jump agent=t1 step=show exit=0",
        "jump agent=t1 step=raise kwin=True",
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
    client_module._run(["/fake/herdr-app", "ls"], timeout=0.5)
    assert seen["timeout"] == 0.5


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


def core_list(status, turn, where="Main / 1"):
    return {"terminals": [{"address": "t1", "agent": "claude-code", "state": "live", "status": status, "turn": turn,
                           "name": "reviewer", "where": where}]}


def app_list(status):
    data = json.loads(json.dumps(APP_LIST))
    data["spaces"][0]["tabs"][0]["terminals"][0]["status"] = status
    return data


def test_without_the_app_an_agent_keeps_its_name_its_place_and_its_idle_status():
    """The core says "done" for an agent that the app showed as idle (seen by the person)."""
    client, runner = make(app=reply(app_list("idle")), core=reply(core_list("done", 7)))
    assert client.list_agents() == [Agent("t1", "idle", "reviewer", "Main", "claude-code")]
    runner.answers[APP] = APP_DOWN
    client.list_agents()
    assert client.list_agents() == [Agent("t1", "idle", "reviewer", "Main", "claude-code")]
    runner.answers[CORE] = reply(core_list("working", 8))
    assert client.list_agents()[0].status == "working"
    runner.answers[CORE] = reply(core_list("done", 8))
    assert client.list_agents()[0].status == "done"  # a new turn ended: the person did not see it
    runner.answers[CORE] = reply(core_list("done", 8))
    assert client.list_agents()[0].status == "done"


def test_without_the_app_a_done_agent_that_the_app_showed_done_stays_done():
    client, runner = make(app=reply(app_list("done")), core=reply(core_list("done", 7)))
    client.list_agents()
    runner.answers[APP] = APP_DOWN
    client.list_agents()
    assert client.list_agents()[0].status == "done"


def test_the_idle_memory_ends_when_the_app_answers_again():
    client, runner = make(app=reply(app_list("idle")), core=reply(core_list("done", 7)))
    client.list_agents()
    runner.answers[APP] = APP_DOWN
    client.list_agents()
    assert client.list_agents()[0].status == "idle"
    runner.answers[APP] = reply(app_list("done"))
    assert client.list_agents()[0].status == "done"
    runner.answers[APP] = APP_DOWN
    client.list_agents()
    assert client.list_agents()[0].status == "done"
