// The plain shell: the panel (PanelShell.qml) as a frameless tool window that stays above the other windows and
// never takes the focus. macOS, Windows, X11, and Wayland with no layer shell. No system call here: the program
// adds what a system needs after the window exists.
//
// The place of the panel is the place of the window: x and y in the whole desktop (the screen of the panel plus
// posX, posY), and its screen. Each change of the place, the size or the screen gives ONE request to the window
// system, after the step in which it was made (Qt.callLater): x, y, width, height together, so the window never
// stands at a point between two places (a point that can be on no monitor) and never has the new size at the old
// place. While the window is hidden the request is made at once: the window shows at its place.
// When the window system puts the window somewhere else (a window manager that keeps it inside an area), the
// shell asks for the place again, one time, and then leaves it until the place changes.
// A Wayland compositor does not let a program place its window: there x and y have no effect.
import QtQuick
import QtQuick.Window
import ".."

PanelShell {
    id: root

    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
           | Qt.NoDropShadowWindowHint

    // The number of geometry requests to the window system (for tests and scripts).
    property int placeRequests: 0
    // The size that the panel takes (applySize) until the request is made. 0: the size of the window.
    property int nextWidth: 0
    property int nextHeight: 0
    // The real screen that the window goes to with the next request (showOn). null: the screen stays.
    property var nextScreen: null
    // The place in the desktop of the last request, and whether it was asked again after the window system put
    // the window somewhere else.
    property real askedX: NaN
    property real askedY: NaN
    property bool askedAgain: false
    property bool placeQueued: false

    // A screen change first, then the geometry: a new screen that is not part of the same desktop makes Qt make
    // the window again, and the geometry must go to that window; on one desktop Qt picks the same screen from the
    // geometry. Both in one step, before the next frame.
    function applyPlace() {
        placeQueued = false
        var w = nextWidth > 0 ? nextWidth : width
        var h = nextHeight > 0 ? nextHeight : height
        nextWidth = 0
        nextHeight = 0
        if (nextScreen) {
            screen = nextScreen
            nextScreen = null
        }
        // During a drag the place can be on two screens: it is not kept on its screen.
        var place = dragging() ? {x: posX, y: posY} : clampedPlace(w, h)
        askedX = home.x + place.x
        askedY = home.y + place.y
        if (x !== askedX || y !== askedY || width !== w || height !== h) {
            placeRequests += 1
            setGeometry(askedX, askedY, w, h)
        }
    }

    function placeWindow() {
        if (!visible) {
            applyPlace()
        } else if (!placeQueued) {
            placeQueued = true
            Qt.callLater(applyPlace)
        }
    }

    // The place changed: a new request, and one more ask if the window system moves the window.
    function placeChanged() {
        askedAgain = false
        placeWindow()
    }

    // The window is somewhere else than asked (after the answer of the window system: both coordinates are there).
    function checkPlace() {
        if (placeQueued || askedAgain || dragging() || isNaN(askedX))
            return
        if (x !== askedX || y !== askedY) {
            askedAgain = true
            placeWindow()
        }
    }

    function applySize(w, h) {
        nextWidth = w
        nextHeight = h
        placeWindow()
    }

    function showOn(target, x, y, real) {
        if (real) {
            nextScreen = real
            surfaceScreen = target.name
        }
        setPlace(target, x, y)
        if (real)
            placeWindow()  // also when the place on the screen is the same
    }

    onPosXChanged: placeChanged()
    onPosYChanged: placeChanged()
    onHomeChanged: placeChanged()
    onXChanged: Qt.callLater(checkPlace)
    onYChanged: Qt.callLater(checkPlace)
}
