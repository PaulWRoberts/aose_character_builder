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


from aose.models import Armor, ConditionalBonus, Weapon, WeaponDamage


def test_weapon_magic_fields_default_off():
    w = Weapon(
        id="dagger", name="Dagger", category="weapons", item_type="weapon",
        cost_gp=3, weight_cn=10, damage=WeaponDamage(default="1d6", variable="1d4"),
        proficiency_group="dagger",
    )
    assert w.magic_bonus == 0
    assert w.conditional_bonus is None


def test_magic_weapon_with_conditional():
    w = Weapon(
        id="sword_plus_1_vs_undead", name="Sword +1, +3 vs Undead",
        category="magic_swords", item_type="weapon", cost_gp=0, weight_cn=60,
        damage=WeaponDamage(default="1d6", variable="1d8"),
        proficiency_group="sword", magic=True, magic_bonus=1,
        conditional_bonus=ConditionalBonus(vs="undead", bonus=2),
    )
    assert w.magic_bonus == 1
    assert w.conditional_bonus.vs == "undead"
    assert w.conditional_bonus.bonus == 2


def test_armor_magic_and_weight_multiplier():
    a = Armor(
        id="chain_mail_plus_1", name="Chain Mail +1", category="magic_armour",
        item_type="armor", cost_gp=0, weight_cn=400, ac_descending=5,
        movement_impact="metal", magic=True, magic_bonus=1, weight_multiplier=0.5,
    )
    assert a.magic_bonus == 1
    assert a.weight_multiplier == 0.5


from aose.models import CharacterSpec, ClassEntry, MagicItemInstance, RuleSet


def _minimal_spec(**overrides):
    base = dict(
        name="Tester",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="law",
        ruleset=RuleSet(),
    )
    base.update(overrides)
    return CharacterSpec(**base)


def test_magic_item_instance_construct():
    inst = MagicItemInstance(
        instance_id="abc123", catalog_id="ring_of_protection", equipped=True,
    )
    assert inst.equipped is True
    assert inst.charges_remaining is None
    assert inst.extra_modifiers == []
    assert inst.note == ""


def test_character_spec_defaults_magic_items_empty():
    spec = _minimal_spec()
    assert spec.magic_items == []
