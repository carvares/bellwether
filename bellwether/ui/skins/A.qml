// Layout A, "Refined list": a list of the four statuses with an accent bar and a count badge; the agents of the
// open status show under its row. The visual reference is design/layouts/a-refined-list.qml. A skin is only
// drawing: the state and the rules are in PanelModel.qml, the pointer handling is in PanelShell.qml.
import QtQuick
import ".."

Item {
    id: skin

    required property PanelModel panel

    // The rows grow with a larger font (theme.fit).
    readonly property int statusRowHeight: theme.fit(38)
    readonly property int agentRowHeight: theme.fit(30)
    // What the model and session-time line adds to the height of an agent row.
    readonly property int metaLineHeight: theme.fit(14)
    readonly property string sans: theme.fontFamily
    // The frame has the colour of the top status. Neutral with no agents and when Herdr is offline.
    readonly property color signalColor: panel.quiet ? theme.frameColor : panel.topColor

    implicitWidth: frame.width
    implicitHeight: frame.height

    ATheme { id: theme }

    Rectangle {
        id: frame
        width: 296
        height: column.height + 16
        radius: theme.radius
        color: theme.panelColor
        border.width: theme.frameWidth
        border.color: skin.signalColor

        Column {
            id: column
            x: 8
            y: 8
            width: parent.width - 16

            // Offline: one quiet row.
            Item {
                visible: !skin.panel.online
                width: parent.width
                height: skin.statusRowHeight
                Rectangle {
                    x: 10; width: 4; height: 18; radius: 2
                    anchors.verticalCenter: parent.verticalCenter
                    color: "transparent"; border.width: 1; border.color: theme.ghostColor
                }
                Text {
                    readonly property bool isOfflineLine: true
                    x: 26
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Herdr is offline"
                    color: theme.dimColor
                    font { family: skin.sans; pixelSize: theme.titleSize; weight: Font.Medium }
                }
            }

            Repeater {
                // The four groups stay the same items when the agents change.
                model: skin.panel.online ? 4 : 0

                Column {
                    id: groupItem
                    required property int index
                    readonly property var group: skin.panel.groups[index]
                    readonly property bool open: skin.panel.openState === group.state
                    readonly property bool empty: group.count === 0
                    width: column.width

                    Rectangle {
                        id: statusRow
                        readonly property string hitRole: "status"
                        readonly property string stateName: groupItem.group.state
                        readonly property bool hovered: skin.panel.hoverItem === statusRow
                        width: parent.width
                        height: skin.statusRowHeight
                        radius: theme.itemRadius
                        // The open row has a plate in its colour. A lighter plate under the pointer.
                        color: groupItem.open ? skin.panel.faded(groupItem.group.color, hovered ? 0.20 : 0.14)
                            : hovered ? skin.panel.faded(groupItem.group.color, 0.07) : "transparent"
                        Accessible.role: Accessible.Button
                        Accessible.name: skin.panel.spokenStatus(groupItem.group)
                        Accessible.onPressAction: skin.panel.toggle(stateName)

                        // Accent bar: filled when the status has agents, an outline when it has none.
                        Rectangle {
                            x: 10; width: 4; height: 18; radius: 2
                            anchors.verticalCenter: parent.verticalCenter
                            color: groupItem.empty ? "transparent" : groupItem.group.color
                            border.width: groupItem.empty ? 1 : 0
                            border.color: theme.ghostColor
                        }
                        Text {
                            x: 26
                            anchors.verticalCenter: parent.verticalCenter
                            text: groupItem.group.label
                            color: groupItem.empty ? theme.faintColor : theme.textColor
                            font { family: skin.sans; pixelSize: theme.titleSize; weight: Font.Medium }
                        }
                        // Count. An attention status (blocked, done) with agents gets a filled badge.
                        Rectangle {
                            readonly property bool isBadge: true
                            readonly property string badgeFor: statusRow.stateName
                            readonly property bool filled: groupItem.group.alert
                            anchors.right: parent.right
                            anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            width: Math.max(height + 4, countText.implicitWidth + 14)
                            height: theme.fit(22)
                            radius: height / 2
                            color: filled ? groupItem.group.color : "transparent"
                            Text {
                                id: countText
                                readonly property string countFor: statusRow.stateName
                                anchors.centerIn: parent
                                text: groupItem.group.count
                                color: groupItem.group.alert ? theme.inkOn(groupItem.group.color) : groupItem.empty ? theme.faintColor : theme.textColor
                                font { family: skin.sans; pixelSize: theme.numeralSize; weight: Font.DemiBold; features: { "tnum": 1 } }
                            }
                        }
                    }

                    Item {
                        visible: groupItem.open
                        width: parent.width
                        height: agentList.height + 6

                        // Guide line that ties the agents to their status.
                        Rectangle {
                            x: 11; y: 4; width: 2; radius: 1
                            height: parent.height - 8
                            color: skin.panel.faded(groupItem.group.color, 0.35)
                        }

                        AgentList {
                            id: agentList
                            panel: skin.panel
                            stateName: groupItem.group.state
                            rowHeight: skin.agentRowHeight
                            metaHeight: skin.metaLineHeight
                            y: 3
                            width: parent.width

                            delegate: AgentRow {
                                id: agentRow
                                view: agentList

                                Rectangle {
                                    visible: agentRow.hovered
                                    x: 20; y: 2
                                    width: parent.width - 20 - (agentList.longer ? 8 : 2)
                                    height: parent.height - 4
                                    radius: 7
                                    color: theme.hoverColor
                                }
                                // The icon that the Herdr app shows for the program of the agent.
                                Image {
                                    id: programIcon
                                    readonly property bool isProgramIcon: true
                                    // An icon that does not load is not shown: the row has no gap.
                                    visible: agentRow.modelData.icon !== "" && status !== Image.Error
                                    x: 26; width: 16; height: 16
                                    anchors.verticalCenter: parent.verticalCenter
                                    // As many pixels as the icon has on the screen at a large scale.
                                    sourceSize: Qt.size(16 * skin.panel.pixelScale, 16 * skin.panel.pixelScale)
                                    source: agentRow.modelData.icon
                                }
                                Text {
                                    id: label
                                    x: programIcon.visible ? 50 : 26
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
                                    corner: -1
                                    anchors.right: parent.right
                                    anchors.rightMargin: agentList.longer ? 14 : 10
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.verticalCenterOffset: answer.drop
                                }
                                Text {
                                    id: detail
                                    anchors.right: parent.right
                                    anchors.rightMargin: (agentList.longer ? 14 : 10) + answer.reserve
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
                                    width: (answer.visible ? answer.x - answer.gap : parent.width - (agentList.longer ? 14 : 10)) - x
                                }
                            }

                            // Scroll hint: a thumb at the right, and a fade over the last row while more rows are below.
                            overlay: Item {
                                visible: agentList.longer

                                Rectangle {
                                    readonly property bool isScrollHint: true
                                    visible: !agentList.atEnd
                                    y: agentList.height + 3 - height
                                    width: agentList.width; height: 26
                                    // From clear to the colour of the panel.
                                    gradient: Gradient {
                                        GradientStop { position: 0; color: skin.panel.faded(theme.panelColor, 0) }
                                        GradientStop { position: 1; color: theme.panelColor }
                                    }
                                }
                                Rectangle {
                                    readonly property bool isScrollHint: true
                                    readonly property bool isScrollThumb: true
                                    readonly property real span: agentList.height - 4
                                    x: agentList.width - 5; width: 3; radius: 1.5
                                    height: span * agentList.shown / Math.max(1, agentList.count)
                                    y: 2 + (span - height) * agentList.contentY
                                        / Math.max(1, agentList.contentHeight - agentList.height)
                                    color: theme.faintColor
                                }
                            }
                        }
                    }
                }
            }

            // The message of a failed jump when its agent has no row (the agent is gone, or Herdr is offline).
            Text {
                readonly property bool isFailedLine: true
                visible: skin.panel.failedAlone
                width: parent.width
                height: theme.fit(28)
                leftPadding: 26
                rightPadding: 10
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                text: skin.panel.failedMessage
                color: skin.panel.failedColor
                font { family: skin.sans; pixelSize: theme.smallSize; weight: Font.Medium }
            }
        }
    }
}
