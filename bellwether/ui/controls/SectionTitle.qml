// The title of a section of the options window, and with `minor` the title of a group inside a section.
import QtQuick

Text {
    required property QtObject theme
    property bool minor: false
    readonly property bool isSectionTitle: !minor

    height: theme.fit(16)
    verticalAlignment: Text.AlignVCenter
    elide: Text.ElideRight
    color: minor ? theme.faintColor : theme.dimColor
    font {
        family: theme.fontFamily; pixelSize: theme.smallSize; weight: minor ? Font.Medium : Font.DemiBold
        letterSpacing: theme.letterSpacing
        capitalization: theme.uppercaseTitles ? Font.AllUppercase : Font.MixedCase
    }
}
