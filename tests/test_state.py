from herdr_float.state import ATTENTION, STATES, Agent, count_states, parse_agents


def row(pane_id, status, name=None, agent="claude", workspace_id="w1"):
    return {
        "terminal_id": "t-" + pane_id,
        "agent_status": status,
        "workspace_id": workspace_id,
        "tab_id": "w1:t1",
        "pane_id": pane_id,
        "focused": False,
        "revision": 1,
        "name": name,
        "agent": agent,
        "display_agent": None,
    }


def result(*rows):
    return {"type": "agent_list", "agents": list(rows)}


def test_constants():
    assert STATES == ("blocked", "done", "working", "idle", "unknown")
    assert ATTENTION == frozenset({"blocked", "done"})


def test_no_agents():
    assert parse_agents(result()) == []
    assert count_states([]) == {"blocked": 0, "done": 0, "working": 0, "idle": 0, "unknown": 0}


def test_one_agent():
    agents = parse_agents(result(row("w1:p1", "working", name="reviewer")))
    assert agents == [Agent("w1:p1", "working", "reviewer", "w1")]
    assert count_states(agents)["working"] == 1


def test_each_state_has_its_own_count():
    agents = parse_agents(result(*[row(f"w1:p{i}", s) for i, s in enumerate(STATES)]))
    assert count_states(agents) == dict.fromkeys(STATES, 1)


def test_sort_is_state_order_then_name():
    agents = parse_agents(
        result(
            row("w1:p1", "idle", name="b"),
            row("w1:p2", "blocked", name="z"),
            row("w1:p3", "idle", name="A"),
            row("w1:p4", "done", name="m"),
        )
    )
    assert [a.pane_id for a in agents] == ["w1:p2", "w1:p4", "w1:p3", "w1:p1"]


def test_name_falls_back_to_agent_kind_then_pane_id():
    assert parse_agents(result(row("w1:p1", "idle", name=None, agent="codex")))[0].name == "codex"
    display = row("w1:p2", "idle", name=None, agent=None)
    display["display_agent"] = "Claude Code"
    assert parse_agents(result(display))[0].name == "Claude Code"


def test_status_that_is_not_known_counts_as_unknown():
    agents = parse_agents(result(row("w1:p1", "sleeping")))
    assert agents[0].status == "unknown"


def test_invalid_input_gives_no_agents():
    assert parse_agents(None) == []
    assert parse_agents({"agents": "nope"}) == []
    assert parse_agents({"agents": [None, 3, {"agent_status": "idle"}, {"pane_id": ""}]}) == []


def test_invalid_row_does_not_remove_valid_rows():
    agents = parse_agents({"agents": [None, row("w1:p1", "idle")]})
    assert [a.pane_id for a in agents] == ["w1:p1"]
