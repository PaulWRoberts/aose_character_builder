"""Tests for magic items: Modifier value type, MagicItem catalog variant,
magic Weapon/Armor enchantment fields, MagicItemInstance runtime model, the
magic engine (active_modifiers / effective_abilities / charge helpers), the
derivation hooks (AC / saves / THAC0 / attacks / encumbrance), acquisition
routing, and the sheet + wizard HTTP routes."""
from pathlib import Path

import pytest

from aose.models import Modifier

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def test_modifier_parses_and_defaults():
    m = Modifier(target="ability:STR", op="set", value=18)
    assert m.target == "ability:STR"
    assert m.op == "set"
    assert m.value == 18


def test_modifier_rejects_unknown_op():
    with pytest.raises(ValueError):
        Modifier(target="ac", op="multiply", value=2)


def test_modifier_forbids_extra_fields():
    with pytest.raises(ValueError):
        Modifier(target="ac", op="add", value=1, bogus=True)


from aose.models import AdventuringGear, MagicItem


def test_itembase_new_fields_default_safely():
    gear = AdventuringGear(
        id="torch", name="Torch", category="adventuring_gear",
        item_type="gear", cost_gp=1, weight_cn=20,
    )
    assert gear.description is None
    assert gear.magic is False


def test_magic_item_parses_with_modifiers():
    ring = MagicItem(
        id="ring_of_protection", name="Ring of Protection",
        category="magic_rings", item_type="magic", cost_gp=0, weight_cn=0,
        magic=True, equippable=True,
        description="+1 AC and saves.",
        modifiers=[
            {"target": "ac", "op": "add", "value": 1},
            {"target": "save:all", "op": "add", "value": 1},
        ],
    )
    assert ring.equippable is True
    assert ring.magic is True
    assert len(ring.modifiers) == 2
    assert ring.modifiers[0].target == "ac"
    assert ring.max_charges is None
    assert ring.charge_dice is None


def test_magic_item_charge_fields():
    wand = MagicItem(
        id="ring_of_spell_turning", name="Ring of Spell Turning",
        category="magic_rings", item_type="magic", cost_gp=0, weight_cn=0,
        magic=True, equippable=True, charge_dice="2d6",
    )
    assert wand.charge_dice == "2d6"
    assert wand.modifiers == []
