"""The layouts (skins) of the panel: the five approved designs, and which of them are built."""
from __future__ import annotations

import re
from pathlib import Path

DEFAULT = "C"
# Letter, name, and one line for the options window.
LAYOUTS = (
    ("A", "Refined list", "A list of the statuses with count badges."),
    ("B", "Tiles", "Four tiles with large numerals."),
    ("C", "Techno / HUD", "Monospace numerals and one cell for each agent."),
    ("D", "Signal strip", "A headline, a share bar and tabs."),
    ("E", "Ring", "A ring of the shares, with a legend."),
)
UI_PATH = Path(__file__).parent / "ui"
SKINS_PATH = UI_PATH / "skins"
# One small picture of each design for the options window: <letter>.png.
PREVIEWS_PATH = UI_PATH / "previews"


def built_skins(folder: Path = SKINS_PATH) -> dict[str, Path]:
    """The skin file of each design that is built. A design is built when its file <letter>.qml is there."""
    files = {letter: Path(folder) / f"{letter}.qml" for letter, _, _ in LAYOUTS}
    return {letter: path for letter, path in files.items() if path.is_file()}


def theme_file(skin: Path) -> Path:
    """The file with the theme tokens of a skin: <letter>Theme.qml next to <letter>.qml."""
    skin = Path(skin)
    return skin.with_name(f"{skin.stem}Theme.qml")


# The theme tokens that every <letter>Theme.qml must have: the options window reads them, and the skin uses them.
THEME_TOKENS = (
    "panelColor", "frameColor", "frameWidth", "radius", "itemRadius", "lineColor", "textColor", "dimColor",
    "faintColor", "accentColor", "selectedColor", "hoverColor", "fontFamily", "titleSize", "bodySize", "smallSize",
    "letterSpacing", "uppercaseTitles", "decoration",
)

# The token of a theme file that holds the default colour of each role that a theme has. The theme file gives the
# colour as a text, alone or in the helper of that role: `readonly property color panelColor: background("#f00b0e11")`.
_ROLE_TOKENS = {"background": "panelColor", "text": "textColor", "frame": "frameColor", "accent": "accentColor"}
# The colours of Layout C: only for a theme file that cannot be read.
FALLBACK_COLORS = {"background": "#f00b0e11", "text": "#e3e9ee", "frame": "#2b333b", "accent": "#8ab4f8"}


class ThemeColorError(ValueError):
    """A theme file that can be read has a role token whose colour is not written as `"#rrggbb"` text."""


def theme_colors(theme: Path) -> dict[str, str]:
    """The default colour of the roles background, text, frame and accent in a theme file: "#rrggbb", and
    "#aarrggbb" for the background. The backend gives them to the options window. A test compares them with the
    loaded QML theme of each layout. A file that cannot be read gives the colours of Layout C. A file that can be
    read and has a token with no colour text is an error (ThemeColorError names the token): never a silent
    colour of a different layout."""
    try:
        text = Path(theme).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return dict(FALLBACK_COLORS)
    found = {}
    for role, token in _ROLE_TOKENS.items():
        match = re.search(rf'\bproperty color {token}: (?:{role}\()?"#([0-9a-fA-F]{{6}}(?:[0-9a-fA-F]{{2}})?)"', text)
        if not match:
            raise ThemeColorError(token)
        color = match[1].lower()
        # The panel is drawn with an opacity: its colour always has the alpha, as QML shows it.
        found[role] = "#" + ("ff" + color if role == "background" and len(color) == 6 else color)
    return found
