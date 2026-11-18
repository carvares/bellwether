"""Qt object between the Herdr client and the QML interface."""
from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from .client import HerdrError, HerdrOffline
from .settings import DEFAULT_PATH, load_position, save_position
from .state import ATTENTION, STATES, Agent, count_states, top_state

log = logging.getLogger("bellwether")

# Seconds between two reads while the event stream is healthy. The changes come as events, so these reads
# only repair a missed one. With no healthy stream, `interval` (one second) is used.
SLOW_INTERVAL = 2.0
# The shortest time from the start of one read to the start of the next read that an event starts.
# Titles can change ten times each second while an agent works: this keeps the reads at four each second.
FLOOR = 0.25
# After a wake: the waits before more reads. The app shows some changes up to 0.5 s (one time 1.5 s) later
# than herdr-core tells of them. The reads come 0.15, 0.4, 0.55, 1.0 and 1.6 s after the read of the wake.
AFTER = (0.15, 0.25, 0.15, 0.45, 0.6)


def _natural(address: str) -> list:
    """A sort key that reads the numbers of an address as numbers: "t2" is before "t10"."""
    # The split gives text and numbers in turn: the parts at the odd places are the numbers.
    return [int(part) if place % 2 else part for place, part in enumerate(re.split(r"(\d+)", address))]


class Backend(QObject):
    changed = Signal()
    focusFailed = Signal(str, str)
    openingChanged = Signal()
    _snapshot = Signal(object)
    _focusDone = Signal()

    def __init__(self, client, interval: float = 1.0, settings_path: Path = DEFAULT_PATH, icons=None,
                 events=None, slow_interval: float = SLOW_INTERVAL, floor: float = FLOOR,
                 after: tuple[float, ...] = AFTER, clock=time.monotonic, wait=None) -> None:
        super().__init__()
        self._clock = clock
        # wait(event, seconds) waits for a threading.Event and returns True when it is set. Tests give
        # a clock and a wait that use no real time.
        self._wait = wait or (lambda event, seconds: event.wait(seconds))
        self._client = client
        self._icons = icons  # None: the agent rows show text and no icon.
        self._interval = interval  # seconds between two reads when no event stream tells of changes
        self._slow_interval = slow_interval  # the same, while the event stream is healthy
        self._floor = floor
        self._after = after
        self._settings_path = Path(settings_path)
        self._agents: list[Agent] = []
        self._online = False
        self._stop = threading.Event()
        self._wake = threading.Event()
        # `events` makes the event source from the function that starts a read now. None: reads by time only.
        self._events = events(self._wake.set) if events else None
        self._thread: threading.Thread | None = None
        self._last_failure: str | None = None
        self._opening = ""  # the key of the agent that a jump is going to; "" when no jump runs
        self._saved = load_position(self._settings_path) or (-1, -1, "")
        self._snapshot.connect(self.apply)
        self._focusDone.connect(self._set_opening)

    # ----- properties for QML -----

    @Property(bool, notify=changed)
    def online(self) -> bool:
        return self._online

    @Property("QVariantList", notify=changed)
    def counters(self) -> list[dict]:
        counts = count_states(self._agents)
        return [{"state": s, "count": counts[s], "attention": s in ATTENTION} for s in STATES]

    @Property("QVariantList", notify=changed)
    def groups(self) -> list[dict]:
        """The four states in display order, each with its agents."""
        return [
            {
                "state": s,
                "label": s.capitalize(),
                "count": sum(a.status == s for a in self._agents),
                "attention": s in ATTENTION,
                "agents": self._rows([a for a in self._agents if a.status == s]),
            }
            for s in STATES
        ]

    def _rows(self, agents: list[Agent]) -> list[dict]:
        """The agent rows of one group. A row with an icon does not show the program word."""
        rows = []
        for a in agents:
            icon = self._icons.url(a.app) if self._icons else ""
            spoken = "Go to " + (", ".join(filter(None, (a.name, a.app))) or a.key)
            rows.append({
                "key": a.key,
                "icon": icon,
                "label": a.name or (a.workspace if icon else a.app) or a.key,
                "detail": a.workspace if a.name or not icon else "",
                "address": "",
                "spoken": spoken + (f" in {a.workspace}" if a.workspace else ""),
            })
        # Agents with a name first, then the order of the text that shows, then the address (t2 before t10).
        named = {a.key for a in agents if a.name}
        rows.sort(key=lambda row: (row["key"] not in named, row["label"].lower(), _natural(row["key"])))
        looks = [(row["icon"], row["label"], row["detail"]) for row in rows]
        for row, look in zip(rows, looks):
            if looks.count(look) > 1 and row["label"] != row["key"]:
                row["address"] = row["key"]  # Rows that look the same: the address tells them apart.
        return rows

    @Property(str, notify=changed)
    def topState(self) -> str:
        """What the border and the tray dot show: "offline", "none", or the most important state with an agent."""
        return top_state(self._online, count_states(self._agents))

    @Property(str, notify=openingChanged)
    def opening(self) -> str:
        return self._opening

    @Property(int, constant=True)
    def savedX(self) -> int:
        return self._saved[0]

    @Property(int, constant=True)
    def savedY(self) -> int:
        return self._saved[1]

    @Property(str, constant=True)
    def savedScreen(self) -> str:
        """The name of the screen of the saved position. "" when the file has no screen (an older version)."""
        return self._saved[2]

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
            agents = self._client.list_agents()
        except Exception as exc:  # any failure means offline; the poll thread must not end
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
        if self._events is not None:
            self._events.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._events is not None:
            self._events.stop()  # Ends the child process of the event stream.
        if self._thread is not None:
            self._thread.join(timeout=3)

    def _run(self) -> None:
        after: tuple[float, ...] = ()  # the waits before the reads that follow a wake and are not done yet
        while not self._stop.is_set():
            began = self._clock()
            # Clear before the read: a wake that comes during the read starts the next read at once.
            # Many wakes during one read start one read: there is never a queue of reads.
            self._wake.clear()
            self._snapshot.emit(self.fetch())
            # A stop() that came before the clear above is seen here, so the thread does not wait one interval.
            if self._stop.is_set():
                break
            if after:
                seconds, after = after[0], after[1:]
            elif self._events is not None and self._events.healthy():
                seconds = self._slow_interval  # The stream tells of each change: this read is only a net.
            else:
                seconds = self._interval
            if self._wait(self._wake, seconds):
                # The app can show a change a short time after herdr-core tells of it: read again later.
                after = self._after
                # A stream that never stops must not start reads without a pause.
                rest = self._floor - (self._clock() - began)
                if rest > 0:
                    self._wait(self._stop, rest)

    # ----- actions from QML -----

    @Slot(str)
    def focus(self, key: str) -> None:
        if self._opening:
            return  # One jump at a time: a second click must not start the app a second time.
        self._set_opening(key)
        threading.Thread(target=self.focus_now, args=(key,), daemon=True).start()

    @Slot()
    def _set_opening(self, key: str = "") -> None:
        if key != self._opening:
            self._opening = key
            self.openingChanged.emit()

    def focus_now(self, key: str) -> None:
        """Run one jump. Runs on its own thread: the start of the app can take some seconds."""
        try:
            self._client.focus_agent(key)
            log.info("focus ok agent=%s", key)
        except HerdrError as exc:
            log.warning("focus failed agent=%s code=%s", key, exc.code)
            self.focusFailed.emit(key, exc.message or exc.code)
        except HerdrOffline:
            log.warning("focus failed agent=%s offline", key)
            self.focusFailed.emit(key, "Herdr is offline")
        except Exception as exc:  # The class name only: the text of an error can hold command output.
            log.warning("focus failed agent=%s error=%s", key, type(exc).__name__)
            self.focusFailed.emit(key, "jump failed")
        finally:
            self._focusDone.emit()
            self._wake.set()

    @Slot(int, int)
    @Slot(int, int, str)
    def savePosition(self, x: int, y: int, screen: str = "") -> None:
        try:
            save_position(x, y, self._settings_path, screen)
        except OSError:
            log.warning("position was not saved")
