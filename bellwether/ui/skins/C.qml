// Layout C, "Techno / HUD": monospace numerals, thin lines, corner brackets and one cell for each agent.
// The visual reference is design/layouts/c-hud.qml. A skin is only drawing: the state and the rules are in
// PanelModel.qml, the pointer handling is in Main.qml (it finds the rows by their hitRole).
import QtQuick
import ".."

Item {
    id: skin

    required property PanelModel panel

    // The rows grow with a larger font (theme.fit).
    readonly property int statusRowHeight: theme.fit(32)
    readonly property int agentRowHeight: theme.fit(28)
    readonly property int inset: 14
    // The colour of the top status: the corner brackets and the tag in the header. Neutral with no agents
    // and when Herdr is offline.
    readonly property color signalColor: panel.quiet ? theme.neutralColor : panel.topColor
    readonly property string mono: theme.fontFamily
    readonly property color line: theme.lineColor
    readonly property color dim: theme.dimColor
    readonly property color ink: theme.textColor

    implicitWidth: frame.width
    implicitHeight: frame.height

    CTheme { id: theme }

    Rectangle {
        id: frame
        width: 320
        height: column.height + 22
        color: theme.panelColor
        border.width: theme.frameWidth
        border.color: theme.frameColor

        // Corner brackets in the colour of the top status.
        Loader {
            id: brackets
            anchors.fill: parent
            sourceComponent: theme.decoration
            Binding { target: brackets.item; property: "tone"; value: skin.signalColor }
        }

        Column {
            id: column
            x: skin.inset
            y: 11
            width: parent.width - skin.inset * 2

            // Header: name, total, and the top status as a lamp with a word.
            // With a larger or a wider font the three parts do not all fit: the name goes first (it is not
            // information), and then the total gets shorter.
            Item {
                id: header
                // The room at the left of the lamp and its word.
                readonly property real room: width - lampWord.implicitWidth - 12 - 8
                readonly property bool named: nameWord.implicitWidth + 12 + totalWord.implicitWidth <= room
                width: parent.width
                height: theme.fit(22)
                Text {
                    id: nameWord
                    visible: header.named
                    anchors.verticalCenter: parent.verticalCenter
                    text: "BELLWETHER"
                    color: skin.dim
                    font { family: skin.mono; pixelSize: theme.smallSize; letterSpacing: 2; weight: Font.Bold }
                }
                Text {
                    id: totalWord
                    readonly property bool isTotal: true
                    x: header.named ? nameWord.width + 12 : 0
                    width: Math.min(implicitWidth, header.room - x)
                    elide: Text.ElideRight
                    anchors.verticalCenter: parent.verticalCenter
                    text: skin.panel.online ? "AGENTS " + skin.panel.pad2(skin.panel.total) : "NO LINK"
                    color: skin.dim
                    font { family: skin.mono; pixelSize: theme.smallSize; letterSpacing: 1 }
                }
                Text {
                    id: lampWord
                    readonly property bool isTopTag: true
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: skin.panel.topLabel.toUpperCase()
                    color: skin.signalColor
                    font { family: skin.mono; pixelSize: theme.smallSize; letterSpacing: 1.5; weight: Font.Bold }
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
                height: theme.fit(44)
                Rectangle {
                    y: 6
                    width: parent.width
                    height: parent.height - 12
                    color: "transparent"
                    border.width: 1
                    border.color: skin.line
                    clip: true
                    Repeater {
                        model: 40
                        Rectangle {
                            required property int index
                            x: index * 10 - 40; y: -10
                            width: 1; height: parent.height + 28
                            rotation: 35
                            color: theme.hatchColor
                        }
                    }
                    Text {
                        anchors.centerIn: parent
                        text: "OFFLINE"
                        color: skin.dim
                        font { family: skin.mono; pixelSize: theme.noticeSize; letterSpacing: 4; weight: Font.Bold }
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
                            border.color: groupItem.empty ? theme.markColor : groupItem.tone
                        }
                        Text {
                            id: nameText
                            x: 20
                            anchors.verticalCenter: parent.verticalCenter
                            text: groupItem.group.label.toUpperCase()
                            color: groupItem.empty ? theme.faintColor : skin.ink
                            font { family: skin.mono; pixelSize: theme.titleSize; letterSpacing: 1.5 }
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
                                Rectangle { width: 2; height: 1; color: theme.dotColor }
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
                                color: theme.guideColor
                                font { family: skin.mono; pixelSize: theme.numeralSize; weight: Font.Bold }
                            }
                            Text {
                                readonly property string countFor: statusRow.stateName
                                text: groupItem.group.count
                                color: groupItem.empty ? theme.ghostColor : groupItem.group.attention ? groupItem.tone : skin.ink
                                font { family: skin.mono; pixelSize: theme.numeralSize; weight: Font.Bold }
                            }
                        }
                    }

                    Item {
                        visible: groupItem.open
                        width: parent.width
                        // More rows than fit: a line under the list says so.
                        height: agentList.height + (agentList.longer ? theme.fit(20) : 4)

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
                                    color: theme.hoverColor
                                }
                                // Tree lines from the status marker to each agent.
                                Rectangle {
                                    x: 5; width: 1
                                    height: agentRow.last ? parent.height / 2 : parent.height
                                    color: theme.guideColor
                                }
                                Rectangle { x: 5; y: parent.height / 2; width: 9; height: 1; color: theme.guideColor }
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
                                    // As many pixels as the icon has on the screen at a large scale.
                                    sourceSize: Qt.size(16 * skin.panel.pixelScale, 16 * skin.panel.pixelScale)
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
                                    font { family: skin.mono; pixelSize: theme.bodySize }
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
                                    color: theme.faintColor
                                    font { family: skin.mono; pixelSize: theme.detailSize }
                                }
                                Text {
                                    id: detail
                                    anchors.right: parent.right
                                    anchors.rightMargin: agentList.longer ? 10 : 0
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: Math.min(implicitWidth, agentRow.failed ? 200 : 120)
                                    elide: Text.ElideRight
                                    text: (agentRow.note === "failed" ? "! " : agentRow.note === "opening" ? "> " : "")
                                        + agentRow.noteText
                                    color: agentRow.note === "failed" ? skin.panel.failedColor
                                        : agentRow.note === "opening" ? skin.panel.openingColor : skin.dim
                                    font { family: skin.mono; pixelSize: theme.detailSize }
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
                                            color: lit ? skin.dim : skin.line
                                        }
                                    }
                                }
                                Rectangle { visible: !track.ticks; width: 3; height: track.span; color: skin.line }
                                Rectangle {
                                    visible: !track.ticks
                                    width: 3
                                    height: Math.max(8, track.span * agentList.height / Math.max(1, agentList.contentHeight))
                                    y: (track.span - height) * agentList.contentY
                                        / Math.max(1, agentList.contentHeight - agentList.height)
                                    color: skin.dim
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
                            color: theme.faintColor
                            font { family: skin.mono; pixelSize: theme.smallSize; letterSpacing: 1 }
                        }
                    }
                }
            }

            // The message of a failed jump when its agent has no row (the agent is gone, or Herdr is offline).
            Text {
                visible: skin.panel.failedAlone
                width: parent.width
                height: theme.fit(24)
                leftPadding: 2
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                text: "! " + skin.panel.failedMessage
                color: skin.panel.failedColor
                font { family: skin.mono; pixelSize: theme.detailSize }
            }
        }
    }
}
