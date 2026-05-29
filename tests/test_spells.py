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


def test_class_entry_has_spellbook_and_prepared():
    from aose.models import ClassEntry
    e = ClassEntry(class_id="magic_user", level=1, hp_rolls=[3])
    assert e.spellbook == []
    assert e.prepared == []


def test_class_entry_rejects_old_chosen_spells_field():
    from aose.models import ClassEntry
    with pytest.raises(ValueError):
        ClassEntry(class_id="magic_user", chosen_spells=["x"])


def test_thorin_example_loads():
    import json
    from aose.models import CharacterSpec
    raw = json.loads((PROJECT_ROOT / "examples" / "thorin.json").read_text(encoding="utf-8"))
    spec = CharacterSpec.model_validate(raw)
    assert spec.classes[0].spellbook == []
    assert spec.classes[0].prepared == []


def test_seed_spells_loaded_and_tagged():
    from aose.data.loader import GameData
    data = GameData.load(DATA_DIR)
    rm = data.spells["read_magic"]
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
    from aose.web.settings_routes import IMPLEMENTED_RULES, RULE_GROUPS, RULE_LABELS
    assert "advanced_spell_books" in IMPLEMENTED_RULES
    assert "advanced_spell_books" in RULE_LABELS
    all_group_fields = {f for _, fields in RULE_GROUPS for f, _ in fields}
    assert "advanced_spell_books" in all_group_fields


from aose.models import CharacterSpec, ClassEntry, RuleSet


def _spec(class_id, level=1, abilities=None, spellbook=None, prepared=None, advanced=False):
    ab = abilities or {"STR": 10, "INT": 13, "WIS": 13, "DEX": 10, "CON": 10, "CHA": 10}
    return CharacterSpec(
        name="T", abilities=ab, race_id="human",
        classes=[ClassEntry(class_id=class_id, level=level, hp_rolls=[3],
                            spellbook=spellbook or [], prepared=prepared or [])],
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
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_missile"])
    cls = data.classes["magic_user"]
    assert [s.id for s in spells.known_spells(e, cls, data)] == ["magic_missile"]


def test_learnable_excludes_known_and_off_level():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_missile"])
    cls = data.classes["magic_user"]
    ids = {s.id for s in spells.learnable_spells(e, cls, data)}
    assert "magic_missile" not in ids
    assert "read_magic" in ids
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
    e2 = spells.learn(e, cls, data, RuleSet(), "magic_missile")
    assert e2.spellbook == ["magic_missile"]
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
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_missile"])
    cls = data.classes["magic_user"]
    with pytest.raises(spells.SpellError):
        spells.learn(e, cls, data, RuleSet(), "sleep")
    e3 = spells.learn(e, cls, data, RuleSet(advanced_spell_books=True), "sleep")
    assert set(e3.spellbook) == {"magic_missile", "sleep"}


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
        spells.learn(e, data.classes["fighter"], data, RuleSet(), "magic_missile")


def test_forget_removes():
    from aose.engine import spells
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_missile", "sleep"])
    e2 = spells.forget(e, "magic_missile")
    assert e2.spellbook == ["sleep"]
    assert e.spellbook == ["magic_missile", "sleep"]  # original untouched


def test_prepare_respects_known_and_slot_cap():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    cls = data.classes["magic_user"]
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_missile"])
    e2 = spells.prepare(e, cls, data, "magic_missile")
    assert e2.prepared == ["magic_missile"]
    with pytest.raises(spells.SpellError):
        spells.prepare(e2, cls, data, "magic_missile")   # exceeds the single slot
    with pytest.raises(spells.SpellError):
        spells.prepare(e, cls, data, "sleep")            # not known


def test_prepare_divine_from_full_list():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    cls = data.classes["druid"]
    e = ClassEntry(class_id="druid", level=1)
    e2 = spells.prepare(e, cls, data, "faerie_fire")
    assert e2.prepared == ["faerie_fire"]


def test_unprepare_removes_one_instance():
    from aose.engine import spells
    e = ClassEntry(class_id="druid", level=1, prepared=["faerie_fire", "faerie_fire"])
    e2 = spells.unprepare(e, "faerie_fire")
    assert e2.prepared == ["faerie_fire"]
