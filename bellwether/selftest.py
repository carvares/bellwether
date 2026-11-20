"""`python -m bellwether --self-test`: the program with made-up agents (no Herdr needed), and ONE JSON object on
stdout with the facts of its real windows. For a machine that nobody of the project can look at (the GitHub runners
of macOS and Windows).

It shows the panel for about 3 seconds, then each layout, the options window and the answer window (a made-up
prompt). Before the wait of each step it
writes one line to stderr, "self-test: shown <step>": a script can take a picture of the screen then. Then it prints
the facts and exits (0, or 1 when the panel did not load). It takes no lock, writes no log file, and reads and writes
no setting of the user: the settings file is in a temporary folder. The log lines go to stderr. Every name and text
of the agents is made up.
"""
from __future__ import annotations

import json
import logging
import re
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QtMsgType, Qt, qInstallMessageHandler, qVersion
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401  (the windows of the engine are QQuickWindows to Python)
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from . import layouts, platform
from .answer import Answer
from .backend import Backend
from .client import Screen
from .icons import Icons
from .options import Options
from .state import Agent
from .tray import Tray

# The seconds that the panel shows first, and that each later step shows.
SHOW = 3.0
STEP = 1.5
# Made-up agents: one of each status, programs with and without an icon.
AGENTS = [
    Agent("t1", "blocked", "made-up reviewer", "Main", "claude-code"),
    Agent("t2", "working", "made-up builder", "api / one", "codex"),
    Agent("t3", "working", "", "api / one", "opencode"),
    Agent("t4", "done", "made-up writer", "docs", "claude-code"),
    Agent("t5", "idle", "made-up planner", "Main", "gemini"),
    Agent("t6", "idle", "", "docs", ""),
]


# The screen of the blocked agent: a made-up permission dialog of Claude Code (the answer window shows it).
RULE = "─" * 80
PROMPT = f"""
❯ Run this made-up command: touch made-up.txt

● Creating a made-up file
  ⎿  $ touch made-up.txt

{RULE}
 Bash command
 Create a made-up file
{"╌" * 80}
 touch made-up.txt
{"╌" * 80}
 Do you want to proceed?
 ❯ 1. Yes
   2. No

 Esc to cancel · Tab to amend
"""


class MadeUpClient:
    """In the place of the Herdr client: the made-up agents, the made-up screen of the blocked one, and a jump and
    keys that do nothing."""

    def list_agents(self) -> list[Agent]:
        return list(AGENTS)

    def focus_agent(self, key: str) -> None:
        pass

    def read_screen(self, terminal: str) -> Screen:
        return Screen(PROMPT, True)

    def press(self, terminal: str, keys, late=None) -> None:
        return None

    def send_text(self, terminal: str, text: str, cancel=None) -> None:
        return None


def wait(app, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


TYPE_MASK = 0xFF  # Qt.WindowType_Mask: the type of the window; the bits above it are its hints


def flag_names(flags) -> list[str]:
    """The type of the window (for example "Tool") and the name of each hint (for example "FramelessWindowHint")."""
    value = int(flags.value if hasattr(flags, "value") else flags)
    members = Qt.WindowType.__members__.items()
    kind = [name for name, flag in members if flag.value == value & TYPE_MASK and name != "Widget"][:1]
    hints = [name for name, flag in members if flag.value > TYPE_MASK and flag.value & value == flag.value
             and bin(flag.value).count("1") == 1]
    return kind + sorted(set(hints))


def rect(r) -> list[int]:
    return [r.x(), r.y(), r.width(), r.height()]


def qt_facts(window) -> dict:
    """The facts of a window as Qt has them."""
    screen = window.screen()
    return {
        "visible": window.isVisible(),
        "exposed": window.isExposed(),
        "active": window.isActive(),
        "flags": int(window.flags().value),
        "flag_names": flag_names(window.flags()),
        "frame": rect(window.frameGeometry()),
        "geometry": rect(window.geometry()),
        "screen": None if screen is None else {"name": screen.name(), "geometry": rect(screen.geometry()),
                                               "available": rect(screen.availableGeometry()),
                                               "ratio": screen.devicePixelRatio()},
    }


def body_alpha(window) -> float | None:
    """The opacity of the colour that the body of a window draws (its item with `isFrame`), 0 to 1. A picture of the
    screen cannot tell it: the screen has no alpha."""
    items = [window.contentItem()]
    while items:
        item = items.pop()
        if item.property("isFrame"):
            return round(item.property("color").alphaF(), 3)
        items += item.childItems()
    return None


def without_home(text: str, home=None) -> str:
    """The text with the home folder of the person as "~" (a path of a checkout holds the name of a person): in each
    form a path can take in a text — the separators of Windows or forward slashes (a file URL), and any case of the
    letters (Windows paths have no case). `home`: for a test (None: the home folder of this process)."""
    home = str(Path.home() if home is None else home).rstrip("/\\")
    if len(home.strip("/\\:")) < 2:  # no home folder, or a root: nothing to hide
        return text
    for form in dict.fromkeys((home, home.replace("\\", "/"), home.replace("/", "\\"))):
        text = re.sub(re.escape(form), "~", text, flags=re.IGNORECASE)
    return text


def native_facts(window) -> dict:
    try:
        return platform.window_facts(window)
    except Exception as error:  # the facts of the system: a failure is a fact too
        return {"error": type(error).__name__}


def run(start_panel, show: float = SHOW, step: float = STEP, out=sys.stdout, err=sys.stderr) -> int:
    """`start_panel`: the load and the set-up of the panel of the program (`__main__.start_panel`)."""
    began = time.monotonic()
    log = logging.getLogger("bellwether")
    handler = logging.StreamHandler(err)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    log.addHandler(handler)
    level = log.level
    log.setLevel(logging.INFO)
    messages: list[str] = []
    # A warning of Qt can name a file of the checkout, and its path the name of a person: the home folder is "~".
    previous = qInstallMessageHandler(
        lambda kind, _context, text: messages.append(without_home(text)) if kind != QtMsgType.QtDebugMsg else None)

    def shown(name: str) -> None:
        print(f"self-test: shown {name}", file=err, flush=True)

    platform.prepare_environment()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("bellwether")
    app.setQuitOnLastWindowClosed(False)
    platform.prepare_app(app)
    facts: dict = {"system": platform.SYSTEM, "qt_platform": app.platformName(), "qt_version": qVersion()}
    with tempfile.TemporaryDirectory(prefix="bellwether-self-test-") as folder:
        backend = Backend(MadeUpClient(), settings_path=Path(folder) / "state.json",
                          icons=Icons(Path(folder) / "app", Path(folder) / "cache"))
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("backend", backend)
        facts["shell"] = start_panel(engine, app)
        tray = None
        try:
            if not engine.rootObjects():
                facts["error"] = "the QML interface did not load"
                return 1
            panel = engine.rootObjects()[0]
            backend.apply(AGENTS)
            options = Options(engine)
            facts["tray"] = {"available": QSystemTrayIcon.isSystemTrayAvailable(), "visible": False, "items": 0}
            if facts["tray"]["available"]:
                tray = Tray(backend, panel, app, options.open)
                items = tray.findChildren(QSystemTrayIcon)  # the tray items that this program made
                facts["tray"].update(items=len(items), visible=any(item.isVisible() for item in items))
            wait(app, 0.5)
            shown(f"panel-{backend.layout}")
            wait(app, show)
            # Before any normal window of the program opens: the facts of a program that shows only its panel (on
            # macOS the app must not be active then: the panel takes no focus, and the start activates nothing).
            facts["panel"] = qt_facts(panel)
            facts["native"] = native_facts(panel)
            facts["layouts"] = {}
            for letter, _slug, _name in layouts.LAYOUTS:
                backend.setLayout(letter)
                panel.setProperty("openState", "working")  # a layout with a group open: the rows show
                wait(app, 0.5)
                facts["layouts"][letter] = {"shown": backend.layout == letter, "visible": panel.isVisible(),
                                            "size": [panel.width(), panel.height()]}
                shown(f"layout-{letter}")
                wait(app, step)
            options.open()
            wait(app, 0.5)
            window = engine.rootObjects()[-1]
            facts["options"] = {**qt_facts(window), "native": native_facts(window), "body_alpha": body_alpha(window),
                                "opaque_dialogs": backend.opaqueDialogs}
            facts["panel_after_options"] = {"active": panel.isActive(), "native": native_facts(panel)}
            shown("options")
            wait(app, step)
            window.close()
            wait(app, 0.2)
            # The answer window, as the Answer control of the blocked row opens it (the prompt of a made-up screen).
            answer = Answer(engine, backend)
            backend.showAnswer("t1")
            wait(app, 0.8)
            if answer.window is None:
                facts["answer"] = {"error": "the answer window did not open"}
            else:
                facts["answer"] = {**qt_facts(answer.window), "native": native_facts(answer.window),
                                   "prompt": backend.prompt.get("state"), "body_alpha": body_alpha(answer.window),
                                   "opaque_dialogs": backend.opaqueDialogs}
                shown("answer")
                wait(app, step)
                answer.window.close()
                wait(app, 0.2)
        finally:
            facts["messages"] = messages[:20]
            facts["seconds"] = round(time.monotonic() - began, 1)
            print(json.dumps(facts, sort_keys=True), file=out, flush=True)
            del tray
            del engine
            backend.stop()
            app.processEvents()
            qInstallMessageHandler(previous)
            log.removeHandler(handler)
            log.setLevel(level)
    return 0 if "error" not in facts else 1
