"""Qt object between the Herdr client and the QML interface."""
from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QFontDatabase

from . import layouts
from .client import HerdrError, HerdrOffline, valid_address
from .icons import TEXT_COLOR
from .prompt_session import FOLLOW, PROMPT_FLOOR, SENT_SECONDS, PromptSession
from .settings import (
    COLOR_ROLES, DEFAULT_LOOK, DEFAULT_PATH, FONT_SCALE_LIMITS, FONT_SCALE_STEP, OPACITY_LIMITS, OPACITY_STEP,
    SCALE_LIMITS, SCALE_STEP, clamped, load_layout, load_look, load_position, save_layout, save_look, save_position,
    save_screen, valid_color)
from .state import ATTENTION, STATE_COLORS, STATES, Agent, count_states, top_state

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
# Milliseconds from the last change of the custom look to its save: a slider that moves writes the file one time.
LOOK_SAVE_DELAY = 400
def _natural(address: str) -> list:
    """A sort key that reads the numbers of an address as numbers: "t2" is before "t10"."""
    # The split gives text and numbers in turn: the parts at the odd places are the numbers.
    return [int(part) if place % 2 else part for place, part in enumerate(re.split(r"(\d+)", address))]


class Backend(QObject):
    changed = Signal()
    focusFailed = Signal(str, str)
    openingChanged = Signal()
    layoutChanged = Signal()
    # The custom look. colorsChanged: one of the colour maps is different (also after a change of the layout).
    scaleChanged = Signal()
    fontScaleChanged = Signal()
    fontFamilyChanged = Signal()
    colorsChanged = Signal()
    lookIsCustomChanged = Signal()
    # The answer to a blocked agent: the value `prompt` or the flag `answering` is different.
    promptChanged = Signal()
    _snapshot = Signal(object)
    _focusDone = Signal()

    def __init__(self, client, interval: float = 1.0, settings_path: Path = DEFAULT_PATH, icons=None,
                 events=None, slow_interval: float = SLOW_INTERVAL, floor: float = FLOOR,
                 after: tuple[float, ...] = AFTER, clock=time.monotonic, wait=None,
                 skins: dict[str, Path] | None = None, families: list[str] | None = None,
                 prompt_floor: float = PROMPT_FLOOR, follow: tuple[float, ...] = FOLLOW,
                 pending_follow: tuple[float, ...] | None = None, sent_seconds: float = SENT_SECONDS) -> None:
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
        # The skin file of each layout that can show. Tests give their own.
        self._skins = layouts.built_skins() if skins is None else skins
        self._layout = load_layout(self._settings_path)
        # The layout of the file. It is not the layout that shows after a skin did not load.
        self._saved_layout = self._layout
        if layouts.DEFAULT not in self._skins:
            log.error("the skin file of the default layout %s is missing: the panel cannot show", layouts.DEFAULT)
        if self._layout is None:
            self._layout = layouts.DEFAULT  # a file of an older version, or no file
        elif self._layout not in self._skins:
            # Not the saved text: a file that a person changed can hold anything.
            log.warning("the saved layout is not available: the layout is %s", layouts.DEFAULT)
            self._layout = layouts.DEFAULT
        # The font families that the user can choose. None: the list of the system, read at its first use.
        self._families = families
        self._theme_colors_of: dict[Path, dict[str, str]] = {}  # theme file -> its default colours
        self._look, ignored = load_look(self._settings_path)
        # The keys of the look that changed and are not saved yet: "scale", "fontScale", "fontFamily", "colors"
        # (every colour) and "colors.<role>". Only these go to the file.
        self._unsaved: set[str] = set()
        if self._look["fontFamily"] and self._look["fontFamily"] not in self.fontFamilies:
            self._look["fontFamily"] = ""
            ignored.append("fontFamily")
        if ignored:  # The keys only: a file that a person changed can hold anything.
            log.warning("the saved custom look has values that cannot be used: %s", ", ".join(ignored))
        self._look_timer = QTimer(self)
        self._look_timer.setSingleShot(True)
        self._look_timer.setInterval(LOOK_SAVE_DELAY)
        self._look_timer.timeout.connect(self._save_look)
        self._tint_icons()
        self.layoutChanged.connect(self.colorsChanged)  # the default colours are those of the layout that shows
        self._snapshot.connect(self.apply)
        self._focusDone.connect(self._set_opening)
        # ----- the answer to one blocked agent (see "the prompt" below) -----
        self._session = PromptSession(
            client, self._agent, self._blocked_agent, lambda agent: self._rows([agent])[0], self._wake.set,
            self._stop.is_set, clock, self._wait, prompt_floor, follow, pending_follow, sent_seconds, parent=self)
        self._session.changed.connect(self.promptChanged)

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
                # The row can open the answer window: the agent is blocked and its key is a terminal address.
                "canAnswer": a.status == "blocked" and valid_address(a.key),
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

    @Property(str, notify=layoutChanged)
    def layout(self) -> str:
        """The letter of the layout that the panel shows."""
        return self._layout

    @Property(QUrl, notify=layoutChanged)
    def skinSource(self) -> QUrl:
        """The skin file of the layout."""
        return QUrl.fromLocalFile(str(self._skins[self._layout])) if self._layout in self._skins else QUrl()

    def _theme(self) -> Path | None:
        """The theme file of the layout: <letter>Theme.qml next to the skin. A skin with no theme file gets the
        theme of the default layout. None when that has none too."""
        for letter in (self._layout, layouts.DEFAULT):
            if letter in self._skins:
                theme = layouts.theme_file(self._skins[letter])
                if theme.is_file():
                    return theme
        return None

    @Property(QUrl, notify=layoutChanged)
    def themeSource(self) -> QUrl:
        """The theme tokens of the layout, for the options window. Empty when there is no theme file."""
        theme = self._theme()
        return QUrl.fromLocalFile(str(theme)) if theme else QUrl()

    @Property("QVariantList", constant=True)
    def layouts(self) -> list[dict]:
        """The five designs for the options window. `built` False: the design cannot be chosen yet."""
        return [
            {
                "id": letter,
                "name": name,
                "description": description,
                "built": letter in self._skins,
                "preview": QUrl.fromLocalFile(str(layouts.PREVIEWS_PATH / f"{letter}.png")),
            }
            for letter, name, description in layouts.LAYOUTS
        ]

    # ----- the custom look, for QML -----

    @Property(float, notify=scaleChanged)
    def scale(self) -> float:
        """The size of the whole panel: 1 is the size of the design."""
        return self._look["scale"]

    @Property(float, constant=True)
    def scaleMin(self) -> float:
        return SCALE_LIMITS[0]

    @Property(float, constant=True)
    def scaleMax(self) -> float:
        return SCALE_LIMITS[1]

    @Property(float, constant=True)
    def scaleDefault(self) -> float:
        return DEFAULT_LOOK["scale"]

    @Property(float, constant=True)
    def scaleStep(self) -> float:
        """The step of the size slider of the options window."""
        return SCALE_STEP

    @Property(float, notify=fontScaleChanged)
    def fontScale(self) -> float:
        """The size of every text against the size that its layout gives it."""
        return self._look["fontScale"]

    @Property(float, constant=True)
    def fontScaleMin(self) -> float:
        return FONT_SCALE_LIMITS[0]

    @Property(float, constant=True)
    def fontScaleMax(self) -> float:
        return FONT_SCALE_LIMITS[1]

    @Property(float, constant=True)
    def fontScaleDefault(self) -> float:
        return DEFAULT_LOOK["fontScale"]

    @Property(float, constant=True)
    def fontScaleStep(self) -> float:
        """The step of the text size slider of the options window."""
        return FONT_SCALE_STEP

    @Property(float, constant=True)
    def opacityMin(self) -> float:
        """The least opacity of the background that the slider of the options window gives."""
        return OPACITY_LIMITS[0]

    @Property(float, constant=True)
    def opacityMax(self) -> float:
        return OPACITY_LIMITS[1]

    @Property(float, constant=True)
    def opacityStep(self) -> float:
        """The step of the opacity slider of the background."""
        return OPACITY_STEP

    @Property(bool, notify=lookIsCustomChanged)
    def lookIsCustom(self) -> bool:
        """A value of the look is not its default: "Reset to defaults" has something to do."""
        return self._look != DEFAULT_LOOK

    @Property(str, notify=fontFamilyChanged)
    def fontFamily(self) -> str:
        """The font family of every layout and of the options window. "": each layout has its own font."""
        return self._look["fontFamily"]

    @Property("QStringList", constant=True)
    def fontFamilies(self) -> list[str]:
        """The font families that setFontFamily() takes, sorted, each one time: the fonts of the system that can
        have any size and that have the Latin letters (so no symbol, emoji or bitmap font)."""
        if self._families is None:
            self._families = sorted(
                {family for family in QFontDatabase.families()
                 if not QFontDatabase.isPrivateFamily(family) and QFontDatabase.isSmoothlyScalable(family)
                 and QFontDatabase.WritingSystem.Latin in QFontDatabase.writingSystems(family)},
                key=str.casefold)
        return self._families

    @Property("QStringList", constant=True)
    def colorRoles(self) -> list[str]:
        """The colours that the user can change, in the order of the options window."""
        return list(COLOR_ROLES)

    def _theme_colors(self) -> dict[str, str]:
        """The colours of the theme file of the layout that shows. A theme file with a colour that cannot be read
        is an error of the program: the log says it one time for the file, and the options window gets the
        colours of Layout C so that it still works."""
        theme = self._theme() or Path()
        if theme not in self._theme_colors_of:
            try:
                self._theme_colors_of[theme] = layouts.theme_colors(theme)
            except layouts.ThemeColorError as error:
                log.error("the theme file %s has no colour that can be read for %s", theme.name, error)
                self._theme_colors_of[theme] = dict(layouts.FALLBACK_COLORS)
        return self._theme_colors_of[theme]

    @Property("QVariantMap", notify=colorsChanged)
    def defaultColors(self) -> dict[str, str]:
        """The colour of each role with no custom look, for the layout that shows: role -> "#rrggbb" (the
        background: "#aarrggbb", with the opacity of the layout)."""
        return {**{state: STATE_COLORS[state] for state in STATES}, **self._theme_colors()}

    @Property("QVariantMap", notify=colorsChanged)
    def colorOverrides(self) -> dict[str, str]:
        """Only the roles that the user changed: role -> colour, as it is saved (a background "#rrggbb" has no
        opacity of its own). ThemeBase.qml applies them to the theme tokens."""
        return dict(self._look["colors"])

    @Property("QVariantMap", notify=colorsChanged)
    def colors(self) -> dict[str, str]:
        """The colour of each role as it is drawn now: the custom colour, or the default of the layout. The
        background is always "#aarrggbb": a custom "#rrggbb" has the opacity of the layout that shows."""
        colors = {**self.defaultColors, **self._look["colors"]}
        if len(colors["background"]) == 7:
            colors["background"] = self.defaultColors["background"][:3] + colors["background"][1:]
        return colors

    @Property("QVariantMap", notify=colorsChanged)
    def stateColors(self) -> dict[str, str]:
        """The colour of each state as it applies now, with "offline" and "none": for the panel and the tray."""
        return {**STATE_COLORS, **{state: color for state, color in self._look["colors"].items() if state in STATES}}

    # ----- state -----

    @Slot(object)
    def apply(self, agents: list[Agent] | None) -> None:
        """Apply a snapshot. None means that Herdr is offline."""
        online = agents is not None
        agents = agents or []
        if online != self._online or agents != self._agents:
            self._online = online
            self._agents = agents
            self.changed.emit()
        self._session.tick()

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
        self._session.finish()  # the question and the screen text do not stay in memory; a held text is killed
        if self._events is not None:
            self._events.stop()  # Ends the child process of the event stream.
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._look_timer.stop()
        if self._unsaved:  # A change of the look that waits for its save, or whose save failed.
            self._save_look()

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

    # ----- the prompt: the answer to one blocked agent (bellwether/prompt_session.py) -----
    # The names for QML stay on the backend: the property `prompt`, the flag `answering`, the signal `promptChanged`,
    # and the slots openPrompt, answer, answerText and closePrompt.

    @Property("QVariantMap", notify=promptChanged)
    def prompt(self) -> dict:
        """The open prompt for the answer window. Every key is always there."""
        return self._session.value()

    @Property(bool, notify=promptChanged)
    def answering(self) -> bool:
        """An answer is on its way, or may still arrive: a second one is ignored."""
        return self._session.answering

    def _agent(self, key: str) -> Agent | None:
        return next((a for a in self._agents if a.key == key), None)

    def _blocked_agent(self, key: str) -> Agent | None:
        """The agent of the list with this key, when Herdr is there and the agent is blocked."""
        agent = self._agent(key)
        return agent if self._online and agent is not None and agent.status == "blocked" else None

    @Slot(str)
    def openPrompt(self, key: str) -> None:
        """Open the prompt of the agent row with this key. A key that is not in the list does nothing."""
        self._session.open(key)

    @Slot()
    def closePrompt(self) -> None:
        """Close the prompt and drop the question and the screen text."""
        self._session.close()

    @Slot(str, result=bool)
    def answer(self, key: str) -> bool:
        """Press the key of one option of the shown prompt. True: the answer started. False: it is refused."""
        return self._session.answer(key)

    @Slot(str, result=bool)
    def answerText(self, text: str) -> bool:
        """Answer the shown prompt with a text, when it has a text entry. True: the answer started."""
        return self._session.answer_text(text)

    @Slot(int, int)
    @Slot(int, int, str)
    def savePosition(self, x: int, y: int, screen: str = "") -> None:
        try:
            save_position(x, y, self._settings_path, screen)
        except OSError:
            log.warning("position was not saved")

    @Slot(str)
    def saveScreen(self, screen: str) -> None:
        """Save the screen of a panel that is at its default corner. The file then has no place, so the panel
        is at the default corner again at the next start."""
        try:
            save_screen(screen, self._settings_path)
        except OSError:
            log.warning("position was not saved")

    @Slot(str)
    def setLayout(self, layout: str) -> None:
        """Show a different layout now, and save it. A layout that is not built is ignored."""
        if layout not in self._skins:
            return
        if layout != self._layout:
            self._layout = layout
            log.info("layout: %s", layout)
            self.layoutChanged.emit()
        if layout != self._saved_layout:  # also the layout that shows after a different one did not load
            self._saved_layout = layout
            try:
                save_layout(layout, self._settings_path)
            except OSError:
                log.warning("layout was not saved")

    @Slot()
    @Slot(str)
    def skinFailed(self, reason: str = "unknown") -> None:
        """The skin file of the layout did not load: show the default layout now. The saved layout stays, so
        a later start tries it again. `reason` is the status of the QML loader, never a path."""
        if self._layout == layouts.DEFAULT:
            log.error("the layout %s did not load (%s)", self._layout, reason)
            return
        log.error("the layout %s did not load (%s): the layout is %s", self._layout, reason, layouts.DEFAULT)
        self._layout = layouts.DEFAULT
        self.layoutChanged.emit()

    # ----- the custom look: actions from QML -----
    # Each slot checks its value, applies it at once, and saves it a moment later (LOOK_SAVE_DELAY after the last
    # change, and when the program stops). It returns True when the value is accepted (also when nothing changes)
    # and False for a value that is not valid: nothing changes then.

    @Slot(float, result=bool)
    def setScale(self, scale: float) -> bool:
        """The size of the whole panel. A number out of the limits is clamped. Two decimal places."""
        return self._set_number("scale", scale, self.scaleChanged)

    @Slot(float, result=bool)
    def setFontScale(self, scale: float) -> bool:
        """The size of every text against its design. A number out of the limits is clamped. Two decimal places."""
        return self._set_number("fontScale", scale, self.fontScaleChanged)

    def _set_number(self, key: str, value: float, signal) -> bool:
        number = clamped(key, value)
        if number is None:
            return False
        self._change(key, number, signal)
        return True

    @Slot(str, result=bool)
    def setFontFamily(self, family: str) -> bool:
        """One family of fontFamilies, or "" for the font of each layout."""
        if family and family not in self.fontFamilies:
            return False
        self._change("fontFamily", family, self.fontFamilyChanged)
        return True

    @Slot(str, str, result=bool)
    def setColor(self, role: str, color: str) -> bool:
        """One colour: a role of colorRoles and "#rrggbb" (the background also "#aarrggbb")."""
        color = valid_color(role, color)
        if color is None:
            return False
        self._change("colors", {**self._look["colors"], role: color}, self.colorsChanged, f"colors.{role}")
        return True

    @Slot(str, result=bool)
    def resetColor(self, role: str) -> bool:
        """One colour back to the default of the layout."""
        if role not in COLOR_ROLES:
            return False
        colors = {r: c for r, c in self._look["colors"].items() if r != role}
        self._change("colors", colors, self.colorsChanged, f"colors.{role}")
        return True

    @Slot()
    def resetLook(self) -> None:
        """Everything back to the defaults: the scale, the font scale, the font family and every colour. The file
        then has none of the four keys (also not a value of them that this version or this system cannot use)."""
        if not self.lookIsCustom:
            return
        for key, signal in (("scale", self.scaleChanged), ("fontScale", self.fontScaleChanged),
                            ("fontFamily", self.fontFamilyChanged), ("colors", self.colorsChanged)):
            self._change(key, type(DEFAULT_LOOK[key])(DEFAULT_LOOK[key]), signal)
        self._unsaved = set(DEFAULT_LOOK)

    def _change(self, key: str, value, signal, unsaved: str = "") -> None:
        """Apply one value of the look now and save it later. `unsaved`: what the save writes (the key itself, or
        one colour of "colors")."""
        if value == self._look[key]:
            return
        custom = self.lookIsCustom
        self._look[key] = value
        self._unsaved.add(unsaved or key)
        self._tint_icons()
        signal.emit()
        if custom != self.lookIsCustom:
            self.lookIsCustomChanged.emit()
        self._look_timer.start()  # again from the start: the save comes after the last change of a burst

    def _tint_icons(self) -> None:
        """The glyph icons of the programs have the text colour of the user. Not the text colour of a layout: with
        no custom colour they have one colour in every layout."""
        if self._icons is None:
            return
        before = self._icons.color
        self._icons.set_color(self._look["colors"].get("text", TEXT_COLOR))
        if self._icons.color != before:
            self.changed.emit()  # the rows have new icon files

    def _save_look(self) -> None:
        """Write the values that changed since the last save. Only these: the rest of the file stays."""
        unsaved, self._unsaved = self._unsaved, set()
        try:
            save_look(self._look, self._settings_path, unsaved)
        except OSError:
            self._unsaved |= unsaved  # the next save (a change, or the stop) writes them with its own
            log.warning("the custom look was not saved")
