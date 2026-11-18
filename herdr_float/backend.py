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
