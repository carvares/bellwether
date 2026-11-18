// Layout E, "Ring". A ring with the share of each status and the total in the centre, with a legend of the
// four counts at its right. The open status shows its agents below.
// A mock-up with made-up data: set `scene` to one of the names in MockData.js.
import QtQuick
import "MockData.js" as Mock

Item {
    id: root
    property string scene: "closed"
    readonly property var d: Mock.scene(scene)
    readonly property var icons: typeof iconUrls === "undefined" ? ({}) : iconUrls
    readonly property string sans: "Adwaita Sans"
    readonly property int agentRow: 30
    readonly property int legendRow: 25

    width: 312
    height: panel.height

    Rectangle {
        id: panel
        width: parent.width
        height: column.height + 4
        radius: 16
        color: "#f21f2023"
        border.width: 2
        border.color: root.d.topColor === Mock.NEUTRAL ? "#3c4043" : root.d.topColor

        Column {
            id: column
            y: 2
            width: parent.width

            Item {
                width: parent.width
                height: 124

                Canvas {
                    id: ring
                    x: 14
                    y: 12
                    width: 100
                    height: 100
                    onPaint: {
                        var ctx = getContext("2d")
                        ctx.reset()
                        var cx = width / 2, cy = height / 2, r = 40
                        var groups = root.d.groups
                        var total = root.d.total
                        ctx.lineCap = "butt"
                        if (!root.d.online || total === 0) {
                            // No agents: a full grey ring. Offline: a ring of dashes.
                            ctx.strokeStyle = "#3c4043"
                            ctx.lineWidth = 9
                            var dashes = root.d.online ? 1 : 24
                            for (var k = 0; k < dashes; k++) {
                                var a0 = k / dashes * 2 * Math.PI
                                var a1 = a0 + (root.d.online ? 2 * Math.PI : Math.PI / dashes)
                                ctx.beginPath()
                                ctx.arc(cx, cy, r, a0, a1)
                                ctx.stroke()
                            }
                            return
                        }
                        var parts = 0
                        for (var i = 0; i < groups.length; i++)
                            if (groups[i].count > 0) parts++
                        var gap = parts > 1 ? 0.07 : 0
                        var start = -Math.PI / 2 + gap / 2
                        for (i = 0; i < groups.length; i++) {
                            if (groups[i].count === 0) continue
                            var sweep = groups[i].count / total * 2 * Math.PI
                            // The open status is thicker. The others go dim while a status is open.
                            ctx.lineWidth = groups[i].open ? 14 : 9
                            ctx.globalAlpha = root.d.open === "" || groups[i].open ? 1 : 0.45
                            ctx.strokeStyle = groups[i].color
                            ctx.beginPath()
                            ctx.arc(cx, cy, r, start, start + sweep - gap)
                            ctx.stroke()
                            start += sweep
                        }
                    }
                }
                Text {
                    id: centre
                    anchors.horizontalCenter: ring.horizontalCenter
                    anchors.verticalCenter: ring.verticalCenter
                    anchors.verticalCenterOffset: root.d.online ? -6 : 0
                    text: root.d.online ? root.d.total : "off"
                    color: root.d.online && root.d.total > 0 ? "#e8eaed" : "#80868b"
                    font { family: root.sans; pixelSize: root.d.online ? 26 : 15; weight: Font.DemiBold; features: { "tnum": 1 } }
                }
                Text {
                    visible: root.d.online
                    anchors.horizontalCenter: ring.horizontalCenter
                    anchors.top: centre.bottom
                    anchors.topMargin: -4
                    text: root.d.total === 1 ? "agent" : "agents"
                    color: "#9aa0a6"
                    font { family: root.sans; pixelSize: 10; weight: Font.Medium }
                }

                // Legend: the four statuses with their counts.
                Column {
                    id: legend
                    x: 128
                    width: parent.width - x - 10
                    anchors.verticalCenter: ring.verticalCenter

                    Repeater {
                        model: root.d.groups
                        Rectangle {
                            id: item
                            required property var modelData
                            readonly property bool empty: modelData.count === 0 || !root.d.online
                            width: legend.width
                            height: root.legendRow
                            radius: 7
                            color: modelData.open ? Mock.alpha(modelData.color, 0.14) : "transparent"

                            Rectangle {
                                x: 8
                                anchors.verticalCenter: parent.verticalCenter
                                width: 9; height: 9; radius: 4.5
                                color: item.empty ? "transparent" : item.modelData.color
                                border.width: item.empty ? 1 : 0
                                border.color: "#5f6368"
                            }
                            Text {
                                x: 25
                                anchors.verticalCenter: parent.verticalCenter
                                text: item.modelData.label
                                color: item.empty ? "#80868b" : "#e8eaed"
                                font { family: root.sans; pixelSize: 13; weight: Font.Medium }
                            }
                            Text {
                                anchors.right: parent.right
                                anchors.rightMargin: 10
                                anchors.verticalCenter: parent.verticalCenter
                                text: root.d.online ? item.modelData.count : "–"
                                color: item.empty ? "#80868b" : item.modelData.attention ? item.modelData.color : "#e8eaed"
                                font { family: root.sans; pixelSize: 15; weight: item.modelData.attention ? Font.Bold : Font.DemiBold; features: { "tnum": 1 } }
                            }
                        }
                    }
                }
            }

            Rectangle {
                visible: root.d.open !== ""
                x: 14
                width: parent.width - 28
                height: 1
                color: "#3c4043"
            }

            Item {
                id: list
                visible: root.d.open !== ""
                width: parent.width
                height: root.d.shown * root.agentRow + 14
                clip: true

                Column {
                    y: 6
                    width: parent.width
                    Repeater {
                        model: root.d.agents
                        Item {
                            id: row
                            required property var modelData
                            required property int index
                            readonly property bool failed: root.d.failed === index
                            readonly property bool opening: root.d.opening === index
                            width: list.width
                            height: root.agentRow

                            Image {
                                x: 18; width: 16; height: 16
                                anchors.verticalCenter: parent.verticalCenter
                                sourceSize: Qt.size(16, 16)
                                source: root.icons[row.modelData.program] || ""
                            }
                            Text {
                                id: label
                                x: 44
                                width: Math.min(implicitWidth, detail.x - 10 - x - (address.visible ? address.width + 6 : 0))
                                anchors.verticalCenter: parent.verticalCenter
                                text: row.modelData.label
                                color: "#e8eaed"
                                elide: Text.ElideRight
                                font { family: root.sans; pixelSize: 13 }
                            }
                            Text {
                                id: address
                                visible: text !== ""
                                anchors.left: label.right
                                anchors.leftMargin: 6
                                anchors.baseline: label.baseline
                                text: row.modelData.address
                                color: "#80868b"
                                font { family: root.sans; pixelSize: 12; features: { "tnum": 1 } }
                            }
                            Text {
                                id: detail
                                anchors.right: parent.right
                                anchors.rightMargin: 20
                                anchors.verticalCenter: parent.verticalCenter
                                width: Math.min(implicitWidth, row.failed ? 180 : 120)
                                elide: Text.ElideRight
                                text: row.failed ? root.d.message : row.opening ? "opening…" : row.modelData.detail
                                color: row.failed ? "#f28b82" : row.opening ? "#8ab4f8" : "#9aa0a6"
                                font { family: root.sans; pixelSize: 12; weight: row.failed || row.opening ? Font.Medium : Font.Normal }
                            }
                        }
                    }
                }
                Rectangle {
                    visible: root.d.scrolls
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 0
                    x: 2
                    width: parent.width - 4
                    height: 30
                    gradient: Gradient {
                        GradientStop { position: 0; color: "#001f2023" }
                        GradientStop { position: 1; color: "#f21f2023" }
                    }
                }
                Rectangle {
                    visible: root.d.scrolls
                    x: parent.width - 9; y: 8; width: 3; radius: 1.5
                    height: (root.d.shown * root.agentRow - 4) * root.d.shown / Math.max(1, root.d.agents.length)
                    color: "#80868b"
                }
            }
        }
    }
}
