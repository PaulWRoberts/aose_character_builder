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


from aose.data.loader import GameData
from aose.models import MagicItem


def _fake_magic_data():
    """In-memory GameData with the magic items the engine tests need."""
    return GameData(items={
        "gauntlets": MagicItem(
            id="gauntlets", name="Gauntlets of Ogre Power",
            category="miscellaneous_magic_items", item_type="magic",
            cost_gp=0, weight_cn=0, magic=True, equippable=True,
            modifiers=[
                {"target": "ability:STR", "op": "set", "value": 18},
                {"target": "carry_capacity", "op": "add", "value": 1000},
            ],
        ),
        "ring_prot": MagicItem(
            id="ring_prot", name="Ring of Protection", category="magic_rings",
            item_type="magic", cost_gp=0, weight_cn=0, magic=True, equippable=True,
            modifiers=[
                {"target": "ac", "op": "add", "value": 1},
                {"target": "save:all", "op": "add", "value": 1},
            ],
        ),
    })


def test_apply_modifiers_order_set_then_add_then_bounds():
    from aose.engine.magic import apply_modifiers
    from aose.models import Modifier
    mods = [
        Modifier(target="x", op="add", value=2),
        Modifier(target="x", op="set", value=10),
        Modifier(target="x", op="set_max", value=11),
        Modifier(target="x", op="set_min", value=12),
        Modifier(target="other", op="add", value=99),  # filtered out
    ]
    # set→10, add→12, set_min(max(12,12))→12, set_max(min(12,11))→11
    assert apply_modifiers(0, mods, "x") == 11


def test_active_modifiers_empty_when_none_equipped():
    from aose.engine.magic import active_modifiers
    from aose.models import MagicItemInstance
    fake = _fake_magic_data()
    spec = _minimal_spec(magic_items=[
        MagicItemInstance(instance_id="i1", catalog_id="ring_prot", equipped=False),
    ])
    assert active_modifiers(spec, fake) == []


def test_active_modifiers_collects_equipped_catalog_and_extra():
    from aose.engine.magic import active_modifiers
    from aose.models import MagicItemInstance, Modifier
    fake = _fake_magic_data()
    spec = _minimal_spec(magic_items=[
        MagicItemInstance(
            instance_id="i1", catalog_id="ring_prot", equipped=True,
            extra_modifiers=[Modifier(target="thac0", op="set_max", value=15)],
        ),
    ])
    mods = active_modifiers(spec, fake)
    targets = sorted(m.target for m in mods)
    assert targets == ["ac", "save:all", "thac0"]


def test_effective_abilities_applies_set_and_leaves_rest():
    from aose.engine.magic import effective_abilities
    from aose.models import Ability, MagicItemInstance
    fake = _fake_magic_data()
    spec = _minimal_spec(
        abilities={"STR": 9, "INT": 12, "WIS": 11, "DEX": 13, "CON": 12, "CHA": 10},
        magic_items=[MagicItemInstance(instance_id="i", catalog_id="gauntlets", equipped=True)],
    )
    eff = effective_abilities(spec, fake)
    assert eff[Ability.STR] == 18
    assert eff[Ability.DEX] == 13  # untouched


def test_effective_abilities_base_when_unequipped():
    from aose.engine.magic import effective_abilities
    from aose.models import Ability, MagicItemInstance
    fake = _fake_magic_data()
    spec = _minimal_spec(
        abilities={"STR": 9, "INT": 12, "WIS": 11, "DEX": 13, "CON": 12, "CHA": 10},
        magic_items=[MagicItemInstance(instance_id="i", catalog_id="gauntlets", equipped=False)],
    )
    assert effective_abilities(spec, fake)[Ability.STR] == 9


def test_carry_capacity_bonus_sums_active():
    from aose.engine.magic import carry_capacity_bonus
    from aose.models import MagicItemInstance
    fake = _fake_magic_data()
    spec = _minimal_spec(magic_items=[
        MagicItemInstance(instance_id="i", catalog_id="gauntlets", equipped=True),
    ])
    assert carry_capacity_bonus(spec, fake) == 1000
