// Layout D, "Signal strip". A headline with the total and the top status, one bar with the share of each
// status, and the four statuses as a row of tabs. The open tab shows its agents below.
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
    readonly property int pad: 12
    readonly property bool quiet: d.topColor === Mock.NEUTRAL

    width: 320
    height: panel.height

    Rectangle {
        id: panel
        width: parent.width
        height: column.height + 4
        radius: 14
        color: "#f21f2023"
        // Top-status signal: the border. The chip in the headline repeats it in words.
        border.width: 2
        border.color: root.quiet ? "#3c4043" : root.d.topColor

        Column {
            id: column
            y: 2
            width: parent.width

            // Headline: total at the left, top status as a chip at the right.
            Item {
                width: parent.width
                height: 44
                Text {
                    id: total
                    x: root.pad + 2
                    anchors.baseline: parent.top
                    anchors.baselineOffset: 31
                    text: root.d.online ? root.d.total : "Offline"
                    color: root.d.online ? "#e8eaed" : "#9aa0a6"
                    font { family: root.sans; pixelSize: root.d.online ? 24 : 17; weight: Font.DemiBold; features: { "tnum": 1 } }
                }
                Text {
                    anchors.left: total.right
                    anchors.leftMargin: 6
                    anchors.baseline: total.baseline
                    visible: root.d.online
                    text: root.d.total === 1 ? "agent" : "agents"
                    color: "#9aa0a6"
                    font { family: root.sans; pixelSize: 13 }
                }
                Rectangle {
                    anchors.right: parent.right
                    anchors.rightMargin: root.pad
                    visible: root.d.online
                    y: 11
                    width: chipText.implicitWidth + 30
                    height: 24
                    radius: 12
                    color: root.quiet ? "transparent" : Mock.alpha(root.d.topColor, 0.16)
                    border.width: 1
                    border.color: root.quiet ? "#3c4043" : Mock.alpha(root.d.topColor, 0.55)
                    Rectangle {
                        x: 9
                        anchors.verticalCenter: parent.verticalCenter
                        width: 8; height: 8; radius: 4
                        color: root.d.topColor
                    }
                    Text {
                        id: chipText
                        x: 22
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.d.topCount > 0 ? root.d.topCount + " " + root.d.topLabel.toLowerCase() : root.d.topLabel
                        color: root.quiet ? "#9aa0a6" : root.d.topColor
                        font { family: root.sans; pixelSize: 12; weight: Font.DemiBold; features: { "tnum": 1 } }
                    }
                }
            }

            // Share bar: one segment for each status that has agents.
            Item {
                id: bar
                readonly property real gap: 3
                readonly property int parts: {
                    var n = 0
                    for (var i = 0; i < root.d.groups.length; i++)
                        if (root.d.groups[i].count > 0) n++
                    return n
                }
                x: root.pad
                width: parent.width - root.pad * 2
                height: 8
                Rectangle {
                    visible: bar.parts === 0
                    anchors.fill: parent
                    radius: 4
                    color: "#2d2f33"
                }
                Row {
                    spacing: bar.gap
                    Repeater {
                        model: root.d.groups
                        Rectangle {
                            required property var modelData
                            visible: modelData.count > 0
                            width: visible ? (bar.width - bar.gap * (bar.parts - 1)) * modelData.count / root.d.total : 0
                            height: 8
                            radius: 4
                            color: modelData.color
                            opacity: root.d.open === "" || modelData.open ? 1 : 0.4
                        }
                    }
                }
            }

            // The four statuses as tabs.
            Row {
                id: tabs
                x: root.pad - 4
                width: parent.width - (root.pad - 4) * 2
                topPadding: 8
                bottomPadding: 8
                Repeater {
                    model: root.d.groups
                    Rectangle {
                        id: tab
                        required property var modelData
                        readonly property bool empty: modelData.count === 0 || !root.d.online
                        width: tabs.width / 4
                        height: 50
                        radius: 9
                        color: modelData.open ? Mock.alpha(modelData.color, 0.14) : "transparent"

                        Text {
                            id: number
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: 5
                            text: root.d.online ? tab.modelData.count : "–"
                            color: tab.empty ? "#5f6368" : tab.modelData.color
                            font { family: root.sans; pixelSize: 20; weight: Font.DemiBold; features: { "tnum": 1 } }
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: 30
                            text: tab.modelData.label
                            color: tab.empty ? "#80868b" : tab.modelData.open ? "#e8eaed" : "#bdc1c6"
                            font { family: root.sans; pixelSize: 11; weight: Font.Medium }
                        }
                        // An attention status with agents has a small lamp next to its number.
                        Rectangle {
                            visible: tab.modelData.attention && root.d.online
                            anchors.left: number.right
                            anchors.leftMargin: 4
                            y: 9
                            width: 6; height: 6; radius: 3
                            color: tab.modelData.color
                        }
                    }
                }
            }

            Rectangle {
                visible: root.d.open !== ""
                x: 2
                width: parent.width - 4
                height: 1
                color: "#3c4043"
            }

            Item {
                id: list
                visible: root.d.open !== ""
                width: parent.width
                height: root.d.shown * root.agentRow + (root.d.scrolls ? 34 : 12)

                Item {
                    y: 6
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

                                Image {
                                    x: root.pad + 2; width: 16; height: 16
                                    anchors.verticalCenter: parent.verticalCenter
                                    sourceSize: Qt.size(16, 16)
                                    source: root.icons[row.modelData.program] || ""
                                }
                                Text {
                                    id: label
                                    x: root.pad + 26
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
                                    anchors.rightMargin: root.pad + 2
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: Math.min(implicitWidth, row.failed ? 190 : 124)
                                    elide: Text.ElideRight
                                    text: row.failed ? root.d.message : row.opening ? "opening…" : row.modelData.detail
                                    color: row.failed ? "#f28b82" : row.opening ? "#8ab4f8" : "#9aa0a6"
                                    font { family: root.sans; pixelSize: 12; weight: row.failed || row.opening ? Font.Medium : Font.Normal }
                                }
                            }
                        }
                    }
                }
                // Scroll hint: a footer that says how many agents are below.
                Rectangle {
                    visible: root.d.scrolls
                    anchors.bottom: parent.bottom
                    x: 2
                    width: parent.width - 4
                    height: 26
                    radius: 11
                    color: "#17181b"
                    Text {
                        anchors.centerIn: parent
                        text: (root.d.agents.length - root.d.shown) + " more  ↓"
                        color: "#9aa0a6"
                        font { family: root.sans; pixelSize: 11; weight: Font.Medium; features: { "tnum": 1 } }
                    }
                }
            }
        }

    }
}
