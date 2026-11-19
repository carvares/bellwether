// The keyboard focus of a control of the options window: a ring outside the control.
import QtQuick

Rectangle {
    // The control that has the ring, and the radius of its corners.
    required property Item target
    property real corner: 0
    readonly property bool isFocusRing: true

    visible: target.activeFocus
    anchors.fill: target
    anchors.margins: -3
    radius: corner > 0 ? corner + 3 : 0
    color: "transparent"
    border.width: 2
}
