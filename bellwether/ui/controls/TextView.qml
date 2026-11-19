// Lines of a screen in the answer window, in a monospace font: the detail of a question (a command, a diff, a plan),
// or the screen of an agent that Bellwether cannot read. Each line of the screen is one item with a thin mark at its
// left. A line that is wider than the view goes on in the next row (at a space, or inside a long word) with no new mark: nothing of a command is hidden
// at the side, and a wrapped line cannot be taken for two lines. A view that is taller than `maxHeight` scrolls:
// with the wheel, a drag, and Page Up, Page Down, Home and End from the window (scrollBy). The text is plain text,
// never formatted. The view keeps no copy: it shows `lines` of its caller.
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
    readonly property bool scrolls: scroller.contentHeight > scroller.height + 0.5
    // A monospace font of the system. The font family of the custom look is not used here: columns must line up.
    readonly property string mono: Fonts.first(
        ["Hack", "JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono"], "monospace")

    function scrollBy(pixels) {
        scroller.contentY = Math.max(0, Math.min(scroller.contentY + pixels, scroller.contentHeight - scroller.height))
    }

    implicitHeight: Math.min(maxHeight, rows.height + 16)
    height: implicitHeight
    radius: Math.min(theme.itemRadius, 8)
    color: Qt.rgba(theme.textColor.r, theme.textColor.g, theme.textColor.b, 0.06)
    border.width: 1
    border.color: theme.lineColor
    Accessible.role: Accessible.StaticText
    Accessible.name: name

    Flickable {
        id: scroller
        anchors.fill: parent
        anchors.margins: 1
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
            width: scroller.width - 16 - (view.scrolls ? 6 : 0)
            spacing: 2

            Repeater {
                model: view.lines

                Item {
                    id: line
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
    // Where the view is, while it scrolls.
    Rectangle {
        readonly property bool isScrollThumb: true
        readonly property real room: scroller.height - 6 - height
        visible: view.scrolls
        x: parent.width - 6
        y: 4 + room * scroller.contentY / Math.max(1, scroller.contentHeight - scroller.height)
        width: 3
        height: Math.max(20, (scroller.height - 6) * scroller.height / Math.max(1, scroller.contentHeight))
        radius: Math.min(1.5, view.theme.itemRadius)
        color: view.theme.faintColor
    }
}
