# Bellwether Implementation Plan

Renamed from herdr-float to Bellwether on 2026-11-18. The task text below (Tasks 1 to 9) is the record of the work as it was planned, and keeps the old names `herdr-float` and `herdr_float`. The current names are in the spec, the README and the code.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A small always-on-top window on KDE Wayland that shows how many Herdr agents are in each state and lets the user jump to an agent.

**Architecture:** A Python backend reads `agent.list` from the Herdr socket one time each second and gives the result to a QML interface. The QML window is a layer-shell overlay surface, so the compositor keeps it above other windows. A thin Herdr plugin starts the program when Herdr starts. After the start, the program is an independent process.

**Tech Stack:** Python 3.12+, PySide6 (system package, Qt 6.12), QML, `org.kde.layershell` QML module (package `layer-shell-qt`), pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-18-bellwether-design.md`

## Global Constraints

- Platform: Linux, KDE Plasma on Wayland. No other platform.
- Scope: the default local Herdr session only. Socket: `~/.config/herdr/herdr.sock`.
- Five states, never merged: `blocked`, `done`, `working`, `idle`, `unknown`. Display order is that order.
- `blocked` and `done` are the attention states.
- A system tray icon lets the user hide, show and quit the widget.
- The widget only reads Herdr state. The one write is `agent.focus` on a user click.
- Logs: `~/.local/state/bellwether/bellwether.log`. IDs and states only. No pane text.
- Position file: `~/.config/bellwether/state.json`.
- PySide6 comes from the system package `pyside6`, not from PyPI. The PyPI wheel has its own Qt and cannot load the system layer-shell plugin.
- Commits: use the configured git identity. No AI attribution in commit messages. Do not push unless the user asks.
- The widget starts with Herdr (plugin). It stays on the screen after the Herdr window closes. No systemd service.
- Do not run `herdr server stop`. Do not close panes, tabs or workspaces.
- All commands run from `/home/carvares/Projects/Personal/bellwether`.

## Verified facts (Herdr 0.9.5, protocol 22, from `herdr api schema`)

- Request: `{"id": "<string>", "method": "<name>", "params": {...}}`.
- Success: `{"id": "<same>", "result": {...}}`. Error: `{"id": "<same>", "error": {"code": "...", "message": "..."}}`.
- `agent.list` takes `{}` and returns `{"type": "agent_list", "agents": [AgentInfo]}`.
- `AgentInfo` required fields: `terminal_id`, `agent_status`, `workspace_id`, `tab_id`, `pane_id`, `focused`, `revision`. Optional: `name`, `agent`, `display_agent`, `title`.
- `agent.focus` takes `{"target": "<pane id or agent name>"}`.
- Plugin manifest: `herdr-plugin.toml` with `id`, `name`, `version`, `min_herdr_version`, `platforms`, `[[startup]]`. Local install: `herdr plugin link <path>`.
- The `pane.agent_status_changed` subscription needs a `pane_id`. There is no global status subscription. This is why the plan uses a 1-second read and not events.

## Not verified (Task 1 tests these)

1. Message framing. Assumption: one JSON object for each line, ended by `\n`, one request for each connection.
2. `org.kde.layershell` works from PySide6 QML, and `margins` can move the surface.
3. A method to raise the terminal window after a jump.

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Project metadata, pytest configuration. |
| `bellwether/state.py` | Pure logic: parse `agent.list`, sort, count. |
| `bellwether/client.py` | Socket request and response. Errors. |
| `bellwether/settings.py` | Load and save the window position. |
| `bellwether/backend.py` | Qt object: 1-second read thread, properties for QML, focus slot. |
| `bellwether/ui/Main.qml` | Layer-shell window, pill, list, drag. |
| `bellwether/tray.py` | System tray icon: hide, show, quit. State colours. |
| `bellwether/__main__.py` | Logging, single instance, start. |
| `plugin/herdr-plugin.toml` | Herdr plugin manifest. |
| `plugin/start.sh` | Start command for the plugin. |
| `tests/` | pytest files, one for each Python module. |
| `spike/` | Throwaway test scripts from Task 1. |

---

### Task 1: Setup and spike

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `herdr_float/__init__.py`, `tests/__init__.py`
- Create: `spike/wire.py`, `spike/Overlay.qml`, `spike/overlay.py`
- Modify: `docs/superpowers/specs/2026-11-18-herdr-float-design.md` (section "Not verified")

**Interfaces:**
- Consumes: nothing.
- Produces: a working `uv run pytest`, and written answers to the three "Not verified" items. Tasks 3, 5 and 7 read those answers.

- [ ] **Step 1: Ask the user to install the system packages**

The agent cannot run `sudo`. Ask the user to run:

```bash
sudo pacman -S --needed pyside6 layer-shell-qt
```

Then check:

```bash
python3 -c "import PySide6; print(PySide6.__version__)"
```

Expected: a version number, for example `6.12.0`.

- [ ] **Step 2: Create the project files**

`pyproject.toml`:

```toml
[project]
name = "herdr-float"
version = "0.1.0"
description = "Floating status widget for Herdr agents"
requires-python = ">=3.12"
dependencies = []

[dependency-groups]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.uv]
package = false
```

`.gitignore`:

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
```

`herdr_float/__init__.py` and `tests/__init__.py`: empty files.

- [ ] **Step 3: Create the virtual environment with access to system packages**

```bash
uv venv --system-site-packages --python /usr/bin/python3
uv sync
uv run python -c "import PySide6, pytest; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Test the wire format**

`spike/wire.py`:

```python
"""Throwaway: print the raw reply of agent.list."""
import json
import socket
from pathlib import Path

path = Path.home() / ".config/herdr/herdr.sock"
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
    sock.settimeout(3)
    sock.connect(str(path))
    sock.sendall(json.dumps({"id": "spike-1", "method": "agent.list", "params": {}}).encode() + b"\n")
    data = b""
    while not data.endswith(b"\n"):
        chunk = sock.recv(65536)
        if not chunk:
            break
        data += chunk
print(repr(data[:2000]))
```

Run: `uv run python spike/wire.py` (Herdr must be running with a minimum of one agent).

Expected: one line of JSON that starts with `{"id":"spike-1","result":{"type":"agent_list","agents":[`.

Record in the spec:
- Is the reply one line that ends with `\n`?
- Does the server close the connection after the reply, or keep it open?
- Does `agent.list` return panes that have no agent? Look at `agent` and `display_agent` in each row.

If the reply is not line-delimited JSON, stop and tell the user. Task 3 depends on it.

- [ ] **Step 5: Test the layer-shell overlay**

`spike/Overlay.qml`:

```qml
import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell

Window {
    id: root
    visible: true
    width: 220
    height: 48
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus

    LayerShell.Window.scope: "herdr-float-spike"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.exclusionZone: -1
    LayerShell.Window.margins.left: 200
    LayerShell.Window.margins.top: 120

    Rectangle {
        anchors.fill: parent
        radius: 12
        color: "#202124"
        Text { anchors.centerIn: parent; color: "white"; text: "herdr-float spike" }
        MouseArea {
            anchors.fill: parent
            onClicked: {
                root.LayerShell.Window.margins.left += 40
                console.log("left margin", root.LayerShell.Window.margins.left)
            }
        }
    }
}
```

`spike/overlay.py`:

```python
"""Throwaway: show a layer-shell overlay."""
import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

app = QGuiApplication(sys.argv)
engine = QQmlApplicationEngine()
engine.load(Path(__file__).with_name("Overlay.qml"))
if not engine.rootObjects():
    sys.exit(1)
sys.exit(app.exec())
```

Run: `QT_QPA_PLATFORM=wayland uv run python spike/overlay.py`

Ask the user to confirm each point (the user must look at the screen):
- The box shows at about 200 px from the left and 120 px from the top.
- The box stays above a maximized window and above a full-screen window.
- A click moves the box 40 px to the right.
- The box does not take keyboard focus from the active window.

If the QML does not load, read the exact property names in `/usr/lib/qt6/qml/org/kde/layershell/LayerShellQtQml.qmltypes` and correct the file. If `margins.left` cannot be written, try `LayerShell.Window.margins: Qt.margins(left, top, 0, 0)`. If the window is a normal window and not an overlay, run again with `QT_WAYLAND_SHELL_INTEGRATION=layer-shell` set.

If no variant gives an overlay, stop and tell the user. The fallback is a normal frameless window with a KWin "keep above" window rule. That is a design change and needs the user's approval.

- [ ] **Step 6: Test the window raise**

With a Herdr agent in a pane that is not focused, and a different application in front, run:

```bash
herdr agent list
herdr agent focus <pane_id from the list>
```

Record: does the terminal window come to the front? If not, record that the known limit stays. Do not build a KWin script in this plan.

- [ ] **Step 7: Record the results in the spec**

In the spec, replace the section "Not verified" with a section "Verified on <date>" that gives the answer for each of the three items and the exact QML lines that worked.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock .gitignore herdr_float tests spike docs
git commit -m "Add project setup and spike results"
```

---

### Task 2: State logic

**Files:**
- Create: `herdr_float/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `STATES: tuple[str, ...]` = `("blocked", "done", "working", "idle", "unknown")`
  - `ATTENTION: frozenset[str]` = `{"blocked", "done"}`
  - `Agent` (frozen dataclass): `pane_id: str`, `status: str`, `name: str`, `workspace_id: str`
  - `parse_agents(result: object) -> list[Agent]` (sorted)
  - `count_states(agents: list[Agent]) -> dict[str, int]` (all five keys, in `STATES` order)

- [ ] **Step 1: Write the failing tests**

`tests/test_state.py`:

```python
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
```

- [ ] **Step 2: Run the tests and confirm that they fail**

Run: `uv run pytest tests/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'herdr_float.state'`.

- [ ] **Step 3: Write the implementation**

`herdr_float/state.py`:

```python
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
```

If Task 1 Step 4 showed that `agent.list` returns panes with no agent, add this line after the `pane_id` check, and add a test for it:

```python
        if not (row.get("agent") or row.get("display_agent") or row.get("name")):
            continue
```

- [ ] **Step 4: Run the tests and confirm that they pass**

Run: `uv run pytest tests/test_state.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add herdr_float/state.py tests/test_state.py
git commit -m "Add agent state logic"
```

---

### Task 3: Socket client

**Files:**
- Create: `herdr_float/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: the framing answer from Task 1 Step 4.
- Produces:
  - `DEFAULT_SOCKET: Path`
  - `HerdrOffline(Exception)`: no connection or timeout.
  - `HerdrProtocolError(Exception)`: the reply is not valid.
  - `HerdrError(Exception)` with `.code: str` and `.message: str`: the server returned an error.
  - `HerdrClient(socket_path: Path = DEFAULT_SOCKET, timeout: float = 2.0)`
  - `HerdrClient.request(method: str, params: dict | None = None) -> dict`
  - `HerdrClient.list_agents() -> dict`
  - `HerdrClient.focus_agent(pane_id: str) -> None`

- [ ] **Step 1: Write the failing tests**

`tests/test_client.py`:

```python
import json
import socket
import threading

import pytest

from herdr_float.client import HerdrClient, HerdrError, HerdrOffline, HerdrProtocolError


@pytest.fixture
def server(tmp_path):
    """Fake Herdr socket. Set server.reply to a function: request dict -> bytes."""
    path = tmp_path / "herdr.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen()
    listener.settimeout(0.2)
    stop = threading.Event()

    class Server:
        requests = []
        reply = staticmethod(lambda request: b"")

    def serve():
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except TimeoutError:
                continue
            with conn:
                data = b""
                while not data.endswith(b"\n"):
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                if not data:
                    continue
                request = json.loads(data)
                Server.requests.append(request)
                conn.sendall(Server.reply(request))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    Server.path = path
    yield Server
    stop.set()
    thread.join()
    listener.close()


def ok(result):
    return lambda request: json.dumps({"id": request["id"], "result": result}).encode() + b"\n"


def test_list_agents_sends_request_and_returns_result(server):
    server.reply = ok({"type": "agent_list", "agents": []})
    result = HerdrClient(server.path).list_agents()
    assert result == {"type": "agent_list", "agents": []}
    assert server.requests[0]["method"] == "agent.list"
    assert server.requests[0]["params"] == {}
    assert isinstance(server.requests[0]["id"], str)


def test_focus_agent_sends_target(server):
    server.reply = ok({"type": "agent_info", "agent": {}})
    HerdrClient(server.path).focus_agent("w1:p2")
    assert server.requests[0]["method"] == "agent.focus"
    assert server.requests[0]["params"] == {"target": "w1:p2"}


def test_large_reply_in_many_chunks(server):
    agents = [{"pane_id": f"w1:p{i}", "agent_status": "idle"} for i in range(5000)]
    server.reply = ok({"type": "agent_list", "agents": agents})
    assert len(HerdrClient(server.path).list_agents()["agents"]) == 5000


def test_server_error_raises_herdr_error(server):
    server.reply = lambda request: (
        json.dumps({"id": request["id"], "error": {"code": "agent_not_found", "message": "no agent"}}).encode()
        + b"\n"
    )
    with pytest.raises(HerdrError) as info:
        HerdrClient(server.path).focus_agent("w9:p9")
    assert info.value.code == "agent_not_found"
    assert info.value.message == "no agent"


def test_missing_socket_raises_offline(tmp_path):
    with pytest.raises(HerdrOffline):
        HerdrClient(tmp_path / "missing.sock").list_agents()


def test_no_reply_raises_offline_after_timeout(server):
    server.reply = lambda request: (threading.Event().wait(0.5), b"")[1]
    with pytest.raises((HerdrOffline, HerdrProtocolError)):
        HerdrClient(server.path, timeout=0.1).list_agents()


@pytest.mark.parametrize(
    "raw",
    [
        b"not json\n",
        b"[1, 2]\n",
        b'{"id": "other", "result": {}}\n',
        b'{"id": "ID"}\n',
        b'{"id": "ID", "result": 5}\n',
        b'{"id": "ID", "result": {}',
    ],
)
def test_invalid_reply_raises_protocol_error(server, raw):
    server.reply = lambda request: raw.replace(b"ID", request["id"].encode())
    with pytest.raises(HerdrProtocolError):
        HerdrClient(server.path).list_agents()


def test_client_works_again_after_server_comes_back(server, tmp_path):
    with pytest.raises(HerdrOffline):
        HerdrClient(tmp_path / "missing.sock").list_agents()
    server.reply = ok({"type": "agent_list", "agents": []})
    assert HerdrClient(server.path).list_agents()["agents"] == []
```

- [ ] **Step 2: Run the tests and confirm that they fail**

Run: `uv run pytest tests/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'herdr_float.client'`.

- [ ] **Step 3: Write the implementation**

`herdr_float/client.py`:

```python
"""Request and response on the Herdr API socket. One connection for each request."""
from __future__ import annotations

import json
import socket
import uuid
from pathlib import Path

DEFAULT_SOCKET = Path.home() / ".config" / "herdr" / "herdr.sock"
MAX_REPLY_BYTES = 16 * 1024 * 1024


class HerdrOffline(Exception):
    """No connection to the Herdr server, or the server did not answer in time."""


class HerdrProtocolError(Exception):
    """The reply is not a valid Herdr response."""


class HerdrError(Exception):
    """The server returned an error response."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class HerdrClient:
    def __init__(self, socket_path: Path = DEFAULT_SOCKET, timeout: float = 2.0) -> None:
        self.socket_path = Path(socket_path)
        self.timeout = timeout

    def request(self, method: str, params: dict | None = None) -> dict:
        request_id = uuid.uuid4().hex
        payload = json.dumps({"id": request_id, "method": method, "params": params or {}}).encode() + b"\n"
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect(str(self.socket_path))
                sock.sendall(payload)
                line = _read_line(sock)
        except OSError as exc:
            raise HerdrOffline(str(exc)) from exc
        try:
            message = json.loads(line)
        except ValueError as exc:
            raise HerdrProtocolError("reply is not JSON") from exc
        if not isinstance(message, dict) or message.get("id") != request_id:
            raise HerdrProtocolError("reply has no matching id")
        error = message.get("error")
        if isinstance(error, dict):
            raise HerdrError(str(error.get("code", "")), str(error.get("message", "")))
        result = message.get("result")
        if not isinstance(result, dict):
            raise HerdrProtocolError("reply has no result object")
        return result

    def list_agents(self) -> dict:
        return self.request("agent.list")

    def focus_agent(self, pane_id: str) -> None:
        self.request("agent.focus", {"target": pane_id})


def _read_line(sock: socket.socket) -> bytes:
    data = bytearray()
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            raise HerdrProtocolError("connection closed before the end of the reply")
        data += chunk
        if data.endswith(b"\n"):
            return bytes(data)
        if len(data) > MAX_REPLY_BYTES:
            raise HerdrProtocolError("reply is too large")
```

Note: `HerdrProtocolError` raised in `_read_line` is not an `OSError`, so it passes through the `except OSError` block unchanged.

- [ ] **Step 4: Run the tests and confirm that they pass**

Run: `uv run pytest tests/test_client.py -v`
Expected: 13 passed.

- [ ] **Step 5: Check against the real server**

Run (Herdr must be running):

```bash
uv run python -c "
from herdr_float.client import HerdrClient
from herdr_float.state import parse_agents, count_states
agents = parse_agents(HerdrClient().list_agents())
print(count_states(agents)); print(agents)"
```

Expected: the counts agree with `herdr agent list`.

- [ ] **Step 6: Commit**

```bash
git add herdr_float/client.py tests/test_client.py
git commit -m "Add Herdr socket client"
```

---

### Task 4: Position settings

**Files:**
- Create: `herdr_float/settings.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `DEFAULT_PATH: Path` = `~/.config/herdr-float/state.json`
  - `load_position(path: Path = DEFAULT_PATH) -> tuple[int, int] | None`
  - `save_position(x: int, y: int, path: Path = DEFAULT_PATH) -> None`

- [ ] **Step 1: Write the failing tests**

`tests/test_settings.py`:

```python
from herdr_float.settings import load_position, save_position


def test_missing_file_gives_none(tmp_path):
    assert load_position(tmp_path / "state.json") is None


def test_save_then_load(tmp_path):
    path = tmp_path / "dir" / "state.json"
    save_position(120, 48, path)
    assert load_position(path) == (120, 48)


def test_save_replaces_old_value(tmp_path):
    path = tmp_path / "state.json"
    save_position(1, 2, path)
    save_position(3, 4, path)
    assert load_position(path) == (3, 4)


def test_invalid_content_gives_none(tmp_path):
    path = tmp_path / "state.json"
    for text in ["", "not json", "[]", '{"x": 1}', '{"x": "a", "y": 2}', '{"x": true, "y": 2}']:
        path.write_text(text)
        assert load_position(path) is None, text
```

- [ ] **Step 2: Run the tests and confirm that they fail**

Run: `uv run pytest tests/test_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'herdr_float.settings'`.

- [ ] **Step 3: Write the implementation**

`herdr_float/settings.py`:

```python
"""Load and save the window position."""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_PATH = Path.home() / ".config" / "herdr-float" / "state.json"


def load_position(path: Path = DEFAULT_PATH) -> tuple[int, int] | None:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    x, y = data.get("x"), data.get("y")
    if type(x) is not int or type(y) is not int:
        return None
    return x, y


def save_position(x: int, y: int, path: Path = DEFAULT_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"x": x, "y": y}))
    os.replace(temporary, path)
```

- [ ] **Step 4: Run the tests and confirm that they pass**

Run: `uv run pytest tests/test_settings.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add herdr_float/settings.py tests/test_settings.py
git commit -m "Add window position settings"
```

---

### Task 5: Backend object for QML

**Files:**
- Create: `herdr_float/backend.py`
- Test: `tests/test_backend.py`

**Interfaces:**
- Consumes: `HerdrClient`, `HerdrOffline`, `HerdrError`, `HerdrProtocolError` (Task 3); `parse_agents`, `count_states`, `STATES`, `ATTENTION`, `Agent` (Task 2); `load_position`, `save_position` (Task 4).
- Produces: `Backend(client, interval: float = 1.0, settings_path: Path = DEFAULT_PATH)`, a `QObject` with:
  - Property `online: bool`
  - Property `counters: list[dict]`. Each item: `{"state": str, "count": int, "attention": bool}`. Always five items in `STATES` order.
  - Property `agents: list[dict]`. Each item: `{"paneId": str, "name": str, "status": str, "workspace": str}`.
  - Properties `savedX: int`, `savedY: int` (`-1` if there is no saved position).
  - Signal `changed()`. Signal `focusFailed(paneId: str, message: str)`.
  - Slot `focus(paneId: str)`. Slot `savePosition(x: int, y: int)`.
  - Methods `start()`, `stop()`, `apply(agents: list[Agent] | None)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_backend.py`:

```python
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication

from herdr_float.backend import Backend
from herdr_float.client import HerdrError, HerdrOffline
from herdr_float.state import Agent


@pytest.fixture(scope="session")
def app():
    return QCoreApplication.instance() or QCoreApplication([])


class FakeClient:
    def __init__(self):
        self.result = {"type": "agent_list", "agents": []}
        self.list_error = None
        self.focus_error = None
        self.focused = []

    def list_agents(self):
        if self.list_error:
            raise self.list_error
        return self.result

    def focus_agent(self, pane_id):
        self.focused.append(pane_id)
        if self.focus_error:
            raise self.focus_error


@pytest.fixture
def backend(app, tmp_path):
    return Backend(FakeClient(), settings_path=tmp_path / "state.json")


def test_starts_offline_with_five_zero_counters(backend):
    assert backend.online is False
    assert [c["state"] for c in backend.counters] == ["blocked", "done", "working", "idle", "unknown"]
    assert all(c["count"] == 0 for c in backend.counters)
    assert backend.agents == []


def test_apply_snapshot_sets_counters_and_agents(backend):
    seen = []
    backend.changed.connect(lambda: seen.append(1))
    backend.apply([Agent("w1:p1", "blocked", "rev", "w1"), Agent("w1:p2", "idle", "dev", "w1")])
    assert backend.online is True
    assert {c["state"]: c["count"] for c in backend.counters} == {
        "blocked": 1, "done": 0, "working": 0, "idle": 1, "unknown": 0,
    }
    assert backend.agents[0] == {"paneId": "w1:p1", "name": "rev", "status": "blocked", "workspace": "w1"}
    assert seen == [1]


def test_attention_flag_is_only_for_blocked_and_done(backend):
    assert {c["state"] for c in backend.counters if c["attention"]} == {"blocked", "done"}


def test_apply_none_goes_offline_and_clears(backend):
    backend.apply([Agent("w1:p1", "working", "a", "w1")])
    backend.apply(None)
    assert backend.online is False
    assert backend.agents == []
    assert all(c["count"] == 0 for c in backend.counters)


def test_same_snapshot_twice_emits_changed_one_time(backend):
    seen = []
    backend.changed.connect(lambda: seen.append(1))
    agents = [Agent("w1:p1", "working", "a", "w1")]
    backend.apply(agents)
    backend.apply(list(agents))
    assert seen == [1]


def test_fetch_returns_agents_or_none(backend):
    backend._client.result = {"agents": [{"pane_id": "w1:p1", "agent_status": "done", "agent": "claude"}]}
    assert backend.fetch() == [Agent("w1:p1", "done", "claude", "")]
    backend._client.list_error = HerdrOffline("no socket")
    assert backend.fetch() is None


def test_focus_calls_client(backend):
    backend.focus_now("w1:p3")
    assert backend._client.focused == ["w1:p3"]


def test_focus_error_emits_focus_failed(backend):
    failures = []
    backend.focusFailed.connect(lambda pane_id, message: failures.append((pane_id, message)))
    backend._client.focus_error = HerdrError("agent_not_found", "no agent")
    backend.focus_now("w1:p3")
    assert failures == [("w1:p3", "no agent")]
    backend._client.focus_error = HerdrOffline("gone")
    backend.focus_now("w1:p4")
    assert failures[-1] == ("w1:p4", "Herdr is offline")


def test_position_is_saved_and_loaded(app, tmp_path):
    path = tmp_path / "state.json"
    first = Backend(FakeClient(), settings_path=path)
    assert (first.savedX, first.savedY) == (-1, -1)
    first.savePosition(300, 40)
    second = Backend(FakeClient(), settings_path=path)
    assert (second.savedX, second.savedY) == (300, 40)
```

- [ ] **Step 2: Run the tests and confirm that they fail**

Run: `uv run pytest tests/test_backend.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'herdr_float.backend'`.

- [ ] **Step 3: Write the implementation**

`herdr_float/backend.py`:

```python
"""Qt object between the Herdr client and the QML interface."""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from .client import HerdrError, HerdrOffline, HerdrProtocolError
from .settings import DEFAULT_PATH, load_position, save_position
from .state import ATTENTION, STATES, Agent, count_states, parse_agents

log = logging.getLogger("herdr_float")


class Backend(QObject):
    changed = Signal()
    focusFailed = Signal(str, str)
    _snapshot = Signal(object)

    def __init__(self, client, interval: float = 1.0, settings_path: Path = DEFAULT_PATH) -> None:
        super().__init__()
        self._client = client
        self._interval = interval
        self._settings_path = Path(settings_path)
        self._agents: list[Agent] = []
        self._online = False
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_failure: str | None = None
        self._saved = load_position(self._settings_path) or (-1, -1)
        self._snapshot.connect(self.apply)

    # ----- properties for QML -----

    @Property(bool, notify=changed)
    def online(self) -> bool:
        return self._online

    @Property("QVariantList", notify=changed)
    def counters(self) -> list[dict]:
        counts = count_states(self._agents)
        return [{"state": s, "count": counts[s], "attention": s in ATTENTION} for s in STATES]

    @Property("QVariantList", notify=changed)
    def agents(self) -> list[dict]:
        return [
            {"paneId": a.pane_id, "name": a.name, "status": a.status, "workspace": a.workspace_id}
            for a in self._agents
        ]

    @Property(int, constant=True)
    def savedX(self) -> int:
        return self._saved[0]

    @Property(int, constant=True)
    def savedY(self) -> int:
        return self._saved[1]

    # ----- state -----

    @Slot(object)
    def apply(self, agents: list[Agent] | None) -> None:
        """Apply a snapshot. None means that Herdr is offline."""
        online = agents is not None
        agents = agents or []
        if online == self._online and agents == self._agents:
            return
        self._online = online
        self._agents = agents
        self.changed.emit()

    def fetch(self) -> list[Agent] | None:
        """Read one snapshot. Runs on the worker thread."""
        try:
            agents = parse_agents(self._client.list_agents())
        except (HerdrOffline, HerdrProtocolError, HerdrError) as exc:
            failure = type(exc).__name__
            if failure != self._last_failure:
                log.warning("snapshot failed: %s", failure)
                self._last_failure = failure
            return None
        if self._last_failure is not None:
            log.info("snapshot ok again, agents=%d", len(agents))
            self._last_failure = None
        return agents

    # ----- worker thread -----

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="herdr-poll", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=3)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._snapshot.emit(self.fetch())
            self._wake.wait(self._interval)
            self._wake.clear()

    # ----- actions from QML -----

    @Slot(str)
    def focus(self, pane_id: str) -> None:
        threading.Thread(target=self.focus_now, args=(pane_id,), daemon=True).start()

    def focus_now(self, pane_id: str) -> None:
        try:
            self._client.focus_agent(pane_id)
            log.info("focus ok pane=%s", pane_id)
        except HerdrError as exc:
            log.warning("focus failed pane=%s code=%s", pane_id, exc.code)
            self.focusFailed.emit(pane_id, exc.message or exc.code)
        except (HerdrOffline, HerdrProtocolError):
            log.warning("focus failed pane=%s offline", pane_id)
            self.focusFailed.emit(pane_id, "Herdr is offline")
        self._wake.set()

    @Slot(int, int)
    def savePosition(self, x: int, y: int) -> None:
        try:
            save_position(x, y, self._settings_path)
        except OSError:
            log.warning("position was not saved")
```

Notes for the implementer:
- A Qt signal emitted from a Python thread is delivered on the thread of the receiver. So `apply` always runs on the Qt main thread.
- The log gets one line when the state changes between ok and failed. It does not get one line each second.

- [ ] **Step 4: Run the tests and confirm that they pass**

Run: `uv run pytest tests/test_backend.py -v`
Expected: 9 passed.

- [ ] **Step 5: Run all tests**

Run: `uv run pytest -v`
Expected: 35 passed.

- [ ] **Step 6: Commit**

```bash
git add herdr_float/backend.py tests/test_backend.py
git commit -m "Add Qt backend with one-second snapshot read"
```

---

### Task 6: Window, pill and program start

**Files:**
- Create: `herdr_float/ui/Main.qml`
- Create: `herdr_float/__main__.py`

**Interfaces:**
- Consumes: `Backend` (Task 5) as the QML context property `backend`; the layer-shell QML lines that Task 1 Step 5 confirmed.
- Produces: `uv run python -m herdr_float` shows the compact pill. `Main.qml` has a property `expanded: bool` that Task 7 uses.

- [ ] **Step 1: Write the QML window with the pill**

Use the exact layer-shell lines from the spec section "Verified on <date>" if they are different from the lines below.

`herdr_float/ui/Main.qml`:

```qml
import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell

Window {
    id: root

    property bool expanded: false
    property int posX: 0
    property int posY: 0
    readonly property int edge: 16
    readonly property var stateColors: ({
        "blocked": "#f28b82",
        "done": "#fdd663",
        "working": "#8ab4f8",
        "idle": "#81c995",
        "unknown": "#9aa0a6"
    })

    visible: true
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
    width: panel.width
    height: panel.height

    LayerShell.Window.scope: "herdr-float"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.exclusionZone: -1
    LayerShell.Window.margins.left: posX
    LayerShell.Window.margins.top: posY

    function clampPosition() {
        var maxX = Math.max(0, Screen.width - width)
        var maxY = Math.max(0, Screen.height - height)
        posX = Math.min(Math.max(0, posX), maxX)
        posY = Math.min(Math.max(0, posY), maxY)
    }

    Component.onCompleted: {
        var valid = backend.savedX >= 0 && backend.savedY >= 0
            && backend.savedX <= Screen.width - width
            && backend.savedY <= Screen.height - height
        posX = valid ? backend.savedX : Screen.width - width - edge
        posY = valid ? backend.savedY : edge
        clampPosition()
    }
    onWidthChanged: clampPosition()
    onHeightChanged: clampPosition()

    Rectangle {
        id: panel
        width: Math.max(pill.implicitWidth, list.visible ? 280 : 0) + 20
        height: column.implicitHeight + 16
        radius: 12
        color: "#e6202124"
        border.color: "#3c4043"

        Column {
            id: column
            x: 10
            y: 8
            spacing: 8

            Row {
                id: pill
                spacing: 12

                Text {
                    visible: !backend.online
                    text: "offline"
                    color: "#9aa0a6"
                    font.pixelSize: 14
                }

                Repeater {
                    model: backend.online ? backend.counters : []
                    Row {
                        required property var modelData
                        spacing: 5
                        opacity: modelData.count === 0 ? 0.35 : 1.0
                        Rectangle {
                            width: 10
                            height: 10
                            radius: 5
                            anchors.verticalCenter: parent.verticalCenter
                            color: root.stateColors[modelData.state]
                        }
                        Text {
                            text: modelData.count
                            color: modelData.attention && modelData.count > 0 ? root.stateColors[modelData.state] : "#e8eaed"
                            font.pixelSize: 14
                            font.bold: modelData.attention && modelData.count > 0
                            Accessible.name: modelData.count + " " + modelData.state
                        }
                    }
                }
            }

            Item {
                id: list
                visible: false
                width: 1
                height: 1
            }
        }

        MouseArea {
            id: dragArea
            width: parent.width
            height: pill.height + 16
            property real startX: 0
            property real startY: 0
            property bool moved: false
            onPressed: (mouse) => { startX = mouse.x; startY = mouse.y; moved = false }
            onPositionChanged: (mouse) => {
                var dx = mouse.x - startX
                var dy = mouse.y - startY
                if (!moved && Math.abs(dx) + Math.abs(dy) < 6)
                    return
                moved = true
                root.posX += dx
                root.posY += dy
                root.clampPosition()
            }
            onReleased: {
                if (moved)
                    backend.savePosition(root.posX, root.posY)
                else
                    root.expanded = !root.expanded
            }
        }
    }
}
```

Notes for the implementer:
- The colour is not the only signal. Each counter has a fixed position, and attention counters are bold.
- The drag area covers only the pill row. A movement of less than 6 px is a click, not a drag.
- The placeholder `Item { id: list }` is replaced in Task 7.

- [ ] **Step 2: Write the program start**

`herdr_float/__main__.py`:

```python
"""Start the herdr-float widget."""
from __future__ import annotations

import fcntl
import logging
import os
import signal
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from .backend import Backend
from .client import HerdrClient

LOG_PATH = Path.home() / ".local" / "state" / "herdr-float" / "herdr-float.log"


def setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=1)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def take_single_instance_lock():
    """Return an open lock file, or None if a different widget process has the lock."""
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp")
    handle = open(runtime / "herdr-float.lock", "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def main() -> int:
    setup_logging()
    lock = take_single_instance_lock()
    if lock is None:
        logging.getLogger("herdr_float").info("a widget is already running, exit")
        return 0

    os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
    app = QGuiApplication(sys.argv)
    app.setApplicationName("herdr-float")
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    backend = Backend(HerdrClient())
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(Path(__file__).parent / "ui" / "Main.qml")
    if not engine.rootObjects():
        logging.getLogger("herdr_float").error("the QML interface did not load")
        return 1

    backend.start()
    app.aboutToQuit.connect(backend.stop)
    logging.getLogger("herdr_float").info("started")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run the widget and check it (the user must look at the screen)**

Run: `uv run python -m herdr_float`

Check each point:
- The pill shows at the top-right corner on the first start.
- The five counts agree with `herdr agent list`.
- A change of an agent state shows in the pill in less than 2 seconds.
- The pill stays above a maximized window.
- Drag moves the pill. It cannot leave the screen.
- Stop with Ctrl+C, start again: the pill is at the saved position.
- A second `uv run python -m herdr_float` in a different terminal exits immediately.
- With `HerdrClient` pointed at a missing socket (temporary edit, then revert), the pill shows "offline".
- `tail ~/.local/state/herdr-float/herdr-float.log` shows "started" and no pane text.

Fix each point that fails before the commit.

- [ ] **Step 4: Run all tests**

Run: `uv run pytest -v`
Expected: 35 passed.

- [ ] **Step 5: Commit**

```bash
git add herdr_float/ui/Main.qml herdr_float/__main__.py
git commit -m "Add overlay window with state counters"
```

---

### Task 7: Agent list and jump

**Files:**
- Modify: `herdr_float/ui/Main.qml` (replace the placeholder `Item { id: list ... }`)

**Interfaces:**
- Consumes: `root.expanded`, `backend.agents`, `backend.focus(paneId)`, `backend.focusFailed(paneId, message)`, `root.stateColors`.
- Produces: the complete interface of the spec.

- [ ] **Step 1: Replace the placeholder with the list**

In `herdr_float/ui/Main.qml`, replace this block:

```qml
            Item {
                id: list
                visible: false
                width: 1
                height: 1
            }
```

with:

```qml
            Column {
                id: list
                visible: root.expanded && backend.online
                width: 280
                spacing: 2

                property string failedPane: ""
                property string failedMessage: ""

                Connections {
                    target: backend
                    function onFocusFailed(paneId, message) {
                        list.failedPane = paneId
                        list.failedMessage = message
                        root.expanded = true
                        failTimer.restart()
                    }
                }

                Timer {
                    id: failTimer
                    interval: 3000
                    onTriggered: { list.failedPane = ""; list.failedMessage = "" }
                }

                Text {
                    visible: backend.agents.length === 0
                    text: "No agents"
                    color: "#9aa0a6"
                    font.pixelSize: 13
                }

                Repeater {
                    model: backend.agents
                    Rectangle {
                        id: rowItem
                        required property var modelData
                        readonly property bool failed: list.failedPane === modelData.paneId
                        width: list.width
                        height: 28
                        radius: 6
                        color: rowMouse.containsMouse ? "#3c4043" : "transparent"

                        Rectangle {
                            id: dot
                            x: 6
                            width: 10
                            height: 10
                            radius: 5
                            anchors.verticalCenter: parent.verticalCenter
                            color: root.stateColors[rowItem.modelData.status]
                        }
                        Text {
                            anchors.left: dot.right
                            anchors.leftMargin: 8
                            anchors.right: detail.left
                            anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            text: rowItem.modelData.name
                            color: "#e8eaed"
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                        Text {
                            id: detail
                            anchors.right: parent.right
                            anchors.rightMargin: 6
                            anchors.verticalCenter: parent.verticalCenter
                            width: Math.min(implicitWidth, 150)
                            elide: Text.ElideRight
                            text: rowItem.failed
                                ? list.failedMessage
                                : rowItem.modelData.status + " · " + rowItem.modelData.workspace
                            color: rowItem.failed ? "#f28b82" : "#9aa0a6"
                            font.pixelSize: 12
                        }
                        MouseArea {
                            id: rowMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            Accessible.name: "Go to " + rowItem.modelData.name
                            onClicked: {
                                root.expanded = false
                                backend.focus(rowItem.modelData.paneId)
                            }
                        }
                    }
                }
            }
```

Notes for the implementer:
- A fast double click closes the list on the first click. The second click cannot reach a row, so it cannot send a second focus request.
- A long agent name is cut with "…" and does not make the row wider.
- When a focus request fails, the list opens again and the row shows the error for 3 seconds.

- [ ] **Step 2: Run the widget and check it (the user must look at the screen)**

Run: `uv run python -m herdr_float`

Check each point:
- A click on the pill opens the list. A second click closes it.
- The rows are in the order blocked, done, working, idle, unknown.
- With no agents, the list shows "No agents".
- A click on a row focuses that pane in Herdr, and the list closes.
- A click on a `done` agent changes it to `idle` in less than 2 seconds.
- Close a pane in Herdr with the list open: the row goes away and nothing breaks.
- An agent name of 32 characters does not make the widget wider.
- With the list open at the bottom edge of the screen, the widget moves up and stays on the screen.
- Stop Herdr access (temporary missing socket path), click a row: the row shows "Herdr is offline", then the pill shows "offline".

Fix each point that fails before the commit.

- [ ] **Step 3: Run all tests**

Run: `uv run pytest -v`
Expected: 35 passed.

- [ ] **Step 4: Commit**

```bash
git add herdr_float/ui/Main.qml
git commit -m "Add agent list with jump to pane"
```

---

### Task 8: System tray icon (hide, show, quit)

**Files:**
- Create: `herdr_float/tray.py`
- Test: `tests/test_tray.py`
- Modify: `herdr_float/__main__.py` (the `main` function)
- Modify: `herdr_float/ui/Main.qml` (the `stateColors` property)

**Interfaces:**
- Consumes: `Backend.online`, `Backend.counters`, `Backend.changed` (Task 5); the QML root window from `engine.rootObjects()[0]` (Task 6).
- Produces:
  - `STATE_COLORS: dict[str, str]` (the one source of the state colours, also given to QML as the context property `stateColors_`)
  - `top_state(online: bool, counters: list[dict]) -> str`: `"offline"`, the first state in display order with a count above zero, or `"none"`.
  - `tooltip_text(online: bool, counters: list[dict]) -> str`
  - `Tray(backend, window, app)`: a `QObject` that owns the tray icon and its menu.

Requirement from the user: an icon in the system tray, as Slack has. From the icon, the user can hide the widget or close it.

Behaviour:
- A left click on the icon hides the widget. A second left click shows it again.
- A right click opens a menu: "Hide widget" or "Show widget" (the text follows the state), and "Quit".
- "Quit" stops the program. The plugin starts it again at the next Herdr start.
- The icon is a dot. Its colour is the colour of the most important state that has agents. So the icon shows that an agent needs attention when the widget is hidden.
- The tooltip gives the five counts.
- The widget is always visible after a start. The hidden state is not saved.

- [ ] **Step 1: Write the failing tests**

`tests/test_tray.py`:

```python
from herdr_float.state import STATES
from herdr_float.tray import STATE_COLORS, tooltip_text, top_state


def counters(**counts):
    return [{"state": s, "count": counts.get(s, 0), "attention": s in ("blocked", "done")} for s in STATES]


def test_every_state_and_offline_and_none_has_a_colour():
    assert set(STATE_COLORS) == set(STATES) | {"offline", "none"}


def test_top_state_is_offline_when_not_online():
    assert top_state(False, counters(blocked=3)) == "offline"


def test_top_state_is_none_with_no_agents():
    assert top_state(True, counters()) == "none"


def test_top_state_follows_display_order():
    assert top_state(True, counters(idle=5, working=2)) == "working"
    assert top_state(True, counters(idle=5, done=1, working=2)) == "done"
    assert top_state(True, counters(idle=5, done=1, blocked=1)) == "blocked"
    assert top_state(True, counters(unknown=1)) == "unknown"


def test_tooltip_text():
    assert tooltip_text(False, counters()) == "Herdr Float: offline"
    assert tooltip_text(True, counters(blocked=1, idle=2)) == (
        "Herdr Float: 1 blocked, 0 done, 0 working, 2 idle, 0 unknown"
    )
```

- [ ] **Step 2: Run the tests and confirm that they fail**

Run: `uv run pytest tests/test_tray.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'herdr_float.tray'`.

- [ ] **Step 3: Write the implementation**

`herdr_float/tray.py`:

```python
"""System tray icon: hide, show and quit."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

log = logging.getLogger("herdr_float")

STATE_COLORS: dict[str, str] = {
    "blocked": "#f28b82",
    "done": "#fdd663",
    "working": "#8ab4f8",
    "idle": "#81c995",
    "unknown": "#9aa0a6",
    "offline": "#5f6368",
    "none": "#5f6368",
}


def top_state(online: bool, counters: list[dict]) -> str:
    if not online:
        return "offline"
    for counter in counters:
        if counter["count"] > 0:
            return counter["state"]
    return "none"


def tooltip_text(online: bool, counters: list[dict]) -> str:
    if not online:
        return "Herdr Float: offline"
    return "Herdr Float: " + ", ".join(f'{c["count"]} {c["state"]}' for c in counters)


def make_icon(color: str) -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(8, 8, 48, 48)
    painter.end()
    return QIcon(pixmap)


class Tray(QObject):
    def __init__(self, backend, window, app) -> None:
        super().__init__()
        self._backend = backend
        self._window = window
        self._shown_state: str | None = None

        self._menu = QMenu()
        self._toggle_action = self._menu.addAction("Hide widget")
        self._toggle_action.triggered.connect(self.toggle)
        self._menu.addSeparator()
        self._menu.addAction("Quit").triggered.connect(app.quit)

        self._icon = QSystemTrayIcon(self)
        self._icon.setContextMenu(self._menu)
        self._icon.activated.connect(self._on_activated)

        backend.changed.connect(self.refresh)
        window.visibleChanged.connect(self._sync_label)
        self.refresh()
        self._sync_label()
        self._icon.show()

    def toggle(self, *_args) -> None:
        visible = not self._window.isVisible()
        self._window.setVisible(visible)
        log.info("widget %s from tray", "shown" if visible else "hidden")

    def refresh(self) -> None:
        online, counters = self._backend.online, self._backend.counters
        state = top_state(online, counters)
        if state != self._shown_state:
            self._icon.setIcon(make_icon(STATE_COLORS[state]))
            self._shown_state = state
        self._icon.setToolTip(tooltip_text(online, counters))

    def _sync_label(self, *_args) -> None:
        self._toggle_action.setText("Hide widget" if self._window.isVisible() else "Show widget")

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle()
```

- [ ] **Step 4: Run the tests and confirm that they pass**

Run: `uv run pytest tests/test_tray.py -v`
Expected: 5 passed.

- [ ] **Step 5: Use the tray in the program start**

A tray icon needs `QApplication` from `QtWidgets`. `QGuiApplication` is not sufficient.

In `herdr_float/__main__.py`, replace the import line:

```python
from PySide6.QtGui import QGuiApplication
```

with:

```python
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
```

Add this import below `from .client import HerdrClient`:

```python
from .tray import STATE_COLORS, Tray
```

Replace this block in `main`:

```python
    app = QGuiApplication(sys.argv)
    app.setApplicationName("herdr-float")
```

with:

```python
    app = QApplication(sys.argv)
    app.setApplicationName("herdr-float")
    app.setQuitOnLastWindowClosed(False)
```

Replace this line:

```python
    engine.rootContext().setContextProperty("backend", backend)
```

with:

```python
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("stateColors_", STATE_COLORS)
```

Replace this block:

```python
    backend.start()
    app.aboutToQuit.connect(backend.stop)
```

with:

```python
    tray = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = Tray(backend, engine.rootObjects()[0], app)
    else:
        logging.getLogger("herdr_float").warning("no system tray, the widget has no tray icon")

    backend.start()
    app.aboutToQuit.connect(backend.stop)
```

Notes for the implementer:
- `setQuitOnLastWindowClosed(False)` is necessary. Without it, Qt stops the program when the hidden widget is the last window.
- Keep the `tray` variable. If Python deletes the object, the icon goes away.
- Without a system tray, the widget runs as before. The user then stops it with `pkill`.

- [ ] **Step 6: Use the one colour source in QML**

In `herdr_float/ui/Main.qml`, replace this block:

```qml
    readonly property var stateColors: ({
        "blocked": "#f28b82",
        "done": "#fdd663",
        "working": "#8ab4f8",
        "idle": "#81c995",
        "unknown": "#9aa0a6"
    })
```

with:

```qml
    readonly property var stateColors: stateColors_
```

The context property has the name `stateColors_` (Step 5). The different name prevents a binding loop between the window property and the context property.

- [ ] **Step 7: Run the widget and check it (the user must look at the screen)**

Run: `uv run python -m herdr_float`

Check each point:
- A dot icon shows in the system tray. If it is in the hidden part of the tray, the user can pin it in the KDE tray settings.
- A left click on the icon hides the widget. A second left click shows it at the same position.
- A right click opens the menu. The first entry is "Hide widget" when the widget is visible and "Show widget" when it is hidden.
- With the widget hidden, an agent that changes to `blocked` changes the icon colour in less than 2 seconds.
- The tooltip shows the five counts.
- Hide, then show, then drag: the drag and the saved position work as before.
- After a show, the widget is still above a maximized window.
- "Quit" removes the widget and the icon, and the process ends (`pgrep -f "python -m herdr_float"` prints nothing).
- With the widget hidden, a second `uv run python -m herdr_float` exits and does not make a second icon.

Fix each point that fails before the commit.

- [ ] **Step 8: Run all tests**

Run: `uv run pytest -v`
Expected: 40 passed.

- [ ] **Step 9: Commit**

```bash
git add herdr_float/tray.py tests/test_tray.py herdr_float/__main__.py herdr_float/ui/Main.qml
git commit -m "Add system tray icon with hide, show and quit"
```

---

### Task 9: Herdr plugin, README and task notes

**Files:**
- Create: `plugin/herdr-plugin.toml`, `plugin/start.sh`
- Create: `README.md`
- Create: Obsidian task notes (see Step 5)

**Interfaces:**
- Consumes: `python -m herdr_float` (Task 6). The single-instance lock makes a second start safe.
- Produces: the widget starts when Herdr starts. After that it is an independent process: it stays on the screen when the Herdr window closes, and it stops at desktop logout.

Decision from the user: the widget is a Herdr plugin that starts only when Herdr starts. There is no systemd service and no start at desktop login.

- [ ] **Step 1: Write the plugin files**

`plugin/herdr-plugin.toml`:

```toml
# herdr-float plugin manifest.

id = "carvares.herdr-float"
name = "Herdr Float"
version = "0.1.0"
min_herdr_version = "0.9.0"
description = "Starts the floating agent status widget"
platforms = ["linux"]

# A one-shot launch. The widget keeps itself alive and allows one instance only.
[[startup]]
platforms = ["linux"]
command = ["./start.sh"]
```

`plugin/start.sh`:

```bash
#!/bin/sh
# Start herdr-float as an independent background process and return immediately.
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root" || exit 1
setsid -f "$root/.venv/bin/python" -m herdr_float >/dev/null 2>&1
```

Then: `chmod +x plugin/start.sh`

Notes for the implementer:
- `setsid -f` puts the widget in its own session. So the widget does not stop when the plugin command ends or when Herdr closes.
- A second start is safe. The widget allows one instance only and the second process exits with code 0.

- [ ] **Step 2: Link the plugin (ask the user first)**

This step changes the user's Herdr configuration. Ask the user before you run it.

```bash
herdr plugin link /home/carvares/Projects/Personal/herdr-float/plugin
herdr plugin list --plugin carvares.herdr-float
```

Expected: the plugin shows as enabled with no warnings.

If `herdr plugin link` rejects the manifest, read the error, compare with `~/.config/herdr/plugins/github/herdr.auto-title-*/herdr-plugin.toml`, and correct the manifest.

- [ ] **Step 3: Check the start and the life of the widget (the user does these steps)**

Not verified before this step: the moment when Herdr runs a `[[startup]]` command. It is possibly at server start only, and not each time the Herdr window opens. This step finds the answer.

Do not stop the Herdr server yourself. Ask the user to do these steps at a time that is safe for their running agents.

1. Stop the widget: tray icon, "Quit".
2. Close the Herdr window and open it again. Does the widget show? Record the answer.
3. If it does not show, restart the Herdr server. Confirm that the widget shows.
4. Run `herdr plugin log list --plugin carvares.herdr-float --limit 5` and confirm that the startup command succeeded.
5. Close the Herdr window. Confirm that the widget stays on the screen. Record what the pill shows: the counts or "offline".
6. Open Herdr again. Confirm that there is one widget only, and that the counts are correct in less than 2 seconds.

If step 2 shows that the widget does not start when the window opens, tell the user. The user decides if a start at server start only is sufficient.

Mark each step that the user did not do as **not verified** in the final report.

- [ ] **Step 4: Write the README**

`README.md`:

```markdown
# herdr-float

A small always-on-top window that shows the states of your Herdr agents.
For KDE Plasma on Wayland only.

## Install

    sudo pacman -S --needed pyside6 layer-shell-qt
    uv venv --system-site-packages --python /usr/bin/python3
    uv sync

## Start with Herdr

    herdr plugin link "$PWD/plugin"

The widget starts when Herdr starts. It stays on the screen after you close Herdr.
Stop it: right-click the tray icon, then "Quit".
Remove the automatic start: `herdr plugin unlink carvares.herdr-float`

## Start manually

    uv run python -m herdr_float

## Use

- The pill shows five counts: blocked, done, working, idle, unknown.
- Click the pill to open the agent list. Click an agent to go to its pane.
- Drag the pill to move it. The position is saved.
- Click the tray icon to hide or show the widget. Right-click it for the menu with "Quit".
- The tray icon colour shows the most important state that has agents.
- The pill shows "offline" when the Herdr server does not answer.

## Files

- Position: `~/.config/herdr-float/state.json`
- Log: `~/.local/state/herdr-float/herdr-float.log`

## Tests

    uv run pytest

## Limits

- Default local Herdr session only.
- The jump focuses the pane in Herdr. On Wayland it possibly does not raise the terminal window.
```

Update the "Limits" section with the result of Task 1 Step 6, and the "Start with Herdr" section with the result of Step 3.

- [ ] **Step 5: Write the Obsidian task notes**

The user's rules require two linked notes for each task. Find the vault path in `/home/carvares/.claude/projects/-home-carvares/memory/form-agents-obsidian-memory.md`. If the path is not there, ask the user.

Create in the vault:
- `herdr-float handoff.md`: goal, repository path, spec path, plan path, what is done, what is not verified, the exact commands to run and test, and the next step. Short sentences. A new agent must be able to continue from this file only.
- `herdr-float summary.md`: 5 to 8 lines on what the tool is and its status, with a `[[herdr-float handoff]]` link.

- [ ] **Step 6: Remove the spike files and run all tests**

```bash
git rm -r spike
uv run pytest -v
```

Expected: 40 passed.

- [ ] **Step 7: Commit**

```bash
git add plugin README.md
git commit -m "Add Herdr plugin wrapper and README"
```

---

### Task 10: Private GitHub repository (only when the user asks)

**Files:** none.

**Interfaces:**
- Consumes: a clean working tree on `main`.
- Produces: a private remote `origin`.

The user said: "remember to make the repo private". The user did not ask for a push. Do this task only after the user confirms.

- [ ] **Step 1: Ask the user to confirm**

Ask: "Create the private repository `carvares/bellwether` on GitHub and push `main`?" The `gh` account on this machine is `carvares`.

- [ ] **Step 2: Create the repository as private and push**

```bash
gh repo create carvares/bellwether --private --source . --remote origin --push
```

- [ ] **Step 3: Confirm that it is private**

```bash
gh repo view carvares/bellwether --json visibility,url
```

Expected: `"visibility":"PRIVATE"`.

---

## Later, not in this plan

- Push updates in place of the 1-second read. This needs one `pane.agent_status_changed` subscription for each pane, plus `pane.created` and `pane.closed` to keep the subscriptions correct. Do this only if the 1-second delay is a problem.
- A KWin script to raise the terminal window after a jump.
- A start at desktop login (systemd user service). The user decided on a plugin start.
- Other named sessions and SSH machines.
