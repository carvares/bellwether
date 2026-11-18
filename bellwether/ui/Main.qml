// The floating panel, Layout C "Techno / HUD". The visual reference is design/layouts/c-hud.qml.
import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell

Window {
    id: root

    // The state and the rules that every layout uses.
    // (QtObject: Python reads this property, and it has no converter for a QML type.)
    readonly property QtObject panel: panelModel
    // The open group and the row under the pointer, for tests and scripts.
    property alias openState: panelModel.openState
    property alias hoverRow: panelModel.hoverItem
    // The place of the panel, from the top-left corner of its screen (screenName).
    property int posX: 0
    property int posY: 0
    // The name of the screen that holds the panel: the layer surface is on the output of this screen.
    // "" until the start is complete.
    property string screenName: ""
    // The name of the screen whose output the layer surface was made on. A surface gets its output when it is made.
    property string surfaceScreen: ""
    // The screens of the desktop. Each has name, virtualX, virtualY, width and height. A test gives its own list.
    property var screenSource: Qt.application.screens
    // The screen that holds the panel as {name, x, y, width, height}, with x and y in the whole desktop.
    // The screen of the window while the named screen is not there.
    readonly property var home: screenNamed(screenName)
        || ({name: Screen.name, x: Screen.virtualX, y: Screen.virtualY, width: Screen.width, height: Screen.height})
    // True from the time the compositor closes the surface (its monitor went away) until the panel shows again.
    property bool closedByCompositor: false
    // True until the user moves the widget: it then stays at the top-right corner when its size changes.
    property bool atDefault: false
    // The refresh rate of the screen of the window, in Hz. The program sets it (QML does not have it). 0: unknown.
    property real refreshRate: 0
    // The shortest time between two moves of a drag: two frames of the screen, from 4 ms to 20 ms. A new margin
    // goes to the compositor with the next commit, and Qt holds that commit until the frame before it is on the
    // screen. So a pointer event can come one frame after a move and still be relative to the old place.
    readonly property real minMoveMs: refreshRate > 0 ? Math.min(20, Math.max(4, 2000 / refreshRate)) : 16
    readonly property int edge: 16
    readonly property int statusRowHeight: 32
    readonly property int agentRowHeight: 28
    readonly property int inset: 14
    // The colour of the top status: the corner brackets and the tag in the header. Neutral with no agents
    // and when Herdr is offline.
    readonly property color signalColor: panel.quiet ? "#6b747d" : panel.topColor
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
    width: frame.width
    height: frame.height

    LayerShell.Window.scope: "bellwether"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.exclusionZone: -1
    LayerShell.Window.margins.left: posX
    LayerShell.Window.margins.top: posY
    // The compositor applies a new margin only with the next commit of the surface, so ask for a frame.
    LayerShell.Window.onMarginsChanged: root.requestUpdate()

    // Keep the panel on its screen. During a drag the panel can be on two screens, so the drag does this itself.
    function clampPosition() {
        if (pointerArea.pressed && pointerArea.moved)
            return
        if (atDefault) {
            posX = home.width - width - edge
            posY = edge
        }
        var maxX = Math.max(0, home.width - width)
        var maxY = Math.max(0, home.height - height)
        posX = Math.min(Math.max(0, posX), maxX)
        posY = Math.min(Math.max(0, posY), maxY)
    }

    // The screens as {name, x, y, width, height}, with x and y in the whole desktop.
    function screens() {
        var out = []
        var list = screenSource
        for (var i = 0; i < list.length; i++)
            out.push({name: list[i].name, x: list[i].virtualX, y: list[i].virtualY,
                      width: list[i].width, height: list[i].height})
        return out
    }

    function screenNamed(name) {
        var list = screens()
        for (var i = 0; i < list.length; i++)
            if (list[i].name === name)
                return list[i]
        return null
    }

    // The screen of `list` that holds the point, or the screen nearest to it. null with no screens.
    function screenAt(list, px, py) {
        var best = null
        var bestGap = 0
        for (var i = 0; i < list.length; i++) {
            var s = list[i]
            var gapX = Math.max(s.x - px, 0, px - (s.x + s.width - 1))
            var gapY = Math.max(s.y - py, 0, py - (s.y + s.height - 1))
            if (best === null || gapX + gapY < bestGap) {
                best = s
                bestGap = gapX + gapY
            }
        }
        return best
    }

    // Where a drag can put a panel of w × h that wants to be at (gx, gy) of the desktop: the nearest place where
    // the four corners of the panel are on a screen. So the panel goes across an edge that two screens share,
    // and it stops at an edge that has no screen behind it.
    function dragPlace(list, gx, gy, w, h) {
        function shown(px, py) {
            for (var i = 0; i < list.length; i++)
                if (px >= list[i].x && px < list[i].x + list[i].width
                        && py >= list[i].y && py < list[i].y + list[i].height)
                    return true
            return false
        }
        function fits(x, y) {
            return shown(x, y) && shown(x + w - 1, y) && shown(x, y + h - 1) && shown(x + w - 1, y + h - 1)
        }
        if (list.length === 0 || fits(gx, gy))
            return {x: gx, y: gy}
        var best = null
        var bestGap = 0
        for (var i = 0; i < list.length; i++) {
            // Inside this screen in one direction (the panel can then be on two screens), or in both.
            var cx = Math.min(Math.max(list[i].x, gx), list[i].x + Math.max(0, list[i].width - w))
            var cy = Math.min(Math.max(list[i].y, gy), list[i].y + Math.max(0, list[i].height - h))
            var tries = [[gx, cy], [cx, gy], [cx, cy]]
            for (var k = 0; k < 3; k++) {
                var gap = Math.abs(tries[k][0] - gx) + Math.abs(tries[k][1] - gy)
                if ((k === 2 || fits(tries[k][0], tries[k][1])) && (best === null || gap < bestGap)) {
                    best = tries[k]
                    bestGap = gap
                }
            }
        }
        return {x: best[0], y: best[1]}
    }

    // The place on the screen `to` for a panel at (x, y) of the screen `from`: the same distance to the nearer
    // side edge and to the nearer of the top and bottom edges.
    function carried(from, to, x, y, w, h) {
        return {x: x + w / 2 > from.width / 2 ? to.width - (from.width - x) : x,
                y: y + h / 2 > from.height / 2 ? to.height - (from.height - y) : y}
    }

    // Put the panel on the screen `target` (one of screens()) at (x, y) of it, kept on that screen.
    // A layer surface gets its output when it is made, from the screen of the window. So for a different
    // output: hide the window, change its screen, show it again.
    function rehome(target, x, y) {
        var real = null
        var list = Qt.application.screens
        for (var i = 0; i < list.length; i++)
            if (list[i].name === target.name)
                real = list[i]
        var rebind = real !== null && surfaceScreen !== target.name
        var shown = visible
        if (rebind)
            visible = false
        screenName = target.name
        posX = x
        posY = y
        clampPosition()
        if (rebind) {
            screen = real
            // Qt takes the screen of a new surface from the place of the window.
            root.x = target.x + posX
            root.y = target.y + posY
            surfaceScreen = target.name
            visible = shown
        }
    }

    // The end of a drag: the panel belongs to the screen that holds its centre.
    function settle() {
        var to = screenAt(screens(), home.x + posX + width / 2, home.y + posY + height / 2) || home
        rehome(to, home.x + posX - to.x, home.y + posY - to.y)
        backend.savePosition(posX, posY, screenName)
    }

    // The tray entry: the panel goes to the next screen of the list, to the same place from the nearer edges.
    function moveToNextScreen() {
        var list = screens()
        if (list.length < 2)
            return
        var index = 0
        for (var i = 0; i < list.length; i++)
            if (list[i].name === home.name)
                index = i
        var to = list[(index + 1) % list.length]
        var place = carried(home, to, posX, posY, width, height)
        rehome(to, place.x, place.y)
        backend.savePosition(posX, posY, screenName)
    }

    // After a change of the screens. When the monitor of the panel is gone, the panel goes to the screen that
    // the window has now, and it shows again when the compositor closed it. The saved place stays: the panel
    // is on its monitor again at the next start with that monitor.
    function recover() {
        if (screenName !== "" && screenNamed(screenName) === null) {
            var to = screenNamed(Screen.name) || screens()[0]
            if (to) {
                surfaceScreen = ""
                rehome(to, posX, posY)
            }
        }
        if (closedByCompositor) {
            closedByCompositor = false
            visible = true
        }
    }

    // The first item at (x, y) of `item`, from the outside in, whose hitRole is one of `roles`: "status" (a
    // status row, with stateName), "agent" (an agent row, with key) or "scroll" (a list that scrolls).
    function hitAt(item, x, y, roles) {
        var child = item.childAt(x, y)
        while (child) {
            if (roles.indexOf(child.hitRole) >= 0)
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
        surfaceScreen = Screen.name
        // The saved screen. A file with no screen name, or a screen that is not there: the screen of the window.
        var saved = backend.savedScreen === "" ? null : screenNamed(backend.savedScreen)
        screenName = saved ? saved.name : Screen.name
        var valid = (saved !== null || backend.savedScreen === "")
            && backend.savedX >= 0 && backend.savedY >= 0
            && backend.savedX <= home.width - width
            && backend.savedY <= home.height - height
        atDefault = !valid
        rehome(home, valid ? backend.savedX : 0, valid ? backend.savedY : 0)
    }
    onWidthChanged: clampPosition()
    onHeightChanged: clampPosition()
    // Not while the screen of the panel is gone: recover() then gives the panel a screen.
    onHomeChanged: if (screenNamed(screenName) !== null) clampPosition()
    onScreenSourceChanged: recoverTimer.restart()
    // Only the compositor closes the window (the tray hides it): the monitor of the surface went away.
    onClosing: {
        closedByCompositor = true
        recoverTimer.restart()
    }

    // After the screens change, Qt needs a moment to give the window its new screen.
    Timer {
        id: recoverTimer
        interval: 200
        onTriggered: root.recover()
    }

    PanelModel {
        id: panelModel
    }

    Rectangle {
        id: frame
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
                x: atRight ? frame.width - 14 : 0
                y: atBottom ? frame.height - 14 : 0
                width: 14; height: 14
                Rectangle { x: 0; y: bracket.atBottom ? 12 : 0; width: 14; height: 2; color: root.signalColor }
                Rectangle { x: bracket.atRight ? 12 : 0; y: 0; width: 2; height: 14; color: root.signalColor }
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
                    id: nameWord
                    anchors.verticalCenter: parent.verticalCenter
                    text: "BELLWETHER"
                    color: root.dim
                    font { family: root.mono; pixelSize: 10; letterSpacing: 2; weight: Font.Bold }
                }
                Text {
                    readonly property bool isTotal: true
                    anchors.left: nameWord.right
                    anchors.leftMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.panel.online ? "AGENTS " + root.panel.pad2(root.panel.total) : "NO LINK"
                    color: root.dim
                    font { family: root.mono; pixelSize: 10; letterSpacing: 1 }
                }
                Text {
                    id: lampWord
                    readonly property bool isTopTag: true
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.panel.topLabel.toUpperCase()
                    color: root.signalColor
                    font { family: root.mono; pixelSize: 10; letterSpacing: 1.5; weight: Font.Bold }
                }
                Rectangle {
                    anchors.right: lampWord.left
                    anchors.rightMargin: 6
                    anchors.verticalCenter: parent.verticalCenter
                    width: 6; height: 6
                    color: root.signalColor
                }
            }

            // Cell bar: one cell for each agent, in the colour of its status. The cells fill the width.
            // With no agents, and offline: one empty track.
            Item {
                id: cells
                readonly property var states: root.panel.cells
                readonly property int n: states.length
                readonly property real cellGap: n > 24 ? 1 : 2
                readonly property real cell: (width - cellGap * (n - 1)) / n
                width: parent.width
                height: 20
                Rectangle {
                    readonly property bool isEmptyTrack: true
                    visible: cells.n === 0
                    y: 5
                    width: parent.width
                    height: 8
                    color: "transparent"
                    border.width: 1
                    border.color: root.line
                }
                Repeater {
                    model: cells.n
                    Rectangle {
                        required property int index
                        readonly property string cellState: cells.states[index]
                        readonly property bool isCell: true
                        x: index * (cells.cell + cells.cellGap)
                        y: 5
                        width: cells.cell
                        height: 8
                        color: root.panel.stateColors[cellState]
                    }
                }
            }

            // Offline body: a hatched plate with one word.
            Item {
                visible: !root.panel.online
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
                model: root.panel.online ? 4 : 0

                Column {
                    id: groupItem
                    required property int index
                    readonly property var group: root.panel.groups[index]
                    readonly property bool open: root.panel.openState === group.state
                    readonly property bool empty: group.count === 0
                    readonly property color tone: group.color
                    width: column.width

                    Item {
                        id: statusRow
                        readonly property string hitRole: "status"
                        readonly property string stateName: groupItem.group.state
                        width: parent.width
                        height: root.statusRowHeight
                        Accessible.role: Accessible.Button
                        Accessible.name: root.panel.spokenStatus(groupItem.group)
                        Accessible.onPressAction: root.panel.toggle(stateName)

                        // The plate of the open row, with the accent at the left. A lighter plate under the pointer.
                        Rectangle {
                            readonly property bool hovered: root.panel.hoverItem === statusRow && !groupItem.empty
                            visible: groupItem.open || hovered
                            x: -6; y: 2
                            width: parent.width + 12
                            height: parent.height - 4
                            color: root.panel.faded(groupItem.tone, groupItem.open ? (hovered ? 0.16 : 0.10) : 0.06)
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
                            id: nameText
                            x: 20
                            anchors.verticalCenter: parent.verticalCenter
                            text: groupItem.group.label.toUpperCase()
                            color: groupItem.empty ? "#68727c" : root.ink
                            font { family: root.mono; pixelSize: 12; letterSpacing: 1.5 }
                        }
                        // Dotted leader between the name and the numeral.
                        Row {
                            anchors.left: nameText.right
                            anchors.leftMargin: 10
                            anchors.right: countRow.left
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
                            id: countRow
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            Text {
                                visible: groupItem.group.count < 10
                                text: "0"
                                color: "#3a444d"
                                font { family: root.mono; pixelSize: 20; weight: Font.Bold }
                            }
                            Text {
                                readonly property string countFor: statusRow.stateName
                                text: groupItem.group.count
                                color: groupItem.empty ? "#4a555f" : groupItem.group.attention ? groupItem.tone : root.ink
                                font { family: root.mono; pixelSize: 20; weight: Font.Bold }
                            }
                        }
                    }

                    Item {
                        visible: groupItem.open
                        width: parent.width
                        // More rows than fit: a line under the list says so.
                        height: agentList.height + (agentList.longer ? 20 : 4)

                        AgentList {
                            id: agentList
                            panel: root.panel
                            stateName: groupItem.group.state
                            rowHeight: root.agentRowHeight
                            width: parent.width

                            delegate: AgentRow {
                                id: agentRow
                                view: agentList

                                Rectangle {
                                    visible: agentRow.hovered
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
                                    anchors.rightMargin: agentList.longer ? 10 : 0
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: Math.min(implicitWidth, agentRow.failed ? 200 : 120)
                                    elide: Text.ElideRight
                                    text: agentRow.failed ? "! " + root.panel.failedMessage
                                        : agentRow.opening ? "> opening…"
                                        : agentRow.modelData.detail
                                    color: agentRow.failed ? "#f28b82" : agentRow.opening ? "#8ab4f8" : root.dim
                                    font { family: root.mono; pixelSize: 11 }
                                }
                            }

                            // Scroll track.
                            overlay: Component {
                            Item {
                                id: track
                                readonly property int count: agentList.count
                                readonly property real span: agentList.height - 8
                                // One tick for each agent while a tick is 1 px or more. One bar for a longer list.
                                readonly property bool ticks: track.count <= (track.span + 2) / 3
                                visible: agentList.longer
                                x: agentList.width - 3
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
                                                && index < agentList.first + agentList.shown
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
                            }
                        }

                        // Scroll hint: the rows on the screen and the direction in which more rows are.
                        Text {
                            readonly property bool isScrollHint: true
                            visible: agentList.longer
                            x: 20
                            y: agentList.height + 2
                            text: "ROWS " + root.panel.pad2(agentList.first + 1) + "–" + root.panel.pad2(agentList.first + agentList.shown)
                                + " / " + root.panel.pad2(agentList.count) + (agentList.atEnd ? "  ▲ SCROLL" : "  ▼ SCROLL")
                            color: "#68727c"
                            font { family: root.mono; pixelSize: 10; letterSpacing: 1 }
                        }
                    }
                }
            }

            // The message of a failed jump when its agent has no row (the agent is gone, or Herdr is offline).
            Text {
                visible: root.panel.failedAlone
                width: parent.width
                height: 24
                leftPadding: 2
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                text: "! " + root.panel.failedMessage
                color: "#f28b82"
                font { family: root.mono; pixelSize: 11 }
            }
        }

        // The one pointer handler of the panel. A press that moves 6 px or more drags the widget.
        // A press that moves less is a click on the row under it: a status row opens, an agent row jumps.
        MouseArea {
            id: pointerArea
            anchors.fill: parent
            hoverEnabled: true
            property real startX: 0
            property real startY: 0
            property bool moved: false
            // Time of the last margin change. At most one change in each step (minMoveMs), so that a pointer
            // event that comes before the compositor applies the last margin does not count the motion twice.
            // A dropped event loses nothing: the next one uses the absolute pointer position again.
            property double lastMoveMs: 0
            // The row or the list under the pointer. The search starts below this handler, in the column.
            function under(point, roles) {
                return root.hitAt(column, point.x - column.x, point.y - column.y, roles)
            }
            // lastMoveMs starts again at each press: a clock that went back must not block the drag.
            onPressed: (mouse) => { startX = mouse.x; startY = mouse.y; moved = false; lastMoveMs = 0 }
            onPositionChanged: (mouse) => {
                if (!pressed) {
                    root.panel.hoverItem = under(mouse, ["status", "agent"])
                    return
                }
                var dx = mouse.x - startX
                var dy = mouse.y - startY
                if (!moved && Math.abs(dx) + Math.abs(dy) < 6)
                    return
                moved = true
                root.panel.hoverItem = null
                var now = Date.now()
                if (now - lastMoveMs < root.minMoveMs)
                    return
                lastMoveMs = now
                root.atDefault = false
                // The panel follows the pointer on all the screens. The surface stays on its output until the release.
                var place = root.dragPlace(root.screens(), root.home.x + root.posX + dx, root.home.y + root.posY + dy,
                                           root.width, root.height)
                root.posX = place.x - root.home.x
                root.posY = place.y - root.home.y
            }
            onReleased: (mouse) => {
                if (moved) {
                    moved = false
                    root.settle()
                    return
                }
                var row = under(mouse, ["status", "agent"])
                if (row && row.hitRole === "status")
                    root.panel.toggle(row.stateName)
                else if (row)
                    root.panel.jump(row.key)
            }
            onExited: root.panel.hoverItem = null
            onWheel: (wheel) => {
                var list = under(wheel, ["scroll"])
                if (list)
                    list.scrollBy(wheel.pixelDelta.y, wheel.angleDelta.y)
            }
        }
    }
}
