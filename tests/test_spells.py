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
