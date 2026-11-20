// The theme tokens of Layout A: the values that its skin and the options window share. This file states the
// values of the design; the helpers of ThemeBase.qml apply the custom look to them (the font scale, the font
// family and the colours of the user).
// The list of tokens is in the spec ("options window and layout skins", "Theme tokens").
import QtQuick
import "fonts.js" as Fonts

ThemeBase {
    readonly property color panelColor: background("#f21f2023")
    // The neutral frame: the skin shows the colour of the top status in its place when there are agents.
    readonly property color frameColor: frame("#3c4043")
    readonly property int frameWidth: 2
    readonly property int radius: 14
    readonly property int itemRadius: 9
    readonly property color lineColor: frame("#3c4043")
    readonly property color textColor: text("#e8eaed")
    readonly property color dimColor: dim("#9aa0a6")
    readonly property color faintColor: faint("#80868b")
    readonly property color accentColor: accent("#8ab4f8")
    readonly property color selectedColor: accent("#248ab4f8")
    readonly property color hoverColor: text("#14e8eaed")
    // The colours that only this design has.
    // The grey of what is empty: the outline of a mark with no agents, a count of 0.
    readonly property color ghostColor: tone("#5f6368", 0.35)
    // Adwaita Sans, or the first of these that this system has.
    readonly property string fontFamily: family(Fonts.first(
        ["Adwaita Sans", "Inter", "Noto Sans", "DejaVu Sans", /* macOS: */ "SF Pro", "Helvetica Neue",
         /* Windows: */ "Segoe UI"],
        Qt.application.font.family))
    readonly property int titleSize: size(15)
    readonly property int bodySize: size(13)
    readonly property int smallSize: size(12)
    // The second line of an agent row: the model and the session time.
    readonly property int metaSize: size(11)
    // The text sizes that only this design has.
    // The count in the badge of a status row.
    readonly property int numeralSize: size(15)
    readonly property real letterSpacing: 0
    readonly property bool uppercaseTitles: false
    // No frame ornament.
    readonly property Component decoration: null
}
