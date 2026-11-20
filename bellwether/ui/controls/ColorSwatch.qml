// One colour of the custom look in the options window: a chip with the colour in effect, the name, the value,
// and "Reset" while the colour is custom. Activating it asks for the editor (`activated`). Only theme tokens.
import QtQuick

Rectangle {
    id: swatch

    required property QtObject theme
    // The role of the backend ("blocked") and its name on the screen ("Blocked").
    property string role: ""
    property string name: ""
    // The colour in effect: "#rrggbb", or "#aarrggbb" for a colour with an opacity (the background).
    property string colour: "#000000"
    // The user changed this colour.
    property bool custom: false
    // The editor shows this colour now.
    property bool editing: false
    readonly property string swatchFor: role
    readonly property string rgb: "#" + colour.slice(-6)
    readonly property bool hasOpacity: colour.length === 9
    readonly property int opacityPercent: hasOpacity ? Math.round(parseInt(colour.substr(1, 2), 16) / 2.55) : 100
    readonly property bool hovered: pointer.containsMouse
    signal activated()
    signal resetRequested()

    implicitWidth: 121
    implicitHeight: 8 + 22 + 6 + nameText.height + valueText.height + 7
    width: implicitWidth
    height: implicitHeight
    radius: theme.itemRadius
    color: editing ? theme.selectedColor : hovered ? theme.hoverColor : "transparent"
    border.width: 1
    border.color: editing ? theme.accentColor : hovered ? theme.faintColor : theme.lineColor
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: name + " colour, " + (custom ? "custom" : "default") + ", " + rgb
        + (hasOpacity ? ", " + opacityPercent + " percent opacity" : "")
    Accessible.focusable: true
    Accessible.onPressAction: activated()
    Keys.onReturnPressed: activated()
    Keys.onEnterPressed: activated()
    Keys.onSpacePressed: activated()

    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            swatch.forceActiveFocus()
            swatch.activated()
        }
    }
    // The colour in effect, without its opacity.
    Rectangle {
        readonly property bool isChip: true
        x: 8
        y: 8
        width: 34
        height: 22
        radius: Math.min(5, swatch.theme.itemRadius)
        color: swatch.rgb
        border.width: 1
        border.color: swatch.theme.lineColor
    }
    LookButton {
        readonly property bool isColourReset: true
        theme: swatch.theme
        small: true
        visible: swatch.custom
        enabled: swatch.custom
        anchors.right: parent.right
        anchors.rightMargin: 7
        y: 8 + (22 - height) / 2
        text: "Reset"
        spoken: "Reset " + swatch.name + " colour"
        onActivated: swatch.resetRequested()
    }
    Text {
        id: nameText
        x: 8
        y: 36
        width: parent.width - 16
        height: swatch.theme.fit(17)
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        text: swatch.name
        color: swatch.theme.textColor
        font { family: swatch.theme.fontFamily; pixelSize: swatch.theme.bodySize; weight: Font.Medium }
    }
    Text {
        id: valueText
        readonly property bool isColourValue: true
        x: 8
        y: nameText.y + nameText.height
        width: parent.width - 16
        height: swatch.theme.fit(15)
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        text: swatch.rgb + (swatch.hasOpacity ? " " + swatch.opacityPercent + "%" : "")
        color: swatch.custom ? swatch.theme.textColor : swatch.theme.dimColor
        font { family: swatch.theme.fontFamily; pixelSize: swatch.theme.size(10) }
    }
    FocusRing { target: swatch; corner: swatch.radius; border.color: swatch.theme.textColor }
}
