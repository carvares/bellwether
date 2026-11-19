// The answer window: the question of one blocked agent, with one button for each option. The "Answer" control of an
// agent row opens it (bellwether/answer.py); it is one window, and it changes to a different agent when that one is
// asked for. A normal window (an xdg toplevel, not a layer surface) with no title bar of the system: it draws its
// frame and header in the style of the layout that shows (the theme tokens of that skin), like the options window,
// and it takes the keyboard. It shows `backend.prompt` and calls the slots of the backend; it keeps no copy of a
// question or of a screen, it logs nothing, and it never sends anything by itself: one click or one key of the
// person is one answer. Every text of a prompt is plain text. The states and the messages are those of the engine
// (docs/superpowers/specs/2026-11-19-bellwether-unblock-agents-design.md).
import QtQuick
import QtQuick.Window
import "skins" as Skins
import "controls" as Controls

Window {
    id: answer

    // The open prompt of the backend: every key is always there. Read again at each change; never copied.
    readonly property var prompt: backend.prompt
    // The state of the engine: "loading", "ready", "unreadable", "gone", "answering", "pending", "sent", "failed".
    readonly property string phase: prompt.state
    // The theme tokens of the layout that shows. The tokens of Layout C while a theme file loads or is missing.
    readonly property QtObject theme: themeLoader.item ? themeLoader.item : fallbackTheme
    readonly property int pad: 20
    readonly property int headerHeight: 44
    readonly property int controlHeight: theme.fit(28)
    readonly property int footerHeight: controlHeight + 24
    readonly property int fixedWidth: 600
    // The height of the screen of the window. A test gives its own.
    property int roomHeight: Screen.height
    // The height follows the content, from 220 px to the height of the screen less 80 px. A longer content scrolls
    // between the header and the footer; a long detail scrolls inside its own view first.
    readonly property int wantedHeight: headerHeight + content.height + footerHeight
    readonly property int fixedHeight: Math.max(220, Math.min(wantedHeight, roomHeight - 80))
    // A plate and inks that can be read with any colours of the custom look (as in the options window).
    readonly property color safePlate: theme.solid(theme.panelColor)
    readonly property color safeInk: theme.readable(theme.textColor, safePlate)
    readonly property color closeInk: theme.readable(theme.dimColor, safePlate)
    // The colour of what needs care: an option that approves more than one thing, and the notes. It is the colour
    // of the status "blocked" of the custom look, or the ink when that cannot be told from the panel.
    readonly property color warnColor: theme.readable(backend.stateColors.blocked, safePlate)

    // ----- what shows -----

    readonly property bool hasQuestion: prompt.options.length > 0
    readonly property bool blind: phase === "ready" && prompt.blind
    // The message of a text that was refused shows at the text field, not at the top.
    readonly property bool fieldNote: phase === "ready" && ["text_empty", "text_long", "text_lines", "text_control"]
                                                               .indexOf(prompt.reason) >= 0
    readonly property string note: fieldNote ? "" : prompt.message
    // The state in a word, in the header, when it is not "ready with a question".
    readonly property string stateWord: phase === "loading" ? "Reading…" : phase === "answering" ? "Sending…"
        : phase === "pending" ? "Not confirmed" : phase === "sent" ? "Sent" : phase === "failed" ? "Failed"
        : phase === "gone" ? "Not blocked" : phase === "unreadable" ? "Not readable" : blind ? "Partly visible" : ""
    // "Open in Herdr" is the main action when the window cannot answer.
    readonly property bool herdrFirst: blind || ["unreadable", "pending", "failed", "gone"].indexOf(phase) >= 0
    // The text option of the question (the field), or null.
    readonly property var textOption: {
        for (var i = 0; i < prompt.options.length; i++)
            if (prompt.options[i].kind === "text")
                return prompt.options[i]
        return null
    }

    // ----- the guards after a new question -----

    // A question that takes the place of an other one in the open window could get the second click of a person
    // who clicks two times on the same place, or the next keys of a person who types. So each time a question shows,
    // and each time the window comes into a state where it can answer (also the same question again):
    // - the pointer answers only after `guardMs` with no press of a key or of the pointer (400 ms: the double-click
    //   time of KDE, so the second click of a double click never answers);
    // - a number key answers only after `keyQuietMs` with no key press (1000 ms: a person who types presses a key
    //   each 0.1 to 0.3 s, so 1 s with no key means that the typing has stopped).
    // Each press of a key or of the pointer starts a guard that is not over again.
    // The number keys follow one rule more. At each change of the question that shows (not at the first question
    // after the window opens), they are locked, except when all of these are true: the new question is the next
    // question after an answer of the person sent from this window (the engine went from "answering" or "pending"
    // to "ready" with a new question, and says nothing of it but "held"), the window is active at the change, and
    // no key was pressed in the window since that answer went. A lock ends only by a press of the pointer in the
    // window or by Tab or Shift+Tab: never by an other change, a change of the state, of the keyboard or of the
    // activation. A close ends it too (the next open starts as an open). The engine has its own rules; these are of
    // the window.
    property int guardMs: 400
    property int keyQuietMs: 1000
    readonly property bool answerable: phase === "ready" && hasQuestion
    // The number of the question for which each guard is over (0: none).
    property int pointerPassed: 0
    property int keysPassed: 0
    readonly property bool armed: answerable && shown !== 0 && pointerPassed === shown
    readonly property bool keysArmed: armed && keysPassed === shown
    property bool digitsLocked: false
    // An answer of the person went from this window for the question with the number `answeredShown`, and no key
    // was pressed in the window since (bellwether/answer.py sets it to false at each key press, before any item of
    // the window gets the key).
    property bool answerSent: false
    property int answeredShown: 0
    // The question took the place of an other question of the same agent while the window was open, and how many
    // questions showed since the window opened.
    property bool fresh: false
    property int questionCount: 0
    // The text field of the question (it is inside the list of the options), or null.
    property Item entryItem: null
    // The program hides and shows the window to bring it to the front: that is not a close.
    property bool raising: false
    property int lastShown: 0
    property string lastKey: ""
    readonly property int shown: prompt.shown
    onShownChanged: {
        if (shown === 0)
            return
        fresh = lastShown !== 0 && lastKey === prompt.key
        questionCount = fresh ? questionCount + 1 : 1
        // The values of the prompt itself, not of the bindings of the window: they are of this change.
        var next = answerSent && prompt.state === "ready"
                   && (prompt.reason === "" || prompt.reason === "held") && answer.active
        digitsLocked = fresh && (digitsLocked || !next)
        answerSent = false
        lastShown = shown
        lastKey = prompt.key
        startGuard()
        // The new detail shows from its first line (else a new command could show at the end of the one before,
        // and be seen to its end with no scroll), and the content from its top. Nothing is reported seen before
        // the guard that starts here is over.
        if (detailView)
            detailView.toEnd(false)
        scroller.contentY = 0
        if (fresh)
            changeFlash.restart()
        // Nothing of the question before stays: no text in the field, and no option has the keyboard.
        if (entryItem)
            entryItem.text = ""
        frame.forceActiveFocus()
    }
    // An answer that ended in an other way than the next question (failed, sent, gone, closed, or ready again
    // with the same question): no next question comes from it. A change of the question while the answer is on
    // its way also ends it (above), so `answerSent` is always of the question just before the change.
    onPhaseChanged: {
        if (phase !== "answering" && phase !== "pending" && !(phase === "ready" && prompt.shown !== answeredShown))
            answerSent = false
    }
    onAnswerableChanged: if (answerable) startGuard()
    onArmedChanged: Qt.callLater(reportSeen)

    function startGuard() {
        pointerPassed = 0
        keysPassed = 0
        pointerTimer.restart()
        keyTimer.restart()
    }
    // A press of a key (`isKey`) or of the pointer: a guard that is not over starts again. A press of the pointer
    // in the window also ends a lock of the number keys.
    function notePress(isKey) {
        if (!isKey)
            unlockDigits()
        if (pointerPassed !== shown)
            pointerTimer.restart()
        if (keysPassed !== shown)
            keyTimer.restart()
    }
    // The end of a lock of the number keys (a press of the pointer, Tab): they answer after their quiet time again.
    function unlockDigits() {
        if (!digitsLocked)
            return
        digitsLocked = false
        keysPassed = 0
        keyTimer.restart()
    }
    Timer {
        id: pointerTimer
        interval: answer.guardMs
        onTriggered: answer.pointerPassed = backend.prompt.shown
    }
    Timer {
        id: keyTimer
        interval: answer.keyQuietMs
        onTriggered: answer.keysPassed = backend.prompt.shown
    }

    // ----- the end of the detail -----

    // An option that approves needs the end of the detail seen (the engine refuses it before). The window tells the
    // engine when the last line of the detail was in view after the guard of the question: at once when the whole
    // detail is in view, or when the person scrolls to its end. The values are read from the backend, not from the
    // bindings of the window, so that a report never goes for a question that the window does not show yet.
    readonly property Item detailView: detailLoader.item
    // The last line of the detail is in its view, and its view is in the window (the content of the window can
    // scroll too, on a low screen).
    readonly property bool detailAtEnd: detailView === null || (detailView.atEnd
        && column.y + detailLoader.y + detailLoader.height <= scroller.contentY + scroller.height + 1)
    readonly property bool hasAccept: {
        for (var i = 0; i < prompt.options.length; i++)
            if (prompt.options[i].effect === "accept")
                return true
        return false
    }
    // An option that approves is off because the end of the detail was not in view: in its own view, or in the
    // window (on a low screen the content of the window scrolls too). The line below the detail and the footer
    // say so, so that an option is never off with no reason in view.
    readonly property string scrollNote: "Scroll to the end of the text above to approve."
    readonly property bool waitsForEnd: answerable && !blind && hasAccept && !prompt.seen && detailView !== null
                                        && !detailAtEnd
    // Later, not inside the change: the report changes the prompt, and the prompt the place of the detail.
    onDetailAtEndChanged: Qt.callLater(reportSeen)
    function reportSeen() {
        var current = backend.prompt
        if (current.state === "ready" && current.shown !== 0 && current.shown === pointerPassed && !current.seen
                && detailAtEnd)
            backend.detailSeen(current.shown)
    }

    // ----- actions: each is one act of the person -----

    // Press one option (`how`: "pointer" for a click or the key of an option that has the keyboard, "digit" for a
    // number key). Only while the prompt is ready, the option is allowed, and the guards have passed.
    function choose(key, how) {
        if (phase !== "ready" || !armed || (how === "digit" && (!keysArmed || digitsLocked)))
            return false
        for (var i = 0; i < prompt.options.length; i++) {
            var option = prompt.options[i]
            if (option.key === key && option.allowed && option.kind !== "text")
                return sent(backend.answer(key))
        }
        return false
    }

    // Send the text of the field. The engine checks it; its message shows at the field when it refuses.
    function sendText() {
        if (phase !== "ready" || !armed || !prompt.freeText || !entryItem)
            return false
        return sent(backend.answerText(entryItem.text))
    }

    // The engine took an answer of the person (`started`) for the question that shows.
    function sent(started) {
        if (started) {
            answerSent = true
            answeredShown = shown
        }
        return started
    }

    // Show the agent in Herdr (the jump of the panel), and close this window when the jump starts.
    function openInHerdr() {
        if (backend.opening !== "" || prompt.key === "")
            return
        backend.focus(prompt.key)
        answer.close()
    }

    // A digit presses the option with that key. The digit of the text option puts the keyboard in the field.
    function digit(key) {
        if (!keysArmed || digitsLocked)
            return
        if (textOption && textOption.key === key && prompt.freeText && entryItem) {
            entryItem.take()
            return
        }
        choose(key, "digit")
    }

    title: "Bellwether — Answer"
    flags: Qt.Window | Qt.FramelessWindowHint
    color: "transparent"
    width: fixedWidth
    height: fixedHeight
    minimumWidth: fixedWidth
    maximumWidth: fixedWidth
    minimumHeight: fixedHeight
    maximumHeight: fixedHeight

    // A window that is not on the screen has no open prompt: every way to close it (Esc, the close control, the
    // compositor, "Open in Herdr", the end of the engine) closes the prompt, and the question is dropped.
    onVisibleChanged: {
        if (visible) {
            scroller.contentY = 0
            frame.forceActiveFocus()  // no option has the keyboard: Enter presses nothing
        } else if (!raising) {
            lastShown = 0
            lastKey = ""
            fresh = false
            digitsLocked = false
            answerSent = false
            backend.closePrompt()
        }
    }
    onActiveFocusItemChanged: scroller.reveal(activeFocusItem)

    Connections {
        target: backend
        // The engine closed the prompt (a moment after the answer was sent): the window goes away.
        function onPromptChanged() {
            if (backend.prompt.state === "closed" && answer.visible)
                answer.close()
        }
    }

    Shortcut {
        sequences: [StandardKey.Cancel]
        onActivated: answer.close()
    }

    Skins.CTheme { id: fallbackTheme }
    Loader {
        id: themeLoader
        source: backend.themeSource
    }

    Rectangle {
        id: frame
        readonly property bool isFrame: true
        anchors.fill: parent
        radius: answer.theme.radius
        color: answer.theme.panelColor
        border.width: answer.theme.frameWidth
        border.color: answer.theme.frameColor
        focus: true
        // The keys of the window, when the text field does not have the keyboard (it takes its keys itself). Each key
        // counts for the guards. Tab turns the number keys on again (and moves the keyboard on).
        Keys.onPressed: (event) => {
            answer.notePress(true)
            var plain = (event.modifiers & ~Qt.KeypadModifier) === Qt.NoModifier
            var view = detailLoader.item ? detailLoader.item : screenLoader.item
            if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
                answer.unlockDigits()
            } else if (plain && event.key >= Qt.Key_1 && event.key <= Qt.Key_9) {
                answer.digit(String(event.key - Qt.Key_0))
                event.accepted = true
            } else if (plain && view && (event.key === Qt.Key_PageDown || event.key === Qt.Key_PageUp)) {
                view.page(event.key === Qt.Key_PageDown)
                event.accepted = true
            } else if (plain && view && (event.key === Qt.Key_End || event.key === Qt.Key_Home)) {
                view.toEnd(event.key === Qt.Key_End)
                event.accepted = true
            }
        }

        Loader {
            anchors.fill: parent
            sourceComponent: answer.theme.decoration
        }

        // The header: the program icon, the agent, its address, and the state. A press that moves 6 px or more
        // moves the window (the compositor moves it).
        Item {
            id: header
            readonly property bool isHeader: true
            width: parent.width
            height: answer.headerHeight

            MouseArea {
                anchors.fill: parent
                property real startX: 0
                property real startY: 0
                property bool moving: false
                onPressed: (mouse) => { startX = mouse.x; startY = mouse.y; moving = false }
                onPositionChanged: (mouse) => {
                    if (!pressed || moving || Math.abs(mouse.x - startX) + Math.abs(mouse.y - startY) < 6)
                        return
                    moving = true
                    answer.startSystemMove()
                }
            }
            Image {
                id: programIcon
                readonly property bool isProgramIcon: true
                visible: answer.prompt.icon !== "" && status !== Image.Error
                x: answer.pad
                width: 16
                height: 16
                anchors.verticalCenter: parent.verticalCenter
                sourceSize: Qt.size(32, 32)
                source: answer.prompt.icon
            }
            Text {
                id: agentLabel
                readonly property bool isAgentLabel: true
                x: programIcon.visible ? answer.pad + 24 : answer.pad
                width: Math.min(implicitWidth, stateText.x - 12 - x - (agentAddress.visible ? agentAddress.width + 8 : 0))
                anchors.verticalCenter: parent.verticalCenter
                elide: Text.ElideRight
                textFormat: Text.PlainText
                text: answer.prompt.label
                color: answer.theme.textColor
                font { family: answer.theme.fontFamily; pixelSize: answer.theme.titleSize; weight: Font.DemiBold }
            }
            Text {
                id: agentAddress
                readonly property bool isAgentAddress: true
                visible: text !== "" && text !== answer.prompt.label
                anchors.left: agentLabel.right
                anchors.leftMargin: 8
                anchors.baseline: agentLabel.baseline
                textFormat: Text.PlainText
                text: answer.prompt.address
                color: answer.theme.faintColor
                font { family: answer.theme.fontFamily; pixelSize: answer.theme.smallSize }
            }
            Text {
                id: stateText
                readonly property bool isStateWord: true
                x: parent.width - 48 - width
                anchors.verticalCenter: parent.verticalCenter
                textFormat: Text.PlainText
                text: answer.stateWord
                color: answer.herdrFirst && answer.phase !== "gone" ? answer.warnColor : answer.theme.dimColor
                font {
                    family: answer.theme.fontFamily; pixelSize: answer.theme.smallSize; weight: Font.DemiBold
                    letterSpacing: answer.theme.letterSpacing
                    capitalization: answer.theme.uppercaseTitles ? Font.AllUppercase : Font.MixedCase
                }
            }
            Rectangle {
                x: answer.theme.frameWidth
                anchors.bottom: parent.bottom
                width: parent.width - 2 * x
                height: 1
                color: answer.theme.lineColor
            }
        }

        // The content. It scrolls when it is taller than the window can be.
        Flickable {
            id: scroller
            readonly property bool isScroller: true
            readonly property bool scrolls: contentHeight > height + 0.5
            y: answer.headerHeight
            width: parent.width
            height: parent.height - answer.headerHeight - answer.footerHeight
            contentWidth: width
            contentHeight: content.height
            clip: true
            interactive: scrolls
            flickableDirection: Flickable.VerticalFlick
            boundsBehavior: Flickable.StopAtBounds
            onContentHeightChanged: contentY = Math.max(0, Math.min(contentY, contentHeight - height))
            onHeightChanged: contentY = Math.max(0, Math.min(contentY, contentHeight - height))

            function reveal(item) {
                if (!item || !scrolls)
                    return
                for (var parent = item; parent && parent !== content; parent = parent.parent) {}
                if (!parent)
                    return
                var top = item.mapToItem(content, 0, 0).y
                if (top - 12 < contentY)
                    contentY = Math.max(0, top - 12)
                else if (top + item.height + 12 > contentY + height)
                    contentY = Math.min(contentHeight - height, top + item.height + 12 - height)
            }

            WheelHandler {
                enabled: scroller.scrolls
                onWheel: (event) => {
                    var step = event.pixelDelta.y !== 0 ? -event.pixelDelta.y : -event.angleDelta.y / 2
                    scroller.contentY = Math.max(0, Math.min(scroller.contentY + step,
                                                             scroller.contentHeight - scroller.height))
                }
            }

            Item {
                id: content
                width: scroller.width
                height: column.height + 2 * 16

                // A short light over the content when a new question takes the place of the one before.
                Rectangle {
                    readonly property bool isChangeFlash: true
                    anchors.fill: parent
                    color: answer.theme.accentColor
                    opacity: 0
                    SequentialAnimation on opacity {
                        id: changeFlash
                        running: false
                        NumberAnimation { to: 0.22; duration: 120 }
                        NumberAnimation { to: 0; duration: 1100; easing.type: Easing.InQuad }
                    }
                }

                Column {
                    id: column
                    x: answer.pad
                    y: 16
                    width: parent.width - 2 * answer.pad
                    spacing: 10
                    // The height of everything in the column but the detail, with the spaces: the detail takes
                    // what the screen leaves free. The line "Scroll to the end …" shows only while the detail
                    // scrolls, so its room is kept whenever it can show (else the height of the detail would
                    // depend on itself).
                    readonly property real restHeight: {
                        var total = 0, shown = 0
                        for (var i = 0; i < children.length; i++) {
                            var child = children[i]
                            if (child.isSeenNote === true) {
                                if (answer.hasAccept && !answer.blind && detailLoader.active) {
                                    total += child.implicitHeight
                                    shown += 1
                                }
                                continue
                            }
                            if (child === detailLoader || !child.visible)
                                continue
                            total += child.height
                            shown += 1
                        }
                        return total + spacing * shown
                    }

                    // The note of the engine: why nothing can be sent, what was not sent, what to check.
                    Rectangle {
                        id: noteBox
                        readonly property bool isNote: true
                        // A plain "sent" and "not blocked" are calm; every other note needs the eye.
                        readonly property bool calm: answer.phase === "gone"
                                                     || (answer.phase === "sent" && answer.prompt.reason === "")
                        readonly property color tone: calm ? answer.theme.dimColor : answer.warnColor
                        visible: answer.note !== ""
                        width: parent.width
                        height: noteText.height + 16
                        radius: Math.min(answer.theme.itemRadius, 8)
                        color: Qt.rgba(tone.r, tone.g, tone.b, 0.12)

                        Rectangle { width: 3; height: parent.height; color: noteBox.tone }
                        Text {
                            id: noteText
                            readonly property bool isNoteText: true
                            x: 14
                            y: 8
                            width: parent.width - 26
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            text: answer.note
                            color: answer.theme.textColor
                            font { family: answer.theme.fontFamily; pixelSize: answer.theme.bodySize; weight: Font.Medium }
                        }
                    }

                    // While the screen is read: a quiet line in the place of the question.
                    Text {
                        readonly property bool isLoadingLine: true
                        visible: answer.phase === "loading"
                        width: parent.width
                        height: answer.theme.fit(60)
                        verticalAlignment: Text.AlignVCenter
                        textFormat: Text.PlainText
                        text: "Reading the screen of the agent…"
                        color: answer.theme.dimColor
                        font { family: answer.theme.fontFamily; pixelSize: answer.theme.bodySize }
                    }

                    // A question that took the place of the one before it, with its number since the window opened.
                    Text {
                        readonly property bool isNewMark: true
                        visible: answer.fresh && answer.hasQuestion
                        width: parent.width
                        textFormat: Text.PlainText
                        text: "New question (no. " + answer.questionCount + ")"
                        color: answer.theme.accentColor
                        font {
                            family: answer.theme.fontFamily; pixelSize: answer.theme.smallSize; weight: Font.DemiBold
                            letterSpacing: answer.theme.letterSpacing
                            capitalization: answer.theme.uppercaseTitles ? Font.AllUppercase : Font.MixedCase
                        }
                    }

                    // The number keys are locked after a change of the question (the rule above).
                    Text {
                        readonly property bool isDigitsOff: true
                        visible: answer.digitsLocked && answer.hasQuestion
                        width: parent.width
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        text: "New question — the number keys are off. Click in the window or press Tab to turn them on."
                        color: answer.warnColor
                        font { family: answer.theme.fontFamily; pixelSize: answer.theme.smallSize + 1; weight: Font.DemiBold }
                    }

                    // The title of the dialog and the lines below it (a file name, the purpose of a command).
                    Column {
                        visible: answer.prompt.title !== "" || answer.prompt.subtitle !== ""
                        width: parent.width
                        spacing: 2

                        Text {
                            readonly property bool isPromptTitle: true
                            visible: text !== ""
                            width: parent.width
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            text: answer.prompt.title
                            color: answer.theme.textColor
                            font { family: answer.theme.fontFamily; pixelSize: answer.theme.titleSize; weight: Font.DemiBold }
                        }
                        Text {
                            readonly property bool isPromptSubtitle: true
                            visible: text !== ""
                            width: parent.width
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            text: answer.prompt.subtitle
                            color: answer.theme.dimColor
                            font { family: answer.theme.fontFamily; pixelSize: answer.theme.smallSize + 1 }
                        }
                    }

                    // The detail: the command, the diff, the plan, line for line as on the screen of the agent.
                    Loader {
                        id: detailLoader
                        active: answer.prompt.detail.length > 0
                        visible: active
                        width: parent.width
                        sourceComponent: Controls.TextView {
                            readonly property bool isDetail: true
                            theme: answer.theme
                            lines: answer.prompt.detail
                            name: "What the agent asks for"
                            // The view takes all the height that the screen leaves free, and at least five lines.
                            maxHeight: Math.max(110, answer.roomHeight - 80 - answer.headerHeight - answer.footerHeight
                                                     - 32 - column.restHeight)
                        }
                    }
                    Text {
                        readonly property bool isCutNote: true
                        visible: answer.prompt.cut
                        width: parent.width
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        text: "This is only the lower part: the dialog is taller than the screen of the agent."
                        color: answer.warnColor
                        font { family: answer.theme.fontFamily; pixelSize: answer.theme.smallSize + 1 }
                    }

                    // The options that approve are off until the last line of the detail was in view.
                    Text {
                        readonly property bool isSeenNote: true
                        visible: answer.waitsForEnd
                        width: parent.width
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        text: answer.scrollNote
                        color: answer.warnColor
                        font { family: answer.theme.fontFamily; pixelSize: answer.theme.smallSize + 1; weight: Font.DemiBold }
                    }

                    Text {
                        readonly property bool isQuestion: true
                        visible: text !== ""
                        width: parent.width
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        text: answer.prompt.question
                        color: answer.theme.textColor
                        font { family: answer.theme.fontFamily; pixelSize: answer.theme.bodySize; weight: Font.DemiBold }
                    }

                    // One button for each option, in the order of the dialog. The text option is the field, when a
                    // text can be sent. "Chat about this" (it ends the question with no answer) is apart.
                    Column {
                        id: optionColumn
                        visible: answer.hasQuestion
                        width: parent.width
                        spacing: 6

                        Repeater {
                            id: options
                            // The number of options, not the list: an item stays while the question changes
                            // only in a note or in its cursor, so the text of the field and the keyboard stay.
                            model: answer.prompt.options.length

                            Column {
                                id: slot
                                required property int index
                                readonly property var choice: answer.prompt.options[index]
                                    || ({key: "", label: "", description: "", kind: "choice", effect: "other",
                                         wide: false, allowed: false})
                                readonly property bool isField: choice.kind === "text" && answer.prompt.freeText
                                readonly property bool apart: choice.kind === "other"
                                width: optionColumn.width
                                spacing: 6

                                Rectangle {
                                    visible: slot.apart
                                    width: parent.width
                                    height: 1
                                    color: answer.theme.lineColor
                                }
                                Controls.OptionButton {
                                    visible: !slot.isField
                                    width: parent.width
                                    theme: answer.theme
                                    choice: slot.choice
                                    warnColor: answer.warnColor
                                    enabled: !slot.isField && slot.choice.allowed && slot.choice.kind !== "text"
                                    onActivated: answer.choose(slot.choice.key, "pointer")
                                }
                                // The text option: the field, "Send", and below them the message of a text that
                                // was refused.
                                Loader {
                                    active: slot.isField
                                    visible: active
                                    width: parent.width
                                    sourceComponent: Item {
                                        id: entryRoot
                                        property alias text: entry.text
                                        function take() { entry.take() }
                                        width: slot.width
                                        height: entry.height + (fieldNoteText.visible ? fieldNoteText.height + 6 : 0)
                                        Component.onCompleted: answer.entryItem = entryRoot
                                        Component.onDestruction: if (answer.entryItem === entryRoot) answer.entryItem = null

                                        Controls.TextEntry {
                                            id: entry
                                            theme: answer.theme
                                            choice: slot.choice
                                            width: parent.width - send.width - 8
                                            onAccepted: answer.sendText()
                                            onTyped: answer.notePress(true)
                                        }
                                        Controls.LookButton {
                                            id: send
                                            readonly property bool isSend: true
                                            theme: answer.theme
                                            anchors.right: parent.right
                                            anchors.verticalCenter: entry.verticalCenter
                                            text: "Send"
                                            spoken: "Send the text"
                                            onActivated: answer.sendText()
                                        }
                                        Text {
                                            id: fieldNoteText
                                            readonly property bool isFieldNote: true
                                            visible: answer.fieldNote
                                            y: entry.height + 6
                                            width: parent.width
                                            textFormat: Text.PlainText
                                            wrapMode: Text.Wrap
                                            text: answer.fieldNote ? answer.prompt.message : ""
                                            color: answer.warnColor
                                            font { family: answer.theme.fontFamily; pixelSize: answer.theme.smallSize + 1 }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // The screen of an agent that Bellwether cannot read: only in the state "unreadable".
                    Loader {
                        id: screenLoader
                        active: answer.phase === "unreadable"
                        visible: active
                        width: parent.width
                        sourceComponent: Controls.TextView {
                            readonly property bool isScreen: true
                            theme: answer.theme
                            // Without the empty lines at the end of the screen.
                            lines: answer.prompt.screen.replace(/\s+$/, "").split("\n")
                            name: "Screen of the agent"
                            maxHeight: Math.max(160, Math.min(420, answer.roomHeight - 80 - 260))
                        }
                    }
                }
            }
        }

        // Where the content is, while it scrolls.
        Rectangle {
            readonly property bool isScrollThumb: true
            readonly property real room: scroller.height - 6 - height
            visible: scroller.scrolls
            x: parent.width - answer.theme.frameWidth - 6
            y: scroller.y + 3 + room * scroller.contentY / Math.max(1, scroller.contentHeight - scroller.height)
            width: 3
            height: Math.max(24, (scroller.height - 6) * scroller.height / Math.max(1, scroller.contentHeight))
            radius: Math.min(1.5, answer.theme.itemRadius)
            color: answer.theme.faintColor
        }

        // The footer: the keys, and "Open in Herdr" (always there).
        Item {
            id: footer
            readonly property bool isFooter: true
            y: parent.height - height
            width: parent.width
            height: answer.footerHeight

            Rectangle {
                x: answer.theme.frameWidth
                width: parent.width - 2 * x
                height: 1
                color: answer.theme.lineColor
            }
            Text {
                readonly property bool isFooterNote: true
                x: answer.pad
                width: herdr.x - x - 16
                height: parent.height
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.Wrap
                maximumLineCount: 2
                elide: Text.ElideRight
                textFormat: Text.PlainText
                // Why the number keys or the options that approve are off, when they are; then Esc, when there is
                // room for it (with both reasons there is not, at a large text size).
                readonly property bool locked: answer.digitsLocked && answer.hasQuestion
                text: (locked ? "Number keys off: click or press Tab." : "")
                    + (locked && answer.waitsForEnd ? " " + answer.scrollNote
                       : answer.waitsForEnd ? answer.scrollNote + " Esc closes."
                       : locked ? " Esc closes."
                       : answer.answerable ? "Press the number of an option. Esc closes." : "Esc closes.")
                color: answer.theme.dimColor
                font { family: answer.theme.fontFamily; pixelSize: answer.theme.smallSize + 1 }
            }
            Controls.LookButton {
                id: herdr
                readonly property bool isOpenInHerdr: true
                readonly property bool first: answer.herdrFirst
                theme: answer.theme
                enabled: backend.opening === "" && answer.prompt.key !== ""
                anchors.right: parent.right
                anchors.rightMargin: answer.pad
                anchors.verticalCenter: parent.verticalCenter
                plate: first ? answer.theme.accentColor : answer.safePlate
                ink: first ? answer.theme.inkOn(answer.theme.accentColor) : answer.safeInk
                text: "Open in Herdr"
                spoken: "Open the agent in Herdr"
                onActivated: answer.openInHerdr()
            }
        }

        // Every press of the pointer in the window counts for the guards; the press then goes on to what is below.
        MouseArea {
            anchors.fill: parent
            z: 10
            onPressed: (mouse) => {
                answer.notePress(false)
                mouse.accepted = false
            }
        }

        // The close control, at the right of the header. The last item: the Tab key reaches it last.
        Rectangle {
            id: closeControl
            readonly property bool isClose: true
            readonly property bool lit: closeArea.containsMouse || activeFocus
            anchors.right: parent.right
            anchors.rightMargin: 10
            y: (answer.headerHeight - height) / 2
            width: 28
            height: 28
            radius: answer.theme.itemRadius
            color: "transparent"
            activeFocusOnTab: true
            Accessible.role: Accessible.Button
            Accessible.name: "Close"
            Accessible.focusable: true
            Accessible.onPressAction: answer.close()
            Keys.onReturnPressed: answer.close()
            Keys.onEnterPressed: answer.close()
            Keys.onSpacePressed: answer.close()

            Rectangle {
                visible: closeArea.containsMouse
                anchors.fill: parent
                radius: parent.radius
                color: Qt.rgba(answer.safeInk.r, answer.safeInk.g, answer.safeInk.b, 0.10)
            }
            Repeater {
                model: [45, -45]
                Rectangle {
                    required property int modelData
                    readonly property bool isCloseMark: true
                    anchors.centerIn: parent
                    width: 13
                    height: 1.5
                    rotation: modelData
                    antialiasing: true
                    color: closeControl.lit ? answer.safeInk : answer.closeInk
                }
            }
            MouseArea {
                id: closeArea
                anchors.fill: parent
                hoverEnabled: true
                onClicked: answer.close()
            }
            Controls.FocusRing { target: closeControl; corner: closeControl.radius; border.color: answer.safeInk }
        }
    }
}
