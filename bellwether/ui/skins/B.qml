// Layout B, "Tiles": a 2×2 grid of status tiles with large numerals; the agents of the open status show in a
// card below the grid. The visual reference is design/layouts/b-tiles.qml. A skin is only drawing: the state
// and the rules are in PanelModel.qml, the pointer handling is in Main.qml.
import QtQuick
import ".."

Item {
    id: skin

    required property PanelModel panel

    // The rows, the tiles and the header of the card grow with a larger font (theme.fit).
    readonly property int agentRowHeight: theme.fit(30)
    // What the model and session-time line adds to the height of an agent row.
    readonly property int metaLineHeight: theme.fit(14)
    readonly property int headHeight: theme.fit(30)
    readonly property int pad: 10
    readonly property int gap: 8
    readonly property string sans: theme.fontFamily
    // The frame has the colour of the top status. Neutral with no agents and when Herdr is offline.
    readonly property color signalColor: panel.quiet ? theme.frameColor : panel.topColor

    implicitWidth: frame.width
    implicitHeight: frame.height

    BTheme { id: theme }

    Rectangle {
        id: frame
        width: 304
        height: column.height + skin.pad * 2
        radius: theme.radius
        color: theme.panelColor
        border.width: theme.frameWidth
        border.color: skin.signalColor

        Column {
            id: column
            x: skin.pad
            y: skin.pad
            width: parent.width - skin.pad * 2
            spacing: skin.gap

            Grid {
                columns: 2
                spacing: skin.gap
                width: parent.width

                Repeater {
                    // The four tiles stay the same items when the agents change.
                    model: 4

                    Rectangle {
                        id: tile
                        required property int index
                        readonly property var group: skin.panel.groups[index]
                        readonly property string hitRole: "status"
                        readonly property string stateName: group.state
                        readonly property bool open: skin.panel.openState === group.state
                        readonly property bool empty: group.count === 0
                        // A status that needs attention is a solid tile. The others are tinted.
                        readonly property bool solid: group.alert
                        // The text, the mark and the border on the solid tile: the ink for its colour.
                        readonly property color ink: theme.inkOn(group.color)
                        readonly property bool hovered: skin.panel.hoverItem === tile
                        width: (column.width - skin.gap) / 2
                        height: theme.fit(74)
                        radius: theme.itemRadius
                        color: solid ? group.color : empty ? "transparent" : skin.panel.faded(group.color, 0.13)
                        border.width: open ? 2 : empty ? 1 : 0
                        border.color: open ? (solid ? ink : group.color) : theme.lineColor
                        Accessible.role: Accessible.Button
                        Accessible.name: skin.panel.spokenStatus(group)
                        Accessible.onPressAction: skin.panel.toggle(stateName)

                        // Under the pointer the tile is a little lighter.
                        Rectangle {
                            visible: tile.hovered
                            anchors.fill: parent
                            radius: parent.radius
                            color: tile.solid ? "#24ffffff" : skin.panel.faded(tile.group.color, 0.10)
                        }
                        Text {
                            x: 12
                            y: 9
                            text: tile.group.label
                            color: tile.solid ? tile.ink : tile.empty ? theme.faintColor : theme.textColor
                            font {
                                family: skin.sans; pixelSize: theme.titleSize
                                weight: tile.solid ? Font.DemiBold : Font.Medium
                            }
                        }
                        Text {
                            readonly property string countFor: tile.stateName
                            x: 11
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 3
                            text: skin.panel.online ? tile.group.count : "–"
                            color: tile.solid ? tile.ink : tile.empty ? theme.ghostColor : tile.group.color
                            font { family: skin.sans; pixelSize: theme.numeralSize; weight: Font.DemiBold; features: { "tnum": 1 } }
                        }
                        // The mark of the open tile: a chevron that points to the list.
                        Text {
                            readonly property bool isOpenMark: true
                            visible: tile.open
                            anchors.right: parent.right
                            anchors.rightMargin: 12
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 10
                            text: "▾"
                            color: tile.solid ? tile.ink : tile.group.color
                            font { family: skin.sans; pixelSize: theme.markSize }
                        }
                    }
                }
            }

            // Offline line under the grid.
            Text {
                readonly property bool isOfflineLine: true
                visible: !skin.panel.online
                width: parent.width
                height: theme.fit(22)
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                text: "Herdr is offline"
                color: theme.dimColor
                font { family: skin.sans; pixelSize: theme.bodySize; weight: Font.Medium }
            }

            // The card of the open status: a header and the list of its agents.
            Rectangle {
                id: card
                visible: skin.panel.openState !== ""
                width: parent.width
                height: skin.headHeight + agentList.height + 6
                radius: 10
                color: theme.insetColor
                border.width: 1
                border.color: skin.panel.faded(skin.panel.openColor, 0.45)

                Rectangle {
                    x: 12; y: skin.headHeight / 2 - 3; width: 8; height: 8; radius: 4
                    color: skin.panel.openColor
                }
                Text {
                    readonly property bool isListTitle: true
                    x: 28
                    y: skin.headHeight / 2 - height / 2 + 1
                    text: skin.panel.openLabel
                    color: theme.textColor
                    font { family: skin.sans; pixelSize: theme.labelSize; weight: Font.DemiBold }
                }
                // The number of agents, or the rows on the screen when the list scrolls: "1–8 of 12".
                Text {
                    readonly property bool isListRange: true
                    anchors.right: parent.right
                    anchors.rightMargin: 12
                    y: skin.headHeight / 2 - height / 2 + 1
                    text: agentList.longer
                        ? (agentList.first + 1) + "–" + (agentList.first + agentList.shown) + " of " + agentList.count
                        : agentList.count + (agentList.count === 1 ? " agent" : " agents")
                    color: theme.dimColor
                    font { family: skin.sans; pixelSize: theme.detailSize; features: { "tnum": 1 } }
                }

                AgentList {
                    id: agentList
                    panel: skin.panel
                    rowHeight: skin.agentRowHeight
                    metaHeight: skin.metaLineHeight
                    y: skin.headHeight
                    width: parent.width

                    delegate: AgentRow {
                        id: agentRow
                        view: agentList

                        Rectangle {
                            visible: agentRow.hovered
                            x: 6; y: 2
                            width: parent.width - 12
                            height: parent.height - 3
                            radius: 6
                            color: theme.hoverColor
                        }
                        Rectangle {
                            visible: agentRow.index > 0
                            x: 12; width: parent.width - 24; height: 1
                            color: theme.separatorColor
                        }
                        // The icon that the Herdr app shows for the program of the agent.
                        Image {
                            id: programIcon
                            readonly property bool isProgramIcon: true
                            // An icon that does not load is not shown: the row has no gap.
                            visible: agentRow.modelData.icon !== "" && status !== Image.Error
                            x: 12; width: 16; height: 16
                            anchors.verticalCenter: parent.verticalCenter
                            // As many pixels as the icon has on the screen at a large scale.
                            sourceSize: Qt.size(16 * skin.panel.pixelScale, 16 * skin.panel.pixelScale)
                            source: agentRow.modelData.icon
                        }
                        Text {
                            id: label
                            x: programIcon.visible ? 36 : 12
                            width: Math.min(implicitWidth, detail.x - 10 - x - (address.visible ? address.width + 6 : 0))
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.verticalCenterOffset: agentRow.lineShift
                            text: agentRow.modelData.label
                            color: theme.textColor
                            elide: Text.ElideRight
                            font { family: skin.sans; pixelSize: theme.bodySize }
                        }
                        // The terminal address, only for rows that look the same without it.
                        Text {
                            id: address
                            visible: text !== ""
                            anchors.left: label.right
                            anchors.leftMargin: 6
                            anchors.baseline: label.baseline
                            text: agentRow.modelData.address
                            color: theme.faintColor
                            font { family: skin.sans; pixelSize: theme.smallSize; features: { "tnum": 1 } }
                        }
                        // The "Answer" control of a blocked agent, at the right end of the row. The detail is at its left.
                        AnswerControl {
                            id: answer
                            row: agentRow
                            labelItem: label
                            addressItem: address
                            tokens: theme
                            corner: 6; plated: true
                            anchors.right: parent.right
                            anchors.rightMargin: agentList.longer ? 16 : 12
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.verticalCenterOffset: answer.drop
                        }
                        Text {
                            id: detail
                            anchors.right: parent.right
                            anchors.rightMargin: (agentList.longer ? 16 : 12) + answer.reserve
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.verticalCenterOffset: agentRow.lineShift
                            width: Math.min(implicitWidth, answer.detailRoom(180, 116))
                            elide: Text.ElideRight
                            text: agentRow.noteText
                            color: agentRow.note === "failed" ? skin.panel.failedColor
                                : agentRow.note === "opening" ? skin.panel.openingColor : theme.dimColor
                            font {
                                family: skin.sans; pixelSize: theme.smallSize
                                weight: agentRow.note !== "" ? Font.Medium : Font.Normal
                            }
                        }
                        // The model that the agent runs and the age of its session, below the label.
                        MetaLine {
                            row: agentRow
                            tokens: theme
                            x: label.x
                            anchors.top: label.bottom
                            width: (answer.visible ? answer.x - answer.gap : parent.width - (agentList.longer ? 16 : 12)) - x
                        }
                    }

                    // Scroll hint: a thumb at the right. The header says which rows are on the screen.
                    overlay: Rectangle {
                        readonly property bool isScrollHint: true
                        readonly property real span: agentList.height - 8
                        visible: agentList.longer
                        x: agentList.width - 7; width: 3; radius: 1.5
                        height: span * agentList.shown / Math.max(1, agentList.count)
                        y: 4 + (span - height) * agentList.contentY
                            / Math.max(1, agentList.contentHeight - agentList.height)
                        color: theme.faintColor
                    }
                }
            }

            // The message of a failed jump when its agent has no row (the agent is gone, or Herdr is offline).
            Text {
                readonly property bool isFailedLine: true
                visible: skin.panel.failedAlone
                width: parent.width
                height: theme.fit(22)
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                text: skin.panel.failedMessage
                color: skin.panel.failedColor
                font { family: skin.sans; pixelSize: theme.smallSize; weight: Font.Medium }
            }
        }
    }
}
