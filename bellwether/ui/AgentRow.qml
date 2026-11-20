// One agent row of an AgentList. It holds what every skin needs: the size, the click target for the pointer
// handler of the window (hitRole "agent" and key), the states of the row and the name for a screen reader.
// A skin uses it as the delegate of its AgentList and puts the drawing in it as children.
import QtQuick

Item {
    id: row

    // The row from the backend: {key, icon, label, detail, address, spoken, canAnswer, model, sessionAge, metaText}.
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
    // The note in the place of the detail: "failed" (the message of the failed jump), "opening" (a jump to this
    // agent runs) or "" (no note: the detail). A failure comes before "opening". The skin chooses the colour
    // (panel.failedColor, panel.openingColor) and the place.
    readonly property string note: failed ? "failed" : opening ? "opening" : ""
    // The text in that place: the failure message, "opening…", or the detail of the agent.
    readonly property string noteText: failed ? view.panel.failedMessage : opening ? "opening…" : modelData.detail
    // The pointer is on this row.
    readonly property bool hovered: view.panel.hoverItem === row
    // The row has an "Answer" control (AnswerControl.qml): the agent is blocked and the answer window can open for
    // it. The one place of this rule for every skin; the backend decides (canAnswer of the row).
    readonly property bool canAnswer: modelData.canAnswer === true
    // The last row of the group.
    readonly property bool last: index === view.count - 1
    // The second line of the row (MetaLine.qml): the model that the agent runs ("Opus 5.5") and the age of its
    // session ("2h 14m"). "": that part is not known. The row has the line when it has one of the two. The one
    // place of this rule for every skin; the backend gives the texts.
    readonly property string model: modelData.model || ""
    readonly property string sessionAge: modelData.sessionAge || ""
    readonly property bool hasMeta: model !== "" || sessionAge !== ""
    // Where the first line of the row is (the label, the address, the detail), from the middle of the row: a skin
    // adds it to `anchors.verticalCenter`. A row with the second line has its first line above the middle. A row
    // without it keeps its one line in the middle, also in a list whose other rows have two lines.
    readonly property real lineShift: hasMeta ? -(height - view.rowHeight) / 2 : 0

    width: view.width
    height: view.pitch
    Accessible.role: Accessible.Button
    Accessible.name: modelData.spoken
    Accessible.onPressAction: view.panel.jump(key)
}
