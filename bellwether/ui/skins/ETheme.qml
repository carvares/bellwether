// The theme tokens of Layout E: the values that its skin and the options window share.
// The list of tokens is in the spec ("options window and layout skins", "Theme tokens").
import QtQuick
import "fonts.js" as Fonts

QtObject {
    readonly property color panelColor: "#f21f2023"
    // The neutral frame: the skin shows the colour of the top status in its place when there are agents.
    readonly property color frameColor: "#3c4043"
    readonly property int frameWidth: 2
    readonly property int radius: 16
    readonly property int itemRadius: 7
    readonly property color lineColor: "#3c4043"
    readonly property color textColor: "#e8eaed"
    readonly property color dimColor: "#9aa0a6"
    readonly property color faintColor: "#80868b"
    readonly property color accentColor: "#8ab4f8"
    readonly property color selectedColor: "#248ab4f8"
    readonly property color hoverColor: "#14e8eaed"
    // Adwaita Sans, or the first of these that this system has.
    readonly property string fontFamily: Fonts.first(
        ["Adwaita Sans", "Inter", "Noto Sans", "DejaVu Sans"], Qt.application.font.family)
    readonly property int titleSize: 13
    readonly property int bodySize: 13
    readonly property int smallSize: 12
    readonly property real letterSpacing: 0
    readonly property bool uppercaseTitles: false
    // No frame ornament.
    readonly property Component decoration: null
}
