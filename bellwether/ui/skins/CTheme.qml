// The theme tokens of Layout C: the values that its skin and the options window share. This file states the
// values of the design; ThemeBase.qml applies the custom look to them (size(): the font scale).
// The list of tokens is in the spec ("options window and layout skins", "Theme tokens").
import QtQuick
import "fonts.js" as Fonts

ThemeBase {
    id: tokens

    readonly property color panelColor: "#f00b0e11"
    // The thin line of the frame. The corner brackets (decoration) carry the colour of the top status.
    readonly property color frameColor: "#2b333b"
    // The colour of the corner brackets and of the top status in the header with no agents and offline, and of
    // the brackets of the options window. Only this design has it (not one of the shared tokens).
    readonly property color neutralColor: "#6b747d"
    readonly property int frameWidth: 1
    readonly property int radius: 0
    readonly property int itemRadius: 0
    readonly property color lineColor: "#2b333b"
    readonly property color textColor: "#e3e9ee"
    readonly property color dimColor: "#8a949e"
    readonly property color faintColor: "#68727c"
    readonly property color accentColor: "#8ab4f8"
    readonly property color selectedColor: "#1a8ab4f8"
    readonly property color hoverColor: "#14e3e9ee"
    // Hack, or the first monospace font that this system has.
    readonly property string fontFamily: Fonts.first(
        ["Hack", "JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono"], "monospace")
    readonly property int titleSize: size(12)
    readonly property int bodySize: size(12)
    readonly property int smallSize: size(10)
    // The text sizes that only this design has.
    // The count of a status row.
    readonly property int numeralSize: size(20)
    // The detail and the address of an agent row, and the line of a failed jump.
    readonly property int detailSize: size(11)
    // The word of the offline plate.
    readonly property int noticeSize: size(13)
    readonly property real letterSpacing: 1.5
    readonly property bool uppercaseTitles: true
    // The frame ornament: four corner brackets, 14 px long and 2 px thick, in `tone`. The user of the
    // component gives it the size of the frame, and sets `tone` (the default is neutralColor).
    readonly property Component decoration: Component {
        Item {
            id: brackets
            property color tone: tokens.neutralColor
            Repeater {
                model: 4
                Item {
                    id: bracket
                    required property int index
                    readonly property bool atRight: index % 2 === 1
                    readonly property bool atBottom: index > 1
                    x: atRight ? brackets.width - 14 : 0
                    y: atBottom ? brackets.height - 14 : 0
                    width: 14; height: 14
                    Rectangle { x: 0; y: bracket.atBottom ? 12 : 0; width: 14; height: 2; color: brackets.tone }
                    Rectangle { x: bracket.atRight ? 12 : 0; y: 0; width: 2; height: 14; color: brackets.tone }
                }
            }
        }
    }
}
