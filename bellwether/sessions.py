"""The model that an agent runs and the start of its session, for the second line of an agent row.

Where the facts come from, for a terminal of this machine:
  the processes   `herdr-core get` names the first process of the terminal and the one that has it now. The process
                  host of the system gives their child processes. Only these processes are asked.
  Claude Code     `~/.claude/sessions/<pid>.json` of such a process (it must name that pid, and the start of that
                  process as the process host has it: a file that an older process with this pid left is not used).
                  It has the start of the session and the session id. The model is in the transcript of that session
                  (`~/.claude/projects/<folder>/<session id>.jsonl`): the last record of the assistant counts.
  Codex           a rollout file under `~/.codex/sessions/` that such a process has open (the process host names
                  them). Its first line has the start, and its last "turn_context" record the model. With no open
                  rollout file there is no model: a file is never chosen by its folder or its time.
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
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from .client import Failure, Terminal, valid_address
from .platform import process_host

if TYPE_CHECKING:  # The host of each system is a subclass of this one.
    from .platform.host import ProcessHost as Host

log = logging.getLogger("bellwether")

# One read from the end of a transcript, and the most that one scan of a transcript reads.
BLOCK = 64 * 1024
SCAN_LIMIT = 4 * 1024 * 1024
# The largest session file of Claude Code that is read (it has about 1 KB).
SMALL_FILE = 64 * 1024
# Seconds between two reads of the files of one agent.
REFRESH = 30.0
# Seconds between two checks with the process host that the processes of an agent still live (no command).
CHECK = 5.0
# Seconds between two `herdr-core get` of one agent whose processes live: a net for a terminal that has an other
# foreground process while the old one lives on.
GET_REFRESH = 300.0

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


def _open_regular(path: Path) -> int | str:
    """The open file number of a regular file, or a reason code: "no_file", "not_regular". The open does not wait
    (a pipe has no writer) and does not take a terminal; a pipe or a device is closed again and never read."""
    try:
        number = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY | os.O_CLOEXEC)
    except OSError:
        return "no_file"
    try:
        if stat.S_ISREG(os.fstat(number).st_mode):
            return number
    except OSError:
        pass
    os.close(number)
    return "not_regular"


def _head(path: Path, size: int) -> bytes | str:
    """At most `size` bytes from the start of a regular file, or the reason code of `_open_regular`."""
    number = _open_regular(path)
    if isinstance(number, str):
        return number
    try:
        return os.pread(number, size, 0)
    except OSError:
        return "no_file"
    finally:
        os.close(number)


def _json_file(path: Path) -> dict | str:
    """A small JSON object of a regular file, or a reason code: "no_file" (also a file that is too large or is not
    such an object), "not_regular"."""
    data = _head(path, SMALL_FILE + 1)
    if isinstance(data, str):
        return data
    if len(data) > SMALL_FILE:
        return "no_file"
    try:
        value = json.loads(data)
    except (ValueError, RecursionError):
        return "no_file"
    return value if isinstance(value, dict) else "no_file"


def _milliseconds(value: object) -> int | None:
    return value if type(value) is int and 0 < value < 2 ** 53 else None


def last_model(host: Host, path: Path, needle: bytes, pick, known: SessionFacts | None
               ) -> tuple[str | None, Mark | None]:
    """The model of the last record of the file that `pick` takes, read from the end of the file in blocks, and the
    mark of this scan. `needle`: bytes that every such record has (the other lines are not parsed). With the mark
    of an earlier scan of the same file only the part after it is read, and the model of that scan stays when the
    new part has none. None and no mark: the file cannot be read."""
    number = _open_regular(path)
    if isinstance(number, str):
        return None, None
    try:
        status = os.fstat(number)
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
    """The facts of the Claude Code process of `pids` (the foreground process first). The foreground process with a
    session file is the agent. Else the session files of all the processes count: two or more → no facts
    ("several_sessions"), as which one is the agent is not known."""
    reason, found = "no_session", []
    for index, pid in enumerate(pids):
        session = _json_file(host.home / ".claude" / "sessions" / f"{pid}.json")
        if isinstance(session, str):
            if session != "no_file":
                reason = session
            continue
        ticks = host.start_ticks(pid)
        if session.get("pid") != pid or ticks is None or str(session.get("procStart")) != ticks:
            reason = "other_process"  # the file of an older process that had this pid
            continue
        found.append((pid, session))
        if index == 0:
            break
    if len(found) > 1:
        return SessionFacts(reason="several_sessions")
    for pid, session in found:
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
    head = _head(path, 64)
    if isinstance(head, str):
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


# Codex 0.170 does not keep its rollout file open. It holds one lock file for each thread that it writes, with the
# id of the thread as its name; the rollout file of a thread has that id at the end of its name.
_THREAD_LOCK = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}(?:-[0-9a-f]{4}){2}-[0-9a-f]{12})\.lock")
# A thread of the person (not one of a helper that Codex starts: a review, a sub-agent). In the first line.
_USER_THREAD = re.compile(rb'"thread_source"\s*:\s*"user"')
THREAD_HEAD = 4096
# An argument of Codex that can give the session an other model than the one of the settings file.
_MODEL_ARGUMENTS = ("-m", "--model", "-c", "--config", "-p", "--profile", "--oss", "--local-provider")


def _thread_rollouts(host: Host, thread: str) -> list[Path]:
    """The rollout files of the thread whose first line says that it is a thread of the person. The id of a
    thread starts with its creation time, and Codex puts a rollout file in the folder of that day: only that
    folder and the days beside it are looked at."""
    try:
        made = datetime.fromtimestamp(int(thread[:8] + thread[9:13], 16) / 1000)
    except (ValueError, OverflowError, OSError):
        return []
    found = []
    for day in (made, made - timedelta(days=1), made + timedelta(days=1)):
        folder = host.home / ".codex" / "sessions" / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}"
        try:
            names = sorted(name for name in os.listdir(folder) if name.endswith(f"-{thread}.jsonl"))
        except OSError:
            continue
        for name in names:
            head = _head(folder / name, THREAD_HEAD) if _ROLLOUT.fullmatch(name) else ""
            if isinstance(head, bytes):
                host.bytes_read += len(head)
                if _USER_THREAD.search(head.split(b"\n", 1)[0]):
                    found.append(folder / name)
    return found


def _codex_default(host: Host, pid: int) -> str | None:
    """The model of the settings file of Codex, for a session that has no turn yet. None when an argument of the
    process can name an other model, a profile or a setting, and when the file has no valid model."""
    words = host.arguments(pid)
    if not words or any(word.startswith(_MODEL_ARGUMENTS) for word in words[1:]):
        return None
    data = _head(host.home / ".codex" / "config.toml", SMALL_FILE + 1)
    if isinstance(data, str) or len(data) > SMALL_FILE:
        return None
    try:
        model = tomllib.loads(data.decode()).get("model")
    except (ValueError, RecursionError):  # also a text that is not UTF-8
        return None
    return model if isinstance(model, str) and _MODEL.fullmatch(model) else None


def read_codex(host: Host, pids, known: SessionFacts | None = None) -> SessionFacts:
    """The facts of the session of the processes of `pids` (the foreground process first): of the rollout file
    that a process has open, or of the rollout file of the thread that it holds the lock of. The files of the
    foreground process count when it has one; else those of all the processes. Two or more files → no facts
    ("several_rollouts"): one is never chosen. A process that holds a thread lock and has no rollout file yet (no
    turn was made) has the model of the settings file ("config_default")."""
    sessions = str(host.home / ".codex" / "sessions") + os.sep
    locks = str(host.home / ".codex" / "thread-writer-locks") + os.sep
    found: dict[str, int] = {}  # each rollout file, and the first process that has it (open, or by a thread lock)
    threads: dict[str, int] = {}  # each thread that a process holds the lock of, and the first such process
    for index, pid in enumerate(pids):
        for name in host.open_files(pid):
            base = os.path.basename(name)
            if name.startswith(sessions) and _ROLLOUT.fullmatch(base):
                found.setdefault(name, pid)
            elif name.startswith(locks) and os.path.dirname(name) + os.sep == locks:
                lock = _THREAD_LOCK.fullmatch(base)
                if lock:
                    threads.setdefault(lock.group(1), pid)
        if (found or threads) and index == 0:
            break
    for thread, pid in threads.items():
        for path in _thread_rollouts(host, thread):
            found.setdefault(str(path), pid)
    if len(found) > 1:
        return SessionFacts(reason="several_rollouts")
    for name, pid in found.items():
        path = Path(name)
        mine = known if known is not None and known.pid == pid else None
        model, mark = last_model(host, path, b'"type":"turn_context"', _codex_model, mine)
        if mark is not None:
            return SessionFacts(model, _first_stamp(host, path), "ok" if model else "no_model", pid, mark)
    for pid in dict.fromkeys(threads.values()):
        model = _codex_default(host, pid)
        if model:
            return SessionFacts(model, None, "config_default", pid)
        break  # only the first process that holds a lock
    return SessionFacts(reason="no_session")


# The reader of each program word that the agent rows carry. `herdr-core run` names Claude Code "claude".
READERS = {"claude-code": read_claude, "claude": read_claude, "codex": read_codex}


# ----- the engine: which agent is read when -----

@dataclass
class _Entry:
    app: str
    read_at: float  # the last read of the files
    facts: SessionFacts
    got_at: float = 0.0  # the last `herdr-core get`
    terminal: Terminal | None = None  # what that get gave; None: it failed
    alive: tuple = ()  # (pid, start ticks) of each process of this machine that the facts depend on
    status: str = ""  # the status of the agent at the last look


class SessionWatch:
    """The facts of the agents of the list. `step` does the reads that are due (on a worker thread). For each agent:
    a `herdr-core get` at once when it is new in the list, has an other program word, or when a process that its
    facts depend on ended or is an other process now (checked with the process host at each step: no command), or when its
    status is an other (a program gives its terminal a new title at such a time); else one in GET_REFRESH seconds,
    as a net. `titles` gives the title of each terminal from these gets: the name of an agent with no name in
    Herdr. A title is never in a log line. The files of its processes are read each `interval` seconds, with the processes
    of the last get. `facts` gives what the rows show. Errors are reason codes: a log line has the address, the
    program word and the code, and is written when the code of an agent changes."""

    def __init__(self, client, host: Host | None = None, readers=None, clock=time.monotonic,
                 interval: float = REFRESH) -> None:
        self._client = client
        self._host = host or process_host()
        self._readers = READERS if readers is None else readers
        self._clock = clock
        self._interval = interval
        self._entries: dict[str, _Entry] = {}
        self._titles: dict[str, str] = {}
        self._lock = threading.Lock()

    def facts(self) -> dict[str, tuple[str | None, int | None]]:
        """For each agent that has facts: the model id (or None) and the start in milliseconds (or None)."""
        with self._lock:
            return {key: (entry.facts.model, entry.facts.started_ms) for key, entry in self._entries.items()}

    def titles(self) -> dict[str, str]:
        """For each agent that Herdr was asked of: the title of its terminal ("": it has none)."""
        with self._lock:
            return dict(self._titles)

    def clear(self) -> None:
        """Drop the facts: each agent is asked and read again. The titles stay until then."""
        with self._lock:
            self._entries = {}

    def wait(self) -> float:
        """Seconds until the next step: when a read is due, and at most CHECK (the check of the processes)."""
        now = self._clock()
        with self._lock:
            rests = [entry.read_at + self._interval - now for entry in self._entries.values()]
        if not rests:
            return self._interval
        return max(0.0, min(*rests, CHECK))

    def step(self, agents, stopped=lambda: False, files: bool = True) -> bool:
        """Check the processes of each agent and do the reads that are due. True when a value that the rows show is
        different. A round that ends with `stopped()` true keeps nothing of what it read. `files` False: Herdr is
        asked (for the titles) and no file of a session is read."""
        agents = [agent for agent in agents if valid_address(agent.key)]
        keys = {agent.key for agent in agents}
        with self._lock:
            before = dict(self._entries)
            titles_before = dict(self._titles)
        titles = {key: title for key, title in titles_before.items() if key in keys}
        changed = any(key not in keys and (entry.facts.model or entry.facts.started_ms)
                      for key, entry in before.items())
        after = {key: entry for key, entry in before.items() if key in keys}
        for agent in agents:
            if stopped():
                break
            entry = after.get(agent.key)
            if entry is not None and entry.app != agent.app:
                entry = None
            now = self._clock()
            if entry is None or not self._lives(entry):
                # New, or an other process now: nothing of the old process is kept, and Herdr is asked at once.
                terminal, known = None, None
            elif entry.terminal is None:  # the last get failed
                if now - entry.read_at < self._interval:
                    continue
                terminal, known = None, entry.facts
            elif now - entry.got_at >= GET_REFRESH or entry.status != agent.status:
                terminal, known = None, entry.facts
            elif not files:
                continue
            elif now - entry.read_at >= self._interval:
                terminal, known = entry.terminal, entry.facts
            else:
                continue
            got_at = entry.got_at if entry is not None else 0.0
            if terminal is None:
                answer = self._client.terminal(agent.key)
                got_at = self._clock()
                if isinstance(answer, Failure):
                    facts = SessionFacts(reason=answer.code)
                else:
                    terminal = answer
                    titles[agent.key] = answer.title
            if terminal is not None:
                facts = self._read(agent, terminal, known) if files else SessionFacts(reason="off")
            shown = entry.facts if entry is not None else None
            if shown is None or shown.reason != facts.reason:
                log.info("session facts terminal=%s app=%s reason=%s", agent.key, agent.app or "-", facts.reason)
            changed = changed or shown is None or (shown.model, shown.started_ms) != (facts.model, facts.started_ms)
            after[agent.key] = _Entry(agent.app, self._clock(), facts, got_at, terminal,
                                      self._alive(agent, terminal, facts), agent.status)
        with self._lock:
            if stopped():  # the setting changed, or the app quits, during the round
                return False
            self._entries = after
            self._titles = titles
        return changed or titles != titles_before

    def _alive(self, agent, terminal: Terminal | None, facts: SessionFacts) -> tuple:
        """The processes to check at each step: the foreground process of the terminal (or its first process) and
        the process of the facts, with their start ticks. None for an agent of an other machine."""
        if terminal is None or "/" in agent.key:
            return ()
        pids = dict.fromkeys(pid for pid in (terminal.foreground or terminal.pid, facts.pid) if pid > 0)
        return tuple((pid, self._host.start_ticks(pid)) for pid in pids)

    def _lives(self, entry: _Entry) -> bool:
        """Each process of the entry is still there, and is the same process (the same start). One small read of
        the process host for each; a process that could not be read at the last read counts as the same while it still cannot."""
        return all(self._host.start_ticks(pid) == ticks for pid, ticks in entry.alive)

    def _read(self, agent, terminal: Terminal, known: SessionFacts | None) -> SessionFacts:
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
