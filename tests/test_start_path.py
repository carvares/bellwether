"""The parts of the start path that must work on every system (Windows too): the log file, the text encodings, the
reads of the session files without os.pread, and the wait for the event stream through the platform."""
import json
import logging
import os

from bellwether import __main__ as start
from bellwether import events, sessions, settings


def test_a_rotation_that_fails_keeps_the_file_and_still_writes_the_line(tmp_path, monkeypatch):
    """Windows: a file that an other process has open cannot be renamed. The line is not lost."""
    path = tmp_path / "bellwether.log"
    handler = start.LogFile(path)
    handler.maxBytes = 50
    handler.setFormatter(logging.Formatter("%(message)s"))
    try:
        def refused(source, dest):
            raise PermissionError(13, "made-up: the file is open in an other process")

        monkeypatch.setattr(handler, "rotate", refused)
        for number in range(4):
            handler.emit(logging.makeLogRecord({"msg": f"made-up line {number} ........................"}))
        assert path.read_text(encoding="utf-8").splitlines() == [
            f"made-up line {number} ........................" for number in range(4)]
        assert not (tmp_path / "bellwether.log.1").exists()
        monkeypatch.undo()  # the file can be renamed again: the next line rotates
        handler.emit(logging.makeLogRecord({"msg": "made-up line 4 ✓"}))
        assert (tmp_path / "bellwether.log.1").exists()
        assert path.read_text(encoding="utf-8") == "made-up line 4 ✓\n"
    finally:
        handler.close()


def test_the_log_file_is_utf_8_and_keeps_one_older_file(tmp_path):
    handler = start.LogFile(tmp_path / "x.log")
    try:
        assert (handler.encoding, handler.maxBytes, handler.backupCount) == ("utf-8", 512_000, 1)
    finally:
        handler.close()


def test_the_settings_file_is_utf_8_whatever_the_locale(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    written = []
    real = type(path).write_text

    def write_text(self, data, encoding=None, errors=None, newline=None):
        written.append(encoding)
        return real(self, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(type(path), "write_text", write_text)
    settings._write(path, {"screen": "made-up ✓"})
    assert written == ["utf-8"]
    assert json.loads(path.read_bytes().decode("utf-8")) == {"screen": "made-up ✓"}
    path.write_bytes('{"screen": "made-up é"}'.encode("utf-8"))
    assert settings._load(path) == {"screen": "made-up é"}


def test_the_open_flags_of_a_session_file_are_those_of_linux_here_and_bytes_on_windows():
    wanted = os.O_RDONLY
    for name in ("O_NONBLOCK", "O_NOCTTY", "O_CLOEXEC", "O_BINARY", "O_NOINHERIT"):
        wanted |= getattr(os, name, 0)
    assert sessions._OPEN_FLAGS == wanted
    if hasattr(os, "O_NONBLOCK"):
        assert sessions._OPEN_FLAGS == os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY | os.O_CLOEXEC


def test_without_pread_a_transcript_is_read_the_same_way(tmp_path, monkeypatch):
    """Windows has no os.pread: a seek and a read give the same bytes and the same model, CR LF and Ctrl-Z too."""
    path = tmp_path / "made-up.jsonl"
    lines = [json.dumps({"type": "assistant", "message": {"model": f"made-up-{n}"}}, separators=(",", ":"))
             for n in range(3)]
    path.write_bytes(("\r\n".join(lines) + "\n\x1a" + "x" * 10 + "\n").encode())
    host = type("Host", (), {"bytes_read": 0})()
    found = sessions.last_model(host, path, b'"type":"assistant"', sessions._claude_model, None)
    monkeypatch.setattr(sessions, "_pread", sessions._seek_read)
    assert sessions.last_model(host, path, b'"type":"assistant"', sessions._claude_model, None)[0] == found[0]
    assert found[0] == "made-up-2"
    assert sessions._head(path, 5) == lines[0][:5].encode()


def test_the_event_source_waits_through_the_wait_of_the_platform(monkeypatch):
    """No select of its own (select takes no pipe on Windows): the platform gives the wait."""
    asked = []
    monkeypatch.setattr(events, "readable", lambda descriptors, timeout: asked.append((len(descriptors), timeout)) or [])

    class Child:
        def __init__(self):
            self.read_end, self.write_end = os.pipe()
            self.stdout = os.fdopen(self.read_end, "rb", buffering=0)

    child = Child()
    source = events.EventSource(["made-up"], lambda: None, quiet=0.01)
    try:
        assert source._follow(child, 0.0, announce=True) is False  # nothing came in the quiet time
        assert asked == [(2, 0.01)]
    finally:
        child.stdout.close()
        os.close(child.write_end)
        for descriptor in source._stop_pipe:
            os.close(descriptor)
