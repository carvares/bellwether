// The layer shell: the panel (PanelShell.qml) as a wlr-layer-shell surface (org.kde.layershell). KDE Plasma on
// Wayland, and any compositor with the layer-shell protocol. The surface is in the overlay layer, anchored at the
// top-left corner of its output; the place of the panel is its two margins; it never takes the keyboard.
import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell
import ".."

PanelShell {
    id: root

    flags: Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus

    LayerShell.Window.scope: "bellwether"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.exclusionZone: -1
    LayerShell.Window.margins.left: posX
    LayerShell.Window.margins.top: posY
    // The compositor applies a new margin only with the next commit of the surface, so ask for a frame.
    LayerShell.Window.onMarginsChanged: root.requestUpdate()

    // A layer surface gets its output when it is made, from the screen of the window. So for a different
    // output: hide the window, change its screen, show it again.
    function showOn(target, x, y, real) {
        var shown = visible
        if (real)
            visible = false
        setPlace(target, x, y)
        if (real) {
            screen = real
            // Qt takes the screen of a new surface from the place of the window.
            root.x = target.x + posX
            root.y = target.y + posY
            surfaceScreen = target.name
            visible = shown
        }
    }
}
