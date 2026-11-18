"""The icon that the Herdr app shows for a program. Reads the icons folder of the app, writes only the cache."""
from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path

log = logging.getLogger("herdr_float")

CACHE_PATH = Path.home() / ".cache" / "herdr-float" / "icons"
TEXT_COLOR = "#e8eaed"  # The colour of the row text in Main.qml.
GENERIC = "agent"
# Program words of agents whose icon does not have the name of the word or of its first part.
# From the "match" lists in the program table of the app (herdr-app 2026-11).
ALIASES = {
    "agy": "antigravity",
    "github-copilot": "copilot",
    "kimicodecli": "kimi",
    "oh-my-pi": "omp",
    "qodercli": "qoder",
}
_WORD = re.compile(r"[a-z0-9][a-z0-9._+-]*")
_PAINT = re.compile(r"""\b(fill|stroke|stop-color)(\s*[=:]\s*["']?\s*)([^"';\s>]+)""", re.IGNORECASE)
_ONE_COLOUR = {"none", "currentcolor", "black", "white", "#000", "#fff", "#000000", "#ffffff"}
_ROOT = re.compile(r"<svg\b[^>]*>", re.IGNORECASE)


def app_home() -> Path:
    return Path(os.environ.get("HERDR_APP_HOME") or Path.home() / ".config" / "herdr-app")


def find_icon(app: str, folder: Path) -> Path | None:
    """The icon file for a program word: its alias, its own name, its first part, then the generic agent icon."""
    word = app.lower()
    names = [ALIASES.get(word, word), word, word.split("-")[0]] if _WORD.fullmatch(word) else []
    for name in [*names, GENERIC]:
        path = Path(folder) / f"{name}.svg"
        if path.is_file():
            return path
    return None


def is_glyph(svg: str) -> bool:
    """True for an icon of one colour: the app draws it in the text colour. False for a picture."""
    return all(match[3].lower() in _ONE_COLOUR for match in _PAINT.finditer(svg))


def tinted(svg: str, color: str) -> str:
    """The glyph with `color` in the place of the text colour, black and white."""
    def paint(match: re.Match) -> str:
        return match[0] if match[3].lower() == "none" else match[1] + match[2] + color

    svg = _PAINT.sub(paint, svg)
    root = _ROOT.search(svg)
    if root and not re.search(r"\sfill\s*=", root[0]):  # No fill: SVG draws black.
        svg = svg[: root.start() + 4] + f' fill="{color}"' + svg[root.start() + 4 :]
    return svg


class Icons:
    """Gives QML one file URL for each program word, or "" when the row must show text."""

    def __init__(self, home: Path | None = None, cache: Path = CACHE_PATH, color: str = TEXT_COLOR) -> None:
        self._folder = Path(home or app_home()) / "icons"
        self._cache = Path(cache)
        self._color = color
        self._urls: dict[str, str] = {}

    def url(self, app: str) -> str:
        if app not in self._urls:
            self._urls[app] = self._load(app)
        return self._urls[app]

    def _load(self, app: str) -> str:
        path = find_icon(app, self._folder)
        if path is None or (path.stem == GENERIC and app.lower() != GENERIC):
            log.info("no icon for program %r: %s", app[:32], "the generic icon is used" if path else "the row shows text")
        if path is None:
            return ""
        try:
            svg = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return path.as_uri()
        if not is_glyph(svg):
            return path.as_uri()
        # A black glyph does not show on the dark panel, so QML gets a copy in the text colour.
        svg = tinted(svg, self._color)
        copy = self._cache / f"{path.stem}-{hashlib.sha1(svg.encode()).hexdigest()[:12]}.svg"
        try:
            if not copy.is_file():
                self._cache.mkdir(parents=True, exist_ok=True)
                temporary = copy.with_suffix(f".{os.getpid()}.tmp")
                temporary.write_text(svg, encoding="utf-8")
                os.replace(temporary, copy)
        except OSError:
            return ""
        return copy.as_uri()
