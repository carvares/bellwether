// The "Answer" control of an agent row: the target that opens the answer window for the agent of the row. A skin
// puts one in its AgentRow, gives it a place and its own style (the corner, a plate or an outline, capitals), and
// keeps the room for it free (`reserve`). The rule "which rows have it" is in AgentRow (canAnswer), not in a skin:
// the control shows only then. The pointer handler of the window finds it by its hitRole ("answer", with the key
// of the row): a click on it opens the answer window and does not jump; a drag from it moves the panel.
import QtQuick

Item {
    id: control

    // The row that holds the control, and the theme tokens of the skin.
    required property AgentRow row
    required property QtObject tokens
    // ----- the style, from the skin -----
    // The radius of the corners. -1: a pill.
    property real corner: -1
    // A soft plate of the accent and no outline; false: an outline and no plate.
    property bool plated: false
    // The word in capitals with wider letters (a design with such titles).
    property bool capitals: false
    // The space between the control and what is at its left in the row.
    property int gap: 8
    // The label of the agent and its address in the row, and the space that the skin keeps between the label (or
    // the address) and the detail: on a row with the control, the label has the room first (see detailRoom).
    property Item labelItem: null
    property Item addressItem: null
    property int labelGap: 10

    readonly property string hitRole: "answer"
    readonly property string key: row.key
    // The pointer is on the control.
    readonly property bool hovered: row.view.panel.hoverItem === control
    // A jump runs: a click does nothing, as on a row.
    readonly property bool inert: row.view.panel.opening !== ""
    // On a row with the second line (the model and the session time) the control is at that line, below the first
    // line: the name and the detail of the agent keep the full width of the row, and the control is not on them.
    readonly property bool lowered: visible && row.hasMeta
    // How far the control is below the middle of the row: a skin adds it to `anchors.verticalCenter`. Lowered, the
    // control ends 3 px above the end of the row.
    readonly property real drop: lowered ? Math.max(0, (row.height - height) / 2 - 3) : 0
    // The width that the first line of the row keeps free for the control: 0 when the row has none, or has it lower.
    readonly property real reserve: visible && !lowered ? width + gap : 0
    // The ink of the word: the accent, or on the full plate under the pointer the ink that can be read on it.
    readonly property color ink: hovered ? tokens.inkOn(tokens.accentColor) : tokens.accentColor

    // The room that the label of the agent leaves at the left of the control when it shows in full (the label, the
    // address and the detail are in the same parent as the control).
    readonly property real leftByLabel: labelItem === null ? 72
        : x - gap - labelGap - labelItem.x - (addressItem !== null && addressItem.visible ? addressItem.width + 6 : 0)
          - labelItem.implicitWidth

    // The widest that the detail of the row can be (the skin gives the two widths of its design: for the message
    // of a failed jump, and for the detail). On a row with the control the detail is short (at most 72 px), so that
    // the label of the agent keeps most of the row, and it gives way first: it takes only what the whole label
    // leaves (with a large text it goes). The message of a failed jump gives the control its width.
    function detailRoom(failedRoom, room) {
        return row.failed ? failedRoom - reserve
            : visible && !lowered ? Math.max(0, Math.min(room, 72, leftByLabel)) : room
    }

    visible: row.canAnswer
    width: Math.ceil(word.implicitWidth) + (capitals ? 12 : 16)
    height: tokens.fit(18)
    opacity: inert ? 0.5 : 1
    Accessible.role: Accessible.Button
    Accessible.name: "Answer " + row.modelData.label
    Accessible.onPressAction: row.view.panel.answer(key)

    Rectangle {
        readonly property bool isAnswerPlate: true
        anchors.fill: parent
        radius: control.corner < 0 ? height / 2 : Math.min(control.corner, height / 2)
        color: control.hovered ? control.tokens.accentColor
            : control.plated ? Qt.rgba(control.tokens.accentColor.r, control.tokens.accentColor.g,
                                       control.tokens.accentColor.b, 0.16) : "transparent"
        border.width: control.plated ? 0 : 1
        border.color: Qt.rgba(control.tokens.accentColor.r, control.tokens.accentColor.g,
                              control.tokens.accentColor.b, control.hovered ? 1 : 0.6)
    }
    Text {
        id: word
        readonly property bool isAnswerWord: true
        anchors.centerIn: parent
        text: "Answer"
        color: control.ink
        font {
            family: control.tokens.fontFamily
            pixelSize: control.tokens.smallSize
            weight: Font.Medium
            letterSpacing: control.capitals ? 0.8 : 0
            capitalization: control.capitals ? Font.AllUppercase : Font.MixedCase
        }
    }
}
