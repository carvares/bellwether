// The base of every theme file (skins/<letter>Theme.qml). A theme file states the values of its design; the
// helpers here apply the custom look of the user to them. This is the one place of that rule, and the one file
// of the themes and the skins that reads `backend`. The spec has the list ("Change on 2026-11-19: custom look").
import QtQuick

QtObject {
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
}
