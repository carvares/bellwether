import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell

// Variant: only the margin changes, 5 times, 200 ms apart. Nothing else
// changes on the screen. The context property spikeMode selects what the
// code does after each margin change:
//   none | requestUpdate | update   call in the code that changes the margin
//   signal                          one handler on the marginsChanged signal
Window {
    id: root
    visible: true
    width: 220
    height: 48
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus

    property int posX: 200
    property int moves: 0

    LayerShell.Window.scope: "herdr-float-spike"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.exclusionZone: -1
    LayerShell.Window.margins.left: root.posX
    LayerShell.Window.margins.top: 120
    LayerShell.Window.onMarginsChanged: if (spikeMode === "signal") root.requestUpdate()

    Rectangle { anchors.fill: parent; radius: 12; color: "#202124" }

    Timer {
        interval: 200; repeat: true; running: root.moves < 5
        // First move at 1000 ms, so that the first frames are finished.
        property int ticks: 0
        onTriggered: {
            ticks += 1
            if (ticks < 5) return
            root.moves += 1
            root.posX += 10
            if (spikeMode === "requestUpdate") root.requestUpdate()
            else if (spikeMode === "update") root.update()
        }
    }
}
