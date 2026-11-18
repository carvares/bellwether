import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell

Window {
    id: root

    property bool expanded: false
    property int posX: 0
    property int posY: 0
    // True until the user moves the pill: it then stays at the top-right corner when its size changes.
    property bool atDefault: false
    readonly property int edge: 16
    readonly property var stateColors: ({
        "blocked": "#f28b82",
        "done": "#fdd663",
        "working": "#8ab4f8",
        "idle": "#81c995",
        "unknown": "#9aa0a6"
    })

    visible: true
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
    width: panel.width
    height: panel.height

    LayerShell.Window.scope: "herdr-float"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.exclusionZone: -1
    LayerShell.Window.margins.left: posX
    LayerShell.Window.margins.top: posY
    // The compositor applies a new margin only with the next commit of the surface, so ask for a frame.
    LayerShell.Window.onMarginsChanged: root.requestUpdate()

    function clampPosition() {
        if (atDefault) {
            posX = Screen.width - width - edge
            posY = edge
        }
        var maxX = Math.max(0, Screen.width - width)
        var maxY = Math.max(0, Screen.height - height)
        posX = Math.min(Math.max(0, posX), maxX)
        posY = Math.min(Math.max(0, posY), maxY)
    }

    Component.onCompleted: {
        var valid = backend.savedX >= 0 && backend.savedY >= 0
            && backend.savedX <= Screen.width - width
            && backend.savedY <= Screen.height - height
        if (valid) {
            posX = backend.savedX
            posY = backend.savedY
        }
        atDefault = !valid
        clampPosition()
    }
    onWidthChanged: clampPosition()
    onHeightChanged: clampPosition()

    Rectangle {
        id: panel
        width: Math.max(pill.implicitWidth, list.visible ? 280 : 0) + 20
        height: column.implicitHeight + 16
        radius: 12
        color: "#e6202124"
        border.color: "#3c4043"

        Column {
            id: column
            x: 10
            y: 8
            spacing: 8

            Row {
                id: pill
                spacing: 12

                Text {
                    visible: !backend.online
                    text: "offline"
                    color: "#9aa0a6"
                    font.pixelSize: 14
                }

                Repeater {
                    model: backend.online ? backend.counters : []
                    Row {
                        required property var modelData
                        spacing: 5
                        opacity: modelData.count === 0 ? 0.35 : 1.0
                        Rectangle {
                            width: 10
                            height: 10
                            radius: 5
                            anchors.verticalCenter: parent.verticalCenter
                            color: root.stateColors[modelData.state]
                        }
                        Text {
                            text: modelData.count
                            color: modelData.attention && modelData.count > 0 ? root.stateColors[modelData.state] : "#e8eaed"
                            font.pixelSize: 14
                            font.bold: modelData.attention && modelData.count > 0
                            Accessible.name: modelData.count + " " + modelData.state
                        }
                    }
                }
            }

            Item {
                id: list
                visible: false
                width: 1
                height: 1
            }
        }

        MouseArea {
            id: dragArea
            width: parent.width
            height: pill.height + 16
            property real startX: 0
            property real startY: 0
            property bool moved: false
            onPressed: (mouse) => { startX = mouse.x; startY = mouse.y; moved = false }
            onPositionChanged: (mouse) => {
                var dx = mouse.x - startX
                var dy = mouse.y - startY
                if (!moved && Math.abs(dx) + Math.abs(dy) < 6)
                    return
                moved = true
                root.atDefault = false
                root.posX += dx
                root.posY += dy
                root.clampPosition()
            }
            onReleased: {
                if (moved)
                    backend.savePosition(root.posX, root.posY)
                else
                    root.expanded = !root.expanded
            }
        }
    }
}
