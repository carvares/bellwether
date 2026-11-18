// The agents of one group as a list for a skin: at most panel.maxAgentRows rows on the screen, and a longer
// group scrolls with the wheel. The skin gives the look of a row (`delegate`, an AgentRow) and can put a
// decoration over the rows (`overlay`). The list keeps its scroll position when new data comes.
import QtQuick

Item {
    id: list

    // The controller (PanelModel).
    required property PanelModel panel
    // The group that this list shows. The default is the open group: one list for the skin. A skin with one
    // list in each group sets the state of that group.
    property string stateName: panel.openState
    // The height of one row.
    property int rowHeight: 28
    // The look of one row: an AgentRow with `view` set to this list and the drawing as its children.
    property Component delegate
    // A decoration over the rows that does not scroll with them, at (0, 0) of the list: a scroll track, a fade.
    // Its parent has no size, so the pointer handler of the window does not find it (it uses childAt): a click
    // or a wheel turn on the decoration goes to the row below it.
    property Component overlay

    readonly property var group: panel.groupOf(stateName)
    // True when this list shows its rows: its group is the open one.
    readonly property bool open: stateName !== "" && panel.openState === stateName
    // The number of agents of the group, and the number of rows on the screen.
    readonly property int count: group ? group.count : 0
    readonly property int shown: panel.rowsFor(count)
    // More rows than fit: the list scrolls. A skin then shows a scroll hint.
    readonly property bool longer: count > shown
    // The number of the first row on the screen, from 0.
    readonly property int first: Math.round(view.contentY / rowHeight)
    // True when the last row is on the screen.
    readonly property bool atEnd: view.contentY >= view.contentHeight - view.height
    // The scroll position in pixels, and the height of all the rows.
    readonly property real contentY: view.contentY
    readonly property real contentHeight: view.contentHeight

    implicitHeight: shown * rowHeight

    // A group that opens starts at its first row: also a different group in the one list of a skin.
    onStateNameChanged: view.contentY = 0
    onOpenChanged: if (open) view.contentY = 0

    Flickable {
        id: view
        // The pointer handler of the window scrolls the list under the pointer with the wheel.
        readonly property string hitRole: "scroll"
        anchors.fill: parent
        contentWidth: width
        contentHeight: rows.height
        interactive: false
        clip: true
        onContentHeightChanged: contentY = Math.max(0, Math.min(contentY, contentHeight - height))

        // One turn of the wheel. `pixels` is the distance from a touchpad, else `angle` (120 for one step of a
        // mouse wheel: two rows).
        function scrollBy(pixels, angle) {
            var step = pixels !== 0 ? pixels : angle / 120 * 2 * list.rowHeight
            contentY = Math.max(0, Math.min(contentY - step, contentHeight - height))
        }

        Column {
            id: rows
            width: view.width

            Repeater {
                model: list.open && list.group ? list.group.agents : []
                delegate: list.delegate
            }
        }
    }

    Item {
        Loader { sourceComponent: list.overlay }
    }
}
