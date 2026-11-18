// The theme tokens of Layout C: the values that its skin and the options window share.
// The list of tokens is in the spec ("options window and layout skins", "Theme tokens").
import QtQuick

QtObject {
    readonly property color panelColor: "#f00b0e11"
    // The thin line of the frame. The corner brackets (decoration) carry the colour of the top status.
    readonly property color frameColor: "#2b333b"
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
    readonly property string fontFamily: {
        var have = Qt.fontFamilies()
        var wanted = ["Hack", "JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono"]
        for (var i = 0; i < wanted.length; i++)
            if (have.indexOf(wanted[i]) >= 0)
                return wanted[i]
        return "monospace"
    }
    readonly property int titleSize: 12
    readonly property int bodySize: 12
    readonly property int smallSize: 10
    readonly property real letterSpacing: 1.5
    readonly property bool uppercaseTitles: true
    // The frame ornament: four corner brackets, 14 px long and 2 px thick, in `tone`. The user of the
    // component gives it the size of the frame, and sets `tone` (the default is the neutral colour).
    readonly property Component decoration: Component {
        Item {
            id: brackets
            property color tone: "#6b747d"
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
