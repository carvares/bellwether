// One layout of the section "Layout" of the options window: its preview, its name, its description in two lines,
// and a tag ("SELECTED", "COMING NEXT"). A layout that is not built yet is dim and cannot be chosen. The card does
// not read the backend: the caller gives the layout and `selected`, and sets the layout on `chosen`. Only theme
// tokens, and two colours of this window: the plate under the preview and the dark ink of the tag.
import QtQuick

Rectangle {
    id: card

    required property QtObject theme
    // One row of backend.layouts: id, name, description, preview, built.
    required property var layout
    property bool selected: false
    // The heights of the three texts (they grow with a larger font).
    property int nameHeight: 20
    property int descriptionHeight: 34
    property int tagHeight: 18
    // The dark text of the tag on the accent.
    readonly property color tagInk: "#0b0e11"
    readonly property string layoutId: layout.id
    readonly property bool built: layout.built
    readonly property bool hovered: built && pointer.containsMouse
    signal chosen()

    function choose() {
        if (built)
            chosen()
    }

    radius: theme.itemRadius
    color: selected ? theme.selectedColor : hovered ? theme.hoverColor : "transparent"
    border.width: selected ? theme.frameWidth : 1
    border.color: selected ? theme.accentColor : hovered ? theme.faintColor : theme.lineColor
    activeFocusOnTab: built
    Accessible.role: Accessible.RadioButton
    Accessible.name: "Layout " + layout.id + ", " + layout.name + (selected ? ", selected" : built ? "" : ", coming next")
    Accessible.checkable: true
    Accessible.checked: selected
    Accessible.focusable: built
    Accessible.onPressAction: choose()
    Keys.onReturnPressed: choose()
    Keys.onEnterPressed: choose()
    Keys.onSpacePressed: choose()

    // The ornament of the layout on the selected card (Layout C: the corner brackets).
    Loader {
        id: cardOrnament
        anchors.fill: parent
        sourceComponent: card.selected ? card.theme.decoration : null
        Binding { target: cardOrnament.item; property: "tone"; value: card.theme.accentColor }
    }

    // The keyboard focus: a ring outside the card.
    Rectangle {
        readonly property bool isFocusRing: true
        visible: card.activeFocus
        anchors.fill: parent
        anchors.margins: -4
        radius: card.radius > 0 ? card.radius + 4 : 0
        color: "transparent"
        border.width: 2
        border.color: card.theme.textColor
    }

    Item {
        id: content
        x: 8
        y: 8
        width: parent.width - 16
        height: parent.height - 16
        opacity: card.built ? 1 : 0.4

        Rectangle {
            width: parent.width
            height: 116
            radius: Math.min(3, card.theme.itemRadius)
            color: "#05070a"
            Image {
                readonly property bool isPreview: true
                anchors.centerIn: parent
                width: parent.width
                height: parent.height - 8
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true
                source: card.layout.preview
            }
        }
        Text {
            id: cardName
            y: 124
            width: parent.width
            height: card.nameHeight
            verticalAlignment: Text.AlignVCenter
            text: card.layout.id + " — " + card.layout.name
            color: card.theme.textColor
            elide: Text.ElideRight
            font {
                family: card.theme.fontFamily; pixelSize: card.theme.bodySize + 1
                weight: Font.DemiBold
                capitalization: card.theme.uppercaseTitles ? Font.AllUppercase : Font.MixedCase
            }
        }
        Text {
            id: cardDescription
            y: cardName.y + cardName.height + 6
            width: parent.width
            // Two lines for every card in every theme.
            height: card.descriptionHeight
            clip: true
            text: card.layout.description
            color: card.theme.dimColor
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
            font {
                family: card.theme.fontFamily
                pixelSize: Math.min(card.theme.size(12), card.theme.smallSize + 1)
            }
        }
        // The state of the card, in words.
        Rectangle {
            readonly property bool isTag: true
            visible: card.selected || !card.built
            y: cardDescription.y + cardDescription.height + 8
            width: tagText.implicitWidth + 12
            height: card.tagHeight
            radius: Math.min(9, card.theme.itemRadius)
            color: card.selected ? card.theme.accentColor : card.theme.lineColor
            Text {
                id: tagText
                anchors.centerIn: parent
                text: card.selected ? "SELECTED" : "COMING NEXT"
                // On the accent: the dark ink of this window, or the light ink on a dark accent.
                color: card.selected ? card.theme.inkOn(card.theme.accentColor, card.tagInk) : card.theme.textColor
                font {
                    family: card.theme.fontFamily; pixelSize: card.theme.size(9)
                    letterSpacing: 1; weight: Font.Bold
                }
            }
        }
    }

    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: card.built ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: {
            if (card.built)
                card.forceActiveFocus()
            card.choose()
        }
    }
}
