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


def _minimal_spec(**overrides):
    from aose.models import CharacterSpec, ClassEntry, RuleSet
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


def test_enchanted_instance_defaults():
    from aose.models import EnchantedInstance
    inst = EnchantedInstance(instance_id="i1", base_id="long_sword",
                             enchantment_id="plus_1")
    assert inst.equipped is False
    assert inst.charges_max is None
    assert inst.charges_remaining is None
    assert inst.extra_modifiers == []
    assert inst.note == ""


def test_character_spec_defaults_enchanted_empty():
    spec = _minimal_spec()
    assert spec.enchanted == []


def test_character_spec_accepts_enchanted():
    from aose.models import EnchantedInstance
    spec = _minimal_spec(enchanted=[
        EnchantedInstance(instance_id="i1", base_id="long_sword",
                          enchantment_id="plus_1", equipped=True),
    ])
    assert spec.enchanted[0].equipped is True


def test_loader_reads_enchantments(tmp_path):
    from aose.data.loader import GameData
    (tmp_path / "enchantments.yaml").write_text(
        "- id: plus_1\n"
        "  name_template: \"{base} +1\"\n"
        "  kind: weapon\n"
        "  applies_to: {include: [any_weapon]}\n"
        "  magic_bonus: 1\n",
        encoding="utf-8",
    )
    data = GameData.load(tmp_path)
    assert "plus_1" in data.enchantments
    assert data.enchantments["plus_1"].magic_bonus == 1


def test_loader_enchantments_absent_is_empty(tmp_path):
    from aose.data.loader import GameData
    data = GameData.load(tmp_path)
    assert data.enchantments == {}


import pytest as _pytest


@_pytest.fixture(scope="module")
def data():
    from aose.data.loader import GameData
    return GameData.load(DATA_DIR)


def test_mundane_shield_ac_bonus_from_data(data):
    from aose.models import Armor
    shield = data.items["shield"]
    assert isinstance(shield, Armor)
    assert shield.is_shield is True
    assert shield.ac_bonus == 1


def test_mundane_shield_still_minus_one_ac(data):
    from aose.engine.armor_class import armor_class
    spec = _minimal_spec(abilities={"STR": 12, "INT": 12, "WIS": 11,
                                    "DEX": 10, "CON": 12, "CHA": 10})
    spec.inventory = ["shield"]
    spec.equipped = {"shield": "shield"}
    desc, _ = armor_class(spec, data)
    assert desc == 8   # unarmoured 9, shield bonus 1


def test_base_swords_carry_sword_group(data):
    assert "sword" in data.items["short_sword"].groups


def _wpn(id, groups=(), is_shield=False):
    from aose.models import Weapon, WeaponDamage
    return Weapon(id=id, name=id.title(), category="weapons", item_type="weapon",
                  cost_gp=1, weight_cn=10, damage=WeaponDamage(), groups=list(groups))


def _arm(id, groups=(), is_shield=False, ac=7):
    from aose.models import Armor
    return Armor(id=id, name=id.title(), category="armor", item_type="armor",
                 cost_gp=1, weight_cn=100, ac_descending=ac, is_shield=is_shield,
                 groups=list(groups))


def _ench(id, kind, include, exclude=()):
    from aose.models import Enchantment
    return Enchantment(id=id, name_template="{base} +1", kind=kind,
                       applies_to={"include": list(include), "exclude": list(exclude)})


def test_matches_by_id_group_and_wildcard():
    from aose.engine.enchant import matches
    sword = _wpn("short_sword", groups=["sword"])
    assert matches(sword, "short_sword")          # base id
    assert matches(sword, "sword")                # group tag
    assert matches(sword, "any_weapon")           # weapon wildcard
    assert not matches(sword, "axe")


def test_wildcards_respect_nature():
    from aose.engine.enchant import matches
    plate = _arm("plate_mail", groups=["metal_armour"])
    shield = _arm("shield", is_shield=True)
    assert matches(plate, "any_armour")
    assert not matches(plate, "any_shield")
    assert matches(shield, "any_shield")
    assert not matches(shield, "any_armour")


def test_lightsaber_matches_sword_by_tag_not_name():
    from aose.engine.enchant import is_compatible
    saber = _wpn("lightsaber", groups=["sword"])
    sword_ench = _ench("sword_plus_1", "weapon", ["sword"])
    assert is_compatible(saber, sword_ench)


def test_exclude_wins_generic_not_swords():
    from aose.engine.enchant import is_compatible
    sword = _wpn("short_sword", groups=["sword"])
    axe = _wpn("battle_axe", groups=["axe"])
    generic = _ench("generic_plus_1", "weapon", ["any_weapon"], ["sword"])
    assert not is_compatible(sword, generic)   # excluded
    assert is_compatible(axe, generic)


def test_compatibility_requires_kind_match():
    from aose.engine.enchant import is_compatible
    sword = _wpn("short_sword", groups=["sword"])
    armour_ench = _ench("armour_plus_1", "armor", ["any_armour"])
    assert not is_compatible(sword, armour_ench)


def test_compatible_bases_lists_matches():
    from aose.engine.enchant import compatible_bases
    from aose.data.loader import GameData
    d = GameData(items={
        "short_sword": _wpn("short_sword", groups=["sword"]),
        "battle_axe": _wpn("battle_axe", groups=["axe"]),
        "plate_mail": _arm("plate_mail", groups=["metal_armour"]),
    })
    ench = _ench("sword_plus_1", "weapon", ["sword"])
    ids = {b.id for b in compatible_bases(ench, d)}
    assert ids == {"short_sword"}
