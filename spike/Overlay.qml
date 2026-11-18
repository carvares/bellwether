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

    property int posX: 200
    property int posY: 120

    LayerShell.Window.scope: "herdr-float-spike"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.exclusionZone: -1
    LayerShell.Window.margins.left: root.posX
    LayerShell.Window.margins.top: root.posY

    Rectangle {
        anchors.fill: parent
        radius: 12
        color: "#202124"
        Text { anchors.centerIn: parent; color: "white"; text: "herdr-float spike" }
    }

    // Stand-in for a mouse drag: move the surface after 1.5 s.
    Timer {
        interval: 1500; running: true
        onTriggered: { root.posX += 40; console.log("move posX", root.posX, "margins.left", root.LayerShell.Window.margins.left) }
    }
    // Hide after 3 s, show again after 4 s.
    Timer { interval: 3000; running: true; onTriggered: { console.log("hide"); root.visible = false } }
    Timer { interval: 4000; running: true; onTriggered: { console.log("show"); root.visible = true } }
}
