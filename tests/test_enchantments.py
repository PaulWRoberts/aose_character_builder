"""Tests for the magic-item enchantment composition model (Phase 1)."""
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def test_enchantment_parses_minimal():
    from aose.models import Enchantment
    e = Enchantment(
        id="plus_1",
        name_template="{base} +1",
        kind="weapon",
        applies_to={"include": ["any_weapon"]},
    )
    assert e.magic_bonus == 0
    assert e.conditional_bonus is None
    assert e.modifiers == []
    assert e.applies_to.include == ["any_weapon"]
    assert e.applies_to.exclude == []
    assert e.cursed is False


def test_enchantment_full_fields():
    from aose.models import Enchantment
    e = Enchantment(
        id="sword_plus_1_vs_undead",
        name_template="{base} +1, +3 vs Undead",
        kind="weapon",
        applies_to={"include": ["sword"], "exclude": []},
        magic_bonus=1,
        conditional_bonus={"vs": "undead", "bonus": 2},
        modifiers=[{"target": "save:all", "op": "add", "value": 1}],
        charge_dice="1d4+16",
        cursed=False,
        description="A blessed blade.",
    )
    assert e.conditional_bonus.vs == "undead"
    assert e.conditional_bonus.bonus == 2
    assert e.modifiers[0].target == "save:all"
    assert e.charge_dice == "1d4+16"
    assert e.name_template.format(base="Long Sword") == "Long Sword +1, +3 vs Undead"


def test_enchantment_rejects_bad_kind():
    from aose.models import Enchantment
    with pytest.raises(ValueError):
        Enchantment(id="x", name_template="{base}", kind="potion",
                    applies_to={"include": ["any_weapon"]})


def test_enchantment_forbids_extra_fields():
    from aose.models import Enchantment
    with pytest.raises(ValueError):
        Enchantment(id="x", name_template="{base}", kind="weapon",
                    applies_to={"include": ["any_weapon"]}, bogus=True)


def test_weapon_has_groups_default_empty():
    from aose.models import Weapon, WeaponDamage
    w = Weapon(id="dagger", name="Dagger", category="weapons", item_type="weapon",
               cost_gp=3, weight_cn=10, damage=WeaponDamage())
    assert w.groups == []


def test_weapon_groups_set():
    from aose.models import Weapon, WeaponDamage
    w = Weapon(id="short_sword", name="Short Sword", category="weapons",
               item_type="weapon", cost_gp=7, weight_cn=30,
               damage=WeaponDamage(), groups=["sword"])
    assert w.groups == ["sword"]


def test_armor_has_groups_and_ac_bonus_defaults():
    from aose.models import Armor
    a = Armor(id="leather", name="Leather", category="armor", item_type="armor",
              cost_gp=20, weight_cn=200, ac_descending=7, movement_impact="leather")
    assert a.groups == []
    assert a.ac_bonus == 0


def test_armor_shield_ac_bonus():
    from aose.models import Armor
    a = Armor(id="shield", name="Shield", category="armor", item_type="armor",
              cost_gp=10, weight_cn=100, ac_descending=0, is_shield=True, ac_bonus=1)
    assert a.ac_bonus == 1
