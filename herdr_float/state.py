"""Logic for the agent table: rows of the Herdr lists become sorted agents. No reads of Herdr."""
from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger("herdr_float")

STATES: tuple[str, ...] = ("blocked", "done", "working", "idle")
ATTENTION: frozenset[str] = frozenset({"blocked", "done"})

_logged_words: set[str] = set()


@dataclass(frozen=True)
class Agent:
    key: str  # The terminal address, for example "t11". The jump uses it.
    status: str
    name: str
    workspace: str


def _status(word: object, sub_agent: bool = False) -> str | None:
    """Return one of STATES, or None when the terminal is not an agent."""
    # The same mapping as the agent list of the app: a program that reports "error" needs the person,
    # and a sub-agent is never "done" (it reports to its parent).
    if word == "error":
        return "blocked"
    if word == "done" and sub_agent:
        return "idle"
    if word in STATES:
        return word
    if word and isinstance(word, str) and word not in _logged_words:
        _logged_words.add(word)
        log.warning("status word not known: %r", word[:32])
    return None


def _sorted(agents) -> list[Agent]:
    return sorted(agents, key=lambda a: (STATES.index(a.status), a.name.lower(), a.key))


def parse_app(spaces: list) -> list[Agent]:
    """Convert the "spaces" list of `herdr-app ls` to sorted agents. Invalid rows are skipped."""
    agents: dict[str, Agent] = {}
    for space in spaces:
        tabs = space.get("tabs") if isinstance(space, dict) else None
        if not isinstance(tabs, list):
            continue
        for tab in tabs:
            if not isinstance(tab, dict):
                continue
            where = str(space.get("name") or "")
            if len(tabs) > 1 and tab.get("name"):
                where = f"{where} / {tab['name']}"
            _add_terminals(agents, tab.get("terminals"), where, sub_agent=False)
    return _sorted(agents.values())


def _add_terminals(agents: dict[str, Agent], rows: object, where: str, sub_agent: bool) -> None:
    """Add the rows and their sub-agents. A row has the shape of `herdr-app ls` ("terminal") or,
    for a sub-agent, possibly the shape of `herdr-core ls --json` ("address", "state")."""
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict) or row.get("state", "live") != "live":
            continue
        key = row.get("terminal") or row.get("address")
        status = _status(row.get("status"), sub_agent)
        # The app shows a terminal that is also a sub-agent below its parent, so that entry wins.
        if isinstance(key, str) and key and status and (sub_agent or key not in agents):
            name = row.get("name") or row.get("app") or row.get("agent") or key
            agents[key] = Agent(key, status, str(name), where)
        _add_terminals(agents, row.get("sub_agents"), where, sub_agent=True)


def parse_core(terminals: list) -> list[Agent]:
    """Convert the "terminals" list of `herdr-core ls --json` to sorted agents. Invalid rows are skipped."""
    agents = []
    for row in terminals:
        if not isinstance(row, dict) or row.get("state") != "live":
            continue
        key = row.get("address")
        status = _status(row.get("status"), sub_agent=bool(row.get("parent")))
        if isinstance(key, str) and key and status:
            agents.append(Agent(key, status, str(row.get("agent") or key), ""))
    return _sorted(agents)


def count_states(agents: list[Agent]) -> dict[str, int]:
    counts = dict.fromkeys(STATES, 0)
    for agent in agents:
        counts[agent.status] += 1
    return counts
