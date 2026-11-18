import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell

// Variant: no bindings on margins. Margins are written from JavaScript.
// Result: "margins.left += 40" works. "Qt.margins(...)" does not exist in
// QML and gives a TypeError (lines kept here as the record of that test).
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
    LayerShell.Window.margins: Qt.margins(200, 120, 0, 0)

    Rectangle { anchors.fill: parent; radius: 12; color: "#202124" }

    Timer {
        interval: 800; running: true
        onTriggered: {
            root.LayerShell.Window.margins.left += 40
            console.log("after += : left", root.LayerShell.Window.margins.left)
        }
    }
    Timer {
        interval: 1600; running: true
        onTriggered: {
            root.LayerShell.Window.margins = Qt.margins(300, 150, 0, 0)
            console.log("after Qt.margins: left", root.LayerShell.Window.margins.left, "top", root.LayerShell.Window.margins.top)
        }
    }
}
