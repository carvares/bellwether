// Layout B, "Tiles". A 2×2 grid of status tiles with large numerals. The open status shows its agents in a
// card below the grid. A mock-up with made-up data: set `scene` to one of the names in MockData.js.
import QtQuick
import "MockData.js" as Mock

Item {
    id: root
    property string scene: "closed"
    readonly property var d: Mock.scene(scene)
    readonly property var icons: typeof iconUrls === "undefined" ? ({}) : iconUrls
    readonly property string sans: "Adwaita Sans"
    readonly property int agentRow: 30
    readonly property int pad: 10
    readonly property int gap: 8

    width: 304
    height: panel.height

    Rectangle {
        id: panel
        width: parent.width
        height: column.height + root.pad * 2
        radius: 16
        color: "#f21b1c1f"
        border.width: 2
        border.color: root.d.topColor === Mock.NEUTRAL ? "#3c4043" : root.d.topColor

        Column {
            id: column
            x: root.pad
            y: root.pad
            width: parent.width - root.pad * 2
            spacing: root.gap

            Grid {
                columns: 2
                spacing: root.gap
                width: parent.width

                Repeater {
                    model: root.d.groups

                    Rectangle {
                        id: tile
                        required property var modelData
                        readonly property bool empty: modelData.count === 0 || !root.d.online
                        // A status that needs attention is a solid tile. The others are tinted.
                        readonly property bool solid: modelData.attention && root.d.online
                        width: (column.width - root.gap) / 2
                        height: 74
                        radius: 10
                        color: solid ? modelData.color : empty ? "transparent" : Mock.alpha(modelData.color, 0.13)
                        border.width: modelData.open ? 2 : empty ? 1 : 0
                        border.color: modelData.open ? modelData.color : "#3c4043"

                        Text {
                            x: 12
                            y: 9
                            text: tile.modelData.label
                            color: tile.solid ? "#202124" : tile.empty ? "#80868b" : "#e8eaed"
                            font { family: root.sans; pixelSize: 13; weight: tile.solid ? Font.DemiBold : Font.Medium }
                        }
                        Text {
                            x: 11
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 3
                            text: root.d.online ? tile.modelData.count : "–"
                            color: tile.solid ? "#202124" : tile.empty ? "#5f6368" : tile.modelData.color
                            font { family: root.sans; pixelSize: 34; weight: Font.DemiBold; features: { "tnum": 1 } }
                        }
                        // The mark of the open tile: a chevron that points to the list.
                        Text {
                            visible: tile.modelData.open
                            anchors.right: parent.right
                            anchors.rightMargin: 12
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 10
                            text: "▾"
                            color: tile.modelData.color
                            font { family: root.sans; pixelSize: 14 }
                        }
                    }
                }
            }

            // Offline line under the grid.
            Text {
                visible: !root.d.online
                width: parent.width
                height: 22
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                text: "Herdr is offline"
                color: "#9aa0a6"
                font { family: root.sans; pixelSize: 13; weight: Font.Medium }
            }

            Rectangle {
                id: card
                visible: root.d.open !== ""
                width: parent.width
                height: 30 + root.d.shown * root.agentRow + 6
                radius: 10
                color: "#101114"
                border.width: 1
                border.color: Mock.alpha(root.d.openColor, 0.45)

                Rectangle {
                    x: 12; y: 12; width: 8; height: 8; radius: 4
                    color: root.d.openColor
                }
                Text {
                    x: 28
                    y: 15 - height / 2 + 1
                    text: root.d.openLabel
                    color: "#e8eaed"
                    font { family: root.sans; pixelSize: 12; weight: Font.DemiBold }
                }
                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 12
                    y: 15 - height / 2 + 1
                    text: root.d.scrolls ? "1–" + root.d.shown + " of " + root.d.agents.length
                        : root.d.agents.length + " agents"
                    color: "#9aa0a6"
                    font { family: root.sans; pixelSize: 11; features: { "tnum": 1 } }
                }

                Item {
                    id: list
                    y: 30
                    width: parent.width
                    height: root.d.shown * root.agentRow
                    clip: true

                    Column {
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

                                Rectangle {
                                    visible: row.index > 0
                                    x: 12; width: parent.width - 24; height: 1
                                    color: "#26282c"
                                }
                                Image {
                                    x: 12; width: 16; height: 16
                                    anchors.verticalCenter: parent.verticalCenter
                                    sourceSize: Qt.size(16, 16)
                                    source: root.icons[row.modelData.program] || ""
                                }
                                Text {
                                    id: label
                                    x: 36
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
                                    anchors.rightMargin: root.d.scrolls ? 16 : 12
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: Math.min(implicitWidth, row.failed ? 180 : 116)
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
                        x: parent.width - 7; y: 4; width: 3; radius: 1.5
                        height: (parent.height - 8) * root.d.shown / Math.max(1, root.d.agents.length)
                        color: "#80868b"
                    }
                }
            }
        }
    }
}
