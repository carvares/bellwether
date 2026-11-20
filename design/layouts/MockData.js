.pragma library
// Made-up data for the layout mock-ups. Every layout draws the same scenes, so the images can be compared.

var ORDER = ["blocked", "done", "working", "idle"]
var TOP_ORDER = ["blocked", "done", "idle", "working"]
var LABELS = { blocked: "Blocked", done: "Done", working: "Working", idle: "Idle" }
var COLORS = { blocked: "#f28b82", done: "#fdd663", working: "#8ab4f8", idle: "#81c995" }
var NEUTRAL = "#5f6368"
var MAX_ROWS = 8

// program word, label (terminal name, or workspace text when there is no name), workspace at the right, address
function agent(program, label, detail, address) {
    return { program: program, label: label, detail: detail || "", address: address || "" }
}

var WORKING = [
    agent("claude-code", "reviewer", "api / fix login"),
    agent("opencode", "docs", "", "t4"),
    agent("opencode", "docs", "", "t5"),
]

var IDLE = [
    agent("gemini", "planner", "Main"),
    agent("codex", "builder", "api / fix login"),
    agent("pi", "docs"),
    agent("claude-code", "tester", "api / fix login"),
    agent("opencode", "Main", "", "t9"),
    agent("opencode", "Main", "", "t11"),
    agent("gemini", "scribe", "docs"),
    agent("pi", "linter", "Main"),
    agent("codex", "api / fix login"),
    agent("claude-code", "migrator", "db / schema"),
    agent("pi", "infra"),
    agent("codex", "helper", "Main"),
]

var SCENES = {
    "closed":   { counts: [1, 2, 3, 4] },
    "open":     { counts: [1, 2, 3, 4], open: "working" },
    "long":     { counts: [1, 2, 3, 12], open: "idle" },
    "quiet":    { counts: [0, 0, 2, 0] },
    "none":     { counts: [0, 0, 0, 0] },
    "opening":  { counts: [1, 2, 3, 4], open: "working", opening: 0 },
    "failed":   { counts: [1, 2, 3, 4], open: "working", failed: 1, message: "could not raise the window" },
    "offline":  { counts: [0, 0, 0, 0], offline: true },
    "top-done": { counts: [0, 1, 2, 2] },
    "top-idle": { counts: [0, 0, 3, 1] },
}

// The whole state of one scene, in the form that the layouts read.
function scene(name) {
    var s = SCENES[name] || SCENES["closed"]
    var groups = []
    var total = 0
    var top = "none"
    for (var i = 0; i < ORDER.length; i++) {
        var state = ORDER[i]
        var count = s.counts[i]
        total += count
        groups.push({
            state: state, label: LABELS[state], color: COLORS[state], count: count,
            attention: (state === "blocked" || state === "done") && count > 0,
            open: s.open === state,
        })
    }
    for (var j = TOP_ORDER.length - 1; j >= 0; j--)
        if (s.counts[ORDER.indexOf(TOP_ORDER[j])] > 0)
            top = TOP_ORDER[j]
    var agents = s.open === "working" ? WORKING : s.open === "idle" ? IDLE : []
    return {
        online: !s.offline,
        groups: groups,
        total: total,
        top: s.offline ? "offline" : top,
        topColor: s.offline || top === "none" ? NEUTRAL : COLORS[top],
        topLabel: s.offline ? "Offline" : top === "none" ? "No agents" : LABELS[top],
        topCount: s.offline || top === "none" ? 0 : s.counts[ORDER.indexOf(top)],
        open: s.open || "",
        openColor: s.open ? COLORS[s.open] : NEUTRAL,
        openLabel: s.open ? LABELS[s.open] : "",
        agents: agents,
        shown: Math.min(agents.length, MAX_ROWS),
        scrolls: agents.length > MAX_ROWS,
        opening: s.opening === undefined ? -1 : s.opening,
        failed: s.failed === undefined ? -1 : s.failed,
        message: s.message || "",
    }
}

// "#rrggbb" with an alpha from 0 to 1, as "#aarrggbb".
function alpha(hex, a) {
    var v = Math.round(a * 255).toString(16)
    return "#" + (v.length < 2 ? "0" + v : v) + hex.substring(1)
}

function pad2(n) {
    return n < 10 ? "0" + n : "" + n
}
