"""Pure logic for the agent table. No I/O."""
from __future__ import annotations

from dataclasses import dataclass

STATES: tuple[str, ...] = ("blocked", "done", "working", "idle", "unknown")
ATTENTION: frozenset[str] = frozenset({"blocked", "done"})


@dataclass(frozen=True)
class Agent:
    pane_id: str
    status: str
    name: str
    workspace_id: str


def parse_agents(result: object) -> list[Agent]:
    """Convert an agent.list result to a sorted list. Invalid rows are skipped."""
    if not isinstance(result, dict):
        return []
    rows = result.get("agents")
    if not isinstance(rows, list):
        return []
    agents: list[Agent] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        pane_id = row.get("pane_id")
        if not isinstance(pane_id, str) or not pane_id:
            continue
        status = row.get("agent_status")
        if status not in STATES:
            status = "unknown"
        name = row.get("name") or row.get("agent") or row.get("display_agent") or pane_id
        agents.append(Agent(pane_id, status, str(name), str(row.get("workspace_id") or "")))
    agents.sort(key=lambda a: (STATES.index(a.status), a.name.lower(), a.pane_id))
    return agents


def count_states(agents: list[Agent]) -> dict[str, int]:
    counts = dict.fromkeys(STATES, 0)
    for agent in agents:
        counts[agent.status] += 1
    return counts
