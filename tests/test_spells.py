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
