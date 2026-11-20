// The theme tokens of Layout D: the values that its skin and the options window share. This file states the
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
    // The footer of a long list.
    readonly property color insetColor: inset("#17181b")
    // The track of the share bar with no agents.
    readonly property color trackColor: tone("#2d2f33", 0.15)
    // The name of a tab that is not open.
    readonly property color mutedColor: tone("#bdc1c6", 0.8)
    // Adwaita Sans, or the first of these that this system has.
    readonly property string fontFamily: family(Fonts.first(
        ["Adwaita Sans", "Inter", "Noto Sans", "DejaVu Sans", /* macOS: */ "SF Pro", "Helvetica Neue"],
        Qt.application.font.family))
    readonly property int titleSize: size(13)
    readonly property int bodySize: size(13)
    readonly property int smallSize: size(12)
    // The second line of an agent row: the model and the session time.
    readonly property int metaSize: size(11)
    // The text sizes that only this design has.
    // The total in the headline.
    readonly property int headlineSize: size(24)
    // The word "Offline" in the place of the total.
    readonly property int noticeSize: size(17)
    // The word "agents" after the total.
    readonly property int unitSize: size(13)
    // The top status in the chip.
    readonly property int badgeSize: size(12)
    // The count of a tab.
    readonly property int numeralSize: size(20)
    // The name of a tab.
    readonly property int labelSize: size(11)
    // The footer of a long list.
    readonly property int detailSize: size(11)
    readonly property real letterSpacing: 0
    readonly property bool uppercaseTitles: false
    // No frame ornament.
    readonly property Component decoration: null
}
