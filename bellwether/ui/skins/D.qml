// Layout D, "Signal strip": a headline with the total and the top status, one bar with the share of each
// status, and the four statuses as a row of tabs; the agents of the open tab show below.
// The visual reference is design/layouts/d-signal-strip.qml. A skin is only drawing: the state and the rules
// are in PanelModel.qml, the pointer handling is in PanelShell.qml.
import QtQuick
import ".."

Item {
    id: skin

    required property PanelModel panel

    // The rows, the headline, the tabs and the footer grow with a larger font (theme.fit).
    readonly property int agentRowHeight: theme.fit(30)
    // What the model and session-time line adds to the height of an agent row.
    readonly property int metaLineHeight: theme.fit(14)
    readonly property int footerHeight: theme.fit(26)
    readonly property int pad: 12
    readonly property string sans: theme.fontFamily
    // The frame and the chip have the colour of the top status. Neutral with no agents and when Herdr is offline.
    readonly property color signalColor: panel.quiet ? theme.frameColor : panel.topColor

    implicitWidth: frame.width
    implicitHeight: frame.height

    DTheme { id: theme }

    Rectangle {
        id: frame
        width: 320
        height: column.height + 4
        radius: theme.radius
        color: theme.panelColor
        border.width: theme.frameWidth
        border.color: skin.signalColor

        Column {
            id: column
            y: 2
            width: parent.width

            // Headline: total at the left, top status as a chip at the right.
            Item {
                width: parent.width
                height: theme.fit(44)
                Text {
                    id: total
                    readonly property bool isTotal: true
                    x: skin.pad + 2
                    anchors.baseline: parent.top
                    anchors.baselineOffset: theme.fit(31)
                    text: skin.panel.online ? skin.panel.total : "Offline"
                    color: skin.panel.online ? theme.textColor : theme.dimColor
                    font {
                        family: skin.sans; weight: Font.DemiBold
                        pixelSize: skin.panel.online ? theme.headlineSize : theme.noticeSize
                        features: { "tnum": 1 }
                    }
                }
                Text {
                    anchors.left: total.right
                    anchors.leftMargin: 6
                    anchors.baseline: total.baseline
                    visible: skin.panel.online
                    text: skin.panel.total === 1 ? "agent" : "agents"
                    color: theme.dimColor
                    font { family: skin.sans; pixelSize: theme.unitSize }
                }
                Rectangle {
                    anchors.right: parent.right
                    anchors.rightMargin: skin.pad
                    visible: skin.panel.online
                    y: theme.fit(11)
                    width: chipText.implicitWidth + 30
                    height: theme.fit(24)
                    radius: height / 2
                    color: skin.panel.quiet ? "transparent" : skin.panel.tint(skin.panel.topColor, 0.16)
                    border.width: 1
                    border.color: skin.panel.quiet ? theme.lineColor : skin.panel.tint(skin.panel.topColor, 0.55)
                    Rectangle {
                        x: 9
                        anchors.verticalCenter: parent.verticalCenter
                        width: 8; height: 8; radius: 4
                        // Quiet: the colour of "no agents" (the chip does not show when Herdr is offline).
                        color: skin.panel.topColor
                    }
                    Text {
                        id: chipText
                        readonly property bool isTopBadge: true
                        x: 22
                        anchors.verticalCenter: parent.verticalCenter
                        text: skin.panel.topBadge
                        color: skin.panel.quiet ? theme.dimColor : skin.panel.topColor
                        font { family: skin.sans; pixelSize: theme.badgeSize; weight: Font.DemiBold; features: { "tnum": 1 } }
                    }
                }
            }

            // Share bar: one segment for each status that has agents. With no agents: one neutral track.
            Item {
                id: bar
                readonly property var segments: skin.panel.strip(width, 3, 8)
                x: skin.pad
                width: parent.width - skin.pad * 2
                height: 8
                Rectangle {
                    readonly property bool isEmptyTrack: true
                    visible: skin.panel.parts === 0
                    anchors.fill: parent
                    radius: 4
                    color: theme.trackColor
                }
                Repeater {
                    model: 4
                    Rectangle {
                        required property int index
                        readonly property var group: skin.panel.groups[index]
                        readonly property bool isSegment: true
                        readonly property string segmentFor: group.state
                        visible: group.count > 0
                        x: bar.segments[index].x
                        width: bar.segments[index].width
                        height: 8
                        radius: 4
                        color: group.color
                        opacity: skin.panel.openState === "" || skin.panel.openState === group.state ? 1 : 0.4
                    }
                }
            }

            // The four statuses as tabs.
            Row {
                id: tabs
                x: skin.pad - 4
                width: parent.width - (skin.pad - 4) * 2
                topPadding: 8
                bottomPadding: 8
                Repeater {
                    model: 4
                    Rectangle {
                        id: tab
                        required property int index
                        readonly property var group: skin.panel.groups[index]
                        readonly property string hitRole: "status"
                        readonly property string stateName: group.state
                        readonly property bool open: skin.panel.openState === group.state
                        readonly property bool empty: group.count === 0
                        readonly property bool hovered: skin.panel.hoverItem === tab
                        width: tabs.width / 4
                        height: theme.fit(50)
                        radius: theme.itemRadius
                        // The open tab has a plate in its colour. A lighter plate under the pointer.
                        color: open ? skin.panel.tint(group.color, hovered ? 0.20 : 0.14)
                            : hovered ? skin.panel.tint(group.color, 0.07) : "transparent"
                        Accessible.role: Accessible.Button
                        Accessible.name: skin.panel.spokenStatus(group)
                        Accessible.onPressAction: skin.panel.toggle(stateName)

                        Text {
                            id: number
                            readonly property string countFor: tab.stateName
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: 5
                            text: skin.panel.online ? tab.group.count : "–"
                            color: tab.empty ? theme.ghostColor : tab.group.color
                            font { family: skin.sans; pixelSize: theme.numeralSize; weight: Font.DemiBold; features: { "tnum": 1 } }
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: theme.fit(30)
                            text: tab.group.label
                            color: tab.empty ? theme.faintColor : tab.open ? theme.textColor : theme.mutedColor
                            font { family: skin.sans; pixelSize: theme.labelSize; weight: Font.Medium }
                        }
                        // An attention status with agents has a small lamp next to its number.
                        Rectangle {
                            readonly property bool isLamp: true
                            visible: tab.group.alert
                            anchors.left: number.right
                            anchors.leftMargin: 4
                            y: theme.fit(9)
                            width: 6; height: 6; radius: 3
                            color: tab.group.color
                        }
                    }
                }
            }

            Rectangle {
                visible: skin.panel.openState !== ""
                x: 2
                width: parent.width - 4
                height: 1
                color: theme.lineColor
            }

            Item {
                visible: skin.panel.openState !== ""
                width: parent.width
                height: agentList.height + (agentList.longer ? skin.footerHeight + 8 : 12)

                AgentList {
                    id: agentList
                    panel: skin.panel
                    rowHeight: skin.agentRowHeight
                    metaHeight: skin.metaLineHeight
                    y: 6
                    width: parent.width

                    delegate: AgentRow {
                        id: agentRow
                        view: agentList

                        Rectangle {
                            visible: agentRow.hovered
                            x: 6; y: 2
                            width: parent.width - 12
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
                            x: skin.pad + 2; width: 16; height: 16
                            anchors.verticalCenter: parent.verticalCenter
                            // As many pixels as the icon has on the screen at a large scale.
                            sourceSize: Qt.size(16 * skin.panel.pixelScale, 16 * skin.panel.pixelScale)
                            source: agentRow.modelData.icon
                        }
                        Text {
                            id: label
                            x: programIcon.visible ? skin.pad + 26 : skin.pad + 2
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
                            corner: 6
                            anchors.right: parent.right
                            anchors.rightMargin: skin.pad + 2
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.verticalCenterOffset: answer.drop
                        }
                        Text {
                            id: detail
                            anchors.right: parent.right
                            anchors.rightMargin: (skin.pad + 2) + answer.reserve
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.verticalCenterOffset: agentRow.lineShift
                            width: Math.min(implicitWidth, answer.detailRoom(190, 124))
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
                            width: (answer.visible ? answer.x - answer.gap : parent.width - (skin.pad + 2)) - x
                        }
                    }
                }
                // Scroll hint: a footer under the rows that says how many agents are below (or above, at the end).
                Rectangle {
                    visible: agentList.longer
                    anchors.bottom: parent.bottom
                    x: 2
                    width: parent.width - 4
                    height: skin.footerHeight
                    radius: 11
                    color: theme.insetColor
                    Text {
                        readonly property bool isScrollHint: true
                        readonly property int below: agentList.count - agentList.first - agentList.shown
                        anchors.centerIn: parent
                        text: below > 0 ? below + " more  ↓" : agentList.first + " above  ↑"
                        color: theme.dimColor
                        font { family: skin.sans; pixelSize: theme.detailSize; weight: Font.Medium; features: { "tnum": 1 } }
                    }
                }
            }

            // The message of a failed jump when its agent has no row (the agent is gone, or Herdr is offline).
            Text {
                readonly property bool isFailedLine: true
                visible: skin.panel.failedAlone
                width: parent.width
                height: theme.fit(28)
                leftPadding: skin.pad + 2
                rightPadding: skin.pad + 2
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                text: skin.panel.failedMessage
                color: skin.panel.failedColor
                font { family: skin.sans; pixelSize: theme.smallSize; weight: Font.Medium }
            }
        }
    }
}
