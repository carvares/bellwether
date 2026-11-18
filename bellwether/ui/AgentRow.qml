// One agent row of an AgentList. It holds what every skin needs: the size, the click target for the pointer
// handler of the window (hitRole "agent" and key), the states of the row and the name for a screen reader.
// A skin uses it as the delegate of its AgentList and puts the drawing in it as children.
import QtQuick

Item {
    id: row

    // The row from the backend: {key, icon, label, detail, address, spoken}.
    required property var modelData
    required property int index
    // The AgentList that holds this row.
    required property AgentList view

    readonly property string hitRole: "agent"
    readonly property string key: modelData.key
    // The last jump to this agent failed: the row shows view.panel.failedMessage in the place of its detail.
    readonly property bool failed: view.panel.failedKey === key
    // A jump to this agent runs: the row shows "opening…" in the place of its detail.
    readonly property bool opening: view.panel.opening === key
    // The pointer is on this row.
    readonly property bool hovered: view.panel.hoverItem === row
    // The last row of the group.
    readonly property bool last: index === view.count - 1

    width: view.width
    height: view.rowHeight
    Accessible.role: Accessible.Button
    Accessible.name: modelData.spoken
    Accessible.onPressAction: view.panel.jump(key)
}
