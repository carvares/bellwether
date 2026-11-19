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
    // {state, label, count, attention, alert, color, share, start, agents}:
    //   attention  the state needs the person (blocked, done), with or without agents
    //   alert      attention, and the state has an agent
    //   share      count / total, from 0 to 1 (0 with no agents)
    //   start      the sum of the shares of the states before this one: where its part of a ring or strip starts
    //   agents     the rows of the group in their order: {key, icon, label, detail, address, spoken}
    // Offline, every count is 0.
    readonly property var groups: {
        var source = backend.groups
        var sum = 0
        var i
        for (i = 0; i < source.length; i++)
            sum += source[i].count
        var out = []
        var before = 0
        for (i = 0; i < source.length; i++) {
            var g = source[i]
            out.push({state: g.state, label: g.label, count: g.count, attention: g.attention,
                      alert: g.attention && g.count > 0, color: stateColors[g.state],
                      share: sum > 0 ? g.count / sum : 0, start: sum > 0 ? before / sum : 0, agents: g.agents})
            before += g.count
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
    // A list shows this many rows at the most. A longer group scrolls. rowsFor() is the one place that
    // applies it. Read-only: a skin cannot change it (a test makes a controller with a different cap through an
    // initial property).
    readonly property int maxAgentRows: 8
    // The rows of the open group that are on the screen, and true when the group has more.
    readonly property int shown: rowsFor(agents.length)
    readonly property bool scrolls: agents.length > shown

    // ----- the jump -----

    // The key of the agent that a jump goes to now. "" when no jump runs. Its row shows "opening…".
    readonly property string opening: backend.opening
    // The colours of a failure message and of "opening…", the same in every layout (see AgentRow.note).
    readonly property color failedColor: "#f28b82"
    readonly property color openingColor: "#8ab4f8"
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

    // The status item or agent row under the pointer, for the pointer look of a skin. The window gives it with
    // hover(). null during a drag, and for a status item that cannot open (see canOpen).
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

    // The number of rows that a list shows for a group of `count` agents.
    function rowsFor(count) {
        return Math.min(count, maxAgentRows)
    }

    // True when a click on the status item of this state opens its group: Herdr answers and the state has an
    // agent. A status item that cannot open is inert: no pointer look, and no change on a click.
    function canOpen(stateName) {
        return backend.online && countOf(stateName) > 0
    }

    // The window tells which target is under the pointer (null: none).
    function hover(item) {
        hoverItem = item && item.hitRole === "status" && !canOpen(item.stateName) ? null : item
    }

    // Open the group, or close it when it is open. A group without agents does not open.
    function toggle(stateName) {
        if (openState === stateName)
            openState = ""
        else if (canOpen(stateName))
            openState = stateName
    }

    // Show the agent in the Herdr app. One jump at a time: a call while a jump runs does nothing.
    function jump(key) {
        backend.focus(key)
    }

    // The parts of a share strip of `width` pixels, one for each of the four groups in their order, as
    // {x, width}. A gap of `gap` pixels is between two parts. A group with no agents has the width 0 and takes
    // no gap. The widths are in proportion to the counts, but a group with an agent is never narrower than
    // `minimum`: the wider parts give that space. All widths are 0 with no agents and offline.
    function strip(width, gap, minimum) {
        var list = groups
        var avail = width - gap * Math.max(0, parts - 1)
        var small = []  // the groups that get the minimum
        var i
        for (var round = 0; round < list.length; round++) {
            var rest = 0  // the sum of the shares of the other groups
            for (i = 0; i < list.length; i++)
                if (list[i].count > 0 && small.indexOf(i) < 0)
                    rest += list[i].share
            var found = false
            for (i = 0; i < list.length; i++)
                if (list[i].count > 0 && small.indexOf(i) < 0
                        && (avail - minimum * small.length) * list[i].share / rest < minimum) {
                    small.push(i)
                    found = true
                }
            if (!found)
                break
        }
        var out = []
        var x = 0
        for (i = 0; i < list.length; i++) {
            var w = list[i].count === 0 ? 0
                : small.indexOf(i) >= 0 ? minimum : (avail - minimum * small.length) * list[i].share / rest
            out.push({x: x, width: w})
            if (w > 0)
                x += w + gap
        }
        return out
    }

    // The arcs of a share ring, one for each of the four groups in their order, as {start, sweep} in radians;
    // `start` is from the top of the ring, clockwise. A gap of `gap` radians is between two arcs (no gap with
    // one arc: it is the full circle). The arc of a group is its share of the circle less the gap, but a group
    // with an agent is never shorter than `minimum`: the longest arcs give that space. The sweeps and the gaps
    // fill the circle. A group with no agents has the sweep 0. All sweeps are 0 with no agents and offline.
    function ring(gap, minimum) {
        var list = groups
        var full = 2 * Math.PI
        var space = parts > 1 ? gap : 0
        var sweeps = []
        var i
        for (i = 0; i < list.length; i++)
            sweeps.push(list[i].count === 0 ? 0 : list[i].share * full - space)
        for (i = 0; i < list.length; i++) {
            if (list[i].count === 0 || sweeps[i] >= minimum)
                continue
            var big = 0
            for (var k = 1; k < sweeps.length; k++)
                if (sweeps[k] > sweeps[big])
                    big = k
            sweeps[big] -= minimum - sweeps[i]
            sweeps[i] = minimum
        }
        var out = []
        var at = space / 2
        for (i = 0; i < list.length; i++) {
            out.push({start: at, sweep: sweeps[i]})
            if (sweeps[i] > 0)
                at += sweeps[i] + space
        }
        return out
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

    // "#rrggbb" with an alpha from 0 to 1 as the text "#aarrggbb": the alpha has 8 bits, as in the mock-ups.
    function tint(hex, alpha) {
        var a = Math.round(alpha * 255).toString(16)
        return "#" + (a.length < 2 ? "0" + a : a) + ("" + hex).substring(1)
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
            panel.hover(panel.hoverItem)  // the status item under the pointer can have no agents now
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
