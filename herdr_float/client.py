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
