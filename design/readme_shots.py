"""Makes the pictures of the README in docs/images/ from the real interface (the QML files of the program).

Off screen only: no window opens on the desktop, and nothing of a real terminal is read. The agents, their names,
their models and the questions are made up (the questions are the test fixtures in tests/fixtures/prompts). The
program icons come from the icons folder of the Herdr app at render time (read-only).

Run from the repository root:  uv run python design/readme_shots.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_SCALE_FACTOR"] = "2"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

from bellwether.icons import Icons  # noqa: E402
from bellwether.options import Options  # noqa: E402
from bellwether.state import STATE_COLORS, Agent  # noqa: E402
from bellwether.tray import TrayIcons  # noqa: E402
from tests.test_answer_window import Desk  # noqa: E402
from tests.test_backend_prompt import shown  # noqa: E402
from tests.test_options_look import click, swatch  # noqa: E402
from tests.test_qml import settle  # noqa: E402

OUT = ROOT / "docs" / "images"
SCALE = 2
NOW = 1_795_100_000.0
MINUTE, HOUR, DAY = 60_000, 3_600_000, 86_400_000
SANS = "Adwaita Sans"

# (address, status, name in Herdr, space / tab, program, title of the terminal, model id, age of the session)
CAST = [
    ("t1", "blocked", "", "shop-api", "claude-code", "Add retry to the payment client", "claude-fable-5-2", 2 * HOUR + 14 * MINUTE),
    ("t2", "blocked", "reviewer", "shop-api / Review", "codex", "", "gpt-5.2-codex", 38 * MINUTE),
    ("t3", "done", "", "docs-site", "claude-code", "Rewrite the install guide", "claude-opus-5-5", 51 * MINUTE),
    ("t4", "working", "", "shop-web", "claude-code", "Fix the cart badge count", "claude-sonnet-5-5", 14 * MINUTE),
    ("t5", "working", "migrator", "data-tools", "codex", "", "gpt-5.2-codex", 3 * DAY + 2 * HOUR),
    ("t6", "working", "", "mobile-app", "claude-code", "Dark mode for the settings page", "claude-fable-5-2", 6 * HOUR + 3 * MINUTE),
    ("t7", "idle", "", "infra", "claude-code", "Tidy the deploy module", "claude-haiku-5-5", 1 * DAY + 5 * HOUR),
    ("t8", "idle", "scratch", "sandbox", "gemini", "", None, 9 * MINUTE),
]
AGENTS = [Agent(key, status, name, where, program) for key, status, name, where, program, *_ in CAST]
LETTERS = "ABCDE"
LAYOUT_NAMES = {"A": "A · Refined list", "B": "B · Tiles", "C": "C · Techno / HUD", "D": "D · Signal strip", "E": "E · Ring"}


class Watch:
    """In the place of the SessionWatch: the made-up titles, models and ages of the cast. No read."""

    def facts(self):
        return {key: (model, int(NOW * 1000) - age) for key, *_, model, age in CAST}

    def titles(self):
        return {row[0]: row[5] for row in CAST}

    def clear(self):
        pass

    def wait(self):
        return 30.0

    def step(self, agents, stopped=None, files=True):
        return False


def cast(**status: str) -> list[Agent]:
    """The cast, with an other status for some agents (cast(t1="working")); "" takes the agent out."""
    return [Agent(a.key, status.get(a.key, a.status), a.name, a.workspace, a.app) for a in AGENTS
            if status.get(a.key, a.status)]


def desk(folder: Path, letter: str = "C", agents: list[Agent] | None = None, **look) -> Desk:
    """The panel with the cast, the real program icons and a layout."""
    agents = AGENTS if agents is None else agents
    one = Desk(app, folder, agents, sessions=Watch(), now=lambda: NOW)
    one.backend._icons = Icons(cache=folder / "icons")
    one.backend.setLayout(letter)
    for name, value in look.items():
        if name == "colors":
            for role, colour in value.items():
                assert one.backend.setColor(role, colour) is True
        else:
            assert getattr(one.backend, "set" + name[0].upper() + name[1:])(value) is True
    one.backend.apply(list(agents))
    one.backend.changed.emit()
    settle(app)
    return one


def grab(window) -> QImage:
    settle(app)
    image = window.grabWindow()
    image.setDevicePixelRatio(SCALE)
    return image


def size(image: QImage) -> tuple[float, float]:
    return image.width() / SCALE, image.height() / SCALE


def backdrop(width: float, height: float) -> tuple[QImage, QPainter]:
    """A dark desktop for the windows: a README page can be light or dark, and the panel is partly clear."""
    image = QImage(round(width * SCALE), round(height * SCALE), QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(SCALE)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    shade = QLinearGradient(0, 0, width, height)
    shade.setColorAt(0, QColor("#232a36"))
    shade.setColorAt(1, QColor("#15181e"))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, width, height), 14, 14)
    painter.fillPath(path, shade)
    return image, painter


def caption(painter: QPainter, x: float, y: float, width: float, text: str) -> None:
    font = QFont(SANS)
    font.setPixelSize(13)
    font.setWeight(QFont.Weight.DemiBold)
    painter.setFont(font)
    painter.setPen(QColor("#aeb6c2"))
    painter.drawText(QRectF(x, y, width, 20), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, text)


def sheet(shots: list[tuple[str, QImage]], pad: float = 28, gap: float = 24) -> QImage:
    """The shots in one row, each with its caption ("" for none), on the dark desktop."""
    titled = any(text for text, _ in shots)
    top = pad + (26 if titled else 0)
    width = 2 * pad + sum(size(i)[0] for _, i in shots) + gap * (len(shots) - 1)
    height = top + max(size(i)[1] for _, i in shots) + pad
    image, painter = backdrop(width, height)
    x = pad
    for text, shot in shots:
        if text:
            caption(painter, x, pad - 6, size(shot)[0], text)
        painter.drawImage(QRectF(x, top, *size(shot)), shot)
        x += size(shot)[0] + gap
    painter.end()
    return image


def save(image: QImage, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    assert image.save(str(OUT / name)), name
    print(f"{name}: {image.width()} x {image.height()}")


def panel_shot(folder: Path, letter: str, group: str | None, agents: list[Agent] | None = None,
               offline: bool = False, **look) -> QImage:
    one = desk(folder, letter, agents, **look)
    if offline:
        one.backend.apply(None)
        settle(app)
    if group:
        one.open_group(group)
    image = grab(one.root)
    one.close()
    return image


def answer_shot(folder: Path, fixture: str, key: str = "t1", letter: str = "C") -> QImage:
    one = desk(folder, letter)
    one.client.screens = [shown(fixture)]
    window = one.answer_for(key, quiet=None)
    one.arm()
    image = grab(window)
    one.backend.closePrompt()
    settle(app)
    one.close()
    return image


def options_shot(folder: Path, letter: str = "C", edit: str = "") -> QImage:
    """The options window; `edit`: with the colour editor of that colour open."""
    one = desk(folder, letter)
    options = Options(one.engine)
    options.open()
    settle(app)
    window = one.engine.rootObjects()[-1]
    window.setProperty("roomHeight", 1080)
    if edit:
        settle(app)
        click(app, window, swatch(window, edit))
        settle(app)
    image = grab(window)
    window.close()
    one.close()
    return image


def tray_shot() -> QImage:
    icons = TrayIcons.load()
    states = [("blocked", "Blocked"), ("done", "Done"), ("idle", "Idle"), ("working", "Working")]
    cell, pad = 120, 24
    image, painter = backdrop(2 * pad + cell * len(states), 2 * pad + 78)
    for index, (state, text) in enumerate(states):
        x = pad + index * cell
        painter.drawPixmap(QRectF(x + (cell - 44) / 2, pad, 44, 44).toRect(), icons.icon(STATE_COLORS[state]).pixmap(88, 88))
        caption(painter, x, pad + 56, cell, text)
    painter.end()
    return image


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        count = iter(range(1000))

        def folder() -> Path:
            made = Path(temp) / str(next(count))
            made.mkdir()
            return made

        custom = {"blocked": "#ff5555", "done": "#f1fa8c", "working": "#8be9fd", "idle": "#50fa7b",
                  "background": "#282a36", "text": "#f8f8f2", "frame": "#6272a4", "accent": "#bd93f9"}
        quiet = cast(t1="working", t2="working", t3="idle")
        save(sheet([("", panel_shot(folder(), "C", "blocked", scale=1.25))], pad=36), "hero.png")
        # What the frame says: the most important status that has an agent.
        save(sheet([("An agent waits for you", panel_shot(folder(), "C", None)),
                    ("An agent finished", panel_shot(folder(), "C", None, cast(t1="working", t2="working"))),
                    ("All agents work or rest", panel_shot(folder(), "C", None, quiet)),
                    ("Herdr does not answer", panel_shot(folder(), "C", None, offline=True))]), "states.png")
        save(sheet([("", panel_shot(folder(), "A", "blocked", scale=1.25))], pad=36), "rows.png")
        # The three steps of an answer.
        save(sheet([("1 · A blocked agent has an Answer button", panel_shot(folder(), "C", "blocked")),
                    ("2 · Choose an option", answer_shot(folder(), "claude-ask-3")),
                    ("3 · The agent works again", panel_shot(folder(), "C", "working", cast(t1="working")))], gap=28),
             "answer-flow.png")
        save(sheet([("A permission for a command", answer_shot(folder(), "claude-bash")),
                    ("A file edit, with its diff", answer_shot(folder(), "claude-edit-diff"))], gap=28), "answer.png")
        save(sheet([(LAYOUT_NAMES[letter], panel_shot(folder(), letter, None)) for letter in LETTERS]), "layouts.png")
        for letter in LETTERS:
            save(sheet([("Closed", panel_shot(folder(), letter, None, scale=1.15)),
                        ("A status open", panel_shot(folder(), letter, "blocked", scale=1.15)),
                        ("A different status open", panel_shot(folder(), letter, "working", scale=1.15))]),
                 f"layout-{letter.lower()}.png")
        save(sheet([("", options_shot(folder()))], pad=36), "options.png")
        save(sheet([("", options_shot(folder(), edit="blocked"))], pad=36), "options-colour.png")
        save(tray_shot(), "tray.png")
        save(sheet([("Layout B, custom colours", panel_shot(folder(), "B", "working", colors=custom)),
                    ("Layout E, custom colours, size 125 %", panel_shot(folder(), "E", "blocked", colors=custom, scale=1.25))]),
             "custom-look.png")


if __name__ == "__main__":
    main()
