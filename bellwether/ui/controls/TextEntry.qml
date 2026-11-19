// The text option of a question in the answer window: its key in a cap and a field of one line. The label of the
// option is the hint in the empty field. Enter in the field asks to send the text (`accepted`). A key that is typed
// here is text: it never presses an option. Only theme tokens.
import QtQuick

Rectangle {
    id: entry

    required property QtObject theme
    // The text option of the prompt: {key, label, …}.
    required property var choice
    property alias text: field.text
    readonly property bool isTextEntry: true
    readonly property Item input: field
    signal accepted()

    function take() {
        field.forceActiveFocus()
    }

    implicitHeight: theme.fit(36)
    height: implicitHeight
    radius: Math.min(theme.itemRadius, 10)
    color: Qt.rgba(theme.textColor.r, theme.textColor.g, theme.textColor.b, 0.06)
    border.width: 1
    border.color: field.activeFocus ? theme.accentColor : theme.lineColor

    Rectangle {
        id: cap
        readonly property bool isKeyCap: true
        x: 12
        anchors.verticalCenter: parent.verticalCenter
        width: entry.theme.fit(22)
        height: entry.theme.fit(22)
        radius: Math.min(entry.theme.itemRadius, 6)
        color: "transparent"
        border.width: 1
        border.color: entry.theme.textColor

        Text {
            anchors.centerIn: parent
            textFormat: Text.PlainText
            text: entry.choice.key
            color: entry.theme.textColor
            font { family: entry.theme.fontFamily; pixelSize: entry.theme.smallSize + 1; weight: Font.DemiBold }
        }
    }
    Text {
        readonly property bool isEntryHint: true
        visible: field.text === ""
        anchors.fill: field
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        textFormat: Text.PlainText
        text: entry.choice.label
        color: entry.theme.faintColor
        font { family: entry.theme.fontFamily; pixelSize: entry.theme.bodySize }
    }
    TextInput {
        id: field
        readonly property bool isAnswerField: true
        x: cap.x + cap.width + 10
        width: parent.width - x - 12
        height: parent.height
        verticalAlignment: TextInput.AlignVCenter
        clip: true
        activeFocusOnTab: true
        selectByMouse: true
        maximumLength: 4000
        color: entry.theme.textColor
        selectionColor: entry.theme.accentColor
        selectedTextColor: entry.theme.inkOn(entry.theme.accentColor)
        font { family: entry.theme.fontFamily; pixelSize: entry.theme.bodySize }
        Accessible.role: Accessible.EditableText
        Accessible.name: "Option " + entry.choice.key + ", " + entry.choice.label + ", text"
        onAccepted: entry.accepted()
    }
}
