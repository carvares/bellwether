// One option of a question in the answer window: its key in a cap, its label, and its description below. The look
// tells what the option does, with a shape and not only a colour: an option that approves this one thing has a full
// cap in the accent; an option that approves more than this one thing ("always allow", "don't ask again", "auto
// mode") has an empty cap, a bar in the warning colour and the words "Standing permission" (the same words for each
// such option, so that the look never rests on a colour alone), so that it never looks like the plain "Yes"; an option
// that declines, and an answer to a question, have an empty cap in the colour of the text. Enter, Return and Space
// press the option that has the keyboard. Only theme tokens.
import QtQuick

Rectangle {
    id: button

    required property QtObject theme
    // The option of the prompt: {key, label, description, kind, effect, wide, allowed}.
    required property var choice
    // The colour for an option that approves more than this one thing (a status colour of the custom look).
    required property color warnColor
    readonly property bool isOptionButton: true
    readonly property string key: choice.key
    readonly property bool accepts: choice.effect === "accept"
    readonly property bool wide: accepts && choice.wide === true
    readonly property bool declines: choice.effect === "decline"
    // The look: "accept", "wide", "decline" or "other".
    readonly property string look: wide ? "wide" : accepts ? "accept" : declines ? "decline" : "other"
    readonly property color tone: look === "accept" ? theme.accentColor : look === "wide" ? warnColor
                                : look === "decline" ? theme.dimColor : theme.textColor
    readonly property bool hovered: pointer.containsMouse && enabled
    readonly property string effectWord: accepts ? "approves" : declines ? "declines" : "answers"
    // The words of an option that approves more than this one thing.
    readonly property string wideWords: "Standing permission"
    signal activated()

    implicitHeight: Math.max(theme.fit(36), texts.height + 14)
    height: implicitHeight
    radius: Math.min(theme.itemRadius, 10)
    color: hovered ? Qt.rgba(tone.r, tone.g, tone.b, 0.10) : "transparent"
    border.width: 1
    border.color: Qt.rgba(tone.r, tone.g, tone.b, hovered || activeFocus ? 0.9 : look === "decline" ? 0.5 : 0.6)
    opacity: enabled ? 1 : 0.4
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: "Option " + key + ", " + choice.label + ", " + effectWord
                     + (wide ? ", " + wideWords.toLowerCase() : "") + (enabled ? "" : ", not available")
    Accessible.focusable: enabled
    Accessible.onPressAction: if (enabled) activated()
    Keys.onReturnPressed: activated()
    Keys.onEnterPressed: activated()
    Keys.onSpacePressed: activated()

    // The bar of an option that approves more than this one thing.
    Rectangle {
        readonly property bool isWideBar: true
        visible: button.wide
        x: 1; y: 6
        width: 3
        height: parent.height - 12
        radius: 1.5
        color: button.warnColor
    }
    // The key in its cap.
    Rectangle {
        id: cap
        readonly property bool isKeyCap: true
        readonly property bool full: button.look === "accept"
        x: 12
        y: 7
        width: button.theme.fit(22)
        height: button.theme.fit(22)
        radius: Math.min(button.theme.itemRadius, 6)
        color: full ? button.tone : "transparent"
        border.width: full ? 0 : button.look === "wide" ? 2 : 1
        border.color: button.tone

        Text {
            anchors.centerIn: parent
            textFormat: Text.PlainText
            text: button.key
            color: cap.full ? button.theme.inkOn(button.tone) : button.tone
            font { family: button.theme.fontFamily; pixelSize: button.theme.smallSize + 1; weight: Font.DemiBold }
        }
    }
    Column {
        id: texts
        x: cap.x + cap.width + 10
        y: 7
        width: parent.width - x - 12
        spacing: 2

        Text {
            readonly property bool isOptionLabel: true
            width: parent.width
            height: Math.max(implicitHeight, cap.height)
            verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            text: button.choice.label
            color: button.look === "decline" ? button.theme.dimColor : button.theme.textColor
            font { family: button.theme.fontFamily; pixelSize: button.theme.bodySize; weight: Font.Medium }
        }
        Text {
            readonly property bool isWideTag: true
            visible: button.wide
            width: parent.width
            textFormat: Text.PlainText
            text: button.wideWords
            color: button.warnColor
            font {
                family: button.theme.fontFamily; pixelSize: button.theme.smallSize; weight: Font.DemiBold
                letterSpacing: button.theme.letterSpacing
                capitalization: button.theme.uppercaseTitles ? Font.AllUppercase : Font.MixedCase
            }
        }
        Text {
            readonly property bool isOptionDescription: true
            visible: text !== ""
            width: parent.width
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            text: button.choice.description
            color: button.theme.dimColor
            font { family: button.theme.fontFamily; pixelSize: button.theme.smallSize + 1 }
        }
    }
    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            button.forceActiveFocus()
            button.activated()
        }
    }
    FocusRing { target: button; corner: button.radius; border.color: button.tone }
}
