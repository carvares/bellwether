"""The model and the session time of the agent rows in the backend: the row values, the reads that are due, the
setting `showMeta`. A fake client, made-up readers and a clock of the test: no real session file, no real time."""
import json
import logging
import time

import pytest

from bellwether.backend import Backend
from bellwether.client import Failure, Terminal
from bellwether.platform.linux import Host
from bellwether.sessions import SessionFacts, SessionWatch
from bellwether.state import Agent
from tests.test_backend import wait_for

NOW = 1_795_100_000.0  # the time of the day of the test, in seconds
STARTED = int(NOW * 1000) - (2 * 3600 + 14 * 60) * 1000  # 2 h 14 min before
CREATED = int(NOW * 1000) - 3 * 86400 * 1000 - 2 * 3600 * 1000  # 3 d 2 h before
AGENTS = [Agent("t1", "working", "rev", "Main", "claude-code"), Agent("t2", "blocked", "dev", "Main", "codex"),
          Agent("t3", "working", "", "Main", "made-up-program")]


NO_FILE = object()


class Client:
    def __init__(self):
        self.result = list(AGENTS)
        self.calls = []
        self.answer = {"t1": Terminal(10, 11, CREATED), "t2": Terminal(20, 21, CREATED), "t3": Terminal(30, 31, 0)}

    def list_agents(self):
        return list(self.result)

    def terminal(self, address):
        self.calls.append(address)
        return self.answer.get(address, Failure("herdr_not_found"))


class Desk:
    def __init__(self, tmp_path, show=NO_FILE, **more):
        self.path = tmp_path / "state.json"
        if show is not NO_FILE:
            self.path.write_text(json.dumps({"x": 5, "showMeta": show}), encoding="utf-8")
        self.client = Client()
        self.mono = 100.0
        self.now = NOW
        self.models = {"claude-code": "claude-opus-5-5", "codex": None}
        self.reads = []
        (tmp_path / "home").mkdir(exist_ok=True)
        self.watch = SessionWatch(self.client, Host(tmp_path / "home", tmp_path / "proc"), {
            "claude-code": lambda host, pids, known: self.read("claude-code", STARTED),
            "codex": lambda host, pids, known: self.read("codex", None)}, clock=lambda: self.mono)
        self.backend = Backend(self.client, settings_path=self.path, sessions=self.watch, now=lambda: self.now,
                               **more)
        self.emitted = []
        self.backend.changed.connect(lambda: self.emitted.append(1))

    def read(self, app, started):
        self.reads.append(app)
        model = self.models[app]
        return SessionFacts(model, started, "ok" if model else "no_session")

    def rows(self):
        return {row["key"]: row for group in self.backend.groups for row in group["agents"]}

    def meta(self):
        return {key: row["metaText"] for key, row in self.rows().items()}


@pytest.fixture
def desk(app, tmp_path):
    made = []

    def make(**more):
        made.append(Desk(tmp_path, **more))
        return made[-1]

    yield make
    for one in made:
        one.backend.stop()
        app.processEvents()


def test_a_row_has_the_model_the_age_and_both_in_one_text(app, desk):
    d = desk()
    d.backend.apply(list(AGENTS))
    assert d.meta() == {"t1": "", "t2": "", "t3": ""}  # nothing was read yet
    d.backend.read_meta()
    app.processEvents()
    rows = d.rows()
    assert (rows["t1"]["model"], rows["t1"]["sessionAge"], rows["t1"]["metaText"]) == (
        "Opus 5.5", "2h 14m", "Opus 5.5 · 2h 14m")
    # Codex with no session found: the time of the terminal alone. A program with no reader: the same; here Herdr
    # gives no creation time for it, so the row has no line.
    assert (rows["t2"]["model"], rows["t2"]["sessionAge"], rows["t2"]["metaText"]) == ("", "3d 2h", "3d 2h")
    assert (rows["t3"]["model"], rows["t3"]["sessionAge"], rows["t3"]["metaText"]) == ("", "", "")
    assert d.emitted == [1, 1]  # the list, then the facts


def test_the_spoken_name_of_a_row_has_the_model_and_the_age_in_words(app, desk):
    d = desk()
    d.backend.apply(list(AGENTS))
    before = d.rows()
    assert before["t1"]["spoken"] == "Go to rev, claude-code in Main"
    d.backend.read_meta()
    rows = d.rows()
    assert rows["t1"]["spoken"] == "Go to rev, claude-code in Main, model Opus 5.5, session age 2 hours 14 minutes"
    assert rows["t2"]["spoken"] == "Go to dev, codex in Main, session age 3 days 2 hours"
    assert rows["t3"]["spoken"] == before["t3"]["spoken"]


def test_a_backend_with_no_reader_of_sessions_has_rows_with_no_line(app, fake_client, tmp_path):
    backend = Backend(fake_client, settings_path=tmp_path / "state.json")
    backend.apply(list(AGENTS))
    backend.read_meta()
    rows = [row for group in backend.groups for row in group["agents"]]
    assert {(row["model"], row["sessionAge"], row["metaText"]) for row in rows} == {("", "", "")}
    assert backend.showMeta is True
    backend.stop()


def test_a_get_for_a_new_agent_at_once_and_then_only_as_a_net_in_five_minutes(app, desk):
    d = desk()
    d.backend.apply(list(AGENTS[:2]))
    d.backend.read_meta()
    assert d.client.calls == ["t1", "t2"] and d.reads == ["claude-code", "codex"]
    for second in range(1, 30):
        d.mono = 100.0 + second
        d.backend.apply(list(AGENTS[:2]))
        d.backend.read_meta()
    assert d.client.calls == ["t1", "t2"]
    d.backend.apply(list(AGENTS))  # a new agent in the list
    assert d.backend._meta_wake.is_set()
    d.backend.read_meta()
    assert d.client.calls == ["t1", "t2", "t3"]
    d.mono = 130.0
    d.backend.read_meta()  # the files are read again, Herdr is not asked
    assert d.client.calls == ["t1", "t2", "t3"] and d.reads == ["claude-code", "codex"] * 2
    for minute in range(10):  # ten minutes: a get for each agent in five minutes, as a net
        for second in range(0, 60, 5):
            d.mono = 200.0 + 60 * minute + second
            d.backend.read_meta()
    assert d.client.calls == ["t1", "t2", "t3"] + ["t1", "t2", "t3"] * 2


def test_a_new_process_of_an_agent_shows_its_model_after_the_read(app, desk):
    d = desk()
    d.backend.apply(list(AGENTS))
    d.backend.read_meta()
    app.processEvents()
    d.models["claude-code"] = "claude-fable-5-2"
    d.mono += 30
    del d.emitted[:]
    d.backend.read_meta()
    app.processEvents()
    assert d.meta()["t1"] == "Fable 5.2 · 2h 14m" and d.emitted == [1]


def test_the_wake_of_the_reads_is_only_for_a_list_with_an_other_agent_or_program(app, desk):
    d = desk()
    d.backend.apply(list(AGENTS))
    assert d.backend._meta_wake.is_set()
    d.backend._meta_wake.clear()
    d.backend.apply([Agent("t1", "done", "rev 2", "Other", "claude-code"), *AGENTS[1:]])  # a status, a name
    assert not d.backend._meta_wake.is_set()
    d.backend.apply([Agent("t1", "done", "rev", "Main", "codex"), *AGENTS[1:]])  # an other program
    assert d.backend._meta_wake.is_set()


def test_the_age_gets_a_new_text_with_no_read_and_the_rows_are_told_one_time(app, desk):
    d = desk()
    d.backend.apply(list(AGENTS))
    d.backend.read_meta()
    app.processEvents()
    del d.emitted[:], d.client.calls[:], d.reads[:]
    d.now += 30  # the same minute
    d.backend._age_timer.timeout.emit()
    assert d.emitted == [] and d.meta()["t1"] == "Opus 5.5 · 2h 14m"
    d.now += 30
    d.backend._age_timer.timeout.emit()
    assert d.emitted == [1] and d.meta() == {"t1": "Opus 5.5 · 2h 15m", "t2": "3d 2h", "t3": ""}
    d.backend._age_timer.timeout.emit()
    assert d.emitted == [1] and d.client.calls == [] and d.reads == []
    assert d.backend._age_timer.isActive() and d.backend._age_timer.interval() == 60000


def test_an_error_of_herdr_is_a_row_with_no_line_and_one_log_line(app, desk, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    d = desk()
    d.client.answer["t1"] = Failure("timeout")
    d.backend.apply(list(AGENTS))
    d.backend.read_meta()
    d.mono += 30
    d.backend.read_meta()
    assert d.meta()["t1"] == "" and d.rows()["t1"]["spoken"] == "Go to rev, claude-code in Main"
    assert [r.getMessage() for r in caplog.records if "t1" in r.getMessage()] == [
        "session facts terminal=t1 app=claude-code reason=timeout"]


def test_offline_nothing_is_read_and_the_facts_are_dropped(app, desk):
    d = desk()
    d.backend.apply(list(AGENTS))
    d.backend.read_meta()
    d.backend.apply(None)
    d.mono += 60
    d.backend.read_meta()
    assert d.client.calls == ["t1", "t2", "t3"] and d.watch.facts() == {}


# ----- the setting -----

def test_with_the_setting_off_nothing_is_read_and_no_row_has_a_line(app, desk):
    d = desk(show=False)
    assert d.backend.showMeta is False and not d.backend._age_timer.isActive()
    d.backend.apply(list(AGENTS))
    for step in range(5):
        d.mono += 30
        d.backend.read_meta()
    # Herdr is still asked (the title of a terminal is the name of an agent with no name): no file is read.
    assert d.client.calls == ["t1", "t2", "t3"] and d.reads == [] and d.meta() == {"t1": "", "t2": "", "t3": ""}


def test_the_setting_goes_off_and_on_and_is_saved_with_the_other_keys(app, desk):
    d = desk()
    d.path.write_text(json.dumps({"x": 5, "layout": "B", "later": [1]}), encoding="utf-8")
    assert d.backend.showMeta is True
    d.backend.apply(list(AGENTS))
    d.backend.read_meta()
    app.processEvents()
    told = []
    d.backend.showMetaChanged.connect(lambda: told.append(d.backend.showMeta))
    del d.emitted[:], d.client.calls[:]
    d.backend.setShowMeta(False)
    assert told == [False] and d.emitted == [1] and d.meta() == {"t1": "", "t2": "", "t3": ""}
    assert json.loads(d.path.read_text(encoding="utf-8")) == {"x": 5, "layout": "B", "later": [1], "showMeta": False}
    assert d.watch.facts() == {} and not d.backend._age_timer.isActive()
    d.mono += 60
    reads = list(d.reads)
    d.backend.read_meta()
    assert d.client.calls == ["t1", "t2", "t3"] and d.reads == reads  # Herdr for the titles: no file
    del d.client.calls[:]
    d.backend.setShowMeta(False)  # the same value: nothing
    assert told == [False]
    d.backend._meta_wake.clear()
    d.backend.setShowMeta(True)
    assert told == [False, True] and d.backend._meta_wake.is_set() and d.backend._age_timer.isActive()
    assert json.loads(d.path.read_text(encoding="utf-8")) == {"x": 5, "layout": "B", "later": [1]}  # the default has no key
    d.backend.read_meta()  # at once, not 30 seconds later
    app.processEvents()
    assert d.client.calls == ["t1", "t2", "t3"] and d.meta()["t1"] == "Opus 5.5 · 2h 14m"


def test_the_setting_goes_off_during_a_round_and_the_round_stops_and_keeps_nothing(app, desk):
    d = desk()
    d.backend.apply(list(AGENTS))

    def read_and_turn_off(host, pids, known):  # the person clicks the check box while the first agent is read
        d.backend.setShowMeta(False)
        return d.read("claude-code", STARTED)

    d.watch._readers["claude-code"] = read_and_turn_off
    d.backend.read_meta()
    app.processEvents()
    assert d.client.calls == ["t1"] and d.watch.facts() == {} and d.meta() == {"t1": "", "t2": "", "t3": ""}


def test_the_setting_is_restored_at_the_next_start(app, desk, tmp_path):
    first = desk()
    first.backend.setShowMeta(False)
    second = desk()
    assert second.backend.showMeta is False
    second.backend.setShowMeta(True)
    assert desk().backend.showMeta is True


@pytest.mark.parametrize("value", ["no", 0, 1, None, [False], {"a": 1}, 0.0])
def test_a_saved_value_of_an_other_type_is_ignored_with_one_log_line(app, desk, caplog, value):
    caplog.set_level(logging.INFO, logger="bellwether")
    d = desk(show=value)
    assert d.backend.showMeta is True
    assert [r.getMessage() for r in caplog.records] == [
        "the saved value of showMeta cannot be used: the model and session-time line shows"]
    assert json.loads(d.path.read_text(encoding="utf-8")) == {"x": 5, "showMeta": value}  # the file stays as it is


def test_a_save_that_fails_is_one_log_line_and_the_setting_still_applies(app, desk, caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="bellwether")
    d = desk()

    def refuse(*_args, **_more):
        raise OSError("made-up")

    monkeypatch.setattr("bellwether.backend.save_show_meta", refuse)
    d.backend.setShowMeta(False)
    assert d.backend.showMeta is False and [r.getMessage() for r in caplog.records] == ["showMeta was not saved"]


# ----- the thread -----

def test_the_thread_reads_at_the_start_and_when_the_list_has_a_new_agent(app, desk):
    d = desk(interval=0.02)
    d.client.result = list(AGENTS[:1])
    d.backend.start()
    assert wait_for(app, lambda: d.meta().get("t1") == "Opus 5.5 · 2h 14m"), d.meta()
    assert d.client.calls == ["t1"]
    d.client.result = list(AGENTS)
    assert wait_for(app, lambda: d.meta().get("t2") == "3d 2h"), d.meta()
    time.sleep(0.2)  # the clock of the engine stands still: no agent is due again
    assert d.client.calls == ["t1", "t2", "t3"]
    d.backend.stop()
    assert not d.backend._meta_thread.is_alive()


def test_the_thread_goes_on_after_an_unexpected_error_and_logs_its_class_only(app, desk, caplog):
    caplog.set_level(logging.INFO, logger="bellwether")
    d = desk(interval=0.02)
    step, failing = d.watch.step, [True]

    def broken(agents, stopped, files=True):
        if failing[0]:
            raise RuntimeError("MARKER-private-session-text")
        return step(agents, stopped, files)

    d.watch.step = broken
    d.backend.start()
    assert wait_for(app, lambda: any("session facts failed" in r.getMessage() for r in caplog.records))
    failing[0] = False
    d.backend._meta_wake.set()
    assert wait_for(app, lambda: d.meta().get("t1") == "Opus 5.5 · 2h 14m"), d.meta()
    assert [r.getMessage() for r in caplog.records if "failed" in r.getMessage()] == [
        "session facts failed: RuntimeError"]
    assert "MARKER" not in caplog.text


# ----- the title of the terminal as the name of an agent with no name -----

TITLED = [Agent("t1", "working", "rev", "Main", "claude-code"), Agent("t3", "working", "", "Space / Tab", "made-up-program"),
          Agent("t4", "working", "", "Space / Tab", "made-up-program")]


def titles(d, **given):
    for key, title in given.items():
        d.client.answer[key] = Terminal(30, 31, 0, title)


@pytest.mark.parametrize("show", [True, False])
def test_an_agent_with_no_name_has_the_title_of_its_terminal_as_its_name(app, desk, caplog, show):
    caplog.set_level(logging.INFO, logger="bellwether")
    d = desk(show=show)
    titles(d, t1="Made-up title of a named one", t3="Made-up task three")
    d.backend.apply(list(TITLED))
    assert d.rows()["t3"]["label"] == "made-up-program" and d.rows()["t3"]["detail"] == "Space / Tab"
    del d.emitted[:]
    d.backend.read_meta()
    app.processEvents()
    rows = d.rows()
    assert (rows["t3"]["label"], rows["t3"]["detail"]) == ("Made-up task three", "Space / Tab")
    assert rows["t3"]["spoken"].startswith("Go to Made-up task three, made-up-program in Space / Tab")
    assert rows["t1"]["label"] == "rev"  # a name of Herdr wins
    assert rows["t4"]["label"] == "made-up-program"  # no title: as before
    assert d.emitted == [1] and "Made-up" not in caplog.text
    # An agent with a name, or with a title, is before one with neither.
    assert [row["key"] for row in d.backend.groups[2]["agents"]] == ["t3", "t1", "t4"]


def test_a_title_stays_when_the_setting_changes(app, desk):
    d = desk()
    titles(d, t3="Made-up task three")
    d.backend.apply(list(TITLED))
    d.backend.read_meta()
    app.processEvents()
    d.backend.setShowMeta(False)
    assert d.rows()["t3"]["label"] == "Made-up task three"
    d.backend.read_meta()
    app.processEvents()
    assert d.rows()["t3"]["label"] == "Made-up task three" and d.meta()["t1"] == ""
