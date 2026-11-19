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

    readonly property string hitRole: "answer"
    readonly property string key: row.key
    // The pointer is on the control.
    readonly property bool hovered: row.view.panel.hoverItem === control
    // A jump runs: a click does nothing, as on a row.
    readonly property bool inert: row.view.panel.opening !== ""
    // The width that the row keeps free for the control: 0 when the row has none.
    readonly property real reserve: visible ? width + gap : 0
    // The ink of the word: the accent, or on the full plate under the pointer the ink that can be read on it.
    readonly property color ink: hovered ? tokens.inkOn(tokens.accentColor) : tokens.accentColor

    // The widest that the detail of the row can be (the skin gives the two widths of its design: for the message
    // of a failed jump, and for the detail). On a row with the control the detail is short, so that the label of
    // the agent keeps most of the row; the message of a failed jump gives the control its width.
    function detailRoom(failedRoom, room) {
        return row.failed ? failedRoom - reserve : visible ? Math.min(room, 72) : room
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
