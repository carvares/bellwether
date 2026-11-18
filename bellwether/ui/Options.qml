// The options window: a normal window (not a layer surface) that the tray entry "Options…" opens.
// One column of sections. Now one section: the layout of the panel, as five cards.
import QtQuick
import QtQuick.Window

Window {
    id: options

    readonly property color ground: "#0b0e11"
    readonly property color plate: "#12161a"
    readonly property color line: "#2b333b"
    readonly property color dim: "#8a949e"
    readonly property color ink: "#e3e9ee"
    readonly property color accent: "#8ab4f8"
    readonly property int pad: 24
    readonly property int cardWidth: 196
    readonly property int cardGap: 12

    title: "Bellwether — Options"
    color: ground
    // The size is fixed: the content has one size.
    readonly property int fixedWidth: sections.width + 2 * pad
    readonly property int fixedHeight: sections.height + 2 * pad
    width: fixedWidth
    height: fixedHeight
    minimumWidth: fixedWidth
    maximumWidth: fixedWidth
    minimumHeight: fixedHeight
    maximumHeight: fixedHeight

    // At each open the keyboard starts on the card of the layout that shows.
    onVisibleChanged: if (visible) focusSelected()

    function focusSelected() {
        for (var i = 0; i < cards.count; i++)
            if (cards.itemAt(i).selected)
                cards.itemAt(i).forceActiveFocus()
    }

    Shortcut {
        sequences: [StandardKey.Cancel]
        onActivated: options.close()
    }

    // One section of the window: a title and its content below it.
    component Section: Column {
        property alias title: heading.text
        spacing: 14
        Text {
            id: heading
            color: options.dim
            font { pixelSize: 11; letterSpacing: 2; weight: Font.DemiBold; capitalization: Font.AllUppercase }
        }
    }

    Column {
        id: sections
        x: options.pad
        y: options.pad
        spacing: 28

        Section {
            title: "Layout"

            Row {
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
                        height: content.height + 16
                        radius: 6
                        color: selected ? Qt.rgba(options.accent.r, options.accent.g, options.accent.b, 0.10)
                            : hovered ? "#1a2026" : options.plate
                        border.width: selected ? 2 : 1
                        border.color: selected ? options.accent : hovered ? "#68727c" : options.line
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

                        // The keyboard focus: a ring outside the card.
                        Rectangle {
                            readonly property bool isFocusRing: true
                            visible: card.activeFocus
                            anchors.fill: parent
                            anchors.margins: -4
                            radius: card.radius + 4
                            color: "transparent"
                            border.width: 2
                            border.color: options.ink
                        }

                        Column {
                            id: content
                            x: 8
                            y: 8
                            width: parent.width - 16
                            spacing: 8
                            opacity: card.built ? 1 : 0.4

                            Rectangle {
                                width: parent.width
                                height: 116
                                radius: 3
                                color: "#05070a"
                                Image {
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
                                width: parent.width
                                text: card.modelData.id + " — " + card.modelData.name
                                color: options.ink
                                elide: Text.ElideRight
                                font { pixelSize: 14; weight: Font.DemiBold }
                            }
                            Text {
                                width: parent.width
                                // Two lines for every card, so the cards have one height.
                                height: Math.ceil(2 * lines.lineSpacing) + 1
                                text: card.modelData.description
                                color: options.dim
                                wrapMode: Text.WordWrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                font.pixelSize: 12
                                FontMetrics { id: lines; font.pixelSize: 12 }
                            }
                            // The state of the card, in words. The line is there for every card, so the
                            // cards have one height.
                            Item {
                                width: parent.width
                                height: 18
                                Rectangle {
                                    readonly property bool isTag: true
                                    visible: card.selected || !card.built
                                    width: tagText.implicitWidth + 12
                                    height: parent.height
                                    radius: 3
                                    color: card.selected ? options.accent : "#3a444d"
                                    Text {
                                        id: tagText
                                        anchors.centerIn: parent
                                        text: card.selected ? "SELECTED" : "COMING NEXT"
                                        color: card.selected ? "#0b0e11" : options.ink
                                        font { pixelSize: 9; letterSpacing: 1; weight: Font.Bold }
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
                }
            }
        }
    }
}
