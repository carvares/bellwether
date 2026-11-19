// A slider of the options window: a track, the part up to the value in the accent colour, a mark at the default
// value, and a handle. The value comes from outside (a binding to the backend); the slider only asks for a new
// value (`moved`), in whole steps. Keys: the arrows move one step, Page Up and Page Down four, Home and End go to
// the ends. A double click asks for the default (`resetRequested`). Only theme tokens.
import QtQuick

Item {
    id: slider

    required property QtObject theme
    // What the slider sets, for a screen reader: "Panel size".
    property string label: ""
    property real from: 0
    property real to: 1
    property real step: 0.05
    property real value: 0
    // The value that the mark shows. Out of the limits: no mark.
    property real defaultValue: -1
    // The value as a share of the track, and in words. Every slider of the window is a percentage.
    readonly property real share: to > from ? Math.max(0, Math.min(1, (value - from) / (to - from))) : 0
    readonly property int percent: Math.round(value * 100)
    readonly property bool isSlider: true
    readonly property int handleSize: 14
    signal moved(real value)
    signal resetRequested()

    // The nearest whole step inside the limits, with two decimal places.
    function snapped(wanted) {
        var steps = Math.round((wanted - from) / step + 0.000001)
        return Math.round(Math.max(from, Math.min(to, from + steps * step)) * 100) / 100
    }

    function nudge(steps) {
        moved(snapped(snapped(value) + steps * step))
    }

    // The value for the place x of the pointer.
    function moveTo(x) {
        var room = width - handleSize
        moved(snapped(from + Math.max(0, Math.min(1, (x - handleSize / 2) / room)) * (to - from)))
    }

    implicitWidth: 240
    implicitHeight: theme.fit(28)
    activeFocusOnTab: true
    Accessible.role: Accessible.Slider
    Accessible.name: label + ", " + percent + " percent"
    Accessible.focusable: true
    Accessible.onIncreaseAction: nudge(1)
    Accessible.onDecreaseAction: nudge(-1)
    Keys.onLeftPressed: nudge(-1)
    Keys.onDownPressed: nudge(-1)
    Keys.onRightPressed: nudge(1)
    Keys.onUpPressed: nudge(1)
    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Home) moved(from)
        else if (event.key === Qt.Key_End) moved(to)
        else if (event.key === Qt.Key_PageUp) nudge(4)
        else if (event.key === Qt.Key_PageDown) nudge(-4)
        else return
        event.accepted = true
    }

    Rectangle {
        id: track
        x: slider.handleSize / 2
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width - slider.handleSize
        height: 4
        radius: Math.min(2, slider.theme.itemRadius)
        color: slider.theme.lineColor

        Rectangle {
            readonly property bool isSliderFill: true
            width: parent.width * slider.share
            height: parent.height
            radius: parent.radius
            color: slider.theme.accentColor
        }
        // The default value.
        Rectangle {
            readonly property bool isDefaultMark: true
            visible: slider.defaultValue >= slider.from && slider.defaultValue <= slider.to
            x: Math.round(parent.width * (slider.defaultValue - slider.from) / (slider.to - slider.from)) - 1
            y: -4
            width: 2
            height: parent.height + 8
            color: slider.theme.faintColor
        }
    }
    Rectangle {
        id: handle
        readonly property bool isSliderHandle: true
        x: Math.round(track.width * slider.share)
        anchors.verticalCenter: parent.verticalCenter
        width: slider.handleSize
        height: slider.handleSize
        radius: Math.min(slider.handleSize / 2, slider.theme.itemRadius)
        color: pointer.pressed || pointer.containsMouse ? slider.theme.accentColor : slider.theme.textColor
        border.width: 1
        border.color: slider.theme.panelColor
    }
    FocusRing { target: handle; corner: handle.radius; border.color: slider.theme.accentColor }

    MouseArea {
        id: pointer
        // After a double click: the press that is still down does not move the value away from the default.
        property bool rests: false
        anchors.fill: parent
        hoverEnabled: true
        preventStealing: true
        cursorShape: Qt.PointingHandCursor
        onPressed: (mouse) => {
            slider.forceActiveFocus()
            rests = false
            slider.moveTo(mouse.x)
        }
        onPositionChanged: (mouse) => {
            if (pressed && !rests)
                slider.moveTo(mouse.x)
        }
        onDoubleClicked: {
            rests = true
            slider.resetRequested()
        }
    }
}
