"""The README and the reference page: each picture and each page that they link to is in the repository."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = [ROOT / "README.md", ROOT / "docs" / "reference.md"]
_LINK = re.compile(r'(?:src="|\]\()([^")#\s]+)')


def local_links(page: Path) -> list[str]:
    return [link for link in _LINK.findall(page.read_text(encoding="utf-8")) if "://" not in link]


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_each_local_link_of_a_page_is_a_file(page):
    missing = [link for link in local_links(page) if not (page.parent / link).is_file()]
    assert missing == []


def test_the_readme_shows_each_picture_of_the_folder_and_each_has_a_text_for_a_screen_reader():
    text = PAGES[0].read_text(encoding="utf-8")
    shown = set(re.findall(r'src="docs/images/([^"]+)"', text))
    assert shown == {p.name for p in (ROOT / "docs" / "images").glob("*.png")} and len(shown) >= 8
    assert len(re.findall(r'<img [^>]*alt="[^"]{20,}"', text)) == len(re.findall(r"<img ", text))


def test_each_heading_link_of_the_readme_is_a_heading():
    text = PAGES[0].read_text(encoding="utf-8")
    slugs = {re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-") for h in re.findall(r"^#+ (.+)$", text, re.M)}
    assert [a for a in re.findall(r"\]\(#([^)]+)\)", text) if a not in slugs] == []
