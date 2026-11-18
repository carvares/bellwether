"""The layouts (skins) of the panel: the five approved designs, and which of them are built."""
from __future__ import annotations

from pathlib import Path

DEFAULT = "C"
# Letter, name, and one line for the options window.
LAYOUTS = (
    ("A", "Refined list", "The four statuses as a list with count badges."),
    ("B", "Tiles", "A grid of four tiles with large numerals."),
    ("C", "Techno / HUD", "Monospace numerals, corner brackets, one cell for each agent."),
    ("D", "Signal strip", "A headline, one share bar and the statuses as tabs."),
    ("E", "Ring", "A ring with the share of each status, and a legend."),
)
UI_PATH = Path(__file__).parent / "ui"
SKINS_PATH = UI_PATH / "skins"
# One small picture of each design for the options window: <letter>.png.
PREVIEWS_PATH = UI_PATH / "previews"


def built_skins(folder: Path = SKINS_PATH) -> dict[str, Path]:
    """The skin file of each design that is built. A design is built when its file <letter>.qml is there."""
    files = {letter: Path(folder) / f"{letter}.qml" for letter, _, _ in LAYOUTS}
    return {letter: path for letter, path in files.items() if path.is_file()}
