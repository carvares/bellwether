// The state and the rules of the panel that every layout (skin) uses. A skin reads this object and calls
// toggle() and jump(). A skin does not talk to the backend. The contract is in the spec
// (docs/superpowers/specs/2026-11-18-bellwether-design.md, "options window and layout skins").
import QtQuick

QtObject {
    id: panel

    // ----- data -----

    readonly property bool online: backend.online
    // "#rrggbb" for "blocked", "done", "working", "idle", "offline" and "none".
    readonly property var stateColors: stateColors_
    // The four states in the display order (blocked, done, working, idle), always four. Each is
    // {state, label, count, attention, alert, color, share, agents}:
    //   attention  the state needs the person (blocked, done), with or without agents
    //   alert      attention, and the state has an agent
    //   share      count / total, from 0 to 1 (0 with no agents)
    //   agents     the rows of the group in their order: {key, icon, label, detail, address, spoken}
    // Offline, every count is 0.
    readonly property var groups: {
        var source = backend.groups
        var sum = 0
        var i
        for (i = 0; i < source.length; i++)
            sum += source[i].count
        var out = []
        for (i = 0; i < source.length; i++) {
            var g = source[i]
            out.push({state: g.state, label: g.label, count: g.count, attention: g.attention,
                      alert: g.attention && g.count > 0, color: stateColors[g.state],
                      share: sum > 0 ? g.count / sum : 0, agents: g.agents})
        }
        return out
    }
    // The sum of the four counts. 0 when Herdr is offline.
    readonly property int total: {
        var sum = 0
        var list = backend.online ? backend.groups : []
        for (var i = 0; i < list.length; i++)
            sum += list[i].count
        return sum
    }
    // The number of states that have an agent.
    readonly property int parts: {
        var n = 0
        for (var i = 0; i < groups.length; i++)
            if (groups[i].count > 0)
                n++
        return n
    }
    // The most important state that has an agent: "blocked", "done", "idle" or "working". "none" with no
    // agents, "offline" when Herdr does not answer. The tray icon shows the same state.
    readonly property string topState: backend.topState
    // True with no agents and offline: a skin then shows its neutral colour and not topColor.
    readonly property bool quiet: topState === "none" || topState === "offline"
    readonly property color topColor: stateColors[topState]
    // "Blocked", "Done", "Idle", "Working", "No agents" or "Offline".
    readonly property string topLabel: topState === "none" ? "No agents"
        : topState.charAt(0).toUpperCase() + topState.substring(1)
    // The count of the top state. 0 when quiet.
    readonly property int topCount: quiet ? 0 : countOf(topState)
    // The top state as a short badge: "1 blocked", "3 working", "No agents", "Offline".
    readonly property string topBadge: quiet ? topLabel : topCount + " " + topState
    // The states of the lit cells of a cell bar in the row order: one cell for each agent up to cellLimit
    // agents, shared in proportion with more. Empty with no agents and offline.
    readonly property int cellLimit: 60
    readonly property var cells: cellStates(backend.online ? backend.groups : [], cellLimit)

    // ----- the open group -----

    // The state whose agents show ("blocked", ...). "" means that no group is open. One group at a time.
    property string openState: ""
    // The open group (one of groups), or null.
    readonly property var openGroup: openState === "" ? null : groupOf(openState)
    readonly property string openLabel: openGroup ? openGroup.label : ""
    readonly property color openColor: openGroup ? openGroup.color : stateColors["none"]
    // The rows of the open group. Empty with no open group.
    readonly property var agents: openGroup ? openGroup.agents : []
    // A list shows this many rows at the most. A longer group scrolls.
    readonly property int maxAgentRows: 8
    // The rows of the open group that are on the screen, and true when the group has more.
    readonly property int shown: Math.min(agents.length, maxAgentRows)
    readonly property bool scrolls: agents.length > maxAgentRows

    // ----- the jump -----

    // The key of the agent that a jump goes to now. "" when no jump runs. Its row shows "opening…".
    readonly property string opening: backend.opening
    // The agent of the last failed jump and the message for it. Empty again after 3 seconds.
    property string failedKey: ""
    property string failedMessage: ""
    // The group that holds the failed agent now. "" when the agent is in no group (gone, or offline).
    readonly property string failedState: failedKey === "" ? "" : stateOf(failedKey)
    // The group of the failed agent that was opened for the message. The message opens a group one time,
    // and again only when the agent goes to a different group, so the person can close or change the group.
    property string failedShownIn: ""
    // True when the failed agent has no row (the agent is gone, or Herdr is offline): the skin shows
    // failedMessage in a line of its own. With a row, the row of failedKey shows the message.
    readonly property bool failedAlone: failedKey !== "" && failedState === ""

    // ----- the pointer -----

    // The status row or agent row under the pointer. The window sets it. null during a drag.
    property Item hoverItem: null

    // ----- rules -----

    function groupOf(stateName) {
        for (var i = 0; i < groups.length; i++)
            if (groups[i].state === stateName)
                return groups[i]
        return null
    }

    function countOf(stateName) {
        var list = backend.groups
        for (var i = 0; i < list.length; i++)
            if (list[i].state === stateName)
                return list[i].count
        return 0
    }

    function stateOf(key) {
        var list = backend.online ? backend.groups : []
        for (var i = 0; i < list.length; i++)
            for (var j = 0; j < list[i].agents.length; j++)
                if (list[i].agents[j].key === key)
                    return list[i].state
        return ""
    }

    // Open the group, or close it when it is open. A group without agents does not open.
    function toggle(stateName) {
        if (openState === stateName)
            openState = ""
        else if (backend.online && countOf(stateName) > 0)
            openState = stateName
    }

    // Show the agent in the Herdr app. One jump at a time: a call while a jump runs does nothing.
    function jump(key) {
        backend.focus(key)
    }

    // The name of a status row for a screen reader: "Blocked, 1 agent".
    function spokenStatus(group) {
        return group.label + ", " + group.count + (group.count === 1 ? " agent" : " agents")
    }

    function pad2(n) {
        return n < 10 ? "0" + n : "" + n
    }

    // "#rrggbb" with an alpha from 0 to 1.
    function faded(hex, alpha) {
        var c = Qt.color(hex)
        return Qt.rgba(c.r, c.g, c.b, alpha)
    }

    // The states of the lit cells of the bar, in the row order. One cell for each agent up to `limit` agents.
    // With more agents the `limit` cells are shared in proportion, and a state with an agent has at least one.
    function cellStates(list, limit) {
        var sum = 0
        var i
        for (i = 0; i < list.length; i++)
            sum += list[i].count
        var share = []
        for (i = 0; i < list.length; i++)
            share.push(sum <= limit ? list[i].count
                : list[i].count === 0 ? 0 : Math.max(1, Math.floor(list[i].count * limit / sum)))
        if (sum > limit) {
            var used = share.reduce((a, b) => a + b, 0)
            while (used !== limit) {  // Give the cells that are left to, or take the extra ones from, the biggest state.
                var big = 0
                for (i = 1; i < share.length; i++)
                    if (share[i] > share[big])
                        big = i
                share[big] += used < limit ? 1 : -1
                used += used < limit ? 1 : -1
            }
        }
        var out = []
        for (i = 0; i < list.length; i++)
            for (var k = 0; k < share[i]; k++)
                out.push(list[i].state)
        return out
    }

    property Connections backendLink: Connections {
        target: backend
        function onChanged() {
            // Close the group when Herdr goes offline, so that it does not open by itself when Herdr comes back.
            if (!backend.online) {
                panel.openState = ""
                return
            }
            // The failed agent can change its state: keep its message on the screen.
            // stateOf() and not failedState: that binding can be older than this signal.
            var failedNow = panel.failedKey === "" ? "" : panel.stateOf(panel.failedKey)
            if (failedNow !== panel.failedShownIn) {
                panel.failedShownIn = failedNow
                if (failedNow !== "")
                    panel.openState = failedNow
            }
            if (panel.openState !== "" && panel.countOf(panel.openState) === 0)
                panel.openState = ""
        }
        function onFocusFailed(key, message) {
            panel.failedKey = key
            panel.failedMessage = message
            panel.failedShownIn = panel.stateOf(key)
            if (panel.failedShownIn !== "")
                panel.openState = panel.failedShownIn
            panel.failTimer.restart()
        }
    }

    property Timer failTimer: Timer {
        interval: 3000
        onTriggered: { panel.failedKey = ""; panel.failedMessage = ""; panel.failedShownIn = "" }
    }
}
