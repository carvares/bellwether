// The floating panel, Layout C "Techno / HUD". The visual reference is design/layouts/c-hud.qml.
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
    // The group of the failed agent that was opened for the message. The message opens a group one time,
    // and again only when the agent goes to a different group, so the person can close or change the group.
    property string failedShownIn: ""
    property Item hoverRow: null
    // The refresh rate of the screen of the window, in Hz. The program sets it (QML does not have it). 0: unknown.
    property real refreshRate: 0
    // The shortest time between two moves of a drag: one frame of the screen, from 4 ms to 20 ms.
    readonly property real minMoveMs: refreshRate > 0 ? Math.min(20, Math.max(4, 1000 / refreshRate)) : 16
    readonly property int edge: 16
    readonly property int statusRowHeight: 32
    readonly property int agentRowHeight: 28
    readonly property int maxAgentRows: 8
    readonly property int inset: 14
    readonly property var stateColors: stateColors_
    // The sum of the four counts. 0 when Herdr is offline.
    readonly property int total: {
        var sum = 0
        var groups = backend.online ? backend.groups : []
        for (var i = 0; i < groups.length; i++)
            sum += groups[i].count
        return sum
    }
    // The colour of the top status: the corner brackets and the tag in the header. Neutral with no agents
    // and when Herdr is offline.
    readonly property color signal: backend.topState === "none" || backend.topState === "offline" ? "#6b747d"
        : stateColors[backend.topState]
    // Hack, or the first monospace font that this system has.
    readonly property string mono: {
        var have = Qt.fontFamilies()
        var wanted = ["Hack", "JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono"]
        for (var i = 0; i < wanted.length; i++)
            if (have.indexOf(wanted[i]) >= 0)
                return wanted[i]
        return "monospace"
    }
    readonly property color line: "#2b333b"
    readonly property color dim: "#8a949e"
    readonly property color ink: "#e3e9ee"

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

    function pad2(n) {
        return n < 10 ? "0" + n : "" + n
    }

    // "#rrggbb" with an alpha from 0 to 1.
    function faded(hex, alpha) {
        var c = Qt.color(hex)
        return Qt.rgba(c.r, c.g, c.b, alpha)
    }

    // The states of the lit cells of the bar, in the row order. One cell for each agent up to `limit` agents.
    // With more agents the `limit` cells are shared in proportion, and a state with an agent has at least one.
    function cellStates(groups, limit) {
        var sum = 0
        var i
        for (i = 0; i < groups.length; i++)
            sum += groups[i].count
        var share = []
        for (i = 0; i < groups.length; i++)
            share.push(sum <= limit ? groups[i].count
                : groups[i].count === 0 ? 0 : Math.max(1, Math.floor(groups[i].count * limit / sum)))
        if (sum > limit) {
            var used = share.reduce((a, b) => a + b, 0)
            while (used !== limit) {  // Give the cells that are left to, or take the extra ones from, the biggest state.
                var big = 0
                for (i = 1; i < share.length; i++)
                    if (share[i] > share[big])
                        big = i
                share[big] += used < limit ? 1 : -1
                used += used < limit ? 1 : -1
            }
        }
        var out = []
        for (i = 0; i < groups.length; i++)
            for (var k = 0; k < share[i]; k++)
                out.push(groups[i].state)
        return out
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
            if (failedNow !== root.failedShownIn) {
                root.failedShownIn = failedNow
                if (failedNow !== "")
                    root.openState = failedNow
            }
            if (root.openState !== "" && root.countOf(root.openState) === 0)
                root.openState = ""
        }
        function onFocusFailed(key, message) {
            root.failedKey = key
            root.failedMessage = message
            root.failedShownIn = root.stateOf(key)
            if (root.failedShownIn !== "")
                root.openState = root.failedShownIn
            failTimer.restart()
        }
    }

    Timer {
        id: failTimer
        interval: 3000
        onTriggered: { root.failedKey = ""; root.failedMessage = ""; root.failedShownIn = "" }
    }

    Rectangle {
        id: panel
        width: 320
        height: column.height + 22
        color: "#f00b0e11"
        border.width: 1
        border.color: root.line

        // Corner brackets in the colour of the top status.
        Repeater {
            model: 4
            Item {
                id: bracket
                required property int index
                readonly property bool atRight: index % 2 === 1
                readonly property bool atBottom: index > 1
                x: atRight ? panel.width - 14 : 0
                y: atBottom ? panel.height - 14 : 0
                width: 14; height: 14
                Rectangle { x: 0; y: bracket.atBottom ? 12 : 0; width: 14; height: 2; color: root.signal }
                Rectangle { x: bracket.atRight ? 12 : 0; y: 0; width: 2; height: 14; color: root.signal }
            }
        }

        Column {
            id: column
            x: root.inset
            y: 11
            width: parent.width - root.inset * 2

            // Header: name, total, and the top status as a lamp with a word.
            Item {
                width: parent.width
                height: 22
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "HERDR"
                    color: root.dim
                    font { family: root.mono; pixelSize: 10; letterSpacing: 2; weight: Font.Bold }
                }
                Text {
                    readonly property bool isTotal: true
                    x: 52
                    anchors.verticalCenter: parent.verticalCenter
                    text: backend.online ? "AGENTS " + root.pad2(root.total) : "NO LINK"
                    color: root.dim
                    font { family: root.mono; pixelSize: 10; letterSpacing: 1 }
                }
                Text {
                    id: lampWord
                    readonly property bool isTopTag: true
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: backend.topState === "none" ? "NO AGENTS" : backend.topState.toUpperCase()
                    color: root.signal
                    font { family: root.mono; pixelSize: 10; letterSpacing: 1.5; weight: Font.Bold }
                }
                Rectangle {
                    anchors.right: lampWord.left
                    anchors.rightMargin: 6
                    anchors.verticalCenter: parent.verticalCenter
                    width: 6; height: 6
                    color: root.signal
                }
            }

            // Cell bar: one cell for each agent, in the colour of its status. At least 10 cells.
            Item {
                id: cells
                readonly property int limit: 60
                readonly property var states: root.cellStates(backend.online ? backend.groups : [], limit)
                readonly property int n: Math.max(states.length, 10)
                readonly property real cellGap: n > 24 ? 1 : 2
                readonly property real cell: (width - cellGap * (n - 1)) / n
                width: parent.width
                height: 20
                Repeater {
                    model: cells.n
                    Rectangle {
                        required property int index
                        // The state of the cell. "" for an empty cell.
                        readonly property string cellState: index < cells.states.length ? cells.states[index] : ""
                        readonly property bool isCell: true
                        x: index * (cells.cell + cells.cellGap)
                        y: 5
                        width: cells.cell
                        height: 8
                        color: cellState !== "" ? root.stateColors[cellState] : "transparent"
                        border.width: cellState !== "" ? 0 : 1
                        border.color: root.line
                    }
                }
            }

            // Offline body: a hatched plate with one word.
            Item {
                visible: !backend.online
                width: parent.width
                height: 44
                Rectangle {
                    y: 6
                    width: parent.width
                    height: 32
                    color: "transparent"
                    border.width: 1
                    border.color: root.line
                    clip: true
                    Repeater {
                        model: 40
                        Rectangle {
                            required property int index
                            x: index * 10 - 40; y: -10
                            width: 1; height: 60
                            rotation: 35
                            color: "#1d242b"
                        }
                    }
                    Text {
                        anchors.centerIn: parent
                        text: "OFFLINE"
                        color: root.dim
                        font { family: root.mono; pixelSize: 13; letterSpacing: 4; weight: Font.Bold }
                    }
                }
            }

            Repeater {
                // The four groups stay the same items when the agents change, so a list keeps its scroll position.
                model: backend.online ? 4 : 0

                Column {
                    id: groupItem
                    required property int index
                    readonly property var group: backend.groups[index]
                    readonly property bool open: root.openState === group.state
                    readonly property bool empty: group.count === 0
                    readonly property color tone: root.stateColors[group.state]
                    width: column.width

                    Item {
                        id: statusRow
                        readonly property string rowKind: "status"
                        readonly property string stateName: groupItem.group.state
                        width: parent.width
                        height: root.statusRowHeight
                        Accessible.role: Accessible.Button
                        Accessible.name: groupItem.group.label + ", " + groupItem.group.count
                            + (groupItem.group.count === 1 ? " agent" : " agents")
                        Accessible.onPressAction: root.toggle(stateName)

                        // The plate of the open row, with the accent at the left. A lighter plate under the pointer.
                        Rectangle {
                            readonly property bool hovered: root.hoverRow === statusRow && !groupItem.empty
                            visible: groupItem.open || hovered
                            x: -6; y: 2
                            width: parent.width + 12
                            height: parent.height - 4
                            color: root.faded(groupItem.tone, groupItem.open ? (hovered ? 0.16 : 0.10) : 0.06)
                            Rectangle { visible: groupItem.open; width: 2; height: parent.height; color: groupItem.tone }
                        }
                        // Marker: a filled square when the status has agents, an empty one when it has none.
                        Rectangle {
                            x: 2
                            anchors.verticalCenter: parent.verticalCenter
                            width: 8; height: 8
                            color: groupItem.empty ? "transparent" : groupItem.tone
                            border.width: 1
                            border.color: groupItem.empty ? "#4a535c" : groupItem.tone
                        }
                        Text {
                            id: name
                            x: 20
                            anchors.verticalCenter: parent.verticalCenter
                            text: groupItem.group.label.toUpperCase()
                            color: groupItem.empty ? "#68727c" : root.ink
                            font { family: root.mono; pixelSize: 12; letterSpacing: 1.5 }
                        }
                        // Dotted leader between the name and the numeral.
                        Row {
                            anchors.left: name.right
                            anchors.leftMargin: 10
                            anchors.right: count.left
                            anchors.rightMargin: 10
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.verticalCenterOffset: 4
                            height: 1
                            spacing: 4
                            clip: true
                            Repeater {
                                model: 40
                                Rectangle { width: 2; height: 1; color: "#343d46" }
                            }
                        }
                        // The count with two digits. The zero at the front is dim.
                        Row {
                            id: count
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            Text {
                                visible: groupItem.group.count < 10
                                text: "0"
                                color: "#3a444d"
                                font { family: root.mono; pixelSize: 20; weight: Font.Bold }
                            }
                            Text {
                                readonly property string countOf: statusRow.stateName
                                text: groupItem.group.count
                                color: groupItem.empty ? "#4a555f" : groupItem.group.attention ? groupItem.tone : root.ink
                                font { family: root.mono; pixelSize: 20; weight: Font.Bold }
                            }
                        }
                    }

                    Item {
                        id: listBox
                        readonly property int shown: Math.min(groupItem.group.count, root.maxAgentRows)
                        // More rows than fit: the list scrolls, and a line under it says so.
                        readonly property bool longer: groupItem.group.count > root.maxAgentRows
                        visible: groupItem.open
                        width: parent.width
                        height: shown * root.agentRowHeight + (longer ? 20 : 4)

                        Flickable {
                            id: agentList
                            // True when the group has more rows than fit. The pointer handler of the panel
                            // then scrolls this list with the wheel.
                            readonly property bool scrolls: contentHeight > height
                            // The number of the first row on the screen, from 0.
                            readonly property int first: Math.round(contentY / root.agentRowHeight)
                            width: parent.width
                            height: listBox.shown * root.agentRowHeight
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

                                    Item {
                                        id: agentRow
                                        required property var modelData
                                        required property int index
                                        readonly property string rowKind: "agent"
                                        readonly property string key: modelData.key
                                        readonly property bool failed: root.failedKey === key
                                        readonly property bool opening: backend.opening === key
                                        readonly property bool last: index === groupItem.group.agents.length - 1
                                        width: agentRows.width
                                        height: root.agentRowHeight
                                        Accessible.role: Accessible.Button
                                        Accessible.name: modelData.spoken
                                        Accessible.onPressAction: backend.focus(key)

                                        Rectangle {
                                            visible: root.hoverRow === agentRow
                                            x: 14; y: 2
                                            width: parent.width - 14 + 6
                                            height: parent.height - 4
                                            color: "#14e3e9ee"
                                        }
                                        // Tree lines from the status marker to each agent.
                                        Rectangle {
                                            x: 5; width: 1
                                            height: agentRow.last ? parent.height / 2 : parent.height
                                            color: "#3a444d"
                                        }
                                        Rectangle { x: 5; y: parent.height / 2; width: 9; height: 1; color: "#3a444d" }
                                        // The icon that the Herdr app shows for the program of the agent.
                                        Image {
                                            id: programIcon
                                            readonly property bool isProgramIcon: true
                                            // An icon that does not load is not shown: the row has no gap.
                                            visible: agentRow.modelData.icon !== "" && status !== Image.Error
                                            x: 20
                                            width: 16
                                            height: 16
                                            anchors.verticalCenter: parent.verticalCenter
                                            sourceSize: Qt.size(16, 16)
                                            source: agentRow.modelData.icon
                                        }
                                        Text {
                                            id: label
                                            x: programIcon.visible ? 44 : 20
                                            width: Math.min(implicitWidth, detail.x - 8 - x
                                                - (address.visible ? address.width + 6 : 0))
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: agentRow.modelData.label
                                            color: root.ink
                                            elide: Text.ElideRight
                                            font { family: root.mono; pixelSize: 12 }
                                        }
                                        // The terminal address, only for rows that look the same without it.
                                        Text {
                                            id: address
                                            // The failure message needs the width.
                                            visible: agentRow.modelData.address !== "" && !agentRow.failed
                                            anchors.left: label.right
                                            anchors.leftMargin: 6
                                            anchors.baseline: label.baseline
                                            text: "[" + agentRow.modelData.address + "]"
                                            color: "#68727c"
                                            font { family: root.mono; pixelSize: 11 }
                                        }
                                        Text {
                                            id: detail
                                            anchors.right: parent.right
                                            anchors.rightMargin: listBox.longer ? 10 : 0
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: Math.min(implicitWidth, agentRow.failed ? 200 : 120)
                                            elide: Text.ElideRight
                                            text: agentRow.failed ? "! " + root.failedMessage
                                                : agentRow.opening ? "> opening…"
                                                : agentRow.modelData.detail
                                            color: agentRow.failed ? "#f28b82" : agentRow.opening ? "#8ab4f8" : root.dim
                                            font { family: root.mono; pixelSize: 11 }
                                        }
                                    }
                                }
                            }
                        }

                        // Scroll track. Its parent has no size, so the pointer handler does not find it
                        // (findAt uses childAt): a click or a wheel turn on it goes to the row below it.
                        Item {
                            id: track
                            readonly property int count: groupItem.group.count
                            readonly property real span: agentList.height - 8
                            // One tick for each agent while a tick is 1 px or more. One bar for a longer list.
                            readonly property bool ticks: track.count <= (track.span + 2) / 3
                            visible: listBox.longer
                            x: listBox.width - 3
                            y: 4

                            Column {
                                spacing: 2
                                Repeater {
                                    model: track.visible && track.ticks ? track.count : 0
                                    Rectangle {
                                        required property int index
                                        readonly property bool isScrollTick: true
                                        // Bright for the rows on the screen.
                                        readonly property bool lit: index >= agentList.first
                                            && index < agentList.first + listBox.shown
                                        width: 3
                                        height: (track.span - 2 * (track.count - 1)) / track.count
                                        color: lit ? "#8a949e" : "#2b333b"
                                    }
                                }
                            }
                            Rectangle { visible: !track.ticks; width: 3; height: track.span; color: "#2b333b" }
                            Rectangle {
                                visible: !track.ticks
                                width: 3
                                height: Math.max(8, track.span * agentList.height / Math.max(1, agentList.contentHeight))
                                y: (track.span - height) * agentList.contentY
                                    / Math.max(1, agentList.contentHeight - agentList.height)
                                color: "#8a949e"
                            }
                        }
                        // Scroll hint: the rows on the screen and the direction in which more rows are.
                        Text {
                            readonly property bool isScrollHint: true
                            readonly property bool atEnd: agentList.contentY >= agentList.contentHeight - agentList.height
                            visible: listBox.longer
                            x: 20
                            y: agentList.height + 2
                            text: "ROWS " + root.pad2(agentList.first + 1) + "–" + root.pad2(agentList.first + listBox.shown)
                                + " / " + root.pad2(groupItem.group.count) + (atEnd ? "  ▲ SCROLL" : "  ▼ SCROLL")
                            color: "#68727c"
                            font { family: root.mono; pixelSize: 10; letterSpacing: 1 }
                        }
                    }
                }
            }

            // The message of a failed jump when its agent has no row (the agent is gone, or Herdr is offline).
            Text {
                visible: root.failedKey !== "" && root.failedState === ""
                width: parent.width
                height: 24
                leftPadding: 2
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                text: "! " + root.failedMessage
                color: "#f28b82"
                font { family: root.mono; pixelSize: 11 }
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
            // Time of the last margin change. At most one change in each frame of the screen (minMoveMs), so that
            // a pointer event that comes before the compositor applies the last margin does not count the motion twice.
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
                if (now - lastMoveMs < root.minMoveMs)
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
