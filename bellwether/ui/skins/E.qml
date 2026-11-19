// Layout E, "Ring": a ring with the share of each status and the total in its centre, and a legend of the four
// counts at its right; the agents of the open status show below. The visual reference is
// design/layouts/e-ring.qml. A skin is only drawing: the state and the rules are in PanelModel.qml, the
// pointer handling is in Main.qml.
import QtQuick
import ".."

Item {
    id: skin

    required property PanelModel panel

    // The rows grow with a larger font (theme.fit). The ring grows half as much: its numeral must stay inside it,
    // and the legend at its right keeps its room.
    readonly property int agentRowHeight: theme.fit(30)
    readonly property int legendRowHeight: theme.fit(25)
    readonly property int ringSize: (100 + theme.fit(100)) / 2
    // The total gets smaller above 99 and above 999: three digits and more must stay inside the ring.
    readonly property int totalSize: !panel.online ? theme.noticeSize : panel.total > 999 ? theme.headlineSmallSize
        : panel.total > 99 ? theme.headlineMidSize : theme.headlineSize
    readonly property string sans: theme.fontFamily
    // The frame has the colour of the top status. Neutral with no agents and when Herdr is offline.
    readonly property color signalColor: panel.quiet ? theme.frameColor : panel.topColor

    implicitWidth: frame.width
    implicitHeight: frame.height

    ETheme { id: theme }

    Rectangle {
        id: frame
        width: 312
        height: column.height + 4
        radius: theme.radius
        color: theme.panelColor
        border.width: theme.frameWidth
        border.color: skin.signalColor

        Column {
            id: column
            y: 2
            width: parent.width

            Item {
                id: top
                width: parent.width
                height: Math.max(skin.ringSize, legend.height) + 24

                // The ring: one arc for each status that has agents. The handlers here only draw.
                // The canvas has the pixels of the ring on the screen (panel.pixelScale) and is drawn that many
                // times smaller, so the ring stays sharp when the window draws the skin larger.
                Item {
                    id: ring
                    x: 14
                    y: (top.height - height) / 2
                    width: skin.ringSize
                    height: skin.ringSize

                    Canvas {
                        id: ringCanvas
                        readonly property bool isRing: true
                        readonly property var groups: skin.panel.groups
                        // The arcs from the controller: a gap between two arcs, and no arc too short to see.
                        readonly property var arcs: skin.panel.ring(0.07, 0.10)
                        readonly property string openState: skin.panel.openState
                        readonly property bool online: skin.panel.online
                        readonly property real pixels: skin.panel.pixelScale
                        width: ring.width * pixels
                        height: ring.height * pixels
                        scale: 1 / pixels
                        transformOrigin: Item.TopLeft
                        onArcsChanged: requestPaint()
                        onOpenStateChanged: requestPaint()
                        onOnlineChanged: requestPaint()
                        onPixelsChanged: requestPaint()
                        onWidthChanged: requestPaint()
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.reset()
                            ctx.scale(pixels, pixels)
                            // The design has a ring of 100 px: a radius of 40 and a line of 9 (14 for the open status).
                            var unit = ring.width / 100
                            var cx = ring.width / 2, cy = ring.height / 2, r = 40 * unit
                            ctx.lineCap = "butt"
                            if (!online || skin.panel.parts === 0) {
                                // No agents: a full grey ring. Offline: a ring of dashes.
                                ctx.strokeStyle = theme.lineColor
                                ctx.lineWidth = 9 * unit
                                var dashes = online ? 1 : 24
                                for (var k = 0; k < dashes; k++) {
                                    var a0 = k / dashes * 2 * Math.PI
                                    var a1 = a0 + (online ? 2 * Math.PI : Math.PI / dashes)
                                    ctx.beginPath()
                                    ctx.arc(cx, cy, r, a0, a1)
                                    ctx.stroke()
                                }
                                return
                            }
                            for (var i = 0; i < groups.length; i++) {
                                if (groups[i].count === 0)
                                    continue
                                var open = openState === groups[i].state
                                // The open status is thicker. The others go dim while a status is open.
                                ctx.lineWidth = (open ? 14 : 9) * unit
                                ctx.globalAlpha = openState === "" || open ? 1 : 0.45
                                ctx.strokeStyle = groups[i].color
                                ctx.beginPath()
                                ctx.arc(cx, cy, r, -Math.PI / 2 + arcs[i].start, -Math.PI / 2 + arcs[i].start + arcs[i].sweep)
                                ctx.stroke()
                            }
                        }
                    }
                }
                Text {
                    id: centre
                    readonly property bool isTotal: true
                    anchors.horizontalCenter: ring.horizontalCenter
                    anchors.verticalCenter: ring.verticalCenter
                    anchors.verticalCenterOffset: skin.panel.online ? -6 : 0
                    text: skin.panel.online ? skin.panel.total : "off"
                    color: skin.panel.online && skin.panel.total > 0 ? theme.textColor : theme.faintColor
                    font {
                        family: skin.sans; weight: Font.DemiBold; features: { "tnum": 1 }
                        pixelSize: skin.totalSize
                    }
                }
                Text {
                    visible: skin.panel.online
                    anchors.horizontalCenter: ring.horizontalCenter
                    anchors.top: centre.bottom
                    anchors.topMargin: -4
                    text: skin.panel.total === 1 ? "agent" : "agents"
                    color: theme.dimColor
                    font { family: skin.sans; pixelSize: theme.unitSize; weight: Font.Medium }
                }

                // Legend: the four statuses with their counts.
                Column {
                    id: legend
                    x: ring.x + ring.width + 14
                    width: parent.width - x - 10
                    anchors.verticalCenter: ring.verticalCenter

                    Repeater {
                        model: 4
                        Rectangle {
                            id: item
                            required property int index
                            readonly property var group: skin.panel.groups[index]
                            readonly property string hitRole: "status"
                            readonly property string stateName: group.state
                            readonly property bool open: skin.panel.openState === group.state
                            readonly property bool empty: group.count === 0
                            readonly property bool hovered: skin.panel.hoverItem === item
                            width: legend.width
                            height: skin.legendRowHeight
                            radius: theme.itemRadius
                            // The open row has a plate in its colour. A lighter plate under the pointer.
                            color: open ? skin.panel.tint(group.color, hovered ? 0.20 : 0.14)
                                : hovered ? skin.panel.tint(group.color, 0.07) : "transparent"
                            Accessible.role: Accessible.Button
                            Accessible.name: skin.panel.spokenStatus(group)
                            Accessible.onPressAction: skin.panel.toggle(stateName)

                            Rectangle {
                                x: 8
                                anchors.verticalCenter: parent.verticalCenter
                                width: 9; height: 9; radius: 4.5
                                color: item.empty ? "transparent" : item.group.color
                                border.width: item.empty ? 1 : 0
                                border.color: "#5f6368"
                            }
                            Text {
                                x: 25
                                // A large count with a large font: the name gives the room.
                                width: Math.min(implicitWidth, countText.x - 6 - x)
                                elide: Text.ElideRight
                                anchors.verticalCenter: parent.verticalCenter
                                text: item.group.label
                                color: item.empty ? theme.faintColor : theme.textColor
                                font { family: skin.sans; pixelSize: theme.titleSize; weight: Font.Medium }
                            }
                            Text {
                                id: countText
                                readonly property string countFor: item.stateName
                                anchors.right: parent.right
                                anchors.rightMargin: 10
                                anchors.verticalCenter: parent.verticalCenter
                                text: skin.panel.online ? item.group.count : "–"
                                color: item.empty ? theme.faintColor : item.group.alert ? item.group.color : theme.textColor
                                font {
                                    family: skin.sans; pixelSize: theme.numeralSize; features: { "tnum": 1 }
                                    weight: item.group.alert ? Font.Bold : Font.DemiBold
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                visible: skin.panel.openState !== ""
                x: 14
                width: parent.width - 28
                height: 1
                color: theme.lineColor
            }

            Item {
                visible: skin.panel.openState !== ""
                width: parent.width
                height: agentList.height + 14

                AgentList {
                    id: agentList
                    panel: skin.panel
                    rowHeight: skin.agentRowHeight
                    y: 6
                    width: parent.width

                    delegate: AgentRow {
                        id: agentRow
                        view: agentList

                        Rectangle {
                            visible: agentRow.hovered
                            x: 10; y: 2
                            width: parent.width - 22
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
                            x: 18; width: 16; height: 16
                            anchors.verticalCenter: parent.verticalCenter
                            // As many pixels as the icon has on the screen at a large scale.
                            sourceSize: Qt.size(16 * skin.panel.pixelScale, 16 * skin.panel.pixelScale)
                            source: agentRow.modelData.icon
                        }
                        Text {
                            id: label
                            x: programIcon.visible ? 44 : 18
                            width: Math.min(implicitWidth, detail.x - 10 - x - (address.visible ? address.width + 6 : 0))
                            anchors.verticalCenter: parent.verticalCenter
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
                        Text {
                            id: detail
                            anchors.right: parent.right
                            anchors.rightMargin: 20
                            anchors.verticalCenter: parent.verticalCenter
                            width: Math.min(implicitWidth, agentRow.failed ? 180 : 120)
                            elide: Text.ElideRight
                            text: agentRow.noteText
                            color: agentRow.note === "failed" ? skin.panel.failedColor
                                : agentRow.note === "opening" ? skin.panel.openingColor : theme.dimColor
                            font {
                                family: skin.sans; pixelSize: theme.smallSize
                                weight: agentRow.note !== "" ? Font.Medium : Font.Normal
                            }
                        }
                    }

                    // Scroll hint: a thumb at the right, and a fade over the last row while more rows are below.
                    overlay: Item {
                        visible: agentList.longer

                        Rectangle {
                            readonly property bool isScrollHint: true
                            visible: !agentList.atEnd
                            x: 2
                            y: agentList.height + 8 - height
                            width: agentList.width - 4; height: 30
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
                            x: agentList.width - 9; width: 3; radius: 1.5
                            height: span * agentList.shown / Math.max(1, agentList.count)
                            y: 2 + (span - height) * agentList.contentY
                                / Math.max(1, agentList.contentHeight - agentList.height)
                            color: theme.faintColor
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
                leftPadding: 18
                rightPadding: 18
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                text: skin.panel.failedMessage
                color: skin.panel.failedColor
                font { family: skin.sans; pixelSize: theme.smallSize; weight: Font.Medium }
            }
        }
    }
}
