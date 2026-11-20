"""The model and session-time line of the agent rows, in every layout: the real Main.qml, a real backend, and
made-up facts in the place of the reader of sessions."""
import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QAccessible, QColor

from bellwether import layouts
from bellwether.state import Agent
from tests.audit import text_findings
from tests.test_answer_control import Panel
from tests.test_qml import LAYERSHELL_QMLDIR, OFFSET, rows, settle, use_screens, walk

pytestmark = pytest.mark.skipif(not LAYERSHELL_QMLDIR.is_file(), reason="org.kde.layershell is not installed")

LETTERS = [letter for letter, _, _ in layouts.LAYOUTS]
NOW = 1_795_100_000.0
MINUTE, HOUR, DAY = 60_000, 3_600_000, 86_400_000
LONG_MODEL = "made-up-provider/a-very-long-made-up-model-name-v12"
AGENTS = [
    Agent("t1", "working", "rev", "Main", "claude-code"),
    Agent("t2", "working", "ana", "api / 1", "codex"),
    Agent("t3", "working", "bob", "docs", "claude-code"),
    Agent("t4", "working", "a made-up agent with a long name", "a made-up workspace / 1", "claude-code"),
    Agent("t5", "working", "eve", "Main", "claude-code"),
    Agent("t6", "blocked", "kim", "Main", "claude-code"),
    Agent("t7", "blocked", "a made-up agent with a long name", "db / schema", "claude-code"),
    Agent("t8", "blocked", "lee", "Main", "codex"),
]
# key -> (model id, age in milliseconds). t3 and t8 have no facts; t2 has the time alone.
FACTS = {"t1": ("claude-opus-5-5", 2 * HOUR + 14 * MINUTE), "t2": (None, 3 * DAY + 2 * HOUR),
         "t4": (LONG_MODEL, 23 * HOUR + 59 * MINUTE), "t5": ("claude-fable-5-2", 30_000),
         "t6": ("claude-sonnet-5-5-20261001", 14 * MINUTE), "t7": (LONG_MODEL, 9 * DAY)}
TEXTS = {"t1": ("Opus 5.5", "2h 14m"), "t2": ("", "3d 2h"), "t3": ("", ""),
         "t4": ("a-very-long-made-up-model-name-…", "23h 59m"), "t5": ("Fable 5.2", "<1m"),
         "t6": ("Sonnet 5.5", "14m"), "t7": ("a-very-long-made-up-model-name-…", "9d"), "t8": ("", "")}


class Facts:
    """In the place of the SessionWatch: made-up facts, and no read."""

    def __init__(self, facts):
        self.given = dict(facts)

    def facts(self):
        return {key: (model, int(NOW * 1000) - age) for key, (model, age) in self.given.items()}

    def clear(self):
        pass

    def wait(self):
        return 30.0

    def step(self, agents, stopped=None, files=True):
        return False

    def titles(self):
        return {}


@pytest.fixture
def panel(app, tmp_path):
    made = []

    def make(letter, facts=FACTS, agents=AGENTS, state="working", **look):
        one = Panel(app, tmp_path, agents, sessions=Facts(facts), now=lambda: NOW)
        made.append(one)
        one.backend.setLayout(letter)
        for name, value in look.items():
            assert getattr(one.backend, "set" + name[0].upper() + name[1:])(value) is True
        use_screens(one.root, OFFSET, "B", 0, 0)
        settle(app)
        if state:
            one.open_group(state)
        settle(app)
        return one

    yield make
    for one in made:
        warnings = one.warnings()
        one.close()
        assert warnings == []  # no QML warning in any step


def line(row):
    """The visible parts of the model and session-time line of a row: (the line, the model, the age). None: the row
    shows no such part."""
    def one(name):
        return next((i for i in walk(row) if i.property(name) and i.isVisible()), None)

    return one("isMetaLine"), one("isMetaModel"), one("isMetaAge")


def shown(panel):
    out = {}
    for row in rows(panel.root, "agent"):
        _, model, age = line(row)
        out[row.property("key")] = (model.property("text") if model else "", age.property("text") if age else "")
    return out


def box(item):
    return item.mapRectToScene(QRectF(0, 0, item.width(), item.height()))


def one_line_height(panel):
    return panel.root.property("skin").property("agentRowHeight")


@pytest.mark.parametrize("letter", LETTERS)
def test_a_row_with_facts_has_the_line_below_its_label_and_a_row_without_has_none(app, panel, letter):
    p = panel(letter)
    assert shown(p) == {key: TEXTS[key] for key in ("t1", "t2", "t3", "t4", "t5")}
    base, extra = one_line_height(p), p.root.property("skin").property("metaLineHeight")
    assert extra > 0 and p.root.property("panel").property("rowHeight") == base + extra
    for row in rows(p.root, "agent"):
        assert row.height() == base + extra  # every row of a list has the same height
        meta, model, age = line(row)
        label = next(i for i in walk(row) if i.property("text") == row.property("modelData")["label"])
        if row.property("key") == "t3":
            assert meta is None and model is None and age is None
            assert box(label).center().y() == pytest.approx(box(row).center().y(), abs=0.6)  # in the middle
            continue
        assert box(meta).top() >= box(label).bottom() - 0.5 and box(meta).left() == box(label).left()
        assert box(meta).bottom() <= box(row).bottom()
        assert box(label).center().y() == pytest.approx(box(row).top() + base / 2, abs=0.6)
    assert text_findings(p.root) == []


@pytest.mark.parametrize("letter", LETTERS)
def test_with_no_facts_the_rows_are_as_before(app, panel, letter):
    p = panel(letter, facts={})
    assert set(shown(p).values()) == {("", "")}
    assert [row.height() for row in rows(p.root, "agent")] == [one_line_height(p)] * 5
    assert p.root.property("panel").property("rowHeight") == one_line_height(p)
    assert p.root.property("panel").property("metaRows") is False
    assert not any(i.property("isMetaLine") and i.isVisible() for i in walk(p.root.contentItem()))
    for row in rows(p.root, "agent"):
        label = next(i for i in walk(row) if i.property("text") == row.property("modelData")["label"])
        assert box(label).center().y() == pytest.approx(box(row).center().y(), abs=0.6)


@pytest.mark.parametrize("letter", LETTERS)
def test_the_rows_get_taller_and_lower_again_when_facts_come_and_go(app, panel, letter):
    p = panel(letter, facts={})
    closed = p.root.height() - 5 * one_line_height(p)
    p.backend._watch.given = dict(FACTS)
    p.backend._look_at_meta()
    settle(app)
    tall = one_line_height(p) + p.root.property("skin").property("metaLineHeight")
    assert shown(p)["t1"] == TEXTS["t1"] and p.root.height() == closed + 5 * tall
    p.backend.setShowMeta(False)  # the setting off: no line, the rows of before
    settle(app)
    assert set(shown(p).values()) == {("", "")} and p.root.height() == closed + 5 * one_line_height(p)
    p.backend.setShowMeta(True)
    settle(app)
    assert shown(p)["t1"] == TEXTS["t1"] and p.root.height() == closed + 5 * tall


@pytest.mark.parametrize("letter", LETTERS)
def test_a_long_model_name_ends_in_dots_and_the_age_shows_in_full(app, panel, letter):
    # The backend cuts a name at 32 characters; at a large text the row is still too narrow for it.
    p = panel(letter, fontScale=1.4)
    meta, model, age = line(p.row("t4"))
    assert model.property("truncated") is True and model.width() < model.property("implicitWidth")
    assert age.property("truncated") is False and age.width() >= age.property("implicitWidth")
    assert age.property("text") == "23h 59m"
    assert box(age).right() <= box(meta).right() + 0.5 and box(meta).right() <= box(p.row("t4")).right()
    _, short, _ = line(panel(letter).row("t1"))
    assert short.property("truncated") is False
    assert text_findings(p.root) == []


@pytest.mark.parametrize("letter", LETTERS)
def test_the_line_does_not_touch_the_note_the_detail_or_the_answer_control(app, panel, letter):
    p = panel(letter)
    p.backend._set_opening("t1")
    p.backend.focusFailed.emit("t5", "could not raise the window")
    settle(app)
    assert p.root.property("openState") == "working"
    texts = [i.property("text") for i in walk(p.root.contentItem()) if i.isVisible() and i.property("text")]
    assert any("opening" in t for t in texts) and any("could not raise the window" in t for t in texts)
    assert shown(p)["t1"] == TEXTS["t1"] and shown(p)["t5"] == TEXTS["t5"]
    assert text_findings(p.root) == []
    p.backend._set_opening("")
    blocked = panel(letter, state="blocked")
    assert shown(blocked) == {key: TEXTS[key] for key in ("t6", "t7", "t8")}
    assert text_findings(blocked.root) == []
    for key in ("t6", "t7"):
        meta, _, age = line(blocked.row(key))
        control = blocked.control(key)
        assert box(meta).right() <= box(control).left() - 4 and box(age).right() <= box(control).left() - 4
        # The control is at the second line, below the name of the agent: it ends 3 px above the end of the row,
        # and the first line (the name, the detail) has the full width of the row.
        row = box(blocked.row(key))
        assert box(control).bottom() == pytest.approx(row.bottom() - 3, abs=0.6)
        assert box(control).center().y() > row.center().y() + 3
        assert control.property("lowered") is True and control.property("reserve") == 0
    plain = panel(letter, facts={}, state="blocked")  # no second line: the control is in the middle, as before
    for key in ("t6", "t7"):
        control = plain.control(key)
        assert box(control).center().y() == pytest.approx(box(plain.row(key)).center().y(), abs=0.6)
        assert control.property("lowered") is False and control.property("reserve") > control.width()


@pytest.mark.parametrize("scale", [0.8, 1.4])
@pytest.mark.parametrize("letter", LETTERS)
def test_the_line_follows_the_text_size(app, panel, letter, scale):
    design = panel(letter)
    size = line(design.row("t1"))[1].property("font").pixelSize()
    assert size in (10, 11) and size < next(
        i for i in walk(design.row("t1")) if i.property("text") == "rev").property("font").pixelSize()
    p = panel(letter, fontScale=scale)
    for part in line(p.row("t1"))[1:]:
        assert part.property("font").pixelSize() == int(size * scale + 0.5)
    for state in ("working", "blocked"):
        p.open_group(state)
        settle(app)
        assert text_findings(p.root) == [], state
        for row in rows(p.root, "agent"):
            meta = line(row)[0]
            assert meta is None or box(meta).bottom() <= box(row).bottom()


@pytest.mark.parametrize("letter", LETTERS)
def test_the_line_has_the_custom_text_colour_and_the_custom_font(app, panel, letter):
    design = panel(letter)
    before = line(design.row("t1"))[1].property("color")
    p = panel(letter)
    assert p.backend.setColor("text", "#ff8800") is True
    family = next(f for f in p.backend.fontFamilies if "Mono" in f or "Serif" in f)
    assert p.backend.setFontFamily(family) is True
    settle(app)
    for part in line(p.row("t1"))[1:]:
        colour = part.property("color")
        assert (colour.red(), colour.green(), colour.blue()) == (255, 136, 0) and colour != before
        assert 0 < colour.alphaF() < 1  # dimmer than the label
        assert part.property("font").family() == family
    label = next(i for i in walk(p.row("t1")) if i.property("text") == "rev")
    assert label.property("color") == QColor("#ff8800")


@pytest.mark.parametrize("letter", LETTERS)
def test_a_long_group_with_the_line_stays_on_a_screen_of_1080_pixels_at_the_largest_scale(app, panel, letter):
    agents = [Agent(f"t{n}", "idle", f"made-up {n:02d}", "pool", "claude-code") for n in range(1, 15)]
    facts = {a.key: ("claude-opus-5-5", n * HOUR) for n, a in enumerate(agents, 1)}
    p = panel(letter, facts=facts, agents=agents + AGENTS, state="idle")
    for scale, font in ((2.0, 1.0), (2.0, 1.4)):
        assert p.backend.setScale(scale) and p.backend.setFontScale(font)
        for _ in range(10):
            settle(app)
        cap = p.root.property("panel").property("maxAgentRows")
        visible = rows(p.root, "agent")
        row = visible[0].height()
        assert row == one_line_height(p) + p.root.property("skin").property("metaLineHeight")
        assert p.root.height() <= 1080 and 1 <= cap <= 8, (scale, font, p.root.height(), cap)
        assert p.root.height() + row * scale > 1080 or cap == 8  # and not fewer rows than necessary
        assert text_findings(p.root) == []
    p.backend.resetLook()
    for _ in range(10):
        settle(app)
    assert p.root.property("panel").property("maxAgentRows") == 8 and p.root.height() <= 1080


@pytest.mark.parametrize("letter", LETTERS)
def test_a_wheel_step_moves_a_list_of_tall_rows_by_whole_rows(app, panel, letter):
    agents = [Agent(f"t{n}", "idle", f"made-up {n:02d}", "pool", "claude-code") for n in range(1, 15)]
    p = panel(letter, facts={a.key: ("claude-opus-5-5", HOUR) for a in agents}, agents=agents, state="idle")
    lists = [i for i in walk(p.root.contentItem()) if i.property("pitch") is not None and i.property("open")]
    (agent_list,) = lists
    pitch = agent_list.property("pitch")
    assert agent_list.height() == 8 * pitch and agent_list.property("longer") is True
    from tests.test_skins import wheel
    wheel(app, p.root, box(rows(p.root, "agent")[2]).center())
    assert agent_list.property("contentY") == 2 * pitch and agent_list.property("first") == 2
    p.backend.setShowMeta(False)  # lower rows: the first row on the screen is still a whole row
    settle(app)
    low = agent_list.property("pitch")
    assert low == one_line_height(p) and agent_list.property("contentY") % low == 0


@pytest.mark.parametrize("letter", LETTERS)
def test_a_screen_reader_hears_the_model_and_the_age_of_a_row(app, panel, letter):
    p = panel(letter)
    names = {row.property("key"): QAccessible.queryAccessibleInterface(row).text(QAccessible.Text.Name)
             for row in rows(p.root, "agent")}
    assert names["t1"] == "Go to rev, claude-code in Main, model Opus 5.5, session age 2 hours 14 minutes"
    assert names["t2"] == "Go to ana, codex in api / 1, session age 3 days 2 hours"
    assert names["t3"] == "Go to bob, claude-code in docs"
    assert names["t5"].endswith("model Fable 5.2, session age less than 1 minute")
