"""The model that an agent runs and the start of its session, for the second line of an agent row.

Where the facts come from, for a terminal of this machine:
  the processes   `herdr-core get` names the first process of the terminal and the one that has it now. /proc gives
                  their child processes. Only these processes are asked.
  Claude Code     `~/.claude/sessions/<pid>.json` of such a process (it must name that pid, and the start of that
                  process as /proc has it: a file that an older process with this pid left is not used). It has the
                  start of the session and the session id. The model is in the transcript of that session
                  (`~/.claude/projects/<folder>/<session id>.jsonl`): the last record of the assistant counts.
  Codex           a rollout file under `~/.codex/sessions/` that such a process has open (/proc/<pid>/fd). Its first
                  line has the start, and its last "turn_context" record the model. With no open rollout file there
                  is no model: a file is never chosen by its folder or its time.
A model is a fact only when it was read for that process. With no start of a session, the engine uses the creation
time of the terminal.

The files of a session are private. This module takes two things from them: the model id (checked by its form) and
time stamps. It logs nothing of a file, puts nothing of a file in an error, and writes no file. A transcript is read
from its end in blocks, and never more than SCAN_LIMIT bytes in one read; a file that did not grow is not read again.
"""
from __future__ import annotations

import json
import logging
import os
import re
import stat
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .client import Failure, valid_address

log = logging.getLogger("bellwether")

# One read from the end of a transcript, and the most that one scan of a transcript reads.
BLOCK = 64 * 1024
SCAN_LIMIT = 4 * 1024 * 1024
# The largest session file of Claude Code that is read (it has about 1 KB).
SMALL_FILE = 64 * 1024
# The most processes of one terminal that are asked.
MAX_PROCESSES = 32
# The most threads of one process whose child processes are read.
MAX_TASKS = 256
# Seconds between two reads of the facts of one agent.
REFRESH = 30.0

# A model id: letters, digits and the marks of the known ids ("claude-opus-5-5", "gpt-5.2-codex",
# "us.anthropic.claude-opus-4-1-20250805-v1:0", "claude-opus-5-5[1m]"). Any other text is not a model.
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@\[\]-]{0,79}")
_SESSION_ID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_ROLLOUT = re.compile(r"rollout-[0-9T-]{19}-[0-9a-f-]{36}\.jsonl")
_FIRST_STAMP = re.compile(rb'\{"timestamp":"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?)Z"')


# ----- the text of the line -----

_FAMILY = re.compile(r"claude-([a-z]+)-(\d{1,2})(?:-(\d{1,2}))?(?:-\d{8})?(?:-latest)?")
_FAMILY_LAST = re.compile(r"claude-(\d{1,2})(?:-(\d{1,2}))?-([a-z]+)(?:-\d{8})?(?:-latest)?")
SHORT_LIMIT = 32


def short_model(raw: object) -> str:
    """The model id in the short form of the line: "claude-opus-5-5" is "Opus 5.5", "gpt-5.2-codex" is
    "GPT-5.2-codex". An id that is not known stays as it is (at most SHORT_LIMIT characters). "" only for no id."""
    if not isinstance(raw, str) or not raw.strip():
        return ""
    text = raw.strip()
    window = re.search(r"\[(\d+[km])\]$", text, re.IGNORECASE)  # "[1m]": the large context window
    if window:
        text = text[:window.start()]
    text = text.rsplit("/", 1)[-1]  # "anthropic/claude-…"
    text = re.sub(r"^(?:[a-z]{2,6}\.)?anthropic\.", "", text)  # "us.anthropic.claude-…"
    text = re.sub(r"(?:-v\d+:\d+|@\d{8})$", "", text)  # "…-v1:0", "…@20250514"
    name = text
    found = _FAMILY.fullmatch(text.lower())
    if found:
        name = found.group(1).capitalize() + " " + ".".join(filter(None, found.group(2, 3)))
    else:
        found = _FAMILY_LAST.fullmatch(text.lower())
        if found:
            name = found.group(3).capitalize() + " " + ".".join(filter(None, found.group(1, 2)))
        elif text.lower().startswith("gpt-"):
            name = "GPT-" + text[4:]
    name = name or raw.strip()
    if len(name) > SHORT_LIMIT:
        name = name[:SHORT_LIMIT - 1] + "…"
    return name + (" " + window.group(1).upper() if window else "")


def _parts(seconds: float) -> tuple[int, int, int]:
    minutes = max(0, int(seconds // 60))
    return minutes // 1440, minutes % 1440 // 60, minutes % 60


def age_text(seconds: float) -> str:
    """The age of a session: "<1m", "14m", "2h 14m", "2h", "3d 2h", "3d". Whole units, never rounded up."""
    days, hours, minutes = _parts(seconds)
    if days:
        return f"{days}d {hours}h" if hours else f"{days}d"
    if hours:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    return f"{minutes}m" if minutes else "<1m"


def age_words(seconds: float) -> str:
    """The same age for a screen reader: "less than 1 minute", "2 hours 14 minutes", "3 days 2 hours"."""
    def count(n: int, word: str) -> str:
        return f"{n} {word}" if n == 1 else f"{n} {word}s"

    days, hours, minutes = _parts(seconds)
    if days:
        return count(days, "day") + (" " + count(hours, "hour") if hours else "")
    if hours:
        return count(hours, "hour") + (" " + count(minutes, "minute") if minutes else "")
    return count(minutes, "minute") if minutes else "less than 1 minute"


# ----- this machine: the home folder and /proc -----

class Host:
    """The home folder of the user and /proc. A test gives its own folders. `bytes_read` counts what was read of
    transcripts and rollout files."""

    def __init__(self, home: Path | None = None, proc: Path = Path("/proc")) -> None:
        self.home = Path(os.path.realpath(home if home is not None else Path.home()))
        self.proc = Path(proc)
        self.bytes_read = 0

    def start_ticks(self, pid: int) -> str | None:
        """The start of the process as /proc has it (field 22 of `stat`, in clock ticks since the boot)."""
        try:
            text = (self.proc / str(pid) / "stat").read_text(errors="replace")
        except OSError:
            return None
        fields = text.rsplit(")", 1)[-1].split()  # the name of a process can have spaces and brackets
        return fields[19] if len(fields) > 19 and fields[19].isdigit() else None

    def children(self, pid: int) -> list[int]:
        found: list[int] = []
        try:
            tasks = sorted((self.proc / str(pid) / "task").iterdir())
        except OSError:
            return found
        for task in tasks[:MAX_TASKS]:
            try:
                found += [int(word) for word in (task / "children").read_text().split() if word.isdigit()]
            except OSError:
                continue
        return found

    def family(self, *pids: int):
        """These processes and then their child processes, the nearest first, each one time, at most
        MAX_PROCESSES. One at a time: the child processes are read only when a reader asks for more."""
        order = [pid for pid in dict.fromkeys(pids) if pid > 0]
        at = 0
        while at < len(order) and at < MAX_PROCESSES:
            yield order[at]
            order += [child for child in self.children(order[at]) if child not in order]
            at += 1

    def open_files(self, pid: int) -> list[str]:
        """The files that the process has open (the names only)."""
        found = []
        try:
            numbers = list((self.proc / str(pid) / "fd").iterdir())
        except OSError:
            return found
        for number in numbers[:4096]:
            try:
                found.append(os.readlink(number))
            except OSError:
                continue
        return found


# ----- the facts -----

@dataclass(frozen=True)
class Mark:
    """Where the last scan of a transcript ended: which file, and its size then. Nothing of its content."""
    path: str = field(repr=False)  # the name of a private file: not in the text form
    device: int = 0
    inode: int = 0
    size: int = 0


@dataclass(frozen=True)
class SessionFacts:
    model: str | None = None  # the model id as the program wrote it
    started_ms: int | None = None  # the start of the session, in milliseconds since 1970
    reason: str = "ok"  # a reason code: what was found, or why not
    pid: int = 0  # the process that the facts are of
    mark: Mark | None = field(default=None, repr=False)


def _json_file(path: Path) -> dict | None:
    """A small JSON object of a file. None for no file, a file that is too large, and anything else."""
    try:
        with open(path, "rb") as file:
            data = file.read(SMALL_FILE + 1)
    except OSError:
        return None
    if len(data) > SMALL_FILE:
        return None
    try:
        value = json.loads(data)
    except (ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _milliseconds(value: object) -> int | None:
    return value if type(value) is int and 0 < value < 2 ** 53 else None


def last_model(host: Host, path: Path, needle: bytes, pick, known: SessionFacts | None
               ) -> tuple[str | None, Mark | None]:
    """The model of the last record of the file that `pick` takes, read from the end of the file in blocks, and the
    mark of this scan. `needle`: bytes that every such record has (the other lines are not parsed). With the mark
    of an earlier scan of the same file only the part after it is read, and the model of that scan stays when the
    new part has none. None and no mark: the file cannot be read."""
    try:
        number = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        return None, None
    try:
        status = os.fstat(number)
        if not stat.S_ISREG(status.st_mode):
            return None, None
        size = status.st_size
        mark = Mark(str(path), status.st_dev, status.st_ino, size)
        before = known.mark if known is not None else None
        same = (before is not None and (before.path, before.device, before.inode) == (mark.path, mark.device, mark.inode)
                and before.size <= size)
        if same and before.size == size:
            return known.model, mark
        floor = 0
        # The older part is not read again when the new part starts at the start of a line.
        if same and before.size > 0 and os.pread(number, 1, before.size - 1) == b"\n":
            floor = before.size
        stop = max(floor, size - SCAN_LIMIT)
        at, rest = size, b""
        while at > stop:
            start = max(stop, at - BLOCK)
            data = os.pread(number, at - start, start)
            host.bytes_read += len(data)
            lines = (data + rest).split(b"\n")
            # The first piece is the end of a line that starts before this block, but at the start of the file
            # and at the mark.
            whole = start == 0 or start == floor
            rest = b"" if whole else lines[0]
            for line in reversed(lines if whole else lines[1:]):
                model = _model_of(line, needle, pick)
                if model is not None:
                    return model, mark
            at = start
        return (known.model if same else None), mark  # a file that only grew: the model of before stays
    except OSError:
        return None, None
    finally:
        os.close(number)


def _model_of(line: bytes, needle: bytes, pick) -> str | None:
    if needle not in line:
        return None
    try:
        record = json.loads(line)
        model = pick(record) if isinstance(record, dict) else None
    except (ValueError, RecursionError, AttributeError, TypeError, LookupError):
        return None
    return model if isinstance(model, str) and _MODEL.fullmatch(model) else None


# ----- Claude Code -----

def _claude_model(record: dict) -> object:
    """The model of a record of the assistant. Not of a sub-agent (a side chain): it can run an other model."""
    if record.get("type") != "assistant" or record.get("isSidechain") is True:
        return None
    return record["message"].get("model")


def read_claude(host: Host, pids, known: SessionFacts | None = None) -> SessionFacts:
    reason = "no_session"
    for pid in pids:
        session = _json_file(host.home / ".claude" / "sessions" / f"{pid}.json")
        if session is None:
            continue
        ticks = host.start_ticks(pid)
        if session.get("pid") != pid or ticks is None or str(session.get("procStart")) != ticks:
            reason = "other_process"  # the file of an older process that had this pid
            continue
        started = _milliseconds(session.get("startedAt"))
        session_id, folder = session.get("sessionId"), session.get("cwd")
        if not isinstance(session_id, str) or not _SESSION_ID.fullmatch(session_id):
            return SessionFacts(None, started, "no_transcript", pid)
        projects = host.home / ".claude" / "projects"
        path = projects / re.sub(r"[^A-Za-z0-9]", "-", folder if isinstance(folder, str) else "") / f"{session_id}.jsonl"
        if not path.is_file():
            path = next(iter(sorted(projects.glob(f"*/{session_id}.jsonl"))), None)
            if path is None:
                return SessionFacts(None, started, "no_transcript", pid)
        mine = known if known is not None and known.pid == pid else None
        model, mark = last_model(host, path, b'"type":"assistant"', _claude_model, mine)
        if model is None and mine is not None and mark is not None:
            model = mine.model  # a new session of the same process (after "/clear") with no answer yet
        return SessionFacts(model, started, "ok" if model else "no_model" if mark else "no_transcript", pid, mark)
    return SessionFacts(reason=reason)


# ----- Codex -----

def _codex_model(record: dict) -> object:
    return record["payload"].get("model") if record.get("type") == "turn_context" else None


def _first_stamp(host: Host, path: Path) -> int | None:
    """The time of the first line of a rollout file (UTC), from its first bytes."""
    try:
        with open(path, "rb") as file:
            head = file.read(64)
    except OSError:
        return None
    host.bytes_read += len(head)
    found = _FIRST_STAMP.match(head)
    if not found:
        return None
    try:
        moment = datetime.fromisoformat(found.group(1).decode() + "+00:00")
    except ValueError:
        return None
    return _milliseconds(int(moment.timestamp() * 1000))


def read_codex(host: Host, pids, known: SessionFacts | None = None) -> SessionFacts:
    root = str(host.home / ".codex" / "sessions") + os.sep
    for pid in pids:
        for name in host.open_files(pid):
            if not name.startswith(root) or not _ROLLOUT.fullmatch(os.path.basename(name)):
                continue
            path = Path(name)
            mine = known if known is not None and known.pid == pid else None
            model, mark = last_model(host, path, b'"type":"turn_context"', _codex_model, mine)
            if mark is None:
                continue
            return SessionFacts(model, _first_stamp(host, path), "ok" if model else "no_model", pid, mark)
    return SessionFacts(reason="no_session")


# The reader of each program word that the agent rows carry. `herdr-core run` names Claude Code "claude".
READERS = {"claude-code": read_claude, "claude": read_claude, "codex": read_codex}


# ----- the engine: which agent is read when -----

@dataclass
class _Entry:
    app: str
    read_at: float
    facts: SessionFacts


class SessionWatch:
    """The facts of the agents of the list. `step` does the reads that are due (on a worker thread): for each agent
    at most one `herdr-core get` in `interval` seconds, at once for an agent that is new in the list or has an
    other program word, and the files of its processes. `facts` gives what the rows show. Errors are reason codes:
    a log line has the address, the program word and the code, and is written when the code of an agent changes."""

    def __init__(self, client, host: Host | None = None, readers=None, clock=time.monotonic,
                 interval: float = REFRESH) -> None:
        self._client = client
        self._host = host or Host()
        self._readers = READERS if readers is None else readers
        self._clock = clock
        self._interval = interval
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def facts(self) -> dict[str, tuple[str | None, int | None]]:
        """For each agent that has facts: the model id (or None) and the start in milliseconds (or None)."""
        with self._lock:
            return {key: (entry.facts.model, entry.facts.started_ms) for key, entry in self._entries.items()}

    def clear(self) -> None:
        with self._lock:
            self._entries = {}

    def wait(self) -> float:
        """Seconds until the next read is due."""
        now = self._clock()
        with self._lock:
            rests = [entry.read_at + self._interval - now for entry in self._entries.values()]
        return max(0.0, min(rests, default=self._interval))

    def step(self, agents, stopped=lambda: False) -> bool:
        """Read the agents that are due. True when a value that the rows show is different."""
        agents = [agent for agent in agents if valid_address(agent.key)]
        keys = {agent.key for agent in agents}
        with self._lock:
            before = dict(self._entries)
        changed = any(key not in keys and (entry.facts.model or entry.facts.started_ms)
                      for key, entry in before.items())
        after = {key: entry for key, entry in before.items() if key in keys}
        for agent in agents:
            if stopped():
                break
            entry = after.get(agent.key)
            if entry is not None and entry.app == agent.app and self._clock() - entry.read_at < self._interval:
                continue
            known = entry.facts if entry is not None and entry.app == agent.app else None
            facts = self._read(agent, known)
            if known is None or known.reason != facts.reason:
                log.info("session facts terminal=%s app=%s reason=%s", agent.key, agent.app or "-", facts.reason)
            changed = changed or known is None or (known.model, known.started_ms) != (facts.model, facts.started_ms)
            after[agent.key] = _Entry(agent.app, self._clock(), facts)
        with self._lock:
            self._entries = after
        return changed

    def _read(self, agent, known: SessionFacts | None) -> SessionFacts:
        terminal = self._client.terminal(agent.key)
        if isinstance(terminal, Failure):
            return SessionFacts(reason=terminal.code)
        created = terminal.created_ms or None
        if "/" in agent.key:  # an agent of an other machine: its processes and its files are not here
            return SessionFacts(None, created, "remote")
        reader = self._readers.get(agent.app)
        if reader is None:
            return SessionFacts(None, created, "no_reader")
        try:
            facts = reader(self._host, self._host.family(terminal.foreground, terminal.pid), known)
        except Exception:  # No text of the error: it can hold what a file has.
            return SessionFacts(None, created, "reader_error")
        if facts.started_ms is None:
            facts = SessionFacts(facts.model, created, facts.reason, facts.pid, facts.mark)
        return facts
