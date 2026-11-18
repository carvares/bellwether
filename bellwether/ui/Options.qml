// The options window: a normal window (an xdg toplevel, not a layer surface) that the tray entry "Options…"
// opens. It has no title bar of the system: it draws its own frame and header in the style of the layout that
// shows (the theme tokens of that skin, skins/<letter>Theme.qml), and it changes when the layout changes.
// One column of sections. Now one section: the layout of the panel, as five cards. The places and the sizes of
// the cards are the same in every theme: only the styling changes.
import QtQuick
import QtQuick.Window
import "skins" as Skins

Window {
    id: options

    // The theme tokens of the layout that shows. The tokens of Layout C while a theme file loads or is missing.
    readonly property QtObject theme: themeLoader.item ? themeLoader.item : fallbackTheme
    readonly property int pad: 24
    readonly property int headerHeight: 44
    readonly property int cardWidth: 196
    readonly property int cardHeight: 226
    readonly property int cardGap: 12
    // The header asks for a move of the window: the compositor moves it (no position code here).
    signal systemMoveRequested()

    title: "Bellwether — Options"
    flags: Qt.Window | Qt.FramelessWindowHint
    // The frame can have round corners: the window itself has no background.
    color: "transparent"
    // The size is fixed, and the same in every theme: the content has one size.
    readonly property int fixedWidth: 5 * cardWidth + 4 * cardGap + 2 * pad
    readonly property int fixedHeight: headerHeight + 20 + sectionTitle.height + 14 + cardHeight + pad
    width: fixedWidth
    height: fixedHeight
    minimumWidth: fixedWidth
    maximumWidth: fixedWidth
    minimumHeight: fixedHeight
    maximumHeight: fixedHeight

    // At each open the keyboard starts on the card of the layout that shows.
    onVisibleChanged: if (visible) focusSelected()
    onSystemMoveRequested: options.startSystemMove()

    function focusSelected() {
        for (var i = 0; i < cards.count; i++)
            if (cards.itemAt(i).selected)
                cards.itemAt(i).forceActiveFocus()
    }

    Shortcut {
        sequences: [StandardKey.Cancel]
        onActivated: options.close()
    }

    Skins.CTheme { id: fallbackTheme }
    Loader {
        id: themeLoader
        source: backend.themeSource
    }

    // The frame of the window, as the frame of the panel. Its colour is the neutral one: this window does
    // not show a status.
    Rectangle {
        id: frame
        readonly property bool isFrame: true
        anchors.fill: parent
        radius: options.theme.radius
        color: options.theme.panelColor
        border.width: options.theme.frameWidth
        border.color: options.theme.frameColor

        // The frame ornament of the layout (the corner brackets of Layout C), in its neutral colour.
        Loader {
            anchors.fill: parent
            sourceComponent: options.theme.decoration
        }

        // The header: the title, and the close control at the right. A press that moves 6 px or more moves
        // the window.
        Item {
            id: header
            readonly property bool isHeader: true
            width: parent.width
            height: options.headerHeight

            MouseArea {
                id: grip
                anchors.fill: parent
                property real startX: 0
                property real startY: 0
                property bool moving: false
                onPressed: (mouse) => { startX = mouse.x; startY = mouse.y; moving = false }
                onPositionChanged: (mouse) => {
                    if (!pressed || moving || Math.abs(mouse.x - startX) + Math.abs(mouse.y - startY) < 6)
                        return
                    moving = true
                    options.systemMoveRequested()
                }
            }
            Text {
                readonly property bool isTitle: true
                x: options.pad
                anchors.verticalCenter: parent.verticalCenter
                text: "Bellwether — Options"
                color: options.theme.dimColor
                font {
                    family: options.theme.fontFamily; pixelSize: options.theme.titleSize; weight: Font.DemiBold
                    letterSpacing: options.theme.letterSpacing
                    capitalization: options.theme.uppercaseTitles ? Font.AllUppercase : Font.MixedCase
                }
            }
            Rectangle {
                id: closeControl
                readonly property bool isClose: true
                anchors.right: parent.right
                anchors.rightMargin: 10
                anchors.verticalCenter: parent.verticalCenter
                width: 28
                height: 28
                radius: options.theme.itemRadius
                color: closeArea.containsMouse ? options.theme.hoverColor : "transparent"
                Accessible.role: Accessible.Button
                Accessible.name: "Close"
                Accessible.onPressAction: options.close()
                Repeater {
                    model: [45, -45]
                    Rectangle {
                        required property int modelData
                        anchors.centerIn: parent
                        width: 13
                        height: 1.5
                        rotation: modelData
                        antialiasing: true
                        color: closeArea.containsMouse ? options.theme.textColor : options.theme.dimColor
                    }
                }
                MouseArea {
                    id: closeArea
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: options.close()
                }
            }
            Rectangle {
                x: options.theme.frameWidth
                anchors.bottom: parent.bottom
                width: parent.width - 2 * x
                height: 1
                color: options.theme.lineColor
            }
        }

        // The section "Layout": its title and the five cards.
        Text {
            id: sectionTitle
            x: options.pad
            y: options.headerHeight + 20
            height: 16
            verticalAlignment: Text.AlignVCenter
            text: "Layout"
            color: options.theme.dimColor
            font {
                family: options.theme.fontFamily; pixelSize: options.theme.smallSize; weight: Font.DemiBold
                letterSpacing: options.theme.letterSpacing
                capitalization: options.theme.uppercaseTitles ? Font.AllUppercase : Font.MixedCase
            }
        }

        Row {
            x: options.pad
            y: sectionTitle.y + sectionTitle.height + 14
            spacing: options.cardGap

            Repeater {
                id: cards
                model: backend.layouts

                // One layout. A layout that is not built yet is dim and cannot be chosen.
                Rectangle {
                    id: card
                    required property var modelData
                    readonly property string layoutId: modelData.id
                    readonly property bool built: modelData.built
                    readonly property bool selected: backend.layout === modelData.id
                    readonly property bool hovered: built && pointer.containsMouse

                    function choose() {
                        if (built)
                            backend.setLayout(modelData.id)
                    }

                    width: options.cardWidth
                    height: options.cardHeight
                    radius: options.theme.itemRadius
                    color: selected ? options.theme.selectedColor : hovered ? options.theme.hoverColor : "transparent"
                    border.width: selected ? options.theme.frameWidth : 1
                    border.color: selected ? options.theme.accentColor
                        : hovered ? options.theme.faintColor : options.theme.lineColor
                    activeFocusOnTab: built
                    Accessible.role: Accessible.RadioButton
                    Accessible.name: "Layout " + modelData.id + ", " + modelData.name
                        + (selected ? ", selected" : built ? "" : ", coming next")
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
                        sourceComponent: card.selected ? options.theme.decoration : null
                        Binding { target: cardOrnament.item; property: "tone"; value: options.theme.accentColor }
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
                        border.color: options.theme.textColor
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
                            radius: Math.min(3, options.theme.itemRadius)
                            color: "#05070a"
                            Image {
                                readonly property bool isPreview: true
                                anchors.centerIn: parent
                                width: parent.width
                                height: parent.height - 8
                                fillMode: Image.PreserveAspectFit
                                smooth: true
                                mipmap: true
                                source: card.modelData.preview
                            }
                        }
                        Text {
                            y: 124
                            width: parent.width
                            height: 20
                            verticalAlignment: Text.AlignVCenter
                            text: card.modelData.id + " — " + card.modelData.name
                            color: options.theme.textColor
                            elide: Text.ElideRight
                            font {
                                family: options.theme.fontFamily; pixelSize: options.theme.bodySize + 1
                                weight: Font.DemiBold
                                capitalization: options.theme.uppercaseTitles ? Font.AllUppercase : Font.MixedCase
                            }
                        }
                        Text {
                            y: 150
                            width: parent.width
                            // Two lines for every card in every theme.
                            height: 34
                            clip: true
                            text: card.modelData.description
                            color: options.theme.dimColor
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            font { family: options.theme.fontFamily; pixelSize: Math.min(12, options.theme.smallSize + 1) }
                        }
                        // The state of the card, in words.
                        Rectangle {
                            readonly property bool isTag: true
                            visible: card.selected || !card.built
                            y: 192
                            width: tagText.implicitWidth + 12
                            height: 18
                            radius: Math.min(9, options.theme.itemRadius)
                            color: card.selected ? options.theme.accentColor : options.theme.lineColor
                            Text {
                                id: tagText
                                anchors.centerIn: parent
                                text: card.selected ? "SELECTED" : "COMING NEXT"
                                color: card.selected ? "#0b0e11" : options.theme.textColor
                                font { family: options.theme.fontFamily; pixelSize: 9; letterSpacing: 1; weight: Font.Bold }
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
            }
        }
    }
}
