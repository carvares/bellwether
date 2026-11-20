// One row of a section of the options window for a number of the look: a label, a LookSlider, the value in
// percent, and a small "Reset" while the value is not the default. The row does not read the backend: the caller
// gives the limits and the value, and gets `moved` and `resetRequested` (the slider's double click and the mark).
// `name` is the name of the number for a test ("scale"). Only theme tokens.
import QtQuick

Item {
    id: row

    required property QtObject theme
    required property string name
    // "Panel size": the label, and the name of the slider for a screen reader.
    required property string label
    required property real from
    required property real to
    required property real step
    required property real defaultValue
    required property real value
    // The widths of the label, the value and the reset mark (they grow with the text).
    required property int labelWidth
    required property int valueWidth
    required property int resetWidth
    readonly property alias slider: slider
    signal moved(real value)
    signal resetRequested()

    Text {
        width: row.labelWidth - 8
        height: parent.height
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        text: row.label
        color: row.theme.textColor
        font { family: row.theme.fontFamily; pixelSize: row.theme.bodySize }
    }
    LookSlider {
        id: slider
        readonly property string sliderFor: row.name
        theme: row.theme
        x: row.labelWidth
        width: parent.width - x - row.valueWidth - row.resetWidth - 16
        height: parent.height
        label: row.label
        from: row.from
        to: row.to
        step: row.step
        defaultValue: row.defaultValue
        value: row.value
        onMoved: (value) => row.moved(value)
        onResetRequested: row.resetRequested()
    }
    Text {
        readonly property string valueFor: row.name
        x: slider.x + slider.width + 8
        width: row.valueWidth
        height: parent.height
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment: Text.AlignRight
        elide: Text.ElideRight
        text: slider.percent + " %"
        color: row.theme.textColor
        font { family: row.theme.fontFamily; pixelSize: row.theme.bodySize; features: { "tnum": 1 } }
    }
    LookButton {
        readonly property string resetFor: row.name
        theme: row.theme
        small: true
        visible: row.value !== row.defaultValue
        enabled: visible
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: "Reset"
        spoken: "Reset the " + row.label.toLowerCase() + " to " + Math.round(row.defaultValue * 100) + " percent"
        onActivated: {
            slider.forceActiveFocus()
            row.resetRequested()
        }
    }
}
