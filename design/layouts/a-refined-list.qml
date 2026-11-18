// Layout A, "Refined list". The structure of today, with a clear type scale, an accent bar and count badges.
// A mock-up with made-up data: set `scene` to one of the names in MockData.js.
import QtQuick
import "MockData.js" as Mock

Item {
    id: root
    property string scene: "closed"
    readonly property var d: Mock.scene(scene)
    readonly property var icons: typeof iconUrls === "undefined" ? ({}) : iconUrls
    readonly property string sans: "Adwaita Sans"
    readonly property int statusRow: 38
    readonly property int agentRow: 30

    width: 296
    height: panel.height

    Rectangle {
        id: panel
        width: parent.width
        height: column.height + 16
        radius: 14
        color: "#f21f2023"
        border.width: 2
        border.color: root.d.topColor === Mock.NEUTRAL ? "#3c4043" : root.d.topColor

        Column {
            id: column
            x: 8
            y: 8
            width: parent.width - 16

            // Offline: one quiet row.
            Item {
                visible: !root.d.online
                width: parent.width
                height: root.statusRow
                Rectangle {
                    x: 10; width: 4; height: 18; radius: 2
                    anchors.verticalCenter: parent.verticalCenter
                    color: "transparent"; border.width: 1; border.color: "#5f6368"
                }
                Text {
                    x: 26
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Herdr is offline"
                    color: "#9aa0a6"
                    font { family: root.sans; pixelSize: 15; weight: Font.Medium }
                }
            }

            Repeater {
                model: root.d.online ? root.d.groups : []

                Column {
                    id: group
                    required property var modelData
                    readonly property bool empty: modelData.count === 0
                    width: column.width

                    Rectangle {
                        width: parent.width
                        height: root.statusRow
                        radius: 9
                        color: group.modelData.open ? Mock.alpha(group.modelData.color, 0.14) : "transparent"

                        // Accent bar: filled when the status has agents, an outline when it has none.
                        Rectangle {
                            x: 10; width: 4; height: 18; radius: 2
                            anchors.verticalCenter: parent.verticalCenter
                            color: group.empty ? "transparent" : group.modelData.color
                            border.width: group.empty ? 1 : 0
                            border.color: "#5f6368"
                        }
                        Text {
                            x: 26
                            anchors.verticalCenter: parent.verticalCenter
                            text: group.modelData.label
                            color: group.empty ? "#80868b" : "#e8eaed"
                            font { family: root.sans; pixelSize: 15; weight: Font.Medium }
                        }
                        // Count. An attention status (blocked, done) with agents gets a filled badge.
                        Rectangle {
                            id: badge
                            anchors.right: parent.right
                            anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            width: Math.max(26, countText.implicitWidth + 14)
                            height: 22
                            radius: 11
                            color: group.modelData.attention ? group.modelData.color : "transparent"
                            Text {
                                id: countText
                                anchors.centerIn: parent
                                text: group.modelData.count
                                color: group.modelData.attention ? "#202124" : group.empty ? "#80868b" : "#e8eaed"
                                font { family: root.sans; pixelSize: 15; weight: Font.DemiBold; features: { "tnum": 1 } }
                            }
                        }
                    }

                    Item {
                        id: list
                        visible: group.modelData.open
                        width: parent.width
                        height: root.d.shown * root.agentRow + 6
                        clip: true

                        // Guide line that ties the agents to their status.
                        Rectangle {
                            x: 11; y: 4; width: 2; radius: 1
                            height: parent.height - 8
                            color: Mock.alpha(group.modelData.color, 0.35)
                        }
                        Column {
                            y: 3
                            width: parent.width
                            Repeater {
                                model: group.modelData.open ? root.d.agents : []
                                Item {
                                    id: row
                                    required property var modelData
                                    required property int index
                                    readonly property bool failed: root.d.failed === index
                                    readonly property bool opening: root.d.opening === index
                                    width: list.width
                                    height: root.agentRow

                                    Image {
                                        id: icon
                                        x: 26; width: 16; height: 16
                                        anchors.verticalCenter: parent.verticalCenter
                                        sourceSize: Qt.size(16, 16)
                                        source: root.icons[row.modelData.program] || ""
                                    }
                                    Text {
                                        id: label
                                        x: 50
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
                                        anchors.rightMargin: root.d.scrolls ? 14 : 10
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
                        // Scroll hint: a thumb at the right and a fade over the last row.
                        Rectangle {
                            visible: root.d.scrolls
                            anchors.bottom: parent.bottom
                            width: parent.width; height: 26
                            gradient: Gradient {
                                GradientStop { position: 0; color: "#001f2023" }
                                GradientStop { position: 1; color: "#f21f2023" }
                            }
                        }
                        Rectangle {
                            visible: root.d.scrolls
                            x: parent.width - 5; y: 5; width: 3; radius: 1.5
                            height: (parent.height - 10) * root.d.shown / Math.max(1, root.d.agents.length)
                            color: "#80868b"
                        }
                    }
                }
            }
        }
    }
}
