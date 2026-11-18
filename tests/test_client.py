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
                try:
                    conn.sendall(Server.reply(request))
                except (BrokenPipeError, ConnectionResetError):
                    pass  # The client gave up (timeout test) and closed its end.

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
