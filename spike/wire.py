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
