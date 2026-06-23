"""Spell selection: SpellList registry, loader, spell engine, and sheet view."""
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def test_spell_list_model_parses():
    from aose.models import SpellList
    sl = SpellList(id="magic_user", name="Magic-User", caster_type="arcane")
    assert sl.caster_type == "arcane"
    assert sl.description is None


def test_spell_list_rejects_bad_caster_type():
    from aose.models import SpellList
    with pytest.raises(ValueError):
        SpellList(id="x", name="X", caster_type="psionic")


def test_spell_list_forbids_extra_fields():
    from aose.models import SpellList
    with pytest.raises(ValueError):
        SpellList(id="x", name="X", caster_type="arcane", bogus=1)


def test_loader_reads_spell_lists():
    from aose.data.loader import GameData
    data = GameData.load(DATA_DIR)
    assert data.spell_lists["magic_user"].caster_type == "arcane"
    assert data.spell_lists["druid"].caster_type == "divine"


def test_loader_spell_lists_empty_when_absent(tmp_path):
    from aose.data.loader import GameData
    data = GameData.load(tmp_path)
    assert data.spell_lists == {}


def test_class_entry_has_spellbook_and_slots():
    from aose.models import ClassEntry
    e = ClassEntry(class_id="magic_user", level=1, hp_rolls=[3])
    assert e.spellbook == []
    assert e.slots == []


def test_class_entry_migrates_legacy_chosen_spells():
    # Old saved characters carried an (always-empty) chosen_spells field. Under
    # extra="forbid" that would fail to load; a before-validator strips it so
    # legacy saves survive rather than silently vanishing from the index.
    from aose.models import ClassEntry
    e = ClassEntry(class_id="magic_user", chosen_spells=[])
    assert not hasattr(e, "chosen_spells")
    assert e.spellbook == []
    assert e.slots == []


def test_thorin_example_loads():
    import json
    from aose.models import CharacterSpec
    raw = json.loads((PROJECT_ROOT / "examples" / "thorin.json").read_text(encoding="utf-8"))
    spec = CharacterSpec.model_validate(raw)
    assert spec.classes[0].spellbook == []
    assert spec.classes[0].slots == []
    assert spec.damage_taken == 0


def test_seed_spells_loaded_and_tagged():
    from aose.data.loader import GameData
    data = GameData.load(DATA_DIR)
    rm = data.spells["magic_user_read_magic"]
    assert rm.level == 1
    assert rm.spell_lists == ["magic_user"]
    # Druid L1 spells are tagged for the druid list only (RAW: no L1 spell is
    # shared between the magic-user and druid lists).
    assert data.spells["faerie_fire"].spell_lists == ["druid"]


def test_magic_user_class_tags_its_list():
    from aose.data.loader import GameData
    data = GameData.load(DATA_DIR)
    assert data.classes["magic_user"].spell_lists == ["magic_user"]


def test_ruleset_has_advanced_spell_books_default_off():
    from aose.models import RuleSet
    assert RuleSet().advanced_spell_books is False


def test_advanced_spell_books_is_wired():
    from aose.web.settings_routes import IMPLEMENTED_RULES, SOURCE_RULES, RULE_LABELS, flatten_rule_fields
    assert "advanced_spell_books" in IMPLEMENTED_RULES
    assert "advanced_spell_books" in RULE_LABELS
    all_source_fields = set()
    for tree in SOURCE_RULES.values():
        all_source_fields |= {f for f in flatten_rule_fields(tree) if f is not None}
    assert "advanced_spell_books" in all_source_fields


from aose.models import CharacterSpec, ClassEntry, RuleSet


def _spec(class_id, level=1, abilities=None, spellbook=None, slots=None, advanced=False):
    ab = abilities or {"STR": 10, "INT": 13, "WIS": 13, "DEX": 10, "CON": 10, "CHA": 10}
    return CharacterSpec(
        name="T", abilities=ab, race_id="human",
        classes=[ClassEntry(class_id=class_id, level=level, hp_rolls=[3],
                            spellbook=spellbook or [], slots=slots or [])],
        alignment="neutral",
        ruleset=RuleSet(advanced_spell_books=advanced),
    )


def test_caster_type_of():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    assert spells.caster_type_of(data.classes["magic_user"], data) == "arcane"
    assert spells.caster_type_of(data.classes["druid"], data) == "divine"
    assert spells.caster_type_of(data.classes["fighter"], data) is None


def test_accessible_levels_and_slots():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="magic_user", level=1)
    cls = data.classes["magic_user"]
    assert spells.accessible_levels(e, cls) == {1}
    assert spells.memorizable_slots(e, cls) == {1: 1}


def test_divine_known_is_full_accessible_list():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="druid", level=1)
    cls = data.classes["druid"]
    known_ids = {s.id for s in spells.known_spells(e, cls, data)}
    assert {"faerie_fire", "entangle", "predict_weather"} <= known_ids
    assert "detect_magic" not in known_ids   # magic-user/cleric, not druid


def test_arcane_known_is_just_the_spellbook():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_user_magic_missile"])
    cls = data.classes["magic_user"]
    assert [s.id for s in spells.known_spells(e, cls, data)] == ["magic_user_magic_missile"]


def test_learnable_excludes_known_and_off_level():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_user_magic_missile"])
    cls = data.classes["magic_user"]
    ids = {s.id for s in spells.learnable_spells(e, cls, data)}
    assert "magic_user_magic_missile" not in ids
    assert "magic_user_read_magic" in ids
    assert all(s.level == 1 for s in spells.learnable_spells(e, cls, data))


def test_beginning_spell_count_standard_vs_advanced():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="magic_user", level=1)
    cls = data.classes["magic_user"]
    assert spells.beginning_spell_count(e, cls, 13, RuleSet()) == 1
    adv = RuleSet(advanced_spell_books=True)
    assert spells.beginning_spell_count(e, cls, 13, adv) == 3
    assert spells.beginning_spell_count(e, cls, 9, adv) == 2
    assert spells.beginning_spell_count(e, cls, 18, adv) == 5


def test_learn_adds_to_spellbook():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="magic_user", level=1, spellbook=[])
    cls = data.classes["magic_user"]
    e2 = spells.learn(e, cls, data, RuleSet(), "magic_user_magic_missile")
    assert e2.spellbook == ["magic_user_magic_missile"]
    assert e.spellbook == []  # original untouched


def test_learn_rejects_off_list_or_off_level():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="magic_user", level=1)
    cls = data.classes["magic_user"]
    with pytest.raises(spells.SpellError):
        spells.learn(e, cls, data, RuleSet(), "faerie_fire")   # druid-only


def test_learn_standard_caps_at_memorizable():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_user_magic_missile"])
    cls = data.classes["magic_user"]
    with pytest.raises(spells.SpellError):
        spells.learn(e, cls, data, RuleSet(), "magic_user_sleep")
    # Under the advanced rule, learn() is copy-only and refuses free adds.
    with pytest.raises(spells.SpellError):
        spells.learn(e, cls, data, RuleSet(advanced_spell_books=True), "magic_user_sleep")


def test_learn_rejected_under_advanced_rule():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="magic_user", level=1, spellbook=[])
    cls = data.classes["magic_user"]
    with pytest.raises(spells.SpellError):
        spells.learn(e, cls, data, RuleSet(advanced_spell_books=True),
                     "magic_user_magic_missile")


def test_learn_rejects_divine():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="druid", level=1)
    with pytest.raises(spells.SpellError):
        spells.learn(e, data.classes["druid"], data, RuleSet(), "faerie_fire")


def test_learn_rejects_noncaster():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="fighter", level=1)
    with pytest.raises(spells.SpellError):
        spells.learn(e, data.classes["fighter"], data, RuleSet(), "magic_user_magic_missile")


def test_forget_removes():
    from aose.engine import spells
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_user_magic_missile", "magic_user_sleep"])
    e2 = spells.forget(e, "magic_user_magic_missile")
    assert e2.spellbook == ["magic_user_sleep"]
    assert e.spellbook == ["magic_user_magic_missile", "magic_user_sleep"]  # original untouched



def test_spells_view_arcane_shape():
    from aose.data.loader import GameData
    from aose.models import SpellSlot
    from aose.sheet.view import build_sheet
    data = GameData.load(DATA_DIR)
    spec = _spec("magic_user", spellbook=["magic_user_magic_missile"],
                 slots=[SpellSlot(level=1, spell_id="magic_user_magic_missile")])
    sheet = build_sheet(spec, data)
    assert len(sheet.spells) == 1
    block = sheet.spells[0]
    assert block.caster_type == "arcane"
    assert block.can_learn is True
    assert [s.id for s in block.known] == ["magic_user_magic_missile"]
    grp = block.slot_groups[0]
    assert grp.level == 1 and grp.cap == 1
    assert len(grp.slots) == 1 and grp.slots[0].spell_id == "magic_user_magic_missile"
    assert any(s.id == "magic_user_read_magic" for s in block.learnable)


def test_spells_view_groups_slots_by_level():
    from aose.data.loader import GameData
    from aose.models import SpellSlot
    from aose.sheet.view import spells_view
    data = GameData.load(DATA_DIR)
    spec = _spec(
        "magic_user",
        spellbook=["magic_user_magic_missile"],
        slots=[SpellSlot(level=1, spell_id="magic_user_magic_missile", spent=True)],
    )
    blocks = spells_view(spec, data)
    block = blocks[0]
    assert block.caster_type == "arcane"
    grp = block.slot_groups[0]
    assert grp.level == 1
    assert grp.cap == 1
    assert grp.free == 0
    assert len(grp.slots) == 1
    sv = grp.slots[0]
    assert sv.spell_id == "magic_user_magic_missile"
    assert sv.spent is True
    assert sv.index == 0


def test_spells_view_divine_shape():
    from aose.data.loader import GameData
    from aose.sheet.view import build_sheet
    data = GameData.load(DATA_DIR)
    spec = _spec("druid", abilities={"STR": 10, "INT": 10, "WIS": 13,
                                     "DEX": 10, "CON": 10, "CHA": 10})
    sheet = build_sheet(spec, data)
    block = sheet.spells[0]
    assert block.caster_type == "divine"
    assert block.can_learn is False
    assert block.learnable == []
    assert {s.id for s in block.known} >= {"faerie_fire", "entangle"}


def test_spells_view_empty_for_noncaster():
    from aose.data.loader import GameData
    from aose.sheet.view import build_sheet
    data = GameData.load(DATA_DIR)
    spec = _spec("fighter")
    sheet = build_sheet(spec, data)
    assert sheet.spells == []


def test_learnable_hidden_under_advanced_rule():
    from aose.data.loader import GameData
    from aose.sheet.view import spells_view
    data = GameData.load(DATA_DIR)
    spec = _spec("magic_user", spellbook=["magic_user_magic_missile"], advanced=True)
    block = spells_view(spec, data)[0]
    assert block.can_learn is True          # forget still available
    assert block.learnable == []            # no free pick under advanced


def test_spell_sources_view_cast_and_copy_flags():
    from aose.data.loader import GameData
    from aose.engine import spell_sources as ss
    from aose.sheet.view import spell_sources_view
    data = GameData.load(DATA_DIR)
    scroll = ss.new_spell_source("scroll", "arcane",
                                 ["magic_user_magic_missile", "magic_user_sleep"], data)
    scroll = scroll.model_copy(update={"unlocked": True})
    spec = _spec("magic_user", spellbook=["magic_user_magic_missile"], advanced=True)
    spec.spell_sources = [scroll]
    view = spell_sources_view(spec, data)
    assert len(view) == 1
    sv = view[0]
    assert sv.kind == "scroll"
    assert sv.arcane_class_id == "magic_user"
    by_id = {e.spell_id: e for e in sv.entries}
    # both castable (arcane caster, arcane scroll)
    assert by_id["magic_user_sleep"].can_cast is True
    # sleep is copyable (level 1, not known); magic_missile already known -> not copyable
    assert by_id["magic_user_sleep"].can_copy is True
    assert by_id["magic_user_magic_missile"].can_copy is False


def test_spell_sources_view_copy_hidden_under_standard_rule():
    from aose.data.loader import GameData
    from aose.engine import spell_sources as ss
    from aose.sheet.view import spell_sources_view
    data = GameData.load(DATA_DIR)
    scroll = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], data)
    scroll = scroll.model_copy(update={"unlocked": True})
    spec = _spec("magic_user", advanced=False)
    spec.spell_sources = [scroll]
    sv = spell_sources_view(spec, data)[0]
    assert sv.entries[0].can_copy is False   # copy is advanced-only
    assert sv.entries[0].can_cast is True


def test_copy_chance_for_int_table():
    from aose.engine import spells
    assert spells.copy_chance_for_int(3) == 20
    assert spells.copy_chance_for_int(4) == 30
    assert spells.copy_chance_for_int(5) == 30
    assert spells.copy_chance_for_int(7) == 35
    assert spells.copy_chance_for_int(9) == 40
    assert spells.copy_chance_for_int(12) == 50
    assert spells.copy_chance_for_int(14) == 70
    assert spells.copy_chance_for_int(16) == 75
    assert spells.copy_chance_for_int(17) == 85
    assert spells.copy_chance_for_int(18) == 90
    assert spells.copy_chance_for_int(20) == 90   # 18+


def test_caster_candidates_respect_disabled_source():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.web.wizard import _caster_entries

    data = GameData.load(Path(__file__).parent.parent / "data")
    # Illusionist casts from the Advanced 'illusionist' list. With Advanced
    # disabled, its candidate list must be empty.
    draft = {
        "abilities": {"INT": 13, "WIS": 13},
        "class_id": "illusionist",
        "ruleset": {"disabled_sources": ["ose_advanced_fantasy"],
                    "separate_race_class": True},
    }
    rows = _caster_entries(draft, data)
    for row in rows:
        if row["class_id"] == "illusionist":
            assert row["candidates"] == []
