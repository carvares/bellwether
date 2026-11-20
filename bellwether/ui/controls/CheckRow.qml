// One row of a section of the options window for a setting that is on or off: a box with a mark, and its label.
// A click on the row, Space, Enter and Return change it. The row does not read the backend: the caller gives
// `checked` and gets `toggled` with the new value. `name` is the name of the setting for a test. Only theme tokens.
import QtQuick

Item {
    id: row

    required property QtObject theme
    required property string name
    required property string label
    required property bool checked
    readonly property bool isCheckRow: true
    readonly property bool hovered: pointer.containsMouse
    signal toggled(bool value)

    implicitWidth: box.width + 10 + Math.ceil(labelText.implicitWidth)
    implicitHeight: theme.fit(24)
    width: implicitWidth
    height: implicitHeight
    activeFocusOnTab: true
    Accessible.role: Accessible.CheckBox
    Accessible.name: label
    Accessible.checkable: true
    Accessible.checked: checked
    Accessible.focusable: true
    Accessible.onToggleAction: toggled(!checked)
    Accessible.onPressAction: toggled(!checked)
    Keys.onReturnPressed: toggled(!checked)
    Keys.onEnterPressed: toggled(!checked)
    Keys.onSpacePressed: toggled(!checked)

    Rectangle {
        id: box
        readonly property bool isCheckBox: true
        anchors.verticalCenter: parent.verticalCenter
        width: row.theme.fit(16)
        height: width
        radius: Math.min(row.theme.itemRadius, 4)
        color: row.checked ? row.theme.accentColor : "transparent"
        border.width: 1
        border.color: row.checked ? row.theme.accentColor
            : Qt.rgba(row.theme.textColor.r, row.theme.textColor.g, row.theme.textColor.b, row.hovered ? 0.9 : 0.45)

        // The mark, drawn: a font of the user can lack a check mark.
        Item {
            visible: row.checked
            anchors.centerIn: parent
            width: parent.width * 0.6
            height: parent.height * 0.6
            rotation: 45

            Rectangle {
                x: parent.width * 0.55; y: 0
                width: Math.max(1.5, parent.width * 0.2); height: parent.height
                color: row.theme.inkOn(row.theme.accentColor)
            }
            Rectangle {
                x: parent.width * 0.15; y: parent.height - height
                width: parent.width * 0.6; height: Math.max(1.5, parent.width * 0.2)
                color: row.theme.inkOn(row.theme.accentColor)
            }
        }
    }
    Text {
        id: labelText
        x: box.width + 10
        width: parent.width - x
        height: parent.height
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        text: row.label
        color: row.theme.textColor
        font { family: row.theme.fontFamily; pixelSize: row.theme.bodySize }
    }
    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            row.forceActiveFocus()
            row.toggled(!row.checked)
        }
    }
    FocusRing { target: row; corner: 4; border.color: row.theme.textColor }
}
