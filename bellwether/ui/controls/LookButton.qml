// A button of the options window: a text on a plate. Enter, Return and Space press it. Only theme tokens.
import QtQuick

Rectangle {
    id: button

    required property QtObject theme
    property string text: ""
    // The name for a screen reader, when it says more than the text ("Reset Blocked colour").
    property string spoken: text
    // The colour of the text and of the outline. A caller gives an ink that can always be read
    // (theme.readable) to a control that must stay usable with any colours.
    property color ink: theme.textColor
    property color plate: "transparent"
    property bool small: false
    readonly property bool hovered: pointer.containsMouse
    signal activated()

    implicitWidth: label.implicitWidth + (small ? 14 : 24)
    implicitHeight: theme.fit(small ? 20 : 28)
    width: implicitWidth
    height: implicitHeight
    radius: Math.min(theme.itemRadius, height / 2)
    color: plate
    border.width: 1
    border.color: Qt.rgba(ink.r, ink.g, ink.b, hovered || activeFocus ? 0.9 : 0.45)
    opacity: enabled ? 1 : 0.4
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: spoken
    Accessible.focusable: enabled
    Accessible.onPressAction: if (enabled) activated()
    Keys.onReturnPressed: activated()
    Keys.onEnterPressed: activated()
    Keys.onSpacePressed: activated()

    // Under the pointer the plate is a little lighter (or darker, on a light plate).
    Rectangle {
        visible: button.hovered
        anchors.fill: parent
        radius: parent.radius
        color: Qt.rgba(button.ink.r, button.ink.g, button.ink.b, 0.10)
    }
    Text {
        id: label
        anchors.centerIn: parent
        text: button.text
        color: button.ink
        font {
            family: button.theme.fontFamily
            pixelSize: button.small ? button.theme.size(10) : button.theme.smallSize + 1
            weight: Font.Medium
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
    FocusRing { target: button; corner: button.radius; border.color: button.ink }
}
