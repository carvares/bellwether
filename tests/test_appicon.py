import logging

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from bellwether import appicon
from bellwether.appicon import SIZES, SOURCE_SIZE, default_dirs, find_app_icon, load_app_icon, load_source, tinted_icon
from bellwether.tray import TrayIcons, make_icon

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


def test_an_absolute_icon_path_must_be_an_svg_or_a_png_file(tree, tmp_path):
    desktop, icons = tree
    other = tmp_path / "opt" / "herdr.xpm"
    other.parent.mkdir()
    other.write_text("/* XPM */")
    write_desktop(desktop[1], f"Icon={other}")
    assert find_app_icon(desktop, icons) is None
    (tmp_path / "opt" / "folder.svg").mkdir()
    write_desktop(desktop[1], f"Icon={tmp_path / 'opt' / 'folder.svg'}")
    assert find_app_icon(desktop, icons) is None


@pytest.mark.parametrize("extension", ["svg", "png"])
def test_find_app_icon_takes_an_icon_name_with_an_extension(tree, extension):
    desktop, icons = tree
    write_desktop(desktop[1], f"Icon=herdr-app.{extension}")
    png = write_png(icons[1] / "64x64" / "apps" / "herdr-app.png", 64)
    assert find_app_icon(desktop, icons) == png
    svg = write_svg(icons[1] / "scalable" / "apps" / "herdr-app.svg")
    assert find_app_icon(desktop, icons) == svg


def test_find_app_icon_finds_an_svg_in_a_size_folder_of_the_theme(tree):
    desktop, icons = tree
    write_png(icons[1] / "256x256" / "apps" / "herdr-app.png", 256)
    svg = write_svg(icons[1] / "48x48" / "apps" / "herdr-app.svg")
    assert find_app_icon(desktop, icons) == svg
    scalable = write_svg(icons[1] / "scalable" / "apps" / "herdr-app.svg")  # the scalable folder is first
    assert find_app_icon(desktop, icons) == scalable


def test_default_dirs_has_the_home_folder_before_the_system_folders(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "mine"))
    monkeypatch.setenv("XDG_DATA_DIRS", f"{tmp_path / 'one'}::{tmp_path / 'two'}")
    desktop, icons = default_dirs()
    assert desktop == [tmp_path / n / "applications" for n in ("mine", "one", "two")]
    assert icons == [tmp_path / n / "icons" / "hicolor" for n in ("mine", "one", "two")] + [
        tmp_path / n / "pixmaps" for n in ("mine", "one", "two")
    ]
    monkeypatch.delenv("XDG_DATA_HOME")
    monkeypatch.delenv("XDG_DATA_DIRS")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    desktop, _ = default_dirs()
    assert [str(d) for d in desktop] == [
        str(tmp_path / "home" / ".local" / "share" / "applications"),
        "/usr/local/share/applications",
        "/usr/share/applications",
    ]


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
    with caplog.at_level(logging.INFO, logger="bellwether"):
        assert load_app_icon([tmp_path / "applications"], [tmp_path / "hicolor"]) is None
    assert len(caplog.records) == 1
    assert str(tmp_path) not in caplog.records[0].getMessage()


def test_load_app_icon_logs_one_line_when_the_icon_cannot_be_read(tree, caplog):
    desktop, icons = tree
    (icons[1] / "scalable" / "apps").mkdir(parents=True)
    (icons[1] / "scalable" / "apps" / "herdr-app.svg").write_text("not an svg")
    with caplog.at_level(logging.INFO, logger="bellwether"):
        assert load_app_icon(desktop, icons) is None
    assert len(caplog.records) == 1
    assert "herdr-app" not in caplog.records[0].getMessage()


def test_load_app_icon_gives_the_image_and_no_log(tree, caplog):
    desktop, icons = tree
    write_svg(icons[1] / "scalable" / "apps" / "herdr-app.svg")
    with caplog.at_level(logging.INFO, logger="bellwether"):
        assert load_app_icon(desktop, icons) is not None
    assert caplog.records == []


def test_an_svg_is_clipped_by_the_rectangle_clip_path_it_uses(tmp_path, app):
    # Qt does not apply clip-path: the drawing would cover the whole square.
    svg = tmp_path / "clip.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">'
        '<defs><clipPath id="tile"><rect x="4" y="4" width="24" height="24" rx="2"/></clipPath></defs>'
        '<g clip-path="url(#tile)"><rect width="32" height="32"/></g></svg>'
    )
    image = load_source(svg)
    side = image.width()
    assert alpha(image, side // 2, side // 2) == 255
    assert alpha(image, side // 16, side // 2) == 0 and alpha(image, side - side // 16, side // 2) == 0


def test_a_clip_that_keeps_less_than_half_of_the_drawing_is_not_the_tile(tmp_path, app):
    # The clip keeps a quarter of the drawing. A tile does not crop most of its icon, so the drawing stays whole.
    svg = tmp_path / "crop.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">'
        '<defs><clipPath id="part"><rect x="8" y="8" width="16" height="16"/></clipPath></defs>'
        '<g clip-path="url(#part)"><rect width="32" height="32"/></g></svg>'
    )
    assert appicon.CLIP_KEEPS == 0.5
    image = load_source(svg)
    side = image.width()
    assert [alpha(image, x, side // 2) for x in (side // 16, side // 2, side - side // 16)] == [255] * 3


def test_the_plate_is_the_tone_at_the_edge_even_when_the_picture_is_bigger(app):
    source = image(64, QColor(PLATE), GLYPH, QRect(8, 8, 48, 48))  # the picture covers more than half of the plate
    red = tinted_icon(source, RED, 32)
    assert red.pixelColor(3, 16) == QColor(RED)
    assert alpha(red, 16, 16) == 0


def svg_file(path, body):
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">{body}</svg>')
    return path


def test_a_clip_that_is_not_one_rectangle_and_a_clip_that_is_not_used_are_ignored(tmp_path, app):
    # A circle clip and a clip that no element uses: the drawing shows as Qt draws it, on the whole square.
    path = svg_file(
        tmp_path / "clips.svg",
        '<defs><clipPath id="round"><circle cx="16" cy="16" r="4"/></clipPath>'
        '<clipPath id="two"><rect width="4" height="4"/><rect x="8" width="4" height="4"/></clipPath>'
        '<clipPath id="unused"><rect x="12" y="12" width="8" height="8"/></clipPath></defs>'
        '<g clip-path="url(#round)"><rect width="32" height="16"/></g>'
        '<g clip-path="url(#two)"><rect y="16" width="32" height="16"/></g>',
    )
    assert appicon._rect_clips(path.read_bytes()) == []
    image = load_source(path)
    side = image.width()
    assert [alpha(image, x, y) for x in (2, side - 3) for y in (2, side - 3)] == [255] * 4


def test_a_clip_that_covers_only_a_detail_does_not_cut_the_whole_icon(tmp_path, app):
    # The clip is for the small dot. The union of the clips on the whole drawing would leave only that corner.
    path = svg_file(
        tmp_path / "detail.svg",
        '<defs><clipPath id="dot"><rect x="2" y="2" width="4" height="4"/></clipPath></defs>'
        f'<rect x="2" y="2" width="28" height="28" rx="6" fill="{PLATE}"/>'
        f'<rect x="10" y="10" width="12" height="12" fill="{GLYPH}"/>'
        f'<g clip-path="url(#dot)"><circle cx="4" cy="4" r="6" fill="{GLYPH}"/></g>',
    )
    image = load_source(path)
    side = image.width()
    assert alpha(image, side - side // 4, side - side // 4) == 255  # the plate, far from the clip
    icons = TrayIcons(image)
    red = icons.icon(RED).pixmap(32).toImage()
    assert red.pixelColor(16, 28) == QColor(RED) and alpha(red, 16, 16) == 0  # the plate and the hole of the glyph


def test_a_png_source_is_scaled_down_to_the_working_size(tmp_path, app):
    big = QImage(1024, 512, QImage.Format.Format_ARGB32)
    big.fill(QColor(GLYPH))
    assert big.save(str(tmp_path / "big.png"))
    image = load_source(tmp_path / "big.png")
    assert (image.width(), image.height()) == (SOURCE_SIZE, SOURCE_SIZE)
    assert alpha(image, SOURCE_SIZE // 2, SOURCE_SIZE // 2) == 255  # the picture, in the middle
    assert alpha(image, SOURCE_SIZE // 2, 10) == 0 and alpha(image, SOURCE_SIZE // 2, SOURCE_SIZE - 10) == 0
    small = load_source(write_png(tmp_path / "small.png", 20))  # a small picture is not made bigger
    assert small.width() == 20


def full_tile(size=64):
    result = QImage(size, size, QImage.Format.Format_ARGB32)
    result.fill(QColor(PLATE))
    return result


@pytest.mark.parametrize(
    "source",
    [
        lambda: full_tile(),  # a plate with no picture on it: the mark would be a plain square
        lambda: image(64, Qt.GlobalColor.transparent, GLYPH, QRect(30, 30, 3, 3)),  # nearly empty
        lambda: image(64, Qt.GlobalColor.transparent, GLYPH, QRect(0, 0, 0, 0)),  # empty
    ],
)
def test_a_mark_that_is_empty_or_a_plain_tile_gives_the_circle_and_one_log_line(app, caplog, source):
    with caplog.at_level(logging.INFO, logger="bellwether"):
        icons = TrayIcons(source())
    assert icons.icon(RED).pixmap(64).toImage() == make_icon(RED).pixmap(64).toImage()
    assert len(caplog.records) == 1 and "circle" in caplog.records[0].getMessage()


def test_any_failure_while_the_icon_loads_gives_the_circle_and_one_log_line(tree, caplog, monkeypatch):
    desktop, icons = tree
    secret = write_svg(icons[1] / "scalable" / "apps" / "herdr-app.svg")

    def broken(path):
        raise RuntimeError(f"cannot draw {path}")

    monkeypatch.setattr(appicon, "load_source", broken)
    with caplog.at_level(logging.INFO, logger="bellwether"):
        made = TrayIcons.load(desktop, icons)
    assert made.icon(RED).pixmap(64).toImage() == make_icon(RED).pixmap(64).toImage()
    assert len(caplog.records) == 1
    text = caplog.records[0].getMessage()
    assert "RuntimeError" in text and str(secret) not in text and "herdr-app" not in text and "cannot draw" not in text


def test_any_failure_while_the_mark_is_made_gives_the_circle_and_one_log_line(tree, caplog, monkeypatch):
    desktop, icons = tree
    write_svg(icons[1] / "scalable" / "apps" / "herdr-app.svg")

    def broken(*args):
        raise MemoryError

    monkeypatch.setattr(appicon, "mark", broken)
    with caplog.at_level(logging.INFO, logger="bellwether"):
        made = TrayIcons.load(desktop, icons)
    assert made.icon(BLUE).pixmap(64).toImage() == make_icon(BLUE).pixmap(64).toImage()
    assert len(caplog.records) == 1 and "MemoryError" in caplog.records[0].getMessage()


def test_tray_icons_load_gives_the_mark_of_a_good_icon_with_no_log(tree, caplog):
    desktop, icons = tree
    write_svg(icons[1] / "scalable" / "apps" / "herdr-app.svg")
    with caplog.at_level(logging.INFO, logger="bellwether"):
        made = TrayIcons.load(desktop, icons)
    red = made.icon(RED).pixmap(32).toImage()
    assert red.pixelColor(16, 16) == QColor(RED) and alpha(red, 2, 2) == 0  # the square of the test SVG
    assert caplog.records == []
