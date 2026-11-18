import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell

Window {
    id: root

    // The state whose agents show ("blocked", ...). "" means that no group is open. One group at a time.
    property string openState: ""
    property int posX: 0
    property int posY: 0
    // True until the user moves the widget: it then stays at the top-right corner when its size changes.
    property bool atDefault: false
    // The agent of the last failed jump and the message for it. Empty again after 3 seconds.
    property string failedKey: ""
    property string failedMessage: ""
    // The group that holds the failed agent now. "" when the agent is in no group (gone, or offline).
    readonly property string failedState: failedKey === "" ? "" : stateOf(failedKey)
    property Item hoverRow: null
    readonly property int edge: 16
    readonly property int statusRowHeight: 30
    readonly property int agentRowHeight: 26
    readonly property int maxAgentRows: 8
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

    function countOf(stateName) {
        var groups = backend.groups
        for (var i = 0; i < groups.length; i++)
            if (groups[i].state === stateName)
                return groups[i].count
        return 0
    }

    function stateOf(key) {
        var groups = backend.online ? backend.groups : []
        for (var i = 0; i < groups.length; i++)
            for (var j = 0; j < groups[i].agents.length; j++)
                if (groups[i].agents[j].key === key)
                    return groups[i].state
        return ""
    }

    // Open the group, or close it when it is open. A group without agents does not open.
    function toggle(stateName) {
        if (openState === stateName)
            openState = ""
        else if (backend.online && countOf(stateName) > 0)
            openState = stateName
    }

    // The first item at (x, y) of `item`, from the outside in, where the property `name` is set:
    // a row ("rowKind"), or a list that scrolls ("scrolls").
    function findAt(item, x, y, name) {
        var child = item.childAt(x, y)
        while (child) {
            if (child[name])
                return child
            var point = child.mapFromItem(item, x, y)
            item = child
            x = point.x
            y = point.y
            child = item.childAt(x, y)
        }
        return null
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

    Connections {
        target: backend
        function onChanged() {
            // Close the group when Herdr goes offline, so that it does not open by itself when Herdr comes back.
            if (!backend.online) {
                root.openState = ""
                return
            }
            // The failed agent can change its state: keep its message on the screen.
            // stateOf() and not failedState: that binding can be older than this signal.
            var failedNow = root.failedKey === "" ? "" : root.stateOf(root.failedKey)
            if (failedNow !== "")
                root.openState = failedNow
            if (root.openState !== "" && root.countOf(root.openState) === 0)
                root.openState = ""
        }
        function onFocusFailed(key, message) {
            root.failedKey = key
            root.failedMessage = message
            if (root.failedState !== "")
                root.openState = root.failedState
            failTimer.restart()
        }
    }

    Timer {
        id: failTimer
        interval: 3000
        onTriggered: { root.failedKey = ""; root.failedMessage = "" }
    }

    Rectangle {
        id: panel
        width: 240
        height: column.implicitHeight + 16
        radius: 12
        color: "#e6202124"
        border.color: "#3c4043"

        Column {
            id: column
            x: 8
            y: 8
            width: panel.width - 16

            Text {
                visible: !backend.online
                height: root.statusRowHeight
                leftPadding: 6
                verticalAlignment: Text.AlignVCenter
                text: "offline"
                color: "#9aa0a6"
                font.pixelSize: 14
            }

            Repeater {
                // The four groups stay the same items when the agents change, so a list keeps its scroll position.
                model: backend.online ? 4 : 0

                Column {
                    id: groupItem
                    required property int index
                    readonly property var group: backend.groups[index]
                    readonly property bool open: root.openState === group.state
                    readonly property bool alert: group.attention && group.count > 0
                    width: column.width

                    Rectangle {
                        id: statusRow
                        readonly property string rowKind: "status"
                        readonly property string stateName: groupItem.group.state
                        width: parent.width
                        height: root.statusRowHeight
                        radius: 6
                        color: root.hoverRow === statusRow && groupItem.group.count > 0 ? "#3c4043"
                            : groupItem.open ? "#2d2f33" : "transparent"
                        opacity: groupItem.group.count === 0 ? 0.35 : 1.0
                        Accessible.role: Accessible.Button
                        Accessible.name: groupItem.group.label + ", " + groupItem.group.count
                            + (groupItem.group.count === 1 ? " agent" : " agents")
                        Accessible.onPressAction: root.toggle(stateName)

                        Rectangle {
                            id: dot
                            x: 6
                            width: 10
                            height: 10
                            radius: 5
                            anchors.verticalCenter: parent.verticalCenter
                            color: root.stateColors[statusRow.stateName]
                        }
                        Text {
                            anchors.left: dot.right
                            anchors.leftMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            text: groupItem.group.label
                            color: "#e8eaed"
                            font.pixelSize: 14
                        }
                        Text {
                            anchors.right: parent.right
                            anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            text: groupItem.group.count
                            color: groupItem.alert ? root.stateColors[statusRow.stateName] : "#e8eaed"
                            font.pixelSize: 14
                            font.bold: groupItem.alert
                        }
                    }

                    Item {
                        visible: groupItem.open
                        width: parent.width
                        height: Math.min(groupItem.group.count, root.maxAgentRows) * root.agentRowHeight

                        Flickable {
                            id: agentList
                            // True when the group has more rows than fit. The pointer handler of the panel
                            // then scrolls this list with the wheel.
                            readonly property bool scrolls: contentHeight > height
                            anchors.fill: parent
                            contentWidth: width
                            contentHeight: agentRows.height
                            interactive: false
                            clip: true
                            onContentHeightChanged: contentY = Math.max(0, Math.min(contentY, contentHeight - height))

                            Column {
                                id: agentRows
                                width: agentList.width

                                Repeater {
                                    model: groupItem.open ? groupItem.group.agents : []

                                    Rectangle {
                                        id: agentRow
                                        required property var modelData
                                        readonly property string rowKind: "agent"
                                        readonly property string key: modelData.key
                                        readonly property bool failed: root.failedKey === key
                                        width: agentRows.width
                                        height: root.agentRowHeight
                                        radius: 6
                                        color: root.hoverRow === agentRow ? "#3c4043" : "transparent"
                                        Accessible.role: Accessible.Button
                                        Accessible.name: "Go to " + modelData.name
                                        Accessible.onPressAction: backend.focus(key)

                                        Text {
                                            anchors.left: parent.left
                                            anchors.leftMargin: 24
                                            anchors.right: detail.left
                                            anchors.rightMargin: 8
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: agentRow.modelData.name
                                            color: "#e8eaed"
                                            font.pixelSize: 13
                                            elide: Text.ElideRight
                                        }
                                        Text {
                                            id: detail
                                            anchors.right: parent.right
                                            anchors.rightMargin: 10
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: Math.min(implicitWidth, agentRow.failed ? 150 : 100)
                                            elide: Text.ElideRight
                                            text: agentRow.failed ? root.failedMessage
                                                : backend.opening === agentRow.key ? "opening…"
                                                : agentRow.modelData.workspace
                                            color: agentRow.failed ? "#f28b82" : "#9aa0a6"
                                            font.pixelSize: 12
                                        }
                                    }
                                }
                            }
                        }

                        // Scroll indicator.
                        Rectangle {
                            visible: agentList.scrolls
                            anchors.right: parent.right
                            width: 3
                            radius: 1.5
                            color: "#9aa0a6"
                            height: Math.max(12, parent.height * parent.height / Math.max(1, agentList.contentHeight))
                            y: (parent.height - height) * agentList.contentY
                                / Math.max(1, agentList.contentHeight - agentList.height)
                        }
                    }
                }
            }

            // The message of a failed jump when its agent has no row (the agent is gone, or Herdr is offline).
            Text {
                visible: root.failedKey !== "" && root.failedState === ""
                width: parent.width
                height: 24
                leftPadding: 6
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                text: root.failedMessage
                color: "#f28b82"
                font.pixelSize: 12
            }
        }

        // The one pointer handler of the panel. A press that moves 6 px or more drags the widget.
        // A press that moves less is a click on the row under it: a status row opens, an agent row jumps.
        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            property real startX: 0
            property real startY: 0
            property bool moved: false
            // Time of the last margin change. At most one change in each 16 ms, so that a pointer event
            // that comes before the compositor applies the last margin does not count the motion twice.
            // A dropped event loses nothing: the next one uses the absolute pointer position again.
            property double lastMoveMs: 0
            // The row or the list under the pointer. The search starts below this handler, in the column.
            function under(point, name) {
                return root.findAt(column, point.x - column.x, point.y - column.y, name)
            }
            // lastMoveMs starts again at each press: a clock that went back must not block the drag.
            onPressed: (mouse) => { startX = mouse.x; startY = mouse.y; moved = false; lastMoveMs = 0 }
            onPositionChanged: (mouse) => {
                if (!pressed) {
                    root.hoverRow = under(mouse, "rowKind")
                    return
                }
                var dx = mouse.x - startX
                var dy = mouse.y - startY
                if (!moved && Math.abs(dx) + Math.abs(dy) < 6)
                    return
                moved = true
                root.hoverRow = null
                var now = Date.now()
                if (now - lastMoveMs < 16)
                    return
                lastMoveMs = now
                root.atDefault = false
                root.posX += dx
                root.posY += dy
                root.clampPosition()
            }
            onReleased: (mouse) => {
                if (moved) {
                    backend.savePosition(root.posX, root.posY)
                    return
                }
                var row = under(mouse, "rowKind")
                if (row && row.rowKind === "status")
                    root.toggle(row.stateName)
                else if (row)
                    backend.focus(row.key)
            }
            onExited: root.hoverRow = null
            onWheel: (wheel) => {
                var list = under(wheel, "scrolls")
                if (!list)
                    return
                var step = wheel.pixelDelta.y !== 0 ? wheel.pixelDelta.y
                    : wheel.angleDelta.y / 120 * 2 * root.agentRowHeight
                list.contentY = Math.max(0, Math.min(list.contentY - step, list.contentHeight - list.height))
            }
        }
    }
}
