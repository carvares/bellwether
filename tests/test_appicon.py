import logging

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from herdr_float.appicon import SIZES, find_app_icon, load_app_icon, load_source, tinted_icon
from herdr_float.tray import TrayIcons, make_icon

PLATE, GLYPH = "#f4f1e9", "#303438"
RED, BLUE = "#f28b82", "#8ab4f8"
SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect x="8" y="8" width="16" height="16"/></svg>'


def write_desktop(folder, icon_line="Icon=herdr-app"):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "herdr-app.desktop").write_text(f"[Desktop Entry]\nType=Application\nName=Herdr\n{icon_line}\n")


def write_png(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(QColor(GLYPH))
    assert image.save(str(path))
    return path


def write_svg(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SVG)
    return path


@pytest.fixture
def tree(tmp_path, app):
    """A fake system: (desktop dirs, icon dirs), with the desktop file of the app in the second desktop dir."""
    desktop = [tmp_path / "home" / "applications", tmp_path / "usr" / "applications"]
    icons = [tmp_path / "home" / "hicolor", tmp_path / "usr" / "hicolor", tmp_path / "usr" / "pixmaps"]
    write_desktop(desktop[1])
    return desktop, icons


def test_find_app_icon_prefers_an_svg_to_a_bigger_png(tree):
    desktop, icons = tree
    write_png(icons[0] / "256x256" / "apps" / "herdr-app.png", 256)
    svg = write_svg(icons[1] / "scalable" / "apps" / "herdr-app.svg")
    assert find_app_icon(desktop, icons) == svg


def test_find_app_icon_takes_the_largest_png_without_an_svg(tree):
    desktop, icons = tree
    write_png(icons[1] / "48x48" / "apps" / "herdr-app.png", 48)
    big = write_png(icons[1] / "128x128" / "apps" / "herdr-app.png", 128)
    write_png(icons[2] / "herdr-app.png", 64)
    write_png(icons[1] / "256x256" / "apps" / "other-app.png", 256)
    assert find_app_icon(desktop, icons) == big


def test_find_app_icon_finds_an_svg_in_pixmaps(tree):
    desktop, icons = tree
    assert find_app_icon(desktop, icons) is None
    svg = write_svg(icons[2] / "herdr-app.svg")
    assert find_app_icon(desktop, icons) == svg


def test_find_app_icon_follows_the_icon_name_of_the_first_desktop_file(tree):
    desktop, icons = tree
    write_desktop(desktop[0], "Icon=herdr-new")
    write_svg(icons[1] / "scalable" / "apps" / "herdr-app.svg")
    assert find_app_icon(desktop, icons) is None
    new = write_svg(icons[1] / "scalable" / "apps" / "herdr-new.svg")
    assert find_app_icon(desktop, icons) == new


def test_find_app_icon_takes_an_absolute_icon_path(tree, tmp_path):
    desktop, icons = tree
    svg = write_svg(tmp_path / "opt" / "herdr.svg")
    write_desktop(desktop[1], f"Icon={svg}")
    assert find_app_icon(desktop, icons) == svg


@pytest.mark.parametrize("line", ["", "Icon=", "Icon=../herdr-app", "Icon=sub/herdr-app", "Icon=/missing/herdr.svg"])
def test_find_app_icon_gives_none_for_a_bad_icon_entry(tree, line):
    desktop, icons = tree
    write_desktop(desktop[1], line)
    write_svg(icons[1] / "scalable" / "apps" / "herdr-app.svg")
    assert find_app_icon(desktop, icons) is None


def test_find_app_icon_gives_none_without_a_desktop_file(tmp_path, app):
    write_svg(tmp_path / "hicolor" / "scalable" / "apps" / "herdr-app.svg")
    assert find_app_icon([tmp_path / "applications"], [tmp_path / "hicolor"]) is None


def test_load_source_reads_svg_and_png_and_gives_none_for_a_bad_file(tmp_path, app):
    image = load_source(write_svg(tmp_path / "a.svg"))
    assert image is not None and not image.isNull() and image.width() == image.height()
    image = load_source(write_png(tmp_path / "a.png", 20))
    assert image is not None and image.pixelColor(image.width() // 2, image.height() // 2) == QColor(GLYPH)
    (tmp_path / "bad.svg").write_text("not an svg")
    (tmp_path / "bad.png").write_bytes(b"not a png")
    assert load_source(tmp_path / "bad.svg") is None
    assert load_source(tmp_path / "bad.png") is None
    assert load_source(tmp_path / "missing.svg") is None


def image(size, fill, square_color, square=QRect(8, 8, 16, 16)):
    """A test source: `fill` everywhere (transparent or a plate) and a square of another colour."""
    result = QImage(size, size, QImage.Format.Format_ARGB32)
    result.fill(fill)
    painter = QPainter(result)
    painter.fillRect(square, QColor(square_color))
    painter.end()
    return result


def alpha(img, x, y):
    return img.pixelColor(x, y).alpha()


def test_a_glyph_on_transparency_gets_the_colour_where_it_is_opaque(app):
    source = image(32, Qt.GlobalColor.transparent, GLYPH)
    red = tinted_icon(source, RED, 16)
    assert red.size().width() == 16
    assert red.pixelColor(8, 8) == QColor(RED)  # in the square
    assert alpha(red, 1, 1) == 0 and alpha(red, 14, 14) == 0  # outside the square
    blue = tinted_icon(source, BLUE, 16)
    assert blue.pixelColor(8, 8) == QColor(BLUE)


def test_a_picture_on_a_plate_keeps_the_plate_and_cuts_the_glyph_out(app):
    source = image(64, QColor(PLATE), GLYPH, QRect(20, 20, 24, 24))
    red = tinted_icon(source, RED, 32)
    assert red.pixelColor(5, 16) == QColor(RED)  # the plate
    assert red.pixelColor(0, 0) == QColor(RED)  # the outline of the plate
    assert alpha(red, 16, 16) == 0  # the glyph is a hole
    assert tinted_icon(source, BLUE, 32).pixelColor(5, 16) == QColor(BLUE)


def test_the_outline_of_the_plate_closes_where_the_glyph_touches_the_edge(app):
    source = image(64, QColor(PLATE), GLYPH, QRect(32, 16, 32, 48))  # the glyph reaches the right and bottom edges
    red = tinted_icon(source, RED, 32)
    assert red.pixelColor(31, 20) == QColor(RED) and red.pixelColor(24, 31) == QColor(RED)
    assert alpha(red, 24, 20) == 0


def test_tray_icons_have_every_size_and_are_made_once_for_each_colour(app):
    icons = TrayIcons(image(64, Qt.GlobalColor.transparent, GLYPH, QRect(16, 16, 32, 32)))
    icon = icons.icon(RED)
    assert icons.icon(RED) is icon
    assert sorted(s.width() for s in icon.availableSizes()) == sorted(SIZES)
    assert icon.pixmap(22).toImage().pixelColor(11, 11) == QColor(RED)
    assert icons.icon(BLUE).pixmap(22).toImage().pixelColor(11, 11) == QColor(BLUE)


def test_without_a_source_the_tray_icon_is_the_circle(app):
    icons = TrayIcons(None)
    assert icons.icon(RED).pixmap(64).toImage() == make_icon(RED).pixmap(64).toImage()


def test_load_app_icon_logs_one_line_without_a_path_when_the_icon_is_missing(tmp_path, app, caplog):
    with caplog.at_level(logging.INFO, logger="herdr_float"):
        assert load_app_icon([tmp_path / "applications"], [tmp_path / "hicolor"]) is None
    assert len(caplog.records) == 1
    assert str(tmp_path) not in caplog.records[0].getMessage()


def test_load_app_icon_logs_one_line_when_the_icon_cannot_be_read(tree, caplog):
    desktop, icons = tree
    (icons[1] / "scalable" / "apps").mkdir(parents=True)
    (icons[1] / "scalable" / "apps" / "herdr-app.svg").write_text("not an svg")
    with caplog.at_level(logging.INFO, logger="herdr_float"):
        assert load_app_icon(desktop, icons) is None
    assert len(caplog.records) == 1
    assert "herdr-app" not in caplog.records[0].getMessage()


def test_load_app_icon_gives_the_image_and_no_log(tree, caplog):
    desktop, icons = tree
    write_svg(icons[1] / "scalable" / "apps" / "herdr-app.svg")
    with caplog.at_level(logging.INFO, logger="herdr_float"):
        assert load_app_icon(desktop, icons) is not None
    assert caplog.records == []


def test_an_svg_is_clipped_by_the_rectangle_clip_path_it_uses(tmp_path, app):
    # Qt does not apply clip-path: the drawing would cover the whole square.
    svg = tmp_path / "clip.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">'
        '<defs><clipPath id="tile"><rect x="8" y="8" width="16" height="16" rx="2"/></clipPath></defs>'
        '<g clip-path="url(#tile)"><rect width="32" height="32"/></g></svg>'
    )
    image = load_source(svg)
    side = image.width()
    assert alpha(image, side // 2, side // 2) == 255
    assert alpha(image, side // 8, side // 2) == 0 and alpha(image, side - side // 8, side // 2) == 0


def test_the_plate_is_the_tone_at_the_edge_even_when_the_picture_is_bigger(app):
    source = image(64, QColor(PLATE), GLYPH, QRect(8, 8, 48, 48))  # the picture covers more than half of the plate
    red = tinted_icon(source, RED, 32)
    assert red.pixelColor(3, 16) == QColor(RED)
    assert alpha(red, 16, 16) == 0
