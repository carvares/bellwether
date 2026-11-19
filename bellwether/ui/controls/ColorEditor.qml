// The editor of one colour, inside the options window: a palette of presets, a field for "#rrggbb", and for a
// colour with an opacity (the background) a slider. Each choice asks for the colour at once (`chosen`); the
// caller gives it to the backend, and `colour` comes back through its binding. Only theme tokens.
import QtQuick

Rectangle {
    id: editor

    required property QtObject theme
    // The name of the colour on the screen ("Blocked").
    property string name: ""
    // The colour in effect: "#rrggbb" or "#aarrggbb".
    property string colour: "#000000"
    // The colour can have an opacity (the background).
    property bool withOpacity: false
    // The opacity is a choice of the user. False: a new colour is "#rrggbb" and keeps the opacity of each layout.
    property bool ownOpacity: false
    // The limits and the step of the opacity slider (from the backend).
    property real opacityFrom
    property real opacityTo
    property real opacityStep
    readonly property string rgb: "#" + colour.slice(-6)
    readonly property real alpha: colour.length === 9 ? parseInt(colour.substr(1, 2), 16) / 255 : 1
    readonly property string hint: "Use a colour like #8ab4f8"
    // Colours that work as a status colour on a dark panel, then neutral ones from light to dark for the text,
    // the frame and the panel.
    readonly property var presets: [
        "#f28b82", "#ff5555", "#ffb86c", "#fdd663", "#f1fa8c", "#81c995", "#50fa7b", "#8be9fd",
        "#8ab4f8", "#bd93f9", "#ff79c6", "#e8eaed", "#9aa0a6", "#3c4043", "#1f2023", "#0b0e11"]
    readonly property bool isColourEditor: true
    signal chosen(string colour)
    signal closeRequested()

    function hex2(share) {
        var text = Math.round(Math.max(0, Math.min(1, share)) * 255).toString(16)
        return text.length < 2 ? "0" + text : text
    }

    // A new colour with the opacity that applies, when the opacity is a choice of the user.
    function pick(rgbText) {
        chosen(withOpacity && ownOpacity ? "#" + hex2(alpha) + rgbText.slice(1) : rgbText)
    }

    // The text of the field as "#rrggbb" in small letters. "" when it is not a colour.
    function entered(text) {
        var match = /^#?([0-9a-fA-F]{6})$/.exec(text.trim())
        return match ? "#" + match[1].toLowerCase() : ""
    }

    // The keyboard starts in the palette.
    function start() {
        chips.forceActiveFocus()
    }

    // The width of the titles at the left: they hold text, so they grow with it.
    readonly property int titleWidth: theme.fit(150)

    implicitHeight: 12 + chips.height + 10 + fieldBox.height + 4 + message.height + 6
    height: implicitHeight
    radius: theme.itemRadius
    color: theme.selectedColor
    border.width: 1
    border.color: theme.accentColor

    Text {
        readonly property bool isEditorTitle: true
        x: 14
        y: 12
        width: editor.titleWidth
        height: chips.height
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        text: editor.name + " colour"
        color: editor.theme.textColor
        font { family: editor.theme.fontFamily; pixelSize: editor.theme.bodySize; weight: Font.DemiBold }
    }

    // The presets: one stop of the Tab key. The arrows move, Enter, Return and Space choose.
    Item {
        id: chips
        readonly property bool isPalette: true
        readonly property int chip: 26
        readonly property int gap: 6
        property int current: Math.max(0, editor.presets.indexOf(editor.rgb))
        x: 14 + editor.titleWidth + 8
        y: 12
        width: editor.presets.length * (chip + gap) - gap
        height: chip
        activeFocusOnTab: true
        Accessible.role: Accessible.List
        Accessible.name: "Presets for the " + editor.name + " colour, " + editor.presets[current]
        Accessible.focusable: true
        Keys.onLeftPressed: current = (current + editor.presets.length - 1) % editor.presets.length
        Keys.onRightPressed: current = (current + 1) % editor.presets.length
        Keys.onReturnPressed: editor.pick(editor.presets[current])
        Keys.onEnterPressed: editor.pick(editor.presets[current])
        Keys.onSpacePressed: editor.pick(editor.presets[current])

        Repeater {
            model: editor.presets
            Rectangle {
                id: preset
                required property string modelData
                required property int index
                readonly property string presetColour: modelData
                readonly property bool inEffect: editor.rgb === modelData
                x: index * (chips.chip + chips.gap)
                width: chips.chip
                height: chips.chip
                radius: Math.min(6, editor.theme.itemRadius)
                color: modelData
                border.width: inEffect ? 2 : 1
                border.color: inEffect ? editor.theme.inkOn(modelData) : editor.theme.lineColor
                Accessible.role: Accessible.Button
                Accessible.name: "Preset " + modelData
                Accessible.onPressAction: editor.pick(modelData)

                Rectangle {
                    readonly property bool isFocusRing: true
                    visible: chips.activeFocus && chips.current === preset.index
                    anchors.fill: parent
                    anchors.margins: -3
                    radius: parent.radius > 0 ? parent.radius + 3 : 0
                    color: "transparent"
                    border.width: 2
                    border.color: editor.theme.textColor
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        chips.current = preset.index
                        chips.forceActiveFocus()
                        editor.pick(preset.modelData)
                    }
                }
            }
        }
    }

    // The colour as text. A valid text applies at once; a text that is not a colour changes nothing.
    Text {
        id: fieldLabel
        x: 14
        y: fieldBox.y
        width: editor.titleWidth
        height: fieldBox.height
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        text: "Hex"
        color: editor.theme.dimColor
        font { family: editor.theme.fontFamily; pixelSize: editor.theme.smallSize + 1 }
    }
    Rectangle {
        id: fieldBox
        x: chips.x
        y: 12 + chips.height + 10
        width: editor.theme.fit(122)
        height: editor.theme.fit(28)
        radius: Math.min(6, editor.theme.itemRadius)
        color: editor.theme.panelColor
        border.width: 1
        border.color: field.activeFocus ? editor.theme.accentColor
            : field.wrong ? editor.theme.faintColor : editor.theme.lineColor

        TextInput {
            id: field
            readonly property bool isHexField: true
            // The text is not a colour, and it cannot become one with more letters, or the user said "this is it".
            readonly property bool wrong: activeFocus && editor.entered(text) === ""
                && (said || !/^#?[0-9a-fA-F]{0,6}$/.test(text.trim()))
            property bool said: false
            anchors.fill: parent
            anchors.leftMargin: 9
            anchors.rightMargin: 9
            verticalAlignment: TextInput.AlignVCenter
            clip: true
            activeFocusOnTab: true
            selectByMouse: true
            maximumLength: 16
            text: editor.rgb
            color: editor.theme.textColor
            selectionColor: editor.theme.accentColor
            selectedTextColor: editor.theme.inkOn(editor.theme.accentColor)
            font { family: editor.theme.fontFamily; pixelSize: editor.theme.bodySize }
            Accessible.role: Accessible.EditableText
            Accessible.name: editor.name + " colour as hex, " + editor.rgb
            onTextEdited: {
                said = false
                var colour = editor.entered(text)
                if (colour !== "" && colour !== editor.rgb)
                    editor.pick(colour)
            }
            onAccepted: {
                said = true
                var colour = editor.entered(text)
                if (colour !== "")
                    editor.pick(colour)
            }
            // The field shows the colour in effect again when the keyboard leaves it, and when the colour
            // changes while the keyboard is elsewhere (a preset, "Reset", a different colour in the editor).
            onActiveFocusChanged: {
                said = false
                if (!activeFocus)
                    text = editor.rgb
                else
                    selectAll()
            }
        }
        FocusRing { target: fieldBox; corner: fieldBox.radius; visible: field.activeFocus; border.color: editor.theme.textColor }
    }
    Connections {
        target: editor
        function onRgbChanged() {
            if (!field.activeFocus)
                field.text = editor.rgb
        }
    }
    Text {
        id: message
        readonly property bool isHexMessage: true
        // Its line under the field is always there, so the editor does not change its height.
        visible: field.wrong
        x: fieldBox.x
        y: fieldBox.y + fieldBox.height + 4
        width: editor.width - x - 14
        height: editor.theme.fit(18)
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        text: editor.hint
        color: editor.theme.textColor
        font { family: editor.theme.fontFamily; pixelSize: editor.theme.smallSize + 1 }
        Accessible.role: Accessible.AlertMessage
        Accessible.name: text
    }

    // The opacity of the panel.
    Text {
        id: opacityLabel
        visible: editor.withOpacity
        x: fieldBox.x + fieldBox.width + 40
        y: fieldBox.y
        width: editor.theme.fit(84)
        height: fieldBox.height
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        text: "Opacity"
        color: editor.theme.dimColor
        font { family: editor.theme.fontFamily; pixelSize: editor.theme.smallSize + 1 }
    }
    LookSlider {
        id: opacitySlider
        readonly property bool isOpacitySlider: true
        theme: editor.theme
        visible: editor.withOpacity
        enabled: editor.withOpacity
        x: opacityLabel.x + opacityLabel.width + 8
        y: fieldBox.y + (fieldBox.height - height) / 2
        width: 240
        label: editor.name + " opacity"
        from: editor.opacityFrom
        to: editor.opacityTo
        step: editor.opacityStep
        value: editor.alpha
        onMoved: (value) => editor.chosen("#" + editor.hex2(value) + editor.rgb.slice(1))
    }
    Text {
        readonly property bool isOpacityValue: true
        visible: editor.withOpacity
        x: opacitySlider.x + opacitySlider.width + 8
        y: fieldBox.y
        width: editor.theme.fit(56)
        height: fieldBox.height
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        text: opacitySlider.percent + " %"
        color: editor.theme.textColor
        font { family: editor.theme.fontFamily; pixelSize: editor.theme.bodySize; features: { "tnum": 1 } }
    }

    // The last stop of the Tab key in the editor.
    LookButton {
        readonly property bool isEditorClose: true
        theme: editor.theme
        anchors.right: parent.right
        anchors.rightMargin: 14
        y: 12 + (chips.height - height) / 2
        text: "Done"
        spoken: "Close the colour editor"
        onActivated: editor.closeRequested()
    }
}
