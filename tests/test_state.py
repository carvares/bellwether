import logging

import pytest

from herdr_float import state
from herdr_float.state import ATTENTION, PRIORITY, STATES, Agent, count_states, parse_app, parse_core, top_state


@pytest.fixture(autouse=True)
def no_words_logged_yet(monkeypatch):
    monkeypatch.setattr(state, "_logged_words", set())


def term(address, status, name=None, app="claude-code", sub_agents=()):
    return {
        "terminal": address,
        "pane": "p-" + address,
        "status": status,
        "app": app,
        "name": name,
        "sub_agents": list(sub_agents),
    }


def tab(name, *terminals):
    return {"id": "tb-" + name, "name": name, "active": False, "settled": False, "terminals": list(terminals)}


def space(name, *tabs):
    return {"id": "sp-" + name, "name": name, "folder": "/x", "machine": None, "active": False, "tabs": list(tabs)}


def core_row(address, status=None, agent="claude-code", state_="live"):
    row = {"address": address, "agent": agent, "cwd": "/x", "state": state_, "turn": 1, "where": "x"}
    if status is not None:
        row["status"] = status
    return row


def test_constants():
    assert STATES == ("blocked", "done", "working", "idle")
    assert ATTENTION == frozenset({"blocked", "done"})


def test_no_agents():
    assert parse_app([]) == []
    assert parse_core([]) == []
    assert count_states([]) == {"blocked": 0, "done": 0, "working": 0, "idle": 0}


def test_app_agent_row():
    agents = parse_app([space("Main", tab("1", term("t1", "working", name="reviewer")))])
    assert agents == [Agent("t1", "working", "reviewer", "Main", "claude-code")]
    assert count_states(agents)["working"] == 1


def test_app_terminal_with_no_status_is_not_an_agent():
    assert parse_app([space("Main", tab("1", term("t1", None, app=None), term("t2", "idle")))]) == [
        Agent("t2", "idle", "", "Main", "claude-code")
    ]


def test_app_each_state_has_its_own_count():
    rows = [term(f"t{i}", s) for i, s in enumerate(STATES)]
    assert count_states(parse_app([space("Main", tab("1", *rows))])) == dict.fromkeys(STATES, 1)


def test_app_name_is_only_the_name_of_the_terminal_and_the_program_word_is_apart():
    rows = [term("t1", "idle", app="codex"), term("t2", "idle", app=None), term("t3", "idle", name="rev", app="pi")]
    agents = parse_app([space("Main", tab("1", *rows))])
    assert [(a.key, a.name, a.app) for a in agents] == [("t1", "", "codex"), ("t2", "", ""), ("t3", "rev", "pi")]


def test_program_word_that_is_not_text_is_dropped():
    agents = parse_app([space("Main", tab("1", term("t1", "idle", app=7), term("t2", "idle", name=["x"])))])
    assert [(a.name, a.app) for a in agents] == [("", ""), ("", "claude-code")]


def test_app_workspace_has_the_tab_name_only_when_the_space_has_more_tabs():
    agents = parse_app(
        [
            space("Main", tab("1", term("t1", "idle"))),
            space("api", tab("1", term("t2", "idle")), tab("fix login", term("t3", "idle"))),
        ]
    )
    assert {a.key: a.workspace for a in agents} == {"t1": "Main", "t2": "api / 1", "t3": "api / fix login"}


def test_sort_is_state_order_then_address():
    # The order inside a state is the address here. The backend sorts the rows of a group by their label.
    rows = [term("t3", "idle", name="b"), term("t2", "blocked", name="z"), term("t1", "idle", name="c"), term("t4", "done")]
    agents = parse_app([space("Main", tab("1", *rows))])
    assert [a.key for a in agents] == ["t2", "t4", "t1", "t3"]


def test_app_sub_agents_are_rows_with_the_mapping_of_the_app_list():
    parent = term(
        "t1",
        "working",
        name="builder",
        sub_agents=[
            term("t2", "working", name="helper"),
            term("t3", "done", name="finished"),
            term("t4", "error", name="broken", sub_agents=[term("t5", "idle", name="deep")]),
            term("t6", None, app=None),
        ],
    )
    agents = parse_app([space("Main", tab("1", parent))])
    assert {a.key: a.status for a in agents} == {
        "t1": "working", "t2": "working", "t3": "idle", "t4": "blocked", "t5": "idle",
    }
    assert {a.workspace for a in agents} == {"Main"}


def test_app_terminal_listed_two_times_is_one_row_and_the_sub_agent_entry_wins():
    as_terminal = term("t2", "done")
    as_sub_agent = term("t2", "done")
    parent = term("t1", "working", sub_agents=[as_sub_agent])
    for terminals in ([parent, as_terminal], [as_terminal, parent]):
        agents = parse_app([space("Main", tab("1", *terminals))])
        assert {a.key: a.status for a in agents} == {"t1": "working", "t2": "idle"}


def test_app_sub_agents_in_the_shape_of_the_core_list_are_rows():
    subs = [
        {"address": "t2", "agent": "codex", "state": "live", "status": "working", "parent": "t1"},
        {"address": "t3", "agent": "codex", "state": "live", "status": "done", "parent": "t1"},
        {"address": "t4", "agent": "codex", "state": "finished", "status": "working", "parent": "t1"},
        {"terminal": "t5", "state": "finished", "status": "working", "app": "codex", "name": None},
        {"address": "t6", "state": "live", "parent": "t1"},
    ]
    agents = parse_app([space("Main", tab("1", term("t1", "working", sub_agents=subs)))])
    assert {a.key: a.status for a in agents} == {"t1": "working", "t2": "working", "t3": "idle"}


def test_core_sub_agent_is_never_done():
    child = dict(core_row("t2", "done"), parent="t1")
    agents = parse_core([core_row("t1", "done"), child])
    assert {a.key: a.status for a in agents} == {"t1": "done", "t2": "idle"}


def test_status_word_that_is_not_known_is_skipped_and_logged_one_time(caplog):
    caplog.set_level(logging.WARNING, logger="herdr_float")
    spaces = [space("Main", tab("1", term("t1", "sleeping", name="reviewer"), term("t2", "idle")))]
    assert [a.key for a in parse_app(spaces)] == ["t2"]
    assert [a.key for a in parse_app(spaces)] == ["t2"]
    assert [r.getMessage() for r in caplog.records] == ["status word not known: 'sleeping'"]
    assert "reviewer" not in caplog.text


def test_app_invalid_input_gives_no_agents():
    assert parse_app([None, 3, {"tabs": "nope"}, {"tabs": [None, {"terminals": "nope"}]}]) == []
    bad_rows = [None, 3, {"status": "idle"}, {"terminal": "", "status": "idle"}, {"terminal": 7, "status": "idle"}]
    assert parse_app([space("Main", tab("1", *bad_rows))]) == []


def test_app_invalid_row_does_not_remove_valid_rows():
    agents = parse_app([None, space("Main", tab("1", None, term("t1", "idle")))])
    assert [a.key for a in agents] == ["t1"]


def test_core_agent_rows():
    agents = parse_core(
        [
            core_row("t1", "working"),
            core_row("t2", agent="fish"),
            core_row("t3", "done", agent=None),
            core_row("t4", "error"),
            core_row("t5", "idle", state_="finished"),
        ]
    )
    assert agents == [
        Agent("t4", "blocked", "", "", "claude-code"),
        Agent("t3", "done", "", "", ""),
        Agent("t1", "working", "", "", "claude-code"),
    ]


def test_core_invalid_input_gives_no_agents():
    assert parse_core([None, 3, {"state": "live", "status": "idle"}, {"address": "", "state": "live"}]) == []


def test_priority_is_the_order_of_the_user_and_not_the_row_order():
    assert PRIORITY == ("blocked", "done", "idle", "working")
    assert STATES == ("blocked", "done", "working", "idle")
    assert set(PRIORITY) == set(STATES)


@pytest.mark.parametrize(
    "counts, expected",
    [
        ({}, "none"),
        ({"working": 3}, "working"),
        ({"idle": 1}, "idle"),
        ({"idle": 1, "working": 3}, "idle"),
        ({"done": 1, "idle": 4, "working": 2}, "done"),
        ({"done": 2}, "done"),
        ({"blocked": 1}, "blocked"),
        ({"blocked": 1, "done": 5, "idle": 5, "working": 5}, "blocked"),
    ],
)
def test_top_state_is_the_first_state_of_the_priority_that_has_an_agent(counts, expected):
    assert top_state(True, dict(dict.fromkeys(STATES, 0), **counts)) == expected


def test_top_state_is_offline_when_not_online():
    assert top_state(False, dict.fromkeys(STATES, 3)) == "offline"
