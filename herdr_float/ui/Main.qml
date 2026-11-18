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
    readonly property var stateColors: stateColors_

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

    // Close the list when Herdr goes offline, so that it does not open by itself when Herdr comes back.
    Connections {
        target: backend
        function onChanged() {
            if (!backend.online)
                root.expanded = false
        }
    }

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

            Column {
                id: list
                visible: root.expanded && backend.online
                width: 280
                spacing: 2

                property string failedPane: ""
                property string failedMessage: ""

                Connections {
                    target: backend
                    function onFocusFailed(key, message) {
                        list.failedPane = key
                        list.failedMessage = message
                        if (backend.online)
                            root.expanded = true
                        failTimer.restart()
                    }
                }

                Timer {
                    id: failTimer
                    interval: 3000
                    onTriggered: { list.failedPane = ""; list.failedMessage = "" }
                }

                Text {
                    visible: backend.agents.length === 0
                    text: "No agents"
                    color: "#9aa0a6"
                    font.pixelSize: 13
                }

                Repeater {
                    model: backend.agents
                    Rectangle {
                        id: rowItem
                        required property var modelData
                        readonly property bool failed: list.failedPane === modelData.key
                        width: list.width
                        height: 28
                        radius: 6
                        color: rowMouse.containsMouse ? "#3c4043" : "transparent"

                        Rectangle {
                            id: dot
                            x: 6
                            width: 10
                            height: 10
                            radius: 5
                            anchors.verticalCenter: parent.verticalCenter
                            color: root.stateColors[rowItem.modelData.status]
                        }
                        Text {
                            anchors.left: dot.right
                            anchors.leftMargin: 8
                            anchors.right: detail.left
                            anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            text: rowItem.modelData.name
                            color: "#e8eaed"
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                        Text {
                            id: detail
                            anchors.right: parent.right
                            anchors.rightMargin: 6
                            anchors.verticalCenter: parent.verticalCenter
                            width: Math.min(implicitWidth, 150)
                            elide: Text.ElideRight
                            text: rowItem.failed
                                ? list.failedMessage
                                : rowItem.modelData.status
                                  + (rowItem.modelData.workspace ? " · " + rowItem.modelData.workspace : "")
                            color: rowItem.failed ? "#f28b82" : "#9aa0a6"
                            font.pixelSize: 12
                        }
                        MouseArea {
                            id: rowMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            Accessible.name: "Go to " + rowItem.modelData.name
                            onClicked: {
                                root.expanded = false
                                backend.focus(rowItem.modelData.key)
                            }
                        }
                    }
                }
            }
        }

        MouseArea {
            id: dragArea
            width: parent.width
            height: pill.height + 16
            property real startX: 0
            property real startY: 0
            property bool moved: false
            // Time of the last margin change. At most one change in each 16 ms, so that a pointer event
            // that comes before the compositor applies the last margin does not count the motion twice.
            // A dropped event loses nothing: the next one uses the absolute pointer position again.
            property double lastMoveMs: 0
            onPressed: (mouse) => { startX = mouse.x; startY = mouse.y; moved = false }
            onPositionChanged: (mouse) => {
                var dx = mouse.x - startX
                var dy = mouse.y - startY
                if (!moved && Math.abs(dx) + Math.abs(dy) < 6)
                    return
                moved = true
                var now = Date.now()
                if (now - lastMoveMs < 16)
                    return
                lastMoveMs = now
                root.atDefault = false
                root.posX += dx
                root.posY += dy
                root.clampPosition()
            }
            onReleased: {
                if (moved)
                    backend.savePosition(root.posX, root.posY)
                else
                    root.expanded = backend.online && !root.expanded
            }
        }
    }
}
