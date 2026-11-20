// The plain shell: the panel (PanelShell.qml) as a frameless tool window that stays above the other windows and
// never takes the focus. macOS, Windows, X11, and Wayland with no layer shell. No system call here: the program
// adds what a system needs after the window exists.
//
// The place of the panel is the place of the window: x and y in the whole desktop (the screen of the panel plus
// posX, posY), and its screen. On a system with one space of coordinates for all the screens (X11, macOS,
// Windows) Qt gives the window the screen that holds it when it moves, also during a drag across two screens.
// A Wayland compositor does not let a program place its window: there x and y have no effect.
import QtQuick
import QtQuick.Window
import ".."

PanelShell {
    id: root

    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
           | Qt.NoDropShadowWindowHint
    x: home.x + posX
    y: home.y + posY

    function showOn(target, x, y, real) {
        setPlace(target, x, y)
        if (real) {
            screen = real
            surfaceScreen = target.name
        }
    }
}
