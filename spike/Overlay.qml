import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell

Window {
    id: root
    visible: true
    width: 220
    height: 48
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus

    LayerShell.Window.scope: "herdr-float-spike"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.exclusionZone: -1
    LayerShell.Window.margins.left: 200
    LayerShell.Window.margins.top: 120

    Rectangle {
        anchors.fill: parent
        radius: 12
        color: "#202124"
        Text { anchors.centerIn: parent; color: "white"; text: "herdr-float spike" }
        MouseArea {
            anchors.fill: parent
            onClicked: {
                root.LayerShell.Window.margins.left += 40
                console.log("left margin", root.LayerShell.Window.margins.left)
            }
        }
    }
}
