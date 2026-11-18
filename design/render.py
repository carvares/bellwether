"""Regenerates every design image in design/out/ from the mock-ups in design/layouts/ and design/icons/.

Off screen only: no window opens on the desktop. The program icons come from the icons folder of the Herdr app
at render time (read-only); they are not copied into the repository.

Run from the repository root:  uv run python design/render.py            (everything)
                               uv run python design/render.py layouts a  (only layout A)
                               uv run python design/render.py icons      (only the icons)
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_SCALE_FACTOR"] = "2"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter, QPainterPath, QPen  # noqa: E402
from PySide6.QtQuick import QQuickView  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from herdr_float.icons import Icons  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SCALE = 2
PROGRAMS = ["claude-code", "codex", "gemini", "opencode", "pi"]
LAYOUTS = [
    ("a", "a-refined-list", "A · Refined list"),
    ("b", "b-tiles", "B · Tiles"),
    ("c", "c-hud", "C · Techno / HUD"),
    ("d", "d-signal-strip", "D · Signal strip"),
    ("e", "e-ring", "E · Ring"),
]
ICONS = [
    (1, "1-horn-spiral", "1 · Horn spiral"),
    (2, "2-circuit-ram", "2 · Circuit ram"),
    (3, "3-float-panel", "3 · Float panel"),
    (4, "4-node-herd", "4 · Node herd"),
    (5, "5-prompt-ring", "5 · Prompt ring"),
]
STATUS = [("blocked", "#f28b82"), ("done", "#fdd663"), ("idle", "#81c995"), ("working", "#8ab4f8"), ("none / offline", "#5f6368")]
TRAY_INK = "#8ab4f8"  # The colour that the tray SVG files use for the part that carries the status.
SANS = "Adwaita Sans"

app = QApplication([])
warnings: list[str] = []


# ---------------------------------------------------------------- drawing helpers

def canvas(width: float, height: float) -> QImage:
    image = QImage(int(round(width * SCALE)), int(round(height * SCALE)), QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(SCALE)
    image.fill(Qt.GlobalColor.transparent)
    return image


def painter_for(image: QImage) -> QPainter:
    painter = QPainter(image)
    painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                           | QPainter.RenderHint.SmoothPixmapTransform)
    return painter


def size_of(image: QImage) -> tuple[float, float]:
    return image.width() / image.devicePixelRatio(), image.height() / image.devicePixelRatio()


def font(px: int, weight: QFont.Weight = QFont.Weight.Normal, spacing: float = 0) -> QFont:
    f = QFont(SANS)
    f.setPixelSize(px)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


def backdrop(painter: QPainter, rect: QRectF, dark: bool) -> None:
    """A plain desktop-like background: a soft gradient and one window behind, so translucency shows."""
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    for stop, colour in ((0, "#20242c"), (1, "#101216")) if dark else ((0, "#e9edf2"), (1, "#cfd6de")):
        gradient.setColorAt(stop, QColor(colour))
    painter.fillRect(rect, gradient)


def window_behind(painter: QPainter, rect: QRectF, dark: bool) -> None:
    """A made-up application window whose corner is behind the widget."""
    painter.save()
    painter.setClipRect(rect)
    body = QRectF(rect.left() + rect.width() * 0.42, rect.top() + 34, rect.width(), rect.height())
    painter.setPen(QPen(QColor("#3a3f47" if dark else "#b9c0c9"), 1))
    painter.setBrush(QColor("#2a2e35" if dark else "#fbfcfd"))
    painter.drawRoundedRect(body, 8, 8)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#343942" if dark else "#eceff3"))
    painter.drawRoundedRect(QRectF(body.left() + 1, body.top() + 1, body.width(), 26), 7, 7)
    painter.setBrush(QColor("#454b55" if dark else "#d5dae1"))
    y = body.top() + 44
    for i in range(40):
        if y > rect.bottom():
            break
        painter.drawRoundedRect(QRectF(body.left() + 16, y, (90, 150, 120, 60, 135)[i % 5], 6), 3, 3)
        y += 18
    painter.restore()


def band(cells: list[tuple[QImage, str]], dark: bool, title: str = "", pad: int = 28, gap: int = 28,
         behind: bool = True, min_height: float = 0) -> QImage:
    """One row of images on a dark or a light background, each with a caption above it."""
    sizes = [size_of(image) for image, _ in cells]
    caption = 24 if any(text for _, text in cells) else 0
    head = 30 if title else 0
    inner = max(max(h for _, h in sizes), min_height)
    width = pad * 2 + sum(w for w, _ in sizes) + gap * (len(cells) - 1)
    title_font = font(11, QFont.Weight.DemiBold, 1.2)
    if title:  # A band is never narrower than its title.
        width = max(width, pad * 2 + QFontMetricsF(title_font).horizontalAdvance(title.upper()) + 4)
    height = pad + head + caption + inner + pad
    image = canvas(width, height)
    painter = painter_for(image)
    backdrop(painter, QRectF(0, 0, width, height), dark)
    ink = QColor("#e8eaed" if dark else "#202124")
    dim = QColor("#9aa0a6" if dark else "#5f6368")
    if title:
        painter.setPen(dim)
        painter.setFont(title_font)
        painter.drawText(QPointF(pad, pad + 10), title.upper())
    x = pad
    top = pad + head + caption
    left = x
    for (cell, text), (w, h) in zip(cells, sizes):
        if behind:
            window_behind(painter, QRectF(left - gap / 2, top - 10, w + gap, inner + 20), dark)
        left += w + gap
    for (cell, text), (w, h) in zip(cells, sizes):
        if text:
            painter.setPen(ink)
            painter.setFont(font(13, QFont.Weight.Medium))
            painter.drawText(QPointF(x, top - 10), text)
        painter.drawImage(QPointF(x, top), cell)
        x += w + gap
    painter.end()
    return image


def stack(images: list[QImage], fill: str = "#101216") -> QImage:
    sizes = [size_of(i) for i in images]
    out = canvas(max(w for w, _ in sizes), sum(h for _, h in sizes))
    out.fill(QColor(fill))
    painter = painter_for(out)
    y = 0.0
    for image, (w, h) in zip(images, sizes):
        if w < size_of(out)[0]:  # Stretch the background of a narrow band to the full width.
            painter.drawImage(QRectF(w - 1, y, size_of(out)[0] - w + 1, h), image,
                              QRectF(image.width() - 2, 0, 1, image.height()))
        painter.drawImage(QPointF(0, y), image)
        y += h
    painter.end()
    return out


def beside(images: list[QImage]) -> QImage:
    sizes = [size_of(i) for i in images]
    out = canvas(sum(w for w, _ in sizes), max(h for _, h in sizes))
    painter = painter_for(out)
    x = 0.0
    for image, (w, h) in zip(images, sizes):
        if h < size_of(out)[1]:
            painter.drawImage(QRectF(x, h - 1, w, size_of(out)[1] - h + 1), image,
                              QRectF(0, image.height() - 2, image.width(), 1))
        painter.drawImage(QPointF(x, 0), image)
        x += w
    painter.end()
    return out


def save(image: QImage, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    image.save(str(OUT / name))
    w, h = size_of(image)
    print(f"  {name}  {image.width()}x{image.height()} px  ({w:.0f}x{h:.0f} at scale {SCALE})")


# ---------------------------------------------------------------- layouts

def icon_urls(cache: Path) -> dict[str, str]:
    icons = Icons(None, cache)
    return {word: icons.url(word) for word in PROGRAMS}


def grab(slug: str, scene: str, urls: dict[str, str]) -> QImage:
    """One layout in one scene, as an image with a transparent background."""
    view = QQuickView()
    view.setColor(QColor(Qt.GlobalColor.transparent))
    view.engine().warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
    view.rootContext().setContextProperty("iconUrls", urls)
    view.setInitialProperties({"scene": scene})
    view.setResizeMode(QQuickView.ResizeMode.SizeViewToRootObject)
    view.setSource(QUrl.fromLocalFile(str(HERE / "layouts" / f"{slug}.qml")))
    if view.status() != QQuickView.Status.Ready:
        raise SystemExit(f"{slug}: {[e.toString() for e in view.errors()]}")
    view.show()
    for _ in range(12):
        app.processEvents()
        time.sleep(0.004)
    image = view.grabWindow().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(SCALE)
    view.close()
    view.deleteLater()
    app.processEvents()
    return image


def both(cells: list[tuple[QImage, str]], side_by_side: bool, title: str = "") -> QImage:
    dark = band(cells, True, title and f"{title} — on a dark desktop")
    light = band(cells, False, title and f"{title} — on a light desktop")
    return beside([dark, light]) if side_by_side else stack([dark, light])


def render_layouts(only: str = "") -> None:
    cache = Path(tempfile.mkdtemp(prefix="herdr-float-design-"))
    urls = icon_urls(cache)
    closed, opened = [], []
    for letter, slug, name in LAYOUTS:
        if only and only != letter:
            continue
        if not (HERE / "layouts" / f"{slug}.qml").is_file():
            continue
        print(name)
        g = {scene: grab(slug, scene, urls) for scene in
             ["closed", "open", "long", "quiet", "none", "opening", "failed", "offline", "top-done", "top-idle"]}
        for scene in ("closed", "open", "long"):
            w, h = size_of(g[scene])
            print(f"  size {scene}: {w:.0f}x{h:.0f}")
        closed.append((g["closed"], name))
        opened.append((g["open"], name))
        pre = f"herdr-float-layout-{letter}"
        save(both([(g["closed"], "")], True, "1 · Closed, mixed counts"), f"{pre}-1-closed.png")
        save(both([(g["open"], "")], True, "2 · Working open"), f"{pre}-2-open.png")
        save(both([(g["long"], "")], True, "3 · Idle open, 12 agents, 8 rows"), f"{pre}-3-long.png")
        save(both([(g["quiet"], "Only working agents"), (g["none"], "No agents")], False, "4 · Quiet states"),
             f"{pre}-4-quiet.png")
        save(both([(g["opening"], "A jump runs"), (g["failed"], "A jump failed"), (g["offline"], "Herdr is offline")],
                  False, "5 · Transient states"), f"{pre}-5-transient.png")
        save(both([(g["closed"], "Top status: blocked"), (g["top-done"], "done"), (g["top-idle"], "idle"),
                   (g["quiet"], "working")], False, "6 · Top-status signal"), f"{pre}-6-signal.png")
    if not only and closed:
        tall = max(size_of(i)[1] for i, _ in opened)
        rows = []
        for dark in (True, False):
            side = "dark" if dark else "light"
            rows.append(band(closed, dark, f"Closed — blocked 1, done 2, working 3, idle 4 — {side} desktop"))
            rows.append(band(opened, dark, f"Working open — {side} desktop", min_height=tall))
        save(stack(rows), "herdr-float-layouts-overview.png")


# ---------------------------------------------------------------- icons

HERDR_ICON = Path("/usr/share/icons/hicolor/scalable/apps/herdr-app.svg")  # Read at run time, never copied.
PANELS = {True: "#2a2e32", False: "#eff0f1"}  # The colour of a dark and of a light desktop panel.


def svg_image(svg: str, px: int) -> QImage:
    """An SVG text drawn at exactly `px` real pixels."""
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    if not renderer.isValid():
        raise SystemExit("invalid SVG")
    image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = painter_for(image)
    renderer.render(painter, QRectF(0, 0, px, px))
    painter.end()
    return image


def herdr_image(px: int) -> QImage:
    """The installed Herdr icon. Qt does not apply the clip path of that file, so the tile clips the drawing here."""
    renderer = QSvgRenderer(QByteArray(HERDR_ICON.read_bytes()))
    image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = painter_for(image)
    tile = QPainterPath()
    unit = px / 1024
    tile.addRoundedRect(QRectF(64 * unit, 64 * unit, 896 * unit, 896 * unit), 192 * unit, 192 * unit)
    painter.setClipPath(tile)
    renderer.render(painter, QRectF(0, 0, px, px))
    painter.end()
    return image


def herdr_silhouette(px: int, colour: str) -> QImage | None:
    """The installed Herdr icon as one colour: its dark drawing (the ram) in `colour`, the light tile left out."""
    if not HERDR_ICON.is_file():
        return None
    big = herdr_image(px * 4).convertToFormat(QImage.Format.Format_ARGB32)
    ink = QColor(colour)
    for y in range(big.height()):
        for x in range(big.width()):
            c = big.pixelColor(x, y)
            dark = max(0.0, min(1.0, (0.85 - c.lightnessF()) / 0.5)) * c.alphaF()
            big.setPixelColor(x, y, QColor(ink.red(), ink.green(), ink.blue(), int(round(dark * 255))))
    # The drawing fills only a part of the tile: cut the empty border away, so the shape uses the whole icon.
    box = [big.width(), big.height(), 0, 0]
    for y in range(big.height()):
        for x in range(big.width()):
            if big.pixelColor(x, y).alpha() > 40:
                box = [min(box[0], x), min(box[1], y), max(box[2], x), max(box[3], y)]
    side = max(box[2] - box[0], box[3] - box[1]) + 1
    out = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    painter = painter_for(out)
    inset = px / 22.0
    painter.drawImage(QRectF(inset, inset, px - 2 * inset, px - 2 * inset), big,
                      QRectF(box[0] - (side - (box[2] - box[0] + 1)) / 2, box[1] - (side - (box[3] - box[1] + 1)) / 2, side, side))
    painter.end()
    return out


def tray_image(number: int, slug: str, px: int, colour: str) -> QImage | None:
    if number == 0:
        return herdr_silhouette(px, colour)
    svg = (HERE / "icons" / f"{slug}-tray.svg").read_text(encoding="utf-8")
    return svg_image(svg.replace(TRAY_INK, colour), px)


def app_image(number: int, slug: str, px: int) -> QImage | None:
    if number == 0:
        return herdr_image(px) if HERDR_ICON.is_file() else None
    return svg_image((HERE / "icons" / f"{slug}.svg").read_text(encoding="utf-8"), px)


def real(painter: QPainter, x: float, y: float, image: QImage, zoom: int = 1) -> None:
    """Draws an image so that one of its pixels is `zoom` real pixels of the sheet (no smoothing)."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    painter.drawImage(QRectF(x, y, image.width() * zoom / SCALE, image.height() * zoom / SCALE), image,
                      QRectF(0, 0, image.width(), image.height()))
    painter.restore()


def icon_row(number: int, slug: str, name: str, dark: bool) -> QImage:
    """One concept on one background: the app icon at 256 and 64 px, and the tray icon in the five colours."""
    width, height = 560, 196
    image = canvas(width, height)
    painter = painter_for(image)
    backdrop(painter, QRectF(0, 0, width, height), dark)
    ink = QColor("#e8eaed" if dark else "#202124")
    dim = QColor("#9aa0a6" if dark else "#5f6368")
    painter.setPen(ink)
    painter.setFont(font(13, QFont.Weight.DemiBold))
    painter.drawText(QPointF(20, 28), name)
    painter.setPen(dim)
    painter.setFont(font(10))
    for x, text in ((20, "app icon, 256 px"), (164, "64 px"), (236, "tray, 22 px shown 4×"), (236 + 0, "")):
        painter.drawText(QPointF(x, 46), text)
    big = app_image(number, slug, 256)
    if big is not None:
        real(painter, 20, 54, big)
        real(painter, 164, 54, app_image(number, slug, 64))
    # The tray block: a strip in the colour of a desktop panel.
    strip = QRectF(228, 54, 312, 128)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(PANELS[dark]))
    painter.drawRoundedRect(strip, 6, 6)
    painter.setPen(dim)
    painter.drawText(QPointF(236, 126), "44 px")
    painter.drawText(QPointF(236, 160), "22 px")
    for i, (state, colour) in enumerate(STATUS):
        x = 276 + i * 54
        small = tray_image(number, slug, 22, colour)
        if small is None:
            continue
        real(painter, x - 2, 62, small, 4)
        real(painter, x + 9, 110, tray_image(number, slug, 44, colour))
        real(painter, x + 14.5, 150, small)
        painter.setPen(dim)
        painter.setFont(font(8))
        painter.drawText(QRectF(x - 6, 166, 52, 12), Qt.AlignmentFlag.AlignHCenter, state)
    painter.end()
    return image


def render_icons() -> None:
    print("Icons")
    rows = []
    for number, slug, name in [(0, "", "0 — Herdr icon, tinted (the icon of the Herdr app itself)"), *ICONS]:
        if number and not (HERE / "icons" / f"{slug}.svg").is_file():
            continue
        row = beside([icon_row(number, slug, name, True), icon_row(number, slug, name, False)])
        rows.append(row)
        if number:
            save(row, f"herdr-float-icon-{slug}.png")
    save(stack(rows), "herdr-float-icons-overview.png")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "layouts"):
        render_layouts(sys.argv[2] if len(sys.argv) > 2 else "")
    if what in ("all", "icons"):
        render_icons()
    for line in dict.fromkeys(warnings):
        print("QML WARNING", line)
