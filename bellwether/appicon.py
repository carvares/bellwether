"""The icon of the installed Herdr app as a mark of one colour, for the tray. Read at run time; writes nothing."""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from xml.etree import ElementTree

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QPainterPath
from PySide6.QtSvg import QSvgRenderer

log = logging.getLogger("bellwether")

DESKTOP_FILE = "herdr-app.desktop"
SIZES = (16, 22, 24, 32, 44, 48, 64)  # The tray takes the size it needs, at 1x and 2x.
SOURCE_SIZE = 256  # An SVG is drawn at this size one time and a bigger PNG is scaled down to it.
CLIP_KEEPS = 0.5  # A clip that keeps less than this part of the drawing is a clip for a detail, not for the tile.
# A usable mark covers this part of its square: less is nearly empty, more is a plain square.
MARK_COVER = (0.03, 0.97)
MARK_HOLE = 0.02  # On a plate, the picture that is cut out is at least this part of the square.
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")
_ARGB = QImage.Format.Format_ARGB32
_SVG_NS = "{http://www.w3.org/2000/svg}"


def default_dirs() -> tuple[list[Path], list[Path]]:
    """The XDG folders of desktop files and of icons (hicolor theme, then pixmaps)."""
    home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    system = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    data = [Path(home), *(Path(d) for d in system.split(":") if d)]
    return [d / "applications" for d in data], [d / "icons" / "hicolor" for d in data] + [d / "pixmaps" for d in data]


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _icon_entry(desktop_dirs) -> str | None:
    """The Icon= value of the first herdr-app.desktop (the one the desktop uses)."""
    for folder in desktop_dirs:
        try:
            text = (Path(folder) / DESKTOP_FILE).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        group = None
        for line in map(str.strip, text.splitlines()):
            if line.startswith("["):
                group = line
            elif group == "[Desktop Entry]" and line.startswith("Icon="):
                return line[len("Icon="):].strip() or None
        return None
    return None


def find_app_icon(desktop_dirs, icon_dirs) -> Path | None:
    """The icon file of the Herdr app: an SVG if one exists, else the largest PNG.

    An absolute Icon= path is taken only when it is an existing .svg or .png file.
    """
    entry = _icon_entry(desktop_dirs)
    if entry is None:
        return None
    if entry.startswith("/"):
        path = Path(entry)
        return path if path.suffix.lower() in (".svg", ".png") and _is_file(path) else None
    if not _NAME.fullmatch(entry):
        return None
    if entry.lower().endswith((".svg", ".png", ".xpm")):
        entry = entry[:-4]  # Some desktop files give the name with an extension. The desktop ignores it.
    svgs, pngs = [], []
    for folder in map(Path, icon_dirs):
        svgs.append(folder / "scalable" / "apps" / f"{entry}.svg")
        try:
            svgs += sorted(folder.glob(f"*/apps/{entry}.svg"))  # An SVG in a size folder, for example 48x48.
            pngs += sorted(folder.glob(f"*/apps/{entry}.png"))
        except OSError:
            pass
        svgs.append(folder / f"{entry}.svg")
        pngs.append(folder / f"{entry}.png")
    for path in svgs:
        if _is_file(path):
            return path
    sized = [(QImageReader(str(path)).size().width(), path) for path in pngs if _is_file(path)]
    sized = [item for item in sized if item[0] > 0]
    return max(sized, key=lambda item: item[0])[1] if sized else None


def _rect_clips(svg: bytes) -> list[tuple[float, float, float, float, float, float]]:
    """The rectangles (x, y, width, height, rx, ry) of the clip paths that the SVG uses and that are one <rect>."""
    try:
        root = ElementTree.fromstring(svg)
    except ElementTree.ParseError:
        return []
    used = {m for element in root.iter() for m in re.findall(r"url\(#([^)]+)\)", element.get("clip-path", ""))}
    rects = []
    for clip in root.iter(f"{_SVG_NS}clipPath"):
        shapes = list(clip)
        if clip.get("id") not in used or len(shapes) != 1 or shapes[0].tag != f"{_SVG_NS}rect":
            continue
        try:
            x, y, w, h = (float(shapes[0].get(k, "0")) for k in ("x", "y", "width", "height"))
            rx = float(shapes[0].get("rx") or shapes[0].get("ry") or 0)
            ry = float(shapes[0].get("ry") or rx)
        except ValueError:
            continue
        rects.append((x, y, w, h, rx, ry))
    return rects


def _opaque(image: QImage) -> int:
    """The number of pixels that are more opaque than transparent."""
    return sum(1 for a in _pixels(image)[3::4] if a >= 128)


def _render_svg(path: Path) -> QImage | None:
    """The SVG at SOURCE_SIZE. Qt does not apply clip paths, so a used clip of one rectangle clips the drawing here.

    All the rectangle clips together clip the whole drawing: correct for a clip that is the tile of the icon.
    A clip for one detail would cut most of the icon away, so the drawing then stays as Qt draws it.
    """
    try:
        svg = Path(path).read_bytes()
    except OSError:
        return None
    renderer = QSvgRenderer(QByteArray(svg))
    if not renderer.isValid():
        return None
    renderer.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
    clips = _rect_clips(svg)
    plain = _draw_svg(renderer, [])
    if not clips:
        return plain
    clipped = _draw_svg(renderer, clips)
    return clipped if _opaque(clipped) >= CLIP_KEEPS * _opaque(plain) else plain


def _draw_svg(renderer: QSvgRenderer, clips) -> QImage:
    box = renderer.viewBoxF()
    scale = SOURCE_SIZE / max(box.width(), box.height(), 1e-9)
    image = QImage(SOURCE_SIZE, SOURCE_SIZE, _ARGB)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if clips:
        # The same mapping as the renderer: the view box, scaled to fit, in the centre of the image.
        dx = (SOURCE_SIZE - box.width() * scale) / 2 - box.x() * scale
        dy = (SOURCE_SIZE - box.height() * scale) / 2 - box.y() * scale
        area = QPainterPath()
        for x, y, w, h, rx, ry in clips:
            area.addRoundedRect(QRectF(dx + x * scale, dy + y * scale, w * scale, h * scale), rx * scale, ry * scale)
        painter.setClipPath(area)
    renderer.render(painter, QRectF(0, 0, SOURCE_SIZE, SOURCE_SIZE))
    painter.end()
    return image


def load_source(path: Path) -> QImage | None:
    """The icon as a square image with alpha, or None if it cannot be read."""
    if Path(path).suffix.lower() == ".svg":
        return _render_svg(path)
    picture = QImage(str(path))
    if picture.isNull():
        return None
    if max(picture.width(), picture.height()) > SOURCE_SIZE:
        # A big PNG: the work on each pixel that follows must not run on a million pixels.
        picture = picture.scaled(SOURCE_SIZE, SOURCE_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
    side = max(picture.width(), picture.height())
    image = QImage(side, side, _ARGB)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.drawImage((side - picture.width()) // 2, (side - picture.height()) // 2, picture)
    painter.end()
    return image


def load_app_icon(desktop_dirs=None, icon_dirs=None) -> QImage | None:
    """The Herdr app icon, read one time at start. Logs one line (no path) when the tray must use the circle."""
    if desktop_dirs is None or icon_dirs is None:
        desktop_dirs, icon_dirs = default_dirs()
    path = find_app_icon(desktop_dirs, icon_dirs)
    if path is None:
        log.info("the Herdr app icon was not found: the tray icon is a circle")
        return None
    image = load_source(path)
    if image is None:
        log.info("the Herdr app icon cannot be read: the tray icon is a circle")
    return image


def _pixels(image: QImage) -> bytes:
    """The bytes of an ARGB32 image, 4 for each pixel (B, G, R, A in memory), with no row padding."""
    image = image.convertToFormat(_ARGB)
    return bytes(image.constBits())[: image.width() * image.height() * 4]


def _luminance(b: int, g: int, r: int) -> float:
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def plate_tone(source: QImage) -> float | None:
    """The luminance of the plate under the picture, or None when the icon is a glyph on transparency.

    An icon is on a plate when at least half of its square is opaque. The plate is the most frequent tone in a
    thin band at the outer edge of the opaque area: the picture can cover most of the plate, but not its edge.
    """
    data = _pixels(source)
    side = source.width()
    count = len(data) // 4
    if count == 0 or sum(1 for a in data[3::4] if a >= 128) < count / 2:
        return None
    band = max(1, side // 32)

    def opaque(x: int, y: int) -> bool:
        return 0 <= x < side and 0 <= y < side and data[4 * (y * side + x) + 3] >= 250

    buckets: dict[int, list[float]] = {}
    for y in range(side):
        for x in range(side):
            inside = opaque(x - band, y) and opaque(x + band, y) and opaque(x, y - band) and opaque(x, y + band)
            if opaque(x, y) and not inside:
                i = 4 * (y * side + x)
                tone = _luminance(data[i], data[i + 1], data[i + 2])
                buckets.setdefault(min(7, int(tone * 8)), []).append(tone)
    if not buckets:
        return None
    biggest = max(buckets.values(), key=len)
    return sum(biggest) / len(biggest)


def _drawn(source: QImage, size: int, inset: float = 0) -> QImage:
    """The source scaled into a square of `size`, inside a transparent border of `inset` pixels."""
    inner = max(1, round(size - 2 * inset))
    scaled = source.scaled(
        inner, inner, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    if inner == size:
        return scaled.convertToFormat(_ARGB)
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage(QPointF((size - inner) / 2, (size - inner) / 2), scaled)
    painter.end()
    return image.convertToFormat(_ARGB)


def mark(source: QImage, size: int, tone: float | None) -> QImage:
    """The shape of the icon at `size` as alpha (black pixels).

    A glyph on transparency: its alpha. A picture on a plate (`tone` given): a plain silhouette would be a
    blank square, so the plate stays, the picture on it is cut out, and a thin outline keeps the edge of the
    plate closed where the picture touches it.
    """
    full = _pixels(_drawn(source, size))
    alpha = bytearray(full[3::4])
    if tone is not None:
        ring = _pixels(_drawn(source, size, max(1.5, size / 16)))[3::4]
        for p in range(len(alpha)):
            i = 4 * p
            picture = min(1.0, max(0.0, (abs(_luminance(full[i], full[i + 1], full[i + 2]) - tone) - 0.15) / 0.3))
            alpha[p] = max(round(alpha[p] * (1 - picture)), alpha[p] - ring[p], 0)
    data = bytearray(4 * len(alpha))
    data[3::4] = alpha
    return QImage(bytes(data), size, size, size * 4, _ARGB).copy()


def shapes(source: QImage) -> list[QImage] | None:
    """The mark at each tray size, or None (with one log line) when the mark does not show the icon."""
    tone = plate_tone(source)
    made = [mark(source, size, tone) for size in SIZES]
    big = made[-1]
    area = big.width() * big.height()
    cover = _opaque(big) / area
    hole = _opaque(_drawn(source, big.width())) / area - cover
    if not MARK_COVER[0] <= cover <= MARK_COVER[1] or (tone is not None and hole < MARK_HOLE):
        log.info("the Herdr app icon gives no clear mark: the tray icon is a circle")
        return None
    return made


def tint(shape: QImage, color: str) -> QImage:
    """The shape filled with `color`: the colour where the shape is opaque, transparent elsewhere."""
    image = QImage(shape)
    painter = QPainter(image)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(image.rect(), QColor(color))
    painter.end()
    return image


def tinted_icon(source: QImage, color: str, size: int) -> QImage:
    return tint(mark(source, size, plate_tone(source)), color)
