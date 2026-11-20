// Layout C, "Techno / HUD". Monospace numerals, thin lines, corner brackets and one cell for each agent.
// A mock-up with made-up data: set `scene` to one of the names in MockData.js.
import QtQuick
import "MockData.js" as Mock

Item {
    id: root
    property string scene: "closed"
    readonly property var d: Mock.scene(scene)
    readonly property var icons: typeof iconUrls === "undefined" ? ({}) : iconUrls
    readonly property string mono: "Hack"
    readonly property color line: "#2b333b"
    readonly property color dim: "#8a949e"
    readonly property color ink: "#e3e9ee"
    readonly property color signal: d.topColor === Mock.NEUTRAL ? "#6b747d" : d.topColor
    readonly property int statusRow: 32
    readonly property int agentRow: 28
    readonly property int inset: 14

    width: 320
    height: panel.height

    Rectangle {
        id: panel
        width: parent.width
        height: column.height + 22
        color: "#f00b0e11"
        border.width: 1
        border.color: root.line

        // Corner brackets in the colour of the top status.
        Repeater {
            model: 4
            Item {
                required property int index
                id: bracket
                readonly property bool atRight: index % 2 === 1
                readonly property bool atBottom: index > 1
                x: atRight ? panel.width - 14 : 0
                y: atBottom ? panel.height - 14 : 0
                width: 14; height: 14
                Rectangle { x: 0; y: bracket.atBottom ? 12 : 0; width: 14; height: 2; color: root.signal }
                Rectangle { x: bracket.atRight ? 12 : 0; y: 0; width: 2; height: 14; color: root.signal }
            }
        }

        Column {
            id: column
            x: root.inset
            y: 11
            width: parent.width - root.inset * 2

            // Header: name, total, and the top status as a lamp with a word.
            Item {
                width: parent.width
                height: 22
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "HERDR"
                    color: root.dim
                    font { family: root.mono; pixelSize: 10; letterSpacing: 2; weight: Font.Bold }
                }
                Text {
                    x: 52
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.d.online ? "AGENTS " + Mock.pad2(root.d.total) : "NO LINK"
                    color: root.dim
                    font { family: root.mono; pixelSize: 10; letterSpacing: 1 }
                }
                Text {
                    id: lampWord
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.d.topLabel.toUpperCase()
                    color: root.signal
                    font { family: root.mono; pixelSize: 10; letterSpacing: 1.5; weight: Font.Bold }
                }
                Rectangle {
                    anchors.right: lampWord.left
                    anchors.rightMargin: 6
                    anchors.verticalCenter: parent.verticalCenter
                    width: 6; height: 6
                    color: root.signal
                }
            }

            // Cell bar: one cell for each agent, in the colour of its status.
            Item {
                id: cells
                readonly property int n: Math.max(root.d.total, 10)
                readonly property real cellGap: n > 24 ? 1 : 2
                readonly property real cell: (width - cellGap * (n - 1)) / n
                readonly property var colors: {
                    var out = []
                    for (var i = 0; i < root.d.groups.length; i++)
                        for (var k = 0; k < root.d.groups[i].count; k++)
                            out.push(root.d.groups[i].color)
                    return out
                }
                width: parent.width
                height: 20
                Repeater {
                    model: cells.n
                    Rectangle {
                        required property int index
                        readonly property bool lit: index < cells.colors.length
                        x: index * (cells.cell + cells.cellGap)
                        y: 5
                        width: cells.cell
                        height: 8
                        color: lit ? cells.colors[index] : "transparent"
                        border.width: lit ? 0 : 1
                        border.color: root.line
                    }
                }
            }

            // Offline body: a hatched plate with one word.
            Item {
                visible: !root.d.online
                width: parent.width
                height: 44
                Rectangle {
                    y: 6
                    width: parent.width
                    height: 32
                    color: "transparent"
                    border.width: 1
                    border.color: root.line
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
                        color: root.dim
                        font { family: root.mono; pixelSize: 13; letterSpacing: 4; weight: Font.Bold }
                    }
                }
            }

            Repeater {
                model: root.d.online ? root.d.groups : []

                Column {
                    id: group
                    required property var modelData
                    readonly property bool empty: modelData.count === 0
                    width: column.width

                    Item {
                        width: parent.width
                        height: root.statusRow

                        Rectangle {
                            visible: group.modelData.open
                            x: -6; y: 2
                            width: parent.width + 12
                            height: parent.height - 4
                            color: Mock.alpha(group.modelData.color, 0.10)
                            Rectangle { width: 2; height: parent.height; color: group.modelData.color }
                        }
                        // Marker: a filled square when the status has agents, an empty one when it has none.
                        Rectangle {
                            x: 2
                            anchors.verticalCenter: parent.verticalCenter
                            width: 8; height: 8
                            color: group.empty ? "transparent" : group.modelData.color
                            border.width: 1
                            border.color: group.empty ? "#4a535c" : group.modelData.color
                        }
                        Text {
                            id: name
                            x: 20
                            anchors.verticalCenter: parent.verticalCenter
                            text: group.modelData.label.toUpperCase()
                            color: group.empty ? "#68727c" : root.ink
                            font { family: root.mono; pixelSize: 12; letterSpacing: 1.5 }
                        }
                        // Dotted leader between the name and the numeral.
                        Row {
                            anchors.left: name.right
                            anchors.leftMargin: 10
                            anchors.right: count.left
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
                        Row {
                            id: count
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            Text {
                                visible: group.modelData.count < 10
                                text: "0"
                                color: "#3a444d"
                                font { family: root.mono; pixelSize: 20; weight: Font.Bold }
                            }
                            Text {
                                text: group.modelData.count
                                color: group.empty ? "#4a555f" : group.modelData.attention ? group.modelData.color : root.ink
                                font { family: root.mono; pixelSize: 20; weight: Font.Bold }
                            }
                        }
                    }

                    Item {
                        id: list
                        visible: group.modelData.open
                        width: parent.width
                        height: root.d.shown * root.agentRow + (root.d.scrolls ? 20 : 4)

                        Item {
                            width: parent.width
                            height: root.d.shown * root.agentRow
                            clip: true
                            Column {
                                width: parent.width
                                Repeater {
                                    model: group.modelData.open ? root.d.agents : []
                                    Item {
                                        id: row
                                        required property var modelData
                                        required property int index
                                        readonly property bool failed: root.d.failed === index
                                        readonly property bool opening: root.d.opening === index
                                        readonly property bool last: index === root.d.agents.length - 1
                                        width: list.width
                                        height: root.agentRow

                                        // Tree lines from the status marker to each agent.
                                        Rectangle { x: 5; width: 1; height: row.last ? parent.height / 2 : parent.height; color: "#3a444d" }
                                        Rectangle { x: 5; y: parent.height / 2; width: 9; height: 1; color: "#3a444d" }
                                        Image {
                                            x: 20; width: 16; height: 16
                                            anchors.verticalCenter: parent.verticalCenter
                                            sourceSize: Qt.size(16, 16)
                                            source: root.icons[row.modelData.program] || ""
                                        }
                                        Text {
                                            id: label
                                            x: 44
                                            width: Math.min(implicitWidth, detail.x - 8 - x - (address.visible ? address.width + 6 : 0))
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: row.modelData.label
                                            color: root.ink
                                            elide: Text.ElideRight
                                            font { family: root.mono; pixelSize: 12 }
                                        }
                                        Text {
                                            id: address
                                            visible: row.modelData.address !== "" && !row.failed  // The message needs the width.
                                            anchors.left: label.right
                                            anchors.leftMargin: 6
                                            anchors.baseline: label.baseline
                                            text: "[" + row.modelData.address + "]"
                                            color: "#68727c"
                                            font { family: root.mono; pixelSize: 11 }
                                        }
                                        Text {
                                            id: detail
                                            anchors.right: parent.right
                                            anchors.rightMargin: root.d.scrolls ? 10 : 0
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: Math.min(implicitWidth, row.failed ? 200 : 120)
                                            elide: Text.ElideRight
                                            text: row.failed ? "! " + root.d.message : row.opening ? "> opening…" : row.modelData.detail
                                            color: row.failed ? "#f28b82" : row.opening ? "#8ab4f8" : root.dim
                                            font { family: root.mono; pixelSize: 11 }
                                        }
                                    }
                                }
                            }
                            // Scroll track: one tick for each agent, bright for the rows on screen.
                            Column {
                                visible: root.d.scrolls
                                x: parent.width - 3
                                y: 4
                                spacing: 2
                                Repeater {
                                    model: root.d.agents.length
                                    Rectangle {
                                        required property int index
                                        width: 3
                                        height: (root.d.shown * root.agentRow - 8 - 2 * (root.d.agents.length - 1)) / root.d.agents.length
                                        color: index < root.d.shown ? "#8a949e" : "#2b333b"
                                    }
                                }
                            }
                        }
                        Text {
                            visible: root.d.scrolls
                            x: 20
                            y: root.d.shown * root.agentRow + 2
                            text: "ROWS 01–" + Mock.pad2(root.d.shown) + " / " + Mock.pad2(root.d.agents.length) + "  ▼ SCROLL"
                            color: "#68727c"
                            font { family: root.mono; pixelSize: 10; letterSpacing: 1 }
                        }
                    }
                }
            }
        }
    }
}
