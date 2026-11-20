// The options window: a normal window (an xdg toplevel, not a layer surface) that the tray entry "Options…"
// opens. It has no title bar of the system: it draws its own frame and header in the style of the layout that
// shows (the theme tokens of that skin, skins/<letter>Theme.qml), and it changes when the layout changes.
// A header with the close control, a column of sections that scrolls when the screen is lower than the content,
// and a footer with "Reset to defaults". The sections: the layout of the panel as five cards (their places and
// sizes are the same in every theme), and the custom look: Size, Text and Colours. The controls are the
// components of controls/; they read the values and the limits from the backend and only call its slots.
import QtQuick
import QtQuick.Window
import "skins" as Skins
import "controls" as Controls

Window {
    id: options

    // The theme tokens of the layout that shows. The tokens of Layout C while a theme file loads or is missing.
    readonly property QtObject theme: themeLoader.item ? themeLoader.item : fallbackTheme
    readonly property int pad: 24
    readonly property int headerHeight: 44
    readonly property int cardWidth: 196
    // The texts of a card: the name (one line), the description (two lines) and the tag. Their boxes grow with a
    // larger font (theme.fit), and the card and the window with them.
    readonly property int nameHeight: theme.fit(20)
    readonly property int descriptionHeight: theme.fit(34)
    readonly property int tagHeight: theme.fit(18)
    readonly property int cardHeight: 8 + 124 + nameHeight + 6 + descriptionHeight + 8 + tagHeight + 8
    readonly property int cardGap: 12
    // The custom look: two columns (Size at the left, Text at the right), each a label, a control, a value and
    // a reset mark; then the eight colours in one row of two groups.
    readonly property int innerWidth: fixedWidth - 2 * pad
    readonly property int columnGap: 24
    readonly property int columnWidth: (innerWidth - columnGap) / 2
    // The widths of the label, the value and the reset mark of a row: they hold text, so they grow with it.
    readonly property int labelWidth: theme.fit(104)
    readonly property int valueWidth: theme.fit(56)
    readonly property int resetWidth: theme.fit(58)
    readonly property int controlHeight: theme.fit(28)
    readonly property int sectionGap: 22
    readonly property int swatchWidth: 120
    readonly property int swatchGap: 8
    readonly property int groupGap: 20
    readonly property var roleNames: ({
        "blocked": "Blocked", "done": "Done", "working": "Working", "idle": "Idle",
        "background": "Background", "text": "Text", "frame": "Frame", "accent": "Accent"})
    // The roles of the two groups of colours: the first four of the backend are the statuses.
    readonly property var colourGroups: [
        { "title": "Status", "roles": backend.colorRoles.slice(0, 4) },
        { "title": "Panel", "roles": backend.colorRoles.slice(4) }]
    // The role of the colour that the editor shows. "": the editor is closed.
    property string editingRole: ""
    // "Reset to defaults" waits for its second click.
    property bool resetArmed: false
    // Two controls must stay usable whatever colours the user chose (also a text in the colour of the panel): the
    // close control and "Reset to defaults". They have a plate of the panel colour without its opacity, and an
    // ink that a person can tell from that plate (ThemeBase.readable). The close control shows its plate only when
    // it is needed: an ink of its marks is not the colour of the layout, or the panel lets more of the desktop
    // through than the layout does.
    readonly property color safePlate: theme.solid(theme.panelColor)
    readonly property color safeInk: theme.readable(theme.textColor, safePlate)
    readonly property color closeInk: theme.readable(theme.dimColor, safePlate)
    readonly property bool closePlated: safeInk !== theme.textColor || closeInk !== theme.dimColor
                                        || theme.panelColor.a < Qt.color(backend.defaultColors.background).a - 0.001
    // The header asks for a move of the window: the compositor moves it (no position code here).
    signal systemMoveRequested()

    title: "Bellwether — Options"
    flags: Qt.Window | Qt.FramelessWindowHint
    // The frame can have round corners: the window itself has no background.
    color: "transparent"
    // The height of the screen of the window. A test gives its own.
    property int roomHeight: Screen.height
    // The size is fixed, and the width is the same in every theme and at every text size (1076). The height is
    // the height of the content, or less on a low screen (80 px stay free for a task bar): the sections then
    // scroll between the header and the footer.
    readonly property int fixedWidth: 5 * cardWidth + 4 * cardGap + 2 * pad
    readonly property int footerHeight: controlHeight + 24
    readonly property int wantedHeight: headerHeight + sections.height + footerHeight
    readonly property int fixedHeight: Math.max(headerHeight + footerHeight + 120, Math.min(wantedHeight, roomHeight - 80))
    width: fixedWidth
    height: fixedHeight
    minimumWidth: fixedWidth
    maximumWidth: fixedWidth
    minimumHeight: fixedHeight
    maximumHeight: fixedHeight

    // At each open the keyboard starts on the card of the layout that shows, the sections start at their top,
    // and nothing is open.
    onVisibleChanged: {
        editingRole = ""
        resetArmed = false
        fontChooser.open = false
        if (visible) {
            scroller.contentY = 0
            focusSelected()
        }
    }
    onSystemMoveRequested: options.startSystemMove()
    // The keyboard moved: the control that has it is on the screen.
    onActiveFocusItemChanged: scroller.reveal(activeFocusItem)

    function focusSelected() {
        for (var i = 0; i < cards.count; i++)
            if (cards.itemAt(i).selected)
                cards.itemAt(i).forceActiveFocus()
    }

    function swatchOf(role) {
        for (var g = 0; g < groups.count; g++) {
            var found = groups.itemAt(g).swatchOf(role)
            if (found)
                return found
        }
        return null
    }

    // Open the editor for a colour; for the colour that it shows already, close it.
    function edit(role) {
        if (editingRole === role) {
            closeEditor()
            return
        }
        fontChooser.open = false
        editingRole = role
        editor.start()
        Qt.callLater(scroller.reveal, editor)
    }

    // Close the editor. The keyboard goes back to the swatch of its colour.
    function closeEditor() {
        var swatch = swatchOf(editingRole)
        editingRole = ""
        if (swatch)
            swatch.forceActiveFocus()
    }

    // Esc closes what is open inside the window first (the colour editor, the list of fonts), then the window.
    Shortcut {
        sequences: [StandardKey.Cancel]
        onActivated: {
            if (options.editingRole !== "")
                options.closeEditor()
            else if (fontChooser.open)
                fontChooser.hide()
            else
                options.close()
        }
    }

    Skins.CTheme { id: fallbackTheme }
    Loader {
        id: themeLoader
        source: backend.themeSource
    }

    // The frame of the window, as the frame of the panel. Its colour is the neutral one: this window does
    // not show a status.
    Rectangle {
        id: frame
        readonly property bool isFrame: true
        anchors.fill: parent
        radius: options.theme.radius
        // Opaque where an other app's window can be behind this one (the plain shell): decisions and settings must be
        // readable. The panel colour with its opacity on the layer shell.
        color: backend.opaqueDialogs ? options.theme.solid(options.theme.panelColor) : options.theme.panelColor
        border.width: options.theme.frameWidth
        border.color: options.theme.frameColor

        // The frame ornament of the layout (the corner brackets of Layout C), in its neutral colour.
        Loader {
            anchors.fill: parent
            sourceComponent: options.theme.decoration
        }

        // The header: the title. (The close control at its right is the last item of the frame, so that the
        // Tab key reaches it last.) A press that moves 6 px or more moves the window.
        Item {
            id: header
            readonly property bool isHeader: true
            width: parent.width
            height: options.headerHeight

            MouseArea {
                id: grip
                anchors.fill: parent
                property real startX: 0
                property real startY: 0
                property bool moving: false
                onPressed: (mouse) => { startX = mouse.x; startY = mouse.y; moving = false }
                onPositionChanged: (mouse) => {
                    if (!pressed || moving || Math.abs(mouse.x - startX) + Math.abs(mouse.y - startY) < 6)
                        return
                    moving = true
                    options.systemMoveRequested()
                }
            }
            Text {
                readonly property bool isTitle: true
                x: options.pad
                width: parent.width - options.pad - 48
                anchors.verticalCenter: parent.verticalCenter
                elide: Text.ElideRight
                text: "Bellwether — Options"
                color: options.theme.dimColor
                font {
                    family: options.theme.fontFamily; pixelSize: options.theme.titleSize; weight: Font.DemiBold
                    letterSpacing: options.theme.letterSpacing
                    capitalization: options.theme.uppercaseTitles ? Font.AllUppercase : Font.MixedCase
                }
            }
            Rectangle {
                x: options.theme.frameWidth
                anchors.bottom: parent.bottom
                width: parent.width - 2 * x
                height: 1
                color: options.theme.lineColor
            }
        }

        // The sections. They scroll when the window is lower than its content: with the wheel, a drag of the
        // pointer or a finger, the thumb, and the keyboard (the control that gets the keyboard comes on the screen).
        // A slider keeps its drag (it does not let the Flickable steal it).
        Flickable {
            id: scroller
            readonly property bool isScroller: true
            readonly property bool scrolls: contentHeight > height + 0.5
            y: options.headerHeight
            width: parent.width
            height: parent.height - options.headerHeight - options.footerHeight
            contentWidth: width
            contentHeight: sections.height
            clip: true
            interactive: scrolls
            flickableDirection: Flickable.VerticalFlick
            boundsBehavior: Flickable.StopAtBounds
            onContentHeightChanged: contentY = Math.max(0, Math.min(contentY, contentHeight - height))
            onHeightChanged: contentY = Math.max(0, Math.min(contentY, contentHeight - height))

            function scrollBy(pixels) {
                contentY = Math.max(0, Math.min(contentY + pixels, contentHeight - height))
            }

            // Bring an item of the sections on the screen, with 12 px of room around it.
            function reveal(item) {
                if (!item || !scrolls)
                    return
                for (var parent = item; parent && parent !== sections; parent = parent.parent) {}
                if (!parent)
                    return
                var top = item.mapToItem(sections, 0, 0).y
                if (top - 12 < contentY)
                    contentY = Math.max(0, top - 12)
                else if (top + item.height + 12 > contentY + height)
                    contentY = Math.min(contentHeight - height, top + item.height + 12 - height)
            }

            WheelHandler {
                // A touchpad gives pixels; one step of a mouse wheel (120) is 60 px.
                onWheel: (event) => scroller.scrollBy(event.pixelDelta.y !== 0 ? -event.pixelDelta.y
                                                                               : -event.angleDelta.y / 2)
            }

            Item {
                id: sections
                width: scroller.width
                height: colours.y + colours.height + 20

                // The section "Layout": its title and the five cards.
                Controls.SectionTitle {
                    id: layoutTitle
                    theme: options.theme
                    x: options.pad
                    y: 20
                    text: "Layout"
                }

                // In the line of the title, at the right: the second line of the agent rows of every layout (the
                // model and the age of the session).
                Controls.CheckRow {
                    id: metaRow
                    theme: options.theme
                    x: options.pad + options.innerWidth - width
                    y: layoutTitle.y + (layoutTitle.height - height) / 2
                    name: "showMeta"
                    label: "Show model and session time"
                    checked: backend.showMeta
                    onToggled: (value) => backend.setShowMeta(value)
                }

                Row {
                    id: cardsRow
                    x: options.pad
                    y: layoutTitle.y + layoutTitle.height + 14
                    spacing: options.cardGap

                    Repeater {
                        id: cards
                        model: backend.layouts

                        // One layout. A layout that is not built yet is dim and cannot be chosen.
                        Controls.LayoutCard {
                            required property var modelData
                            theme: options.theme
                            layout: modelData
                            selected: backend.layout === modelData.id
                            width: options.cardWidth
                            height: options.cardHeight
                            nameHeight: options.nameHeight
                            descriptionHeight: options.descriptionHeight
                            tagHeight: options.tagHeight
                            onChosen: backend.setLayout(layoutId)
                        }
                    }
                }

                // The section "Size": the scale of the whole panel. It does not apply to this window.
                Item {
                    id: sizeSection
                    x: options.pad
                    y: cardsRow.y + options.cardHeight + options.sectionGap
                    width: options.columnWidth
                    height: sizeTitle.height + 10 + options.controlHeight

                    Controls.SectionTitle { id: sizeTitle; theme: options.theme; text: "Size" }
                    Controls.SliderRow {
                        id: sizeRow
                        theme: options.theme
                        y: sizeTitle.height + 10
                        width: parent.width
                        height: options.controlHeight
                        name: "scale"
                        label: "Panel size"
                        from: backend.scaleMin
                        to: backend.scaleMax
                        step: backend.scaleStep
                        defaultValue: backend.scaleDefault
                        value: backend.scale
                        labelWidth: options.labelWidth
                        valueWidth: options.valueWidth
                        resetWidth: options.resetWidth
                        onMoved: (value) => backend.setScale(value)
                        onResetRequested: backend.setScale(backend.scaleDefault)
                    }
                }

                // The section "Text": the size of every text, and the font family.
                Item {
                    id: textSection
                    x: options.pad + options.columnWidth + options.columnGap
                    y: sizeSection.y
                    width: options.columnWidth
                    height: textTitle.height + 10 + options.controlHeight + 8 + fontChooser.height

                    Controls.SectionTitle { id: textTitle; theme: options.theme; text: "Text" }
                    Controls.SliderRow {
                        id: textRow
                        theme: options.theme
                        y: textTitle.height + 10
                        width: parent.width
                        height: options.controlHeight
                        name: "fontScale"
                        label: "Text size"
                        from: backend.fontScaleMin
                        to: backend.fontScaleMax
                        step: backend.fontScaleStep
                        defaultValue: backend.fontScaleDefault
                        value: backend.fontScale
                        labelWidth: options.labelWidth
                        valueWidth: options.valueWidth
                        resetWidth: options.resetWidth
                        onMoved: (value) => backend.setFontScale(value)
                        onResetRequested: backend.setFontScale(backend.fontScaleDefault)
                    }
                    Text {
                        y: fontChooser.y
                        width: options.labelWidth - 8
                        height: options.controlHeight
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                        text: "Font"
                        color: options.theme.textColor
                        font { family: options.theme.fontFamily; pixelSize: options.theme.bodySize }
                    }
                    Controls.FontChooser {
                        id: fontChooser
                        theme: options.theme
                        x: options.labelWidth
                        y: textRow.y + textRow.height + 8
                        width: parent.width - x
                        families: backend.fontFamilies
                        current: backend.fontFamily
                        onChosen: (family) => backend.setFontFamily(family)
                        onOpenChanged: {
                            if (open) {
                                options.editingRole = ""
                                Qt.callLater(scroller.reveal, fontChooser)
                            }
                        }
                    }
                }

                // The section "Colours": the four status colours and the four colours of the panel. A swatch opens
                // the editor below the row, inside the window.
                Item {
                    id: colours
                    x: options.pad
                    y: Math.max(sizeSection.y + sizeSection.height, textSection.y + textSection.height) + options.sectionGap
                    width: options.innerWidth
                    height: editor.visible ? editor.y + editor.height : swatchRow.y + swatchRow.height

                    Controls.SectionTitle { id: coloursTitle; theme: options.theme; text: "Colours" }
                    Item {
                        id: swatchRow
                        y: coloursTitle.height + 8
                        width: parent.width
                        height: groups.count > 0 ? groups.itemAt(0).height : 0

                        Repeater {
                            id: groups
                            model: options.colourGroups

                            Item {
                                id: group
                                required property var modelData
                                required property int index
                                readonly property int span: options.swatchWidth + options.swatchGap

                                function swatchOf(role) {
                                    for (var i = 0; i < swatches.count; i++)
                                        if (swatches.itemAt(i).role === role)
                                            return swatches.itemAt(i)
                                    return null
                                }

                                x: index * (4 * span - options.swatchGap + options.groupGap)
                                width: 4 * span - options.swatchGap
                                height: groupTitle.height + 6 + (swatches.count > 0 ? swatches.itemAt(0).height : 0)

                                Controls.SectionTitle {
                                    id: groupTitle
                                    theme: options.theme
                                    minor: true
                                    width: parent.width
                                    text: group.modelData.title
                                }
                                Repeater {
                                    id: swatches
                                    model: group.modelData.roles

                                    Controls.ColorSwatch {
                                        required property string modelData
                                        required property int index
                                        theme: options.theme
                                        x: index * group.span
                                        y: groupTitle.height + 6
                                        width: options.swatchWidth
                                        role: modelData
                                        name: options.roleNames[modelData] || modelData
                                        colour: backend.colors[modelData] || "#000000"
                                        custom: backend.colorOverrides[modelData] !== undefined
                                        editing: options.editingRole === modelData
                                        onActivated: options.edit(modelData)
                                        onResetRequested: {
                                            forceActiveFocus()
                                            backend.resetColor(modelData)
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Controls.ColorEditor {
                        id: editor
                        theme: options.theme
                        visible: options.editingRole !== ""
                        enabled: visible
                        y: swatchRow.y + swatchRow.height + 10
                        width: parent.width
                        name: options.roleNames[options.editingRole] || options.editingRole
                        colour: backend.colors[options.editingRole] || "#000000"
                        withOpacity: options.editingRole === "background"
                        ownOpacity: (backend.colorOverrides.background || "").length === 9
                        opacityFrom: backend.opacityMin
                        opacityTo: backend.opacityMax
                        opacityStep: backend.opacityStep
                        onChosen: (colour) => backend.setColor(options.editingRole, colour)
                        onCloseRequested: options.closeEditor()
                    }
                }
            }
        }

        // Where the sections are, while they scroll. A drag on the thumb scrolls them: the line is thin, the place
        // that takes the pointer is 16 px wide.
        Rectangle {
            id: thumb
            readonly property bool isScrollThumb: true
            readonly property real room: scroller.height - 6 - height
            visible: scroller.scrolls
            x: parent.width - options.theme.frameWidth - 6
            y: scroller.y + 3 + room * scroller.contentY / Math.max(1, scroller.contentHeight - scroller.height)
            width: 3
            height: Math.max(24, (scroller.height - 6) * scroller.height / Math.max(1, scroller.contentHeight))
            radius: Math.min(1.5, options.theme.itemRadius)
            color: options.theme.faintColor

            MouseArea {
                readonly property bool isScrollGrip: true
                property real grabbedAt: 0
                anchors.fill: parent
                anchors.leftMargin: -9
                anchors.rightMargin: -4
                preventStealing: true
                onPressed: (mouse) => grabbedAt = mouse.y
                onPositionChanged: (mouse) => {
                    var top = thumb.y + mouse.y - grabbedAt - scroller.y - 3
                    scroller.contentY = Math.max(0, Math.min(1, top / Math.max(1, thumb.room)))
                        * (scroller.contentHeight - scroller.height)
                }
            }
        }

        // The footer: "Reset to defaults" for the whole custom look. A wrong click does nothing: the first
        // click arms the control for 3 seconds, the second resets.
        Item {
            id: footer
            readonly property bool isFooter: true
            y: parent.height - height
            width: parent.width
            height: options.footerHeight

            Rectangle {
                x: options.theme.frameWidth
                width: parent.width - 2 * x
                height: 1
                color: options.theme.lineColor
            }
            Text {
                readonly property bool isFooterNote: true
                x: options.pad
                width: resetAll.x - x - 16
                height: parent.height
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                text: "The size, the text and the colours apply to all five layouts."
                color: options.theme.dimColor
                font { family: options.theme.fontFamily; pixelSize: options.theme.smallSize + 1 }
            }
            Controls.LookButton {
                id: resetAll
                readonly property bool isResetAll: true
                theme: options.theme
                enabled: backend.lookIsCustom
                anchors.right: parent.right
                anchors.rightMargin: options.pad
                anchors.verticalCenter: parent.verticalCenter
                plate: options.safePlate
                ink: options.safeInk
                text: options.resetArmed ? "Click again to reset" : "Reset to defaults"
                spoken: options.resetArmed ? "Reset to defaults, press again to reset" : "Reset to defaults"
                onActivated: {
                    if (!options.resetArmed) {
                        options.resetArmed = true
                        return
                    }
                    options.resetArmed = false
                    options.editingRole = ""
                    backend.resetLook()
                }
                onEnabledChanged: if (!enabled) options.resetArmed = false
                onActiveFocusChanged: if (!activeFocus) options.resetArmed = false
            }
            Timer {
                id: resetTimer
                interval: 3000
                running: options.resetArmed
                onTriggered: options.resetArmed = false
            }
        }

        // The close control, at the right of the header.
        Rectangle {
            id: closeControl
            readonly property bool isClose: true
            readonly property bool lit: closeArea.containsMouse || activeFocus
            readonly property bool plated: options.closePlated
            anchors.right: parent.right
            anchors.rightMargin: 10
            y: (options.headerHeight - height) / 2
            width: 28
            height: 28
            radius: options.theme.itemRadius
            color: plated ? options.safePlate : "transparent"
            activeFocusOnTab: true
            Accessible.role: Accessible.Button
            Accessible.name: "Close"
            Accessible.focusable: true
            Accessible.onPressAction: options.close()
            Keys.onReturnPressed: options.close()
            Keys.onEnterPressed: options.close()
            Keys.onSpacePressed: options.close()

            Rectangle {
                visible: closeArea.containsMouse
                anchors.fill: parent
                radius: parent.radius
                color: closeControl.plated ? Qt.rgba(options.safeInk.r, options.safeInk.g, options.safeInk.b, 0.10)
                                           : options.theme.hoverColor
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
                    color: closeControl.lit ? options.safeInk : options.closeInk
                }
            }
            MouseArea {
                id: closeArea
                anchors.fill: parent
                hoverEnabled: true
                onClicked: options.close()
            }
            Controls.FocusRing { target: closeControl; corner: closeControl.radius; border.color: options.safeInk }
        }
    }
}
