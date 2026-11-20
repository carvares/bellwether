// The chooser of the font family in the options window: a button with the family in effect; activating it opens,
// below it and inside the window, a filter field and the list: "Layout default" first, then the families. Each
// family shows in its own typeface (the list makes only the rows on the screen). Typing in the field filters the
// list; the arrows move the mark, Enter and Return choose, and so does a click. Only theme tokens.
import QtQuick

Item {
    id: chooser

    required property QtObject theme
    // The families that can be chosen, and the family in effect ("": each layout has its own font).
    property var families: []
    property string current: ""
    property bool open: false
    readonly property string defaultName: "Layout default"
    // The rows of the list: "" (the default) and the families that have the text of the filter in their name.
    readonly property var rows: {
        var wanted = filter.text.trim().toLowerCase()
        var found = [""]
        for (var i = 0; i < families.length; i++)
            if (wanted === "" || families[i].toLowerCase().indexOf(wanted) >= 0)
                found.push(families[i])
        return found
    }
    readonly property int rowHeight: theme.fit(26)
    readonly property int visibleRows: 6
    readonly property bool isFontChooser: true
    signal chosen(string family)

    function show() {
        open = true
        filter.text = ""
        list.currentIndex = Math.max(0, rows.indexOf(current))
        list.positionViewAtIndex(list.currentIndex, ListView.Contain)
        filter.forceActiveFocus()
    }

    // Close the list. The keyboard goes back to the button.
    function hide() {
        if (!open)
            return
        open = false
        button.forceActiveFocus()
    }

    function choose(family) {
        chosen(family)
        hide()
    }

    // Enter in the filter field: the marked row. With a filter that no family matches, nothing (the default is
    // not what the user typed).
    function chooseMarked() {
        if (rows.length > 1 || filter.text.trim() === "")
            choose(rows[list.currentIndex])
    }

    implicitWidth: 360
    implicitHeight: button.height + (open ? 8 + filterBox.height + 6 + listBox.height : 0)
    height: implicitHeight

    Rectangle {
        id: button
        readonly property bool isFontButton: true
        readonly property bool hovered: buttonArea.containsMouse
        width: parent.width
        height: chooser.theme.fit(28)
        radius: Math.min(6, chooser.theme.itemRadius)
        color: hovered ? chooser.theme.hoverColor : "transparent"
        border.width: 1
        border.color: chooser.open ? chooser.theme.accentColor
            : hovered || activeFocus ? chooser.theme.faintColor : chooser.theme.lineColor
        activeFocusOnTab: true
        Accessible.role: Accessible.ComboBox
        Accessible.name: "Font, " + (chooser.current === "" ? chooser.defaultName : chooser.current)
        Accessible.focusable: true
        Accessible.onPressAction: chooser.open ? chooser.hide() : chooser.show()
        Keys.onReturnPressed: chooser.open ? chooser.hide() : chooser.show()
        Keys.onEnterPressed: chooser.open ? chooser.hide() : chooser.show()
        Keys.onSpacePressed: chooser.open ? chooser.hide() : chooser.show()
        Keys.onDownPressed: chooser.show()

        Text {
            readonly property bool isFontName: true
            x: 10
            width: parent.width - 34
            height: parent.height
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            text: chooser.current === "" ? chooser.defaultName : chooser.current
            color: chooser.theme.textColor
            font { family: chooser.theme.fontFamily; pixelSize: chooser.theme.bodySize }
        }
        // The mark of a list that opens: two lines, drawn (a font of the user can lack an arrow).
        Item {
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            width: 9
            height: 5
            rotation: chooser.open ? 180 : 0
            Repeater {
                model: [38, -38]
                Rectangle {
                    required property int modelData
                    x: modelData > 0 ? -0.5 : 3.5
                    y: 2
                    width: 6
                    height: 1.5
                    rotation: modelData
                    antialiasing: true
                    color: chooser.theme.dimColor
                }
            }
        }
        MouseArea {
            id: buttonArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: chooser.open ? chooser.hide() : chooser.show()
        }
        FocusRing { target: button; corner: button.radius; border.color: chooser.theme.textColor }
    }

    Rectangle {
        id: filterBox
        visible: chooser.open
        y: button.height + 8
        width: parent.width
        height: chooser.theme.fit(28)
        radius: Math.min(6, chooser.theme.itemRadius)
        color: chooser.theme.panelColor
        border.width: 1
        border.color: filter.activeFocus ? chooser.theme.accentColor : chooser.theme.lineColor

        TextInput {
            id: filter
            readonly property bool isFontFilter: true
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 92
            verticalAlignment: TextInput.AlignVCenter
            clip: true
            enabled: chooser.open
            activeFocusOnTab: chooser.open
            selectByMouse: true
            maximumLength: 60
            color: chooser.theme.textColor
            selectionColor: chooser.theme.accentColor
            selectedTextColor: chooser.theme.inkOn(chooser.theme.accentColor)
            font { family: chooser.theme.fontFamily; pixelSize: chooser.theme.bodySize }
            Accessible.role: Accessible.EditableText
            Accessible.name: "Filter the fonts, " + (chooser.rows.length - 1) + " of " + chooser.families.length
            onTextEdited: {
                // The first family that matches, or the default when none does.
                list.currentIndex = chooser.rows.length > 1 && text.trim() !== "" ? 1 : 0
                list.positionViewAtIndex(list.currentIndex, ListView.Contain)
            }
            Keys.onDownPressed: list.move(1)
            Keys.onUpPressed: list.move(-1)
            Keys.onReturnPressed: chooser.chooseMarked()
            Keys.onEnterPressed: chooser.chooseMarked()
            Keys.onPressed: (event) => {
                if (event.key === Qt.Key_PageDown) list.move(chooser.visibleRows)
                else if (event.key === Qt.Key_PageUp) list.move(-chooser.visibleRows)
                else return
                event.accepted = true
            }
        }
        Text {
            visible: filter.text === ""
            x: 10
            width: parent.width - 110
            height: parent.height
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            text: "Type to filter"
            color: chooser.theme.faintColor
            font { family: chooser.theme.fontFamily; pixelSize: chooser.theme.bodySize }
        }
        Text {
            readonly property bool isFontCount: true
            anchors.right: parent.right
            anchors.rightMargin: 10
            width: 78
            height: parent.height
            verticalAlignment: Text.AlignVCenter
            horizontalAlignment: Text.AlignRight
            elide: Text.ElideRight
            text: chooser.rows.length === 1 && filter.text.trim() !== "" ? "No match" : (chooser.rows.length - 1) + " fonts"
            color: chooser.theme.faintColor
            font { family: chooser.theme.fontFamily; pixelSize: chooser.theme.size(10) }
        }
    }

    Rectangle {
        id: listBox
        visible: chooser.open
        y: filterBox.y + filterBox.height + 6
        width: parent.width
        height: chooser.visibleRows * chooser.rowHeight + 2
        radius: Math.min(6, chooser.theme.itemRadius)
        color: chooser.theme.panelColor
        border.width: 1
        border.color: chooser.theme.lineColor

        ListView {
            id: list
            readonly property bool isFontList: true
            anchors.fill: parent
            anchors.margins: 1
            clip: true
            model: chooser.open ? chooser.rows : []
            boundsBehavior: Flickable.StopAtBounds
            snapMode: ListView.SnapToItem
            highlightMoveDuration: 0
            // Only the rows on the screen exist: a family loads its typeface when its row shows.
            cacheBuffer: 0

            function move(rows) {
                currentIndex = Math.max(0, Math.min(count - 1, currentIndex + rows))
                positionViewAtIndex(currentIndex, ListView.Contain)
            }

            delegate: Rectangle {
                id: row
                required property string modelData
                required property int index
                readonly property string fontRowFor: modelData === "" ? chooser.defaultName : modelData
                readonly property bool inEffect: modelData === chooser.current
                readonly property bool marked: ListView.isCurrentItem
                width: list.width
                height: chooser.rowHeight
                // The row that Enter chooses: a plate of the accent.
                color: marked ? Qt.rgba(chooser.theme.accentColor.r, chooser.theme.accentColor.g,
                                        chooser.theme.accentColor.b, 0.24)
                    : rowArea.containsMouse ? chooser.theme.hoverColor : "transparent"
                Accessible.role: Accessible.ListItem
                Accessible.name: fontRowFor + (inEffect ? ", selected" : "")
                Accessible.onPressAction: chooser.choose(modelData)

                // The family in effect.
                Rectangle {
                    readonly property bool isCurrentFontMark: true
                    visible: row.inEffect
                    x: 0
                    width: 3
                    height: parent.height
                    color: chooser.theme.accentColor
                }
                Text {
                    x: 12
                    width: parent.width - 24
                    height: parent.height
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                    text: row.fontRowFor
                    color: row.inEffect || row.marked ? chooser.theme.textColor : chooser.theme.dimColor
                    font {
                        family: row.modelData === "" ? chooser.theme.fontFamily : row.modelData
                        pixelSize: chooser.theme.bodySize
                    }
                }
                MouseArea {
                    id: rowArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: chooser.choose(row.modelData)
                }
            }
        }
    }
}
