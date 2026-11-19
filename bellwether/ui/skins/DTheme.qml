// The theme tokens of Layout D: the values that its skin and the options window share. This file states the
// values of the design; ThemeBase.qml applies the custom look to them (size(): the font scale).
// The list of tokens is in the spec ("options window and layout skins", "Theme tokens").
import QtQuick
import "fonts.js" as Fonts

ThemeBase {
    readonly property color panelColor: "#f21f2023"
    // The neutral frame: the skin shows the colour of the top status in its place when there are agents.
    readonly property color frameColor: "#3c4043"
    readonly property int frameWidth: 2
    readonly property int radius: 14
    readonly property int itemRadius: 9
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
    readonly property int titleSize: size(13)
    readonly property int bodySize: size(13)
    readonly property int smallSize: size(12)
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
