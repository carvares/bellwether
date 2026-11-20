// The floating panel, the same for every window shell: its place and its screen, the drag, and the one pointer
// handler. The state and the rules are in PanelModel.qml. The drawing is a skin (skins/<letter>.qml) that the
// Loader below shows: the layout of the backend. The scale of the custom look is applied here, one time, for
// every skin: the skin is drawn larger or smaller, and the window has that size. The skin contract is in the spec
// (docs/superpowers/specs/2026-11-18-bellwether-design.md, "options window and layout skins").
//
// Nothing here names a window system. A shell (shells/Layer.qml, shells/Plain.qml) is this panel with the window
// properties of its system, and it gives showOn(): how the window goes to a screen and to the place of the panel.
// The program loads one shell; its root object is the panel window.
import QtQuick
import QtQuick.Window

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
    // The name of the screen that holds the panel: the window is on this screen. "" until the start is complete.
    property string screenName: ""
    // The name of the screen that the shell put the window on (showOn). A layer surface gets its output when it
    // is made.
    property string surfaceScreen: ""
    // The screens of the desktop. Each has name, virtualX, virtualY, width and height. A test gives its own list.
    property var screenSource: Qt.application.screens
    // The screen that holds the panel as {name, x, y, width, height}, with x and y in the whole desktop.
    // The screen of the window while the named screen is not there.
    readonly property var home: screenNamed(screenName)
        || ({name: Screen.name, x: Screen.virtualX, y: Screen.virtualY, width: Screen.width, height: Screen.height})
    // The parts of each screen that the system keeps for itself (the macOS menu bar and Dock, the panels of an X11
    // desktop): screen name → {left, top, right, bottom} in pixels. The program sets it for the plain shell from the
    // available geometry of each screen; empty (the layer shell: the compositor keeps its panels free itself): none.
    property var reserved: ({})
    // True from the time the system closes the window (the compositor closes a layer surface when its monitor went
    // away) until the panel shows again.
    property bool closedByCompositor: false
    // True until the user moves the widget: it then stays at the top-right corner when its size changes.
    property bool atDefault: false
    // The refresh rate of the screen of the window, in Hz. The program sets it (QML does not have it). 0: unknown.
    property real refreshRate: 0
    // The shortest time between two moves of a drag: two frames of the screen, from 4 ms to 20 ms. A new place
    // can reach the screen one frame late (a margin of a layer surface goes to the compositor with the next
    // commit, and Qt holds that commit until the frame before it is on the screen). So a pointer event can come
    // one frame after a move and still be relative to the old place.
    readonly property real minMoveMs: refreshRate > 0 ? Math.min(20, Math.max(4, 2000 / refreshRate)) : 16
    readonly property int edge: 16
    // The scale of the custom look: the skin is drawn this many times larger (0.75 to 2). The window, its place
    // and the pointer are in pixels of the screen; the skin has its own pixels (the pixels of the design).
    readonly property real panelScale: backend.scale
    // True when the window system, not the panel, decides where the window is (a shell sets it: a plain window on
    // Wayland). A drag is then a move of the window system, and the panel does not change or save its place.
    property bool windowSystemPlaces: false
    // True from the ask for such a move until the button is up again.
    property bool systemMove: false

    // A window must not have the size 0 (a layer surface cannot): the window shows when it has the size of its
    // first skin.
    visible: false
    color: "transparent"

    // Keep the panel on its screen. During a drag the panel can be on two screens, so the drag does this itself.
    function clampPosition() {
        if (dragging())
            return
        var place = clampedPlace(width, height)
        posX = place.x
        posY = place.y
    }

    // The part of the screen `target` (one of screens()) that the panel may use, from its top-left corner: the
    // screen less what the system keeps for itself (`reserved`).
    function workArea(target) {
        var r = reserved[target.name] || {}
        var left = r.left || 0
        var top = r.top || 0
        return {x: left, y: top, width: target.width - left - (r.right || 0),
                height: target.height - top - (r.bottom || 0)}
    }

    // The place of a panel of w × h on its screen: the default corner when the panel has no place of its own, and
    // kept in the work area of the screen.
    function clampedPlace(w, h) {
        var a = workArea(home)
        var px = atDefault ? a.x + a.width - w - edge : posX
        var py = atDefault ? a.y + edge : posY
        return {x: Math.min(Math.max(a.x, px), Math.max(a.x, a.x + a.width - w)),
                y: Math.min(Math.max(a.y, py), Math.max(a.y, a.y + a.height - h))}
    }

    // True while a drag moves the panel: it can then be on two screens, and nothing pulls it back to its own.
    function dragging() {
        return pointerArea.pressed && pointerArea.moved
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

    // Put the panel on the screen `target` (one of screens()) at (x, y) of it, kept on that screen. The shell
    // does it (showOn), with the real screen when the window must go to a different one.
    function rehome(target, x, y) {
        var real = null
        var list = Qt.application.screens
        for (var i = 0; i < list.length; i++)
            if (list[i].name === target.name)
                real = list[i]
        showOn(target, x, y, real !== null && surfaceScreen !== target.name ? real : null)
    }

    // The place of the panel: the screen `target` and (x, y) of it, kept on that screen. Only the shell calls
    // this, from its showOn().
    function setPlace(target, x, y) {
        screenName = target.name
        posX = x
        posY = y
        clampPosition()
    }

    // The shell puts the panel on the screen `target` at (x, y) of it: setPlace(target, x, y), and, when `real`
    // (a screen of Qt) is not null, it moves the window to that screen and sets surfaceScreen. Each shell gives
    // its own showOn(). This one only sets the place: no shell, no window system.
    function showOn(target, x, y, real) {
        setPlace(target, x, y)
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
    // status row, with stateName), "agent" (an agent row, with key), "answer" (the answer control of an agent row,
    // with key) or "scroll" (a list that scrolls). An agent row can hold a target of its own: the search goes on
    // inside the row, and the row is the answer when nothing in it is one.
    function hitAt(item, x, y, roles) {
        var row = null
        var child = item.childAt(x, y)
        while (child) {
            if (roles.indexOf(child.hitRole) >= 0) {
                if (child.hitRole !== "agent")
                    return child
                row = child
            }
            var point = child.mapFromItem(item, x, y)
            item = child
            x = point.x
            y = point.y
            child = item.childAt(x, y)
        }
        return row
    }

    // A length of the skin in pixels of the screen: the next whole pixel. (0.000001: 320 × 1.1 is not 353.)
    function scaled(length) {
        return Math.ceil(length * panelScale - 0.000001)
    }

    // The window has the size of the skin at the scale. Without a skin, and while a skin reports no size, it
    // keeps its size: a layer surface must never get the size 0. The width and the height change together: one
    // new size for the window (and its top-left corner stays).
    // A panel that would be taller than its screen does not get that size while its list can show fewer rows:
    // fitRows() takes rows away before the next frame, and the skin then has a size that fits.
    function takeSize() {
        if (!skin || skin.implicitWidth <= 0 || skin.implicitHeight <= 0)
            return
        var w = scaled(skin.implicitWidth)
        var h = scaled(skin.implicitHeight)
        if (h > workArea(home).height && panelModel.shown > 1 && panelModel.rowHeight > 0) {
            requestUpdate()  // a frame, so that fitRows() runs
            return
        }
        if (width !== w || height !== h)
            applySize(w, h)
    }

    // The window gets the size w × h. A shell that places its window gives its own applySize() (one request for the
    // size and the place).
    function applySize(w, h) {
        setGeometry(x, y, w, h)
    }

    // The size of a skin can change two times and more in one step (one list closes and a different list opens;
    // a new font changes many heights). So a new size of the skin calls takeSize() after the step, one time, and
    // a size on the way never reaches the window.
    function sizeLater() {
        Qt.callLater(takeSize)
    }

    // The one rule for a panel that would be taller than its screen (a long group at a large scale): the lists
    // show only the rows that fit (panel.rowRoom, from 1 to panel.rowLimit), and the group scrolls. The rows that
    // fit are the height of the screen less the height of the skin without its rows, divided by the height of a
    // row. It runs before each frame (onAfterAnimating): the items of the skin then have their final places, so
    // the height of the skin and the number of rows belong together. The same rule gives the rows back when
    // they have room again (a smaller scale, a taller screen), and when no group is open.
    function fitRows() {
        var rows = panelModel.shown
        if (rows === 0) {
            // No list shows rows: nothing is held back. The next open starts with all rows, and takeSize()
            // waits for this rule when they do not fit. (A low number that stays here gives the next open two
            // sizes: the low number of rows first, all rows one frame later.)
            panelModel.rowRoom = panelModel.rowLimit
            return
        }
        if (!skin || panelModel.rowHeight <= 0)
            return
        var rest = skin.implicitHeight - rows * panelModel.rowHeight
        var fit = Math.floor((workArea(home).height / panelScale - rest) / panelModel.rowHeight + 0.000001)
        panelModel.rowRoom = Math.max(1, Math.min(panelModel.rowLimit, fit))
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
    onHomeChanged: {
        if (screenNamed(screenName) !== null)
            clampPosition()
        takeSize()
    }
    onPanelScaleChanged: takeSize()
    // The system keeps a different part of a screen (the Dock moved, a panel of the desktop grew).
    onReservedChanged: {
        if (started && screenNamed(screenName) !== null)
            clampPosition()
        takeSize()
    }
    onAfterAnimating: fitRows()
    onScreenSourceChanged: recoverTimer.restart()
    // Only the system closes the window (the tray hides it): with the layer shell, the monitor of the surface went
    // away.
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
        // The scale of the custom look, from the top-left corner: the place of the panel stays its top-left corner.
        transform: Scale { xScale: root.panelScale; yScale: root.panelScale }
        // The skin of the layout of the backend, with the controller as its `panel`.
        function load() {
            panelModel.hoverItem = null
            setSource(backend.skinSource, {panel: panelModel})
        }
        // Later: this handler runs inside setSource(), and the backend then asks for the default skin.
        onStatusChanged: if (status === Loader.Error) Qt.callLater(function() { backend.skinFailed("Loader.Error") })
    }

    Connections {
        target: root.skin
        function onImplicitWidthChanged() { root.sizeLater() }
        function onImplicitHeightChanged() { root.sizeLater() }
    }

    Connections {
        target: backend
        function onLayoutChanged() { skinLoader.load() }
    }

    // The one pointer handler of the panel. A press that moves 6 px or more drags the widget.
    // A press that moves less is a click on the target under it: a status row opens, an agent row jumps, and the
    // answer control of a row opens the answer window (and the row does not jump).
    // The pointer is in pixels of the screen at every scale: the 6 px, and the panel moves as far as the pointer.
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
        // The row or the list of the skin under the pointer. The skin has its own pixels: the scale is in the map.
        function under(point, roles) {
            if (!root.skin)
                return null
            var place = root.skin.mapFromItem(pointerArea, point.x, point.y)
            return root.hitAt(root.skin, place.x, place.y, roles)
        }
        // lastMoveMs starts again at each press: a clock that went back must not block the drag.
        onPressed: (mouse) => { startX = mouse.x; startY = mouse.y; moved = false; lastMoveMs = 0 }
        onPositionChanged: (mouse) => {
            if (!pressed) {
                root.panel.hover(under(mouse, ["status", "answer", "agent"]))
                return
            }
            var dx = mouse.x - startX
            var dy = mouse.y - startY
            if (!moved && Math.abs(dx) + Math.abs(dy) < 6)
                return
            moved = true
            root.panel.hoverItem = null
            if (root.windowSystemPlaces) {
                if (!root.systemMove) {
                    root.systemMove = true
                    root.startSystemMove()  // false when the window system cannot: the panel then stays
                }
                return
            }
            var now = Date.now()
            if (now - lastMoveMs < root.minMoveMs)
                return
            lastMoveMs = now
            root.atDefault = false
            // The panel follows the pointer on all the screens. The window stays on its screen until the release.
            var place = root.dragPlace(root.screens(), root.home.x + root.posX + dx, root.home.y + root.posY + dy,
                                       root.width, root.height)
            root.posX = place.x - root.home.x
            root.posY = place.y - root.home.y
        }
        onReleased: (mouse) => {
            if (moved) {
                moved = false
                if (root.windowSystemPlaces)
                    root.systemMove = false
                else
                    root.settle()
                return
            }
            var row = under(mouse, ["status", "answer", "agent"])
            if (row && row.hitRole === "status")
                root.panel.toggle(row.stateName)
            else if (row && row.hitRole === "answer")
                root.panel.answer(row.key)
            else if (row)
                root.panel.jump(row.key)
        }
        onExited: root.panel.hoverItem = null
        // The window system took the pointer (a move of the window system): the button is up for this handler.
        onCanceled: { moved = false; root.systemMove = false }
        onWheel: (wheel) => {
            var list = under(wheel, ["scroll"])
            if (list)
                list.scrollBy(wheel.pixelDelta.y, wheel.angleDelta.y)
        }
    }
}
