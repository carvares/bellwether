// Layout C, "Techno / HUD": monospace numerals, thin lines, corner brackets and one cell for each agent.
// The visual reference is design/layouts/c-hud.qml. A skin is only drawing: the state and the rules are in
// PanelModel.qml, the pointer handling is in Main.qml (it finds the rows by their hitRole).
import QtQuick
import ".."

Item {
    id: skin

    required property PanelModel panel

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

    implicitWidth: frame.width
    implicitHeight: frame.height

    Rectangle {
        id: frame
        width: 320
        height: column.height + 22
        color: "#f00b0e11"
        border.width: 1
        border.color: skin.line

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
                Rectangle { x: 0; y: bracket.atBottom ? 12 : 0; width: 14; height: 2; color: skin.signalColor }
                Rectangle { x: bracket.atRight ? 12 : 0; y: 0; width: 2; height: 14; color: skin.signalColor }
            }
        }

        Column {
            id: column
            x: skin.inset
            y: 11
            width: parent.width - skin.inset * 2

            // Header: name, total, and the top status as a lamp with a word.
            Item {
                width: parent.width
                height: 22
                Text {
                    id: nameWord
                    anchors.verticalCenter: parent.verticalCenter
                    text: "BELLWETHER"
                    color: skin.dim
                    font { family: skin.mono; pixelSize: 10; letterSpacing: 2; weight: Font.Bold }
                }
                Text {
                    readonly property bool isTotal: true
                    anchors.left: nameWord.right
                    anchors.leftMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    text: skin.panel.online ? "AGENTS " + skin.panel.pad2(skin.panel.total) : "NO LINK"
                    color: skin.dim
                    font { family: skin.mono; pixelSize: 10; letterSpacing: 1 }
                }
                Text {
                    id: lampWord
                    readonly property bool isTopTag: true
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: skin.panel.topLabel.toUpperCase()
                    color: skin.signalColor
                    font { family: skin.mono; pixelSize: 10; letterSpacing: 1.5; weight: Font.Bold }
                }
                Rectangle {
                    anchors.right: lampWord.left
                    anchors.rightMargin: 6
                    anchors.verticalCenter: parent.verticalCenter
                    width: 6; height: 6
                    color: skin.signalColor
                }
            }

            // Cell bar: one cell for each agent, in the colour of its status. The cells fill the width.
            // With no agents, and offline: one empty track.
            Item {
                id: cells
                readonly property var states: skin.panel.cells
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
                    border.color: skin.line
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
                        color: skin.panel.stateColors[cellState]
                    }
                }
            }

            // Offline body: a hatched plate with one word.
            Item {
                visible: !skin.panel.online
                width: parent.width
                height: 44
                Rectangle {
                    y: 6
                    width: parent.width
                    height: 32
                    color: "transparent"
                    border.width: 1
                    border.color: skin.line
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
                        color: skin.dim
                        font { family: skin.mono; pixelSize: 13; letterSpacing: 4; weight: Font.Bold }
                    }
                }
            }

            Repeater {
                // The four groups stay the same items when the agents change, so a list keeps its scroll position.
                model: skin.panel.online ? 4 : 0

                Column {
                    id: groupItem
                    required property int index
                    readonly property var group: skin.panel.groups[index]
                    readonly property bool open: skin.panel.openState === group.state
                    readonly property bool empty: group.count === 0
                    readonly property color tone: group.color
                    width: column.width

                    Item {
                        id: statusRow
                        readonly property string hitRole: "status"
                        readonly property string stateName: groupItem.group.state
                        width: parent.width
                        height: skin.statusRowHeight
                        Accessible.role: Accessible.Button
                        Accessible.name: skin.panel.spokenStatus(groupItem.group)
                        Accessible.onPressAction: skin.panel.toggle(stateName)

                        // The plate of the open row, with the accent at the left. A lighter plate under the pointer.
                        Rectangle {
                            readonly property bool hovered: skin.panel.hoverItem === statusRow
                            visible: groupItem.open || hovered
                            x: -6; y: 2
                            width: parent.width + 12
                            height: parent.height - 4
                            color: skin.panel.faded(groupItem.tone, groupItem.open ? (hovered ? 0.16 : 0.10) : 0.06)
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
                            color: groupItem.empty ? "#68727c" : skin.ink
                            font { family: skin.mono; pixelSize: 12; letterSpacing: 1.5 }
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
                                font { family: skin.mono; pixelSize: 20; weight: Font.Bold }
                            }
                            Text {
                                readonly property string countFor: statusRow.stateName
                                text: groupItem.group.count
                                color: groupItem.empty ? "#4a555f" : groupItem.group.attention ? groupItem.tone : skin.ink
                                font { family: skin.mono; pixelSize: 20; weight: Font.Bold }
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
                            panel: skin.panel
                            stateName: groupItem.group.state
                            rowHeight: skin.agentRowHeight
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
                                    color: skin.ink
                                    elide: Text.ElideRight
                                    font { family: skin.mono; pixelSize: 12 }
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
                                    font { family: skin.mono; pixelSize: 11 }
                                }
                                Text {
                                    id: detail
                                    anchors.right: parent.right
                                    anchors.rightMargin: agentList.longer ? 10 : 0
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: Math.min(implicitWidth, agentRow.failed ? 200 : 120)
                                    elide: Text.ElideRight
                                    text: agentRow.failed ? "! " + skin.panel.failedMessage
                                        : agentRow.opening ? "> opening…"
                                        : agentRow.modelData.detail
                                    color: agentRow.failed ? "#f28b82" : agentRow.opening ? "#8ab4f8" : skin.dim
                                    font { family: skin.mono; pixelSize: 11 }
                                }
                            }

                            // Scroll track.
                            overlay: Item {
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

                        // Scroll hint: the rows on the screen and the direction in which more rows are.
                        Text {
                            readonly property bool isScrollHint: true
                            visible: agentList.longer
                            x: 20
                            y: agentList.height + 2
                            text: "ROWS " + skin.panel.pad2(agentList.first + 1) + "–" + skin.panel.pad2(agentList.first + agentList.shown)
                                + " / " + skin.panel.pad2(agentList.count) + (agentList.atEnd ? "  ▲ SCROLL" : "  ▼ SCROLL")
                            color: "#68727c"
                            font { family: skin.mono; pixelSize: 10; letterSpacing: 1 }
                        }
                    }
                }
            }

            // The message of a failed jump when its agent has no row (the agent is gone, or Herdr is offline).
            Text {
                visible: skin.panel.failedAlone
                width: parent.width
                height: 24
                leftPadding: 2
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                text: "! " + skin.panel.failedMessage
                color: "#f28b82"
                font { family: skin.mono; pixelSize: 11 }
            }
        }
    }
}
