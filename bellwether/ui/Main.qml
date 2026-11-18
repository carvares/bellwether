// The window of the floating panel: the layer surface, its place and its screen, the drag, and the one pointer
// handler. The state and the rules are in PanelModel.qml. The drawing is a skin (skins/<letter>.qml) that the
// Loader below shows: the layout of the backend. The skin contract is in the spec
// (docs/superpowers/specs/2026-11-18-bellwether-design.md, "options window and layout skins").
import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell

Window {
    id: root

    // The state and the rules that every layout uses.
    // (QtObject: Python reads this property, and it has no converter for a QML type.)
    readonly property QtObject panel: panelModel
    // The open group and the row under the pointer, for tests and scripts.
    property alias openState: panelModel.openState
    property alias hoverRow: panelModel.hoverItem
    // The skin that shows now. null for a moment while a different skin loads.
    readonly property Item skin: skinLoader.item
    // False until the first skin is there and the panel has its place: the window shows after that.
    property bool started: false
    // The place of the panel, from the top-left corner of its screen (screenName).
    property int posX: 0
    property int posY: 0
    // The name of the screen that holds the panel: the layer surface is on the output of this screen.
    // "" until the start is complete.
    property string screenName: ""
    // The name of the screen whose output the layer surface was made on. A surface gets its output when it is made.
    property string surfaceScreen: ""
    // The screens of the desktop. Each has name, virtualX, virtualY, width and height. A test gives its own list.
    property var screenSource: Qt.application.screens
    // The screen that holds the panel as {name, x, y, width, height}, with x and y in the whole desktop.
    // The screen of the window while the named screen is not there.
    readonly property var home: screenNamed(screenName)
        || ({name: Screen.name, x: Screen.virtualX, y: Screen.virtualY, width: Screen.width, height: Screen.height})
    // True from the time the compositor closes the surface (its monitor went away) until the panel shows again.
    property bool closedByCompositor: false
    // True until the user moves the widget: it then stays at the top-right corner when its size changes.
    property bool atDefault: false
    // The refresh rate of the screen of the window, in Hz. The program sets it (QML does not have it). 0: unknown.
    property real refreshRate: 0
    // The shortest time between two moves of a drag: two frames of the screen, from 4 ms to 20 ms. A new margin
    // goes to the compositor with the next commit, and Qt holds that commit until the frame before it is on the
    // screen. So a pointer event can come one frame after a move and still be relative to the old place.
    readonly property real minMoveMs: refreshRate > 0 ? Math.min(20, Math.max(4, 2000 / refreshRate)) : 16
    readonly property int edge: 16

    // A layer surface must not have the size 0: the window shows when it has the size of its first skin.
    visible: false
    color: "transparent"
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

    // Keep the panel on its screen. During a drag the panel can be on two screens, so the drag does this itself.
    function clampPosition() {
        if (pointerArea.pressed && pointerArea.moved)
            return
        if (atDefault) {
            posX = home.width - width - edge
            posY = edge
        }
        var maxX = Math.max(0, home.width - width)
        var maxY = Math.max(0, home.height - height)
        posX = Math.min(Math.max(0, posX), maxX)
        posY = Math.min(Math.max(0, posY), maxY)
    }

    // The screens as {name, x, y, width, height}, with x and y in the whole desktop.
    function screens() {
        var out = []
        var list = screenSource
        for (var i = 0; i < list.length; i++)
            out.push({name: list[i].name, x: list[i].virtualX, y: list[i].virtualY,
                      width: list[i].width, height: list[i].height})
        return out
    }

    function screenNamed(name) {
        var list = screens()
        for (var i = 0; i < list.length; i++)
            if (list[i].name === name)
                return list[i]
        return null
    }

    // The screen of `list` that holds the point, or the screen nearest to it. null with no screens.
    function screenAt(list, px, py) {
        var best = null
        var bestGap = 0
        for (var i = 0; i < list.length; i++) {
            var s = list[i]
            var gapX = Math.max(s.x - px, 0, px - (s.x + s.width - 1))
            var gapY = Math.max(s.y - py, 0, py - (s.y + s.height - 1))
            if (best === null || gapX + gapY < bestGap) {
                best = s
                bestGap = gapX + gapY
            }
        }
        return best
    }

    // Where a drag can put a panel of w × h that wants to be at (gx, gy) of the desktop: the nearest place where
    // the four corners of the panel are on a screen. So the panel goes across an edge that two screens share,
    // and it stops at an edge that has no screen behind it.
    function dragPlace(list, gx, gy, w, h) {
        function shown(px, py) {
            for (var i = 0; i < list.length; i++)
                if (px >= list[i].x && px < list[i].x + list[i].width
                        && py >= list[i].y && py < list[i].y + list[i].height)
                    return true
            return false
        }
        function fits(x, y) {
            return shown(x, y) && shown(x + w - 1, y) && shown(x, y + h - 1) && shown(x + w - 1, y + h - 1)
        }
        if (list.length === 0 || fits(gx, gy))
            return {x: gx, y: gy}
        var best = null
        var bestGap = 0
        for (var i = 0; i < list.length; i++) {
            // Inside this screen in one direction (the panel can then be on two screens), or in both.
            var cx = Math.min(Math.max(list[i].x, gx), list[i].x + Math.max(0, list[i].width - w))
            var cy = Math.min(Math.max(list[i].y, gy), list[i].y + Math.max(0, list[i].height - h))
            var tries = [[gx, cy], [cx, gy], [cx, cy]]
            for (var k = 0; k < 3; k++) {
                var gap = Math.abs(tries[k][0] - gx) + Math.abs(tries[k][1] - gy)
                if ((k === 2 || fits(tries[k][0], tries[k][1])) && (best === null || gap < bestGap)) {
                    best = tries[k]
                    bestGap = gap
                }
            }
        }
        return {x: best[0], y: best[1]}
    }

    // The place on the screen `to` for a panel at (x, y) of the screen `from`: the same distance to the nearer
    // side edge and to the nearer of the top and bottom edges.
    function carried(from, to, x, y, w, h) {
        return {x: x + w / 2 > from.width / 2 ? to.width - (from.width - x) : x,
                y: y + h / 2 > from.height / 2 ? to.height - (from.height - y) : y}
    }

    // Put the panel on the screen `target` (one of screens()) at (x, y) of it, kept on that screen.
    // A layer surface gets its output when it is made, from the screen of the window. So for a different
    // output: hide the window, change its screen, show it again.
    function rehome(target, x, y) {
        var real = null
        var list = Qt.application.screens
        for (var i = 0; i < list.length; i++)
            if (list[i].name === target.name)
                real = list[i]
        var rebind = real !== null && surfaceScreen !== target.name
        var shown = visible
        if (rebind)
            visible = false
        screenName = target.name
        posX = x
        posY = y
        clampPosition()
        if (rebind) {
            screen = real
            // Qt takes the screen of a new surface from the place of the window.
            root.x = target.x + posX
            root.y = target.y + posY
            surfaceScreen = target.name
            visible = shown
        }
    }

    // The end of a drag: the panel belongs to the screen that holds its centre.
    function settle() {
        var to = screenAt(screens(), home.x + posX + width / 2, home.y + posY + height / 2) || home
        rehome(to, home.x + posX - to.x, home.y + posY - to.y)
        backend.savePosition(posX, posY, screenName)
    }

    // The tray entry: the panel goes to the next screen of the list, to the same place from the nearer edges.
    function moveToNextScreen() {
        var list = screens()
        if (list.length < 2)
            return
        var index = 0
        for (var i = 0; i < list.length; i++)
            if (list[i].name === home.name)
                index = i
        var to = list[(index + 1) % list.length]
        var place = carried(home, to, posX, posY, width, height)
        rehome(to, place.x, place.y)
        // A panel at its default corner has no place of its own: with a saved place it would not be at the
        // default corner at the next start, and would not follow the width of the screen any more.
        if (atDefault)
            backend.saveScreen(screenName)
        else
            backend.savePosition(posX, posY, screenName)
    }

    // After a change of the screens. When the monitor of the panel is gone, the panel goes to the screen that
    // the window has now, and it shows again when the compositor closed it. The saved place stays: the panel
    // is on its monitor again at the next start with that monitor.
    function recover() {
        if (screenName !== "" && screenNamed(screenName) === null) {
            var to = screenNamed(Screen.name) || screens()[0]
            if (to) {
                surfaceScreen = ""
                rehome(to, posX, posY)
            }
        }
        if (closedByCompositor) {
            closedByCompositor = false
            visible = true
        }
    }

    // The first item at (x, y) of `item`, from the outside in, whose hitRole is one of `roles`: "status" (a
    // status row, with stateName), "agent" (an agent row, with key) or "scroll" (a list that scrolls).
    function hitAt(item, x, y, roles) {
        var child = item.childAt(x, y)
        while (child) {
            if (roles.indexOf(child.hitRole) >= 0)
                return child
            var point = child.mapFromItem(item, x, y)
            item = child
            x = point.x
            y = point.y
            child = item.childAt(x, y)
        }
        return null
    }

    // The window has the size of the skin. Without a skin it keeps its size. The width and the height change
    // together: one new size for the layer surface.
    function takeSize() {
        if (skin && (width !== skin.implicitWidth || height !== skin.implicitHeight))
            setGeometry(x, y, skin.implicitWidth, skin.implicitHeight)
    }

    // The place at the start, when the size of the panel is known.
    function start() {
        surfaceScreen = Screen.name
        // The saved screen. A file with no screen name, or a screen that is not there: the screen of the window.
        var saved = backend.savedScreen === "" ? null : screenNamed(backend.savedScreen)
        screenName = saved ? saved.name : Screen.name
        var valid = (saved !== null || backend.savedScreen === "")
            && backend.savedX >= 0 && backend.savedY >= 0
            && backend.savedX <= home.width - width
            && backend.savedY <= home.height - height
        atDefault = !valid
        rehome(home, valid ? backend.savedX : 0, valid ? backend.savedY : 0)
        started = true
        visible = true
    }

    Component.onCompleted: skinLoader.load()
    onSkinChanged: {
        takeSize()
        if (skin && !started)
            start()
    }
    onWidthChanged: clampPosition()
    onHeightChanged: clampPosition()
    // Not while the screen of the panel is gone: recover() then gives the panel a screen.
    onHomeChanged: if (screenNamed(screenName) !== null) clampPosition()
    onScreenSourceChanged: recoverTimer.restart()
    // Only the compositor closes the window (the tray hides it): the monitor of the surface went away.
    onClosing: {
        closedByCompositor = true
        recoverTimer.restart()
    }

    // After the screens change, Qt needs a moment to give the window its new screen.
    Timer {
        id: recoverTimer
        interval: 200
        onTriggered: root.recover()
    }

    PanelModel {
        id: panelModel
    }

    // The layout: only drawing. It reads panelModel, and this window finds its rows by their hitRole.
    Loader {
        id: skinLoader
        // The skin of the layout of the backend, with the controller as its `panel`.
        function load() {
            panelModel.hoverItem = null
            setSource(backend.skinSource, {panel: panelModel})
        }
        // Later: this handler runs inside setSource(), and the backend then asks for the default skin.
        onStatusChanged: if (status === Loader.Error) Qt.callLater(function() { backend.skinFailed() })
    }

    Connections {
        target: root.skin
        function onImplicitWidthChanged() { root.takeSize() }
        function onImplicitHeightChanged() { root.takeSize() }
    }

    Connections {
        target: backend
        function onLayoutChanged() { skinLoader.load() }
    }

    // The one pointer handler of the panel. A press that moves 6 px or more drags the widget.
    // A press that moves less is a click on the row under it: a status row opens, an agent row jumps.
    MouseArea {
        id: pointerArea
        anchors.fill: parent
        hoverEnabled: true
        property real startX: 0
        property real startY: 0
        property bool moved: false
        // Time of the last margin change. At most one change in each step (minMoveMs), so that a pointer
        // event that comes before the compositor applies the last margin does not count the motion twice.
        // A dropped event loses nothing: the next one uses the absolute pointer position again.
        property double lastMoveMs: 0
        // The row or the list of the skin under the pointer.
        function under(point, roles) {
            return root.skin ? root.hitAt(root.skin, point.x, point.y, roles) : null
        }
        // lastMoveMs starts again at each press: a clock that went back must not block the drag.
        onPressed: (mouse) => { startX = mouse.x; startY = mouse.y; moved = false; lastMoveMs = 0 }
        onPositionChanged: (mouse) => {
            if (!pressed) {
                root.panel.hoverItem = under(mouse, ["status", "agent"])
                return
            }
            var dx = mouse.x - startX
            var dy = mouse.y - startY
            if (!moved && Math.abs(dx) + Math.abs(dy) < 6)
                return
            moved = true
            root.panel.hoverItem = null
            var now = Date.now()
            if (now - lastMoveMs < root.minMoveMs)
                return
            lastMoveMs = now
            root.atDefault = false
            // The panel follows the pointer on all the screens. The surface stays on its output until the release.
            var place = root.dragPlace(root.screens(), root.home.x + root.posX + dx, root.home.y + root.posY + dy,
                                       root.width, root.height)
            root.posX = place.x - root.home.x
            root.posY = place.y - root.home.y
        }
        onReleased: (mouse) => {
            if (moved) {
                moved = false
                root.settle()
                return
            }
            var row = under(mouse, ["status", "agent"])
            if (row && row.hitRole === "status")
                root.panel.toggle(row.stateName)
            else if (row)
                root.panel.jump(row.key)
        }
        onExited: root.panel.hoverItem = null
        onWheel: (wheel) => {
            var list = under(wheel, ["scroll"])
            if (list)
                list.scrollBy(wheel.pixelDelta.y, wheel.angleDelta.y)
        }
    }
}
