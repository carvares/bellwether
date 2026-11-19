"""A check of every text on the screen of a window: is a text outside the window, cut by its box or by a box
around it, or over a different text? For the tests of the custom look (a larger font, a different font family),
and for the scripts that render the look sheets."""
from PySide6.QtCore import QRectF
from PySide6.QtQml import QQmlExpression, qmlContext

ELIDE_NONE = 3  # Text.ElideNone
# The part of the line box of a text that its letters use: the box has free space above and below the letters, so
# two line boxes can touch while the letters are apart (a label above a large numeral).
INK_TOP, INK_HEIGHT = 0.22, 0.60
MIN_GAP = 3  # pixels between two texts of one line


def walk(item):
    yield item
    for child in item.childItems():
        yield from walk(child)


def number(item, name):
    """An enum property as a number (Python has no converter for the enums of a QML item)."""
    value = QQmlExpression(qmlContext(item), item, name).evaluate()
    return int(value[0] if isinstance(value, tuple) else value)


def ink_box(text):
    """The box of the letters of a Text item, in the window."""
    width, height = text.width(), text.height()
    content_width, content_height = text.property("contentWidth"), text.property("contentHeight")
    left, right = text.property("leftPadding") or 0, text.property("rightPadding") or 0
    horizontal, vertical = number(text, "horizontalAlignment"), number(text, "verticalAlignment")
    x = left  # Text.AlignLeft, and a text with no width of its own
    if horizontal == 2:  # Text.AlignRight
        x = width - right - content_width
    elif horizontal == 4:  # Text.AlignHCenter
        x = left + (width - left - right - content_width) / 2
    y = 0  # Text.AlignTop
    if vertical == 64:  # Text.AlignBottom
        y = height - content_height
    elif vertical == 128:  # Text.AlignVCenter
        y = (height - content_height) / 2
    return text.mapRectToScene(QRectF(x, y + content_height * INK_TOP, content_width, content_height * INK_HEIGHT))


def text_findings(window):
    """One line for each problem of a visible text of the window. Empty: every text has its room."""
    found = []
    inside = QRectF(0, 0, window.width(), window.height()).adjusted(-0.5, -0.5, 0.5, 0.5)
    boxes = []
    for text in walk(window.contentItem()):
        if not (text.isVisible() and text.metaObject().className().startswith("QQuickText") and text.property("text")):
            continue
        box = ink_box(text)
        clips = []  # the boxes around the text that cut their content
        parent = text.parentItem()
        while parent is not None:
            if parent.property("clip"):
                clips.append((parent, parent.mapRectToScene(parent.boundingRect())))
            parent = parent.parentItem()
        if any(not area.intersects(box) for _, area in clips):
            continue  # not on the screen: a row that is scrolled out of its list
        name = repr(text.property("text"))[:30]
        elides = number(text, "elide") != ELIDE_NONE
        if not inside.contains(box):
            found.append(f"outside the window: {name}")
        if not elides and text.width() > 0 and text.property("contentWidth") > text.width() + 0.6:
            found.append(f"wider than its box: {name}")
        if not elides and text.property("truncated"):
            found.append(f"cut with no elide mark: {name}")
        for parent, area in clips:
            scrolls = parent.metaObject().className().startswith("QQuickFlickable")  # a row can be half in its list
            cut_at_a_side = box.left() < area.left() - 0.6 or box.right() > area.right() + 0.6
            cut_above_or_below = box.top() < area.top() - 0.6 or box.bottom() > area.bottom() + 0.6
            if cut_at_a_side or (cut_above_or_below and not scrolls):
                found.append(f"cut by a box around it: {name}")
        boxes.append((name, box, text.parentItem()))
    for place, (name, box, parent) in enumerate(boxes):
        for other, other_box, other_parent in boxes[place + 1:]:
            common = box.intersected(other_box)
            if common.width() > 0.6 and common.height() > 0.6:
                found.append(f"over each other: {name} and {other}")
            elif parent is other_parent and parent.metaObject().className().startswith("QQuickRow"):
                pass  # the parts of one text, side by side in a Row (the two digits of a count of Layout C)
            elif box.top() < other_box.bottom() and other_box.top() < box.bottom():
                # In one line: the two texts need a gap that a person can see.
                gap = max(box.left(), other_box.left()) - min(box.right(), other_box.right())
                if gap < MIN_GAP:
                    found.append(f"too near to each other ({gap:.1f} px): {name} and {other}")
    return found
