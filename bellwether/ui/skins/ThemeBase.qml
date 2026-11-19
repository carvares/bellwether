// The base of every theme file (skins/<letter>Theme.qml). A theme file states the values of its design; the
// helpers here apply the custom look of the user to them. This is the one place of that rule, and the one file
// of the themes and the skins that reads `backend`. The spec has the list ("Change on 2026-11-19: custom look").
//
// A theme file gives each value of its design to the helper of its kind:
//   readonly property int titleSize: size(15)
//   readonly property string fontFamily: family(Fonts.first([...], fallback))
//   readonly property color panelColor: background("#f21f2023")
//   readonly property color dimColor: dim("#9aa0a6")
// With no custom look every helper returns the value of the design, not changed.
import QtQuick

QtObject {
    // The colours that the user changed: role -> "#rrggbb" (the background also "#aarrggbb"). Empty: none.
    readonly property var custom: backend.colorOverrides
    // What a custom text colour keeps of itself in a dim and in a faint text (the rest is the panel behind it).
    readonly property real dimAlpha: 0.62
    readonly property real faintAlpha: 0.45

    // ----- sizes -----

    // The size of a text of the design, at the font scale of the custom look.
    function size(pixels) {
        return Math.round(pixels * backend.fontScale)
    }

    // A length of the design that holds text (the height of a row, of a badge, of a tile), in a skin and in the
    // options window: it grows with a font scale above 1, so the larger text has room. It does not get smaller
    // with a font scale below 1: the design keeps its proportions, with more air.
    function fit(pixels) {
        return Math.round(pixels * Math.max(1, backend.fontScale))
    }

    // ----- the font -----

    // The font family of the design, or the family of the user.
    function family(design) {
        return backend.fontFamily !== "" ? backend.fontFamily : design
    }

    // ----- colours -----
    // Each helper returns `design` while the user did not change the colour of its role.

    // The custom colour of a role with the opacity of the colour of the design: a plate that the design draws
    // at 14 % stays at 14 %.
    function role(name, design) {
        var set = custom[name]
        if (set === undefined)
            return design
        var c = Qt.color(set)
        return Qt.rgba(c.r, c.g, c.b, Qt.color(design).a)
    }

    // The custom colour of a role at an opacity of its own, for a grey of the design that has no opacity.
    function faded(name, design, alpha) {
        var set = custom[name]
        if (set === undefined)
            return design
        var c = Qt.color(set)
        return Qt.rgba(c.r, c.g, c.b, alpha)
    }

    // The panel. "#rrggbb" keeps the opacity of the design, "#aarrggbb" sets it.
    function background(design) {
        var set = custom.background
        return set !== undefined && set.length === 9 ? Qt.color(set) : role("background", design)
    }

    // A plate inside the panel that is darker than the panel (a card, a footer).
    function inset(design) {
        return custom.background === undefined ? design : Qt.darker(background(design), 1.2)
    }

    // The text. Also a plate of the text colour (the look under the pointer): `design` has its opacity.
    function text(design) {
        return role("text", design)
    }

    // The greys of a design are text of less weight: the dim text, the faint text, and with `tone` every other
    // grey that is ink on the panel (a guide line, the outline of an empty mark, a separator). With a custom text
    // colour each is that colour at a fixed opacity, so the user sets one colour.
    function dim(design) {
        return faded("text", design, dimAlpha)
    }

    function faint(design) {
        return faded("text", design, faintAlpha)
    }

    function tone(design, alpha) {
        return faded("text", design, alpha)
    }

    // The neutral frame and the lines.
    function frame(design) {
        return role("frame", design)
    }

    // The accent, and a plate of the accent (the selected card): `design` has its opacity.
    function accent(design) {
        return role("accent", design)
    }

    // ----- the ink on a solid plate -----
    // A text (or a mark, or a border) on a solid plate of a status colour or of the accent is not text on the
    // panel: it has the dark or the light ink, the one that the plate lets a person read better. Every status
    // colour of the designs is light, so the designs keep their dark ink. This is the one place of this rule.

    readonly property color darkInk: "#202124"
    readonly property color lightInk: "#f1f3f4"

    // The relative luminance of a colour (WCAG 2), from 0 (black) to 1 (white). The opacity is not counted.
    function luminance(colour) {
        function linear(part) {
            return part <= 0.03928 ? part / 12.92 : Math.pow((part + 0.055) / 1.055, 2.4)
        }
        var c = Qt.color(colour)
        return 0.2126 * linear(c.r) + 0.7152 * linear(c.g) + 0.0722 * linear(c.b)
    }

    // The contrast of two colours (WCAG 2), from 1 (the same) to 21 (black and white).
    function contrast(one, other) {
        var a = luminance(one), b = luminance(other)
        return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
    }

    // The ink for a solid plate: `dark` or `light`, the one with more contrast. A design gives its own dark ink
    // when it has one.
    function inkOn(plate, dark, light) {
        var darkOne = Qt.color(dark === undefined ? darkInk : dark)
        var lightOne = Qt.color(light === undefined ? lightInk : light)
        return contrast(plate, darkOne) >= contrast(plate, lightOne) ? darkOne : lightOne
    }

    // `wanted` when a person can tell it from `plate` (a contrast of 3 or more), else the ink for that plate.
    // For a control that must stay usable whatever colours the user chose (the options window: its close control
    // and "Reset to defaults").
    function readable(wanted, plate) {
        return contrast(wanted, plate) >= 3 ? Qt.color(wanted) : inkOn(plate)
    }

    // A colour without its opacity: a plate that hides what is behind it.
    function solid(colour) {
        var c = Qt.color(colour)
        return Qt.rgba(c.r, c.g, c.b, 1)
    }
}
