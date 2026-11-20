// The second line of an agent row: the model that the agent runs and the age of its session ("Opus 5.5 · 2h 14m"),
// below the label of the agent. A skin puts one in its AgentRow, gives it a place (below the label, from the left
// edge of the label to the right end of the row or to the "Answer" control) and the height that it adds to the rows
// (AgentList.metaHeight). The rule "which rows have it" is in AgentRow (hasMeta), not in a skin: the line shows only
// then. A model name that is too long for the row ends in "…"; the age always shows in full.
import QtQuick

Item {
    id: line

    // The row that holds the line, and the theme tokens of the skin.
    required property AgentRow row
    required property QtObject tokens
    // ----- the style, from the skin -----
    property string family: tokens.fontFamily
    // The colour of the text, and of the mark between the two parts.
    property color ink: tokens.dimColor
    property color markInk: tokens.faintColor

    readonly property bool isMetaLine: true
    // The space at each side of the mark between the two parts.
    readonly property real gap: Math.max(4, Math.round(tokens.metaSize * 0.4))

    visible: row.hasMeta
    height: Math.max(model.implicitHeight, age.implicitHeight)

    Text {
        id: model
        readonly property bool isMetaModel: true
        visible: text !== ""
        width: Math.max(0, Math.min(implicitWidth, line.width - (age.visible ? mark.width + 2 * line.gap + age.width : 0)))
        textFormat: Text.PlainText
        elide: Text.ElideRight
        text: line.row.model
        color: line.ink
        font { family: line.family; pixelSize: line.tokens.metaSize }
    }
    Text {
        id: mark
        visible: model.visible && age.visible
        x: model.width + line.gap
        textFormat: Text.PlainText
        text: "·"
        color: line.markInk
        font { family: line.family; pixelSize: line.tokens.metaSize }
    }
    Text {
        id: age
        readonly property bool isMetaAge: true
        visible: text !== ""
        x: mark.visible ? mark.x + mark.width + line.gap : 0
        textFormat: Text.PlainText
        text: line.row.sessionAge
        color: line.ink
        font { family: line.family; pixelSize: line.tokens.metaSize; features: { "tnum": 1 } }
    }
}
