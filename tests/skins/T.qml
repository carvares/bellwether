// A skin only for the tests: it is not a design of the program and the options window does not list it.
// It shows that a second skin needs only the controller and the shared agent list: four status rows of 20 px
// and one list for the open group below them.
import QtQuick
import "../../bellwether/ui"

Item {
    id: skin

    required property PanelModel panel

    implicitWidth: 240
    implicitHeight: column.height

    Column {
        id: column
        width: skin.implicitWidth

        Repeater {
            model: 4
            Item {
                required property int index
                readonly property var group: skin.panel.groups[index]
                readonly property string hitRole: "status"
                readonly property string stateName: group.state
                width: column.width
                height: 20
                Text { text: parent.group.label + " " + parent.group.count }
            }
        }

        AgentList {
            id: agentList
            panel: skin.panel
            rowHeight: 20
            width: column.width
            delegate: AgentRow {
                view: agentList
                Text { text: parent.modelData.label }
            }
        }
    }
}
