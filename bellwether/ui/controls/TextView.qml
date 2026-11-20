// Lines of a screen in the answer window, in a monospace font: the detail of a question (a command, a diff, a plan),
// or the screen of an agent that Bellwether cannot read. Each line of the screen is one item with a thin mark at its
// left. A line that is wider than the view goes on in the next row (at a space, or inside a long word) with no new
// mark: nothing of a command is hidden at the side, and a wrapped line cannot be taken for two lines. A view that is
// taller than `maxHeight` scrolls: with the wheel, a drag of the text or of its thumb, and Page Up, Page Down, Home,
// End and the arrows when it has the keyboard (or from the window: keyScroll). While lines are out of view, a
// note at its foot says how many ("12 more lines below"), in the colours of the text. `atTop`: the first line is in
// view; `atEnd`: the last line is in view. `restart()`: new lines show from their first one, and a press that began
// before it moves nothing more. The text is plain text, never formatted. The view keeps no copy: it shows `lines` of
// its caller.
import QtQuick
import "../skins/fonts.js" as Fonts

Rectangle {
    id: view

    required property QtObject theme
    property var lines: []
    property int maxHeight: 240
    // What the view shows, for a screen reader: "Command", "Screen of the agent".
    property string name: ""
    readonly property bool isTextView: true
    // The lines are taller than the view can be.
    readonly property bool scrolls: rows.height + 16 > maxHeight + 0.5
    // The last line is in view (always, when the view does not scroll).
    readonly property bool atEnd: !scrolls || scroller.contentY >= scroller.contentHeight - scroller.height - 1
    // The first line is in view (always, when the view does not scroll).
    readonly property bool atTop: !scrolls || scroller.contentY <= 1
    // The foot of the first row of text, from the top of the view, while the view is at its top.
    readonly property real firstRowBottom: scroller.y + rows.y + Math.ceil(rowMetrics.height)
    // The number of restarts, and the restart at the last key press that was not a repeat of a held key (the
    // thumb keeps its own, of its press).
    property int restarts: 0
    property int keyRestarts: -1
    // The lines of the screen that are below or above the view, in whole or in part.
    readonly property int below: outside(true)
    readonly property int above: outside(false)
    readonly property string moreText: below > 0 && above > 0 ? count(below, "more line") + " below · " + above + " above"
        : below > 0 ? count(below, "more line") + " below" : above > 0 ? count(above, "line") + " above" : ""
    // A monospace font of the system. The font family of the custom look is not used here: columns must line up.
    readonly property string mono: Fonts.first(
        ["Hack", "JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono", /* macOS: */ "SF Mono",
         "Menlo"], "monospace")

    function count(n, word) {
        return n + " " + (n === 1 ? word : word + "s")
    }

    // The number of lines of the screen that are not all in view: below the view (`down`), or above it.
    function outside(down) {
        if (!scrolls)
            return 0
        var top = scroller.contentY - rows.y, bottom = top + scroller.height, n = 0
        for (var i = 0; i < rows.children.length; i++) {
            var row = rows.children[i]
            if (row.isScreenRow && (down ? row.y + row.height > bottom + 0.5 : row.y < top - 0.5))
                n += 1
        }
        return n
    }

    function scrollBy(pixels) {
        scroller.contentY = Math.max(0, Math.min(scroller.contentY + pixels, scroller.contentHeight - scroller.height))
    }
    function toEnd(end) {
        scrollBy(end ? scroller.contentHeight : -scroller.contentHeight)
    }
    function page(down) {
        scrollBy(down ? scroller.height - 30 : 30 - scroller.height)
    }
    // New lines: the view goes to its first line, and what moves it now ends: a flick, a drag of the text (the
    // text loses the pointer), a drag of the thumb and a held key (their moves count only after a new press). Only
    // a new press moves the view again.
    function restart() {
        restarts += 1
        scroller.cancelFlick()
        scroller.enabled = false
        scroller.enabled = true
        scroller.contentY = 0
    }
    // A key that moves the view: Home, End, Page Up, Page Down, the arrows (`repeat`: a repeat of a held key). True
    // for these keys. The repeats of a key that was pressed before the last restart move nothing.
    function keyScroll(key, repeat) {
        var keys = [Qt.Key_Home, Qt.Key_End, Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Up, Qt.Key_Down]
        if (keys.indexOf(key) < 0)
            return false
        if (!repeat)
            keyRestarts = restarts
        else if (keyRestarts !== restarts)
            return true
        if (key === Qt.Key_End || key === Qt.Key_Home)
            toEnd(key === Qt.Key_End)
        else if (key === Qt.Key_PageDown || key === Qt.Key_PageUp)
            page(key === Qt.Key_PageDown)
        else
            scrollBy(key === Qt.Key_Down ? 40 : -40)
        return true
    }

    implicitHeight: scrolls ? maxHeight : rows.height + 16
    height: implicitHeight
    radius: Math.min(theme.itemRadius, 8)
    color: Qt.rgba(theme.textColor.r, theme.textColor.g, theme.textColor.b, 0.06)
    border.width: 1
    border.color: activeFocus ? theme.accentColor : theme.lineColor
    // Only a view that scrolls takes the keyboard: then its keys move it.
    activeFocusOnTab: scrolls
    Accessible.role: Accessible.StaticText
    Accessible.name: name + (moreText !== "" ? ", " + moreText : "")
    Accessible.focusable: scrolls
    Keys.onPressed: (event) => {
        if (event.modifiers === Qt.NoModifier)
            event.accepted = keyScroll(event.key, event.isAutoRepeat)
    }

    FontMetrics {
        id: rowMetrics
        font { family: view.mono; pixelSize: view.theme.size(12) }
    }

    Flickable {
        id: scroller
        x: 1
        y: 1
        width: parent.width - 2
        height: parent.height - 2 - (view.scrolls ? moreBar.height : 0)
        contentWidth: width
        contentHeight: rows.height + 14
        clip: true
        interactive: view.scrolls
        flickableDirection: Flickable.VerticalFlick
        boundsBehavior: Flickable.StopAtBounds
        onContentHeightChanged: contentY = Math.max(0, Math.min(contentY, contentHeight - height))

        WheelHandler {
            enabled: view.scrolls
            onWheel: (event) => view.scrollBy(event.pixelDelta.y !== 0 ? -event.pixelDelta.y : -event.angleDelta.y / 2)
        }

        Column {
            id: rows
            x: 8
            y: 7
            width: scroller.width - 16 - (view.scrolls ? 8 : 0)
            spacing: 2

            Repeater {
                model: view.lines

                Item {
                    id: line
                    readonly property bool isScreenRow: true
                    required property string modelData
                    width: rows.width
                    height: content.height

                    Rectangle {
                        width: 2
                        height: parent.height
                        color: Qt.rgba(view.theme.textColor.r, view.theme.textColor.g, view.theme.textColor.b, 0.18)
                    }
                    Text {
                        id: content
                        readonly property bool isScreenLine: true
                        x: 8
                        width: parent.width - 8
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        text: line.modelData === "" ? " " : line.modelData
                        color: view.theme.textColor
                        font { family: view.mono; pixelSize: view.theme.size(12) }
                    }
                }
            }
        }
    }
    // Where the view is, while it scrolls. A drag of the thumb moves the view.
    Rectangle {
        id: thumb
        readonly property bool isScrollThumb: true
        readonly property real room: scroller.height - 6 - height
        visible: view.scrolls
        x: parent.width - 7
        y: scroller.y + 3 + room * scroller.contentY / Math.max(1, scroller.contentHeight - scroller.height)
        width: 4
        height: Math.max(20, (scroller.height - 6) * scroller.height / Math.max(1, scroller.contentHeight))
        radius: Math.min(2, view.theme.itemRadius)
        color: thumbArea.pressed ? view.theme.dimColor : view.theme.faintColor

        MouseArea {
            id: thumbArea
            property real startY: 0
            property real startContentY: 0
            property int pressRestarts: -1
            x: -6
            width: parent.width + 8
            height: parent.height
            onPressed: (mouse) => {
                startY = mapToItem(view, 0, mouse.y).y
                startContentY = scroller.contentY
                pressRestarts = view.restarts
            }
            onPositionChanged: (mouse) => {
                if (pressRestarts !== view.restarts)
                    return  // a press of before the last restart
                var moved = mapToItem(view, 0, mouse.y).y - startY
                var scale = (scroller.contentHeight - scroller.height) / Math.max(1, thumb.room)
                scroller.contentY = Math.max(0, Math.min(startContentY + moved * scale,
                                                         scroller.contentHeight - scroller.height))
            }
        }
    }
    // The lines out of view, at the foot of the view, while it scrolls.
    Rectangle {
        id: moreBar
        readonly property bool isMoreBar: true
        visible: view.scrolls
        x: 1
        y: parent.height - 1 - height
        width: parent.width - 2
        height: view.theme.fit(24)
        color: Qt.rgba(view.theme.textColor.r, view.theme.textColor.g, view.theme.textColor.b, 0.10)

        Rectangle {
            width: parent.width
            height: 1
            color: view.theme.lineColor
        }
        Text {
            readonly property bool isMoreNote: true
            x: 10
            width: parent.width - 20
            height: parent.height
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            textFormat: Text.PlainText
            text: view.moreText
            color: view.theme.textColor
            font { family: view.theme.fontFamily; pixelSize: view.theme.smallSize + 1; weight: Font.DemiBold }
        }
    }
    FocusRing { target: view; corner: view.radius; border.color: view.theme.accentColor }
}
