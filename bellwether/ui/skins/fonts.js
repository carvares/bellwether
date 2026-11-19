.pragma library
// The font helper of the theme files (skins/<letter>Theme.qml): one copy of the rule for every theme.

// The first family of `wanted` that this system has, or `fallback` when it has none of them.
function first(wanted, fallback) {
    var have = Qt.fontFamilies()
    for (var i = 0; i < wanted.length; i++)
        if (have.indexOf(wanted[i]) >= 0)
            return wanted[i]
    return fallback
}
