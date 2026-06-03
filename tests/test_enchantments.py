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


def test_resolve_weapon_carries_base_stats_and_ench_bonus():
    from aose.engine.enchant import resolve_weapon
    from aose.models import Enchantment, Weapon, WeaponDamage
    base = Weapon(id="long_sword", name="Long Sword", category="weapons",
                  item_type="weapon", cost_gp=10, weight_cn=60,
                  damage=WeaponDamage(default="1d6", variable="1d8"),
                  qualities=["melee"], groups=["sword"])
    ench = Enchantment(id="sword_vs_undead", name_template="{base} +1, +3 vs Undead",
                       kind="weapon", applies_to={"include": ["sword"]},
                       magic_bonus=1, conditional_bonus={"vs": "undead", "bonus": 2})
    w = resolve_weapon(base, ench, "abc123")
    assert isinstance(w, Weapon)
    assert w.name == "Long Sword +1, +3 vs Undead"
    assert w.magic_bonus == 1
    assert w.conditional_bonus.vs == "undead"
    assert w.damage.variable == "1d8"
    assert w.base_weapon == "long_sword"     # proficiency counts as base type
    assert w.id == "ench:abc123"
    assert w.qualities == ["melee"]


def test_resolve_armor_half_weight_and_base_armor():
    from aose.engine.enchant import resolve_armor
    from aose.models import Armor, Enchantment
    base = Armor(id="chain_mail", name="Chain Mail", category="armor",
                 item_type="armor", cost_gp=40, weight_cn=400, ac_descending=5,
                 movement_impact="metal", groups=["metal_armour"])
    ench = Enchantment(id="armour_plus_1", name_template="{base} +1",
                       kind="armor", applies_to={"include": ["any_armour"]},
                       magic_bonus=1)
    a = resolve_armor(base, ench, "xyz")
    assert isinstance(a, Armor)
    assert a.name == "Chain Mail +1"
    assert a.magic_bonus == 1
    assert a.ac_descending == 5            # base AC; magic_bonus applied downstream
    assert a.weight_multiplier == 0.5      # half-weight enchanted armour
    assert a.base_armor == "chain_mail"
    assert a.movement_impact == "metal"
    assert a.id == "ench:xyz"


def test_resolve_shield_carries_ac_bonus():
    from aose.engine.enchant import resolve_armor
    from aose.models import Armor, Enchantment
    base = Armor(id="shield", name="Shield", category="armor", item_type="armor",
                 cost_gp=10, weight_cn=100, ac_descending=0, is_shield=True, ac_bonus=1)
    ench = Enchantment(id="shield_plus_1", name_template="{base} +1",
                       kind="shield", applies_to={"include": ["any_shield"]},
                       magic_bonus=1)
    a = resolve_armor(base, ench, "s1")
    assert a.is_shield is True
    assert a.ac_bonus == 1
    assert a.magic_bonus == 1


def _lifecycle_data():
    from aose.data.loader import GameData
    from aose.models import Enchantment
    d = GameData(items={
        "short_sword": _wpn("short_sword", groups=["sword"]),
        "battle_axe": _wpn("battle_axe", groups=["axe"]),
    })
    d.enchantments = {
        "sword_plus_1": Enchantment(
            id="sword_plus_1", name_template="{base} +1", kind="weapon",
            applies_to={"include": ["sword"]}, magic_bonus=1),
        "charged_trident": Enchantment(
            id="charged_trident", name_template="{base} of Fish Command",
            kind="weapon", applies_to={"include": ["any_weapon"]},
            charge_dice="2d6"),
    }
    return d


def test_new_enchanted_instance_validates_compat():
    from aose.engine.enchant import new_enchanted_instance, IncompatibleBase
    d = _lifecycle_data()
    inst = new_enchanted_instance("short_sword", "sword_plus_1", d)
    assert inst.base_id == "short_sword"
    assert inst.enchantment_id == "sword_plus_1"
    assert inst.equipped is False
    assert len(inst.instance_id) >= 16
    with pytest.raises(IncompatibleBase):
        new_enchanted_instance("battle_axe", "sword_plus_1", d)  # axe vs sword-only


def test_new_enchanted_instance_rolls_charges():
    import random as _r
    from aose.engine.enchant import new_enchanted_instance
    d = _lifecycle_data()
    inst = new_enchanted_instance("short_sword", "charged_trident", d, rng=_r.Random(1))
    assert inst.charges_max == inst.charges_remaining
    assert 2 <= inst.charges_max <= 12


def test_new_enchanted_instance_unknown_raises():
    from aose.engine.enchant import new_enchanted_instance, UnknownEnchantment
    d = _lifecycle_data()
    with pytest.raises(UnknownEnchantment):
        new_enchanted_instance("short_sword", "nope", d)
    with pytest.raises(ValueError):
        new_enchanted_instance("missing_base", "sword_plus_1", d)


def test_add_equip_unequip_remove_roundtrip():
    from aose.engine.enchant import (
        add_free_enchanted, equip, unequip, remove, set_note)
    d = _lifecycle_data()
    items = add_free_enchanted([], "short_sword", "sword_plus_1", d)
    iid = items[0].instance_id
    items = equip(items, iid)
    assert items[0].equipped is True
    items = unequip(items, iid)
    assert items[0].equipped is False
    items = set_note(items, iid, "hoard")
    assert items[0].note == "hoard"
    items = remove(items, iid)
    assert items == []


def test_use_and_reset_charges():
    from aose.engine.enchant import (
        add_free_enchanted, use_charge, reset_charges, NoCharges)
    d = _lifecycle_data()
    items = add_free_enchanted([], "short_sword", "charged_trident", d)
    iid = items[0].instance_id
    start = items[0].charges_remaining
    for _ in range(start):
        items = use_charge(items, iid)
    assert items[0].charges_remaining == 0
    with pytest.raises(NoCharges):
        use_charge(items, iid)
    items = reset_charges(items, iid)
    assert items[0].charges_remaining == start


def test_equipped_enchanted_resolves_by_kind():
    from aose.engine.enchant import add_free_enchanted, equip, equipped_enchanted
    d = _lifecycle_data()
    items = add_free_enchanted([], "short_sword", "sword_plus_1", d)
    items = equip(items, items[0].instance_id)
    spec = _minimal_spec(enchanted=items)
    weapons = equipped_enchanted(spec, d, "weapon")
    assert len(weapons) == 1
    assert weapons[0].magic_bonus == 1
    assert equipped_enchanted(spec, d, "armor") == []


def test_active_modifiers_collect_enchanted_passives(data):
    import copy
    from aose.engine.magic import active_modifiers
    from aose.engine.enchant import add_free_enchanted, equip
    from aose.models import Enchantment, Modifier
    d = copy.deepcopy(data)
    d.enchantments["luck_blade_t9"] = Enchantment(
        id="luck_blade_t9", name_template="{base} of Luck", kind="weapon",
        applies_to={"include": ["any_weapon"]}, magic_bonus=1,
        modifiers=[Modifier(target="save:all", op="add", value=1)])
    items = add_free_enchanted([], "short_sword", "luck_blade_t9", d)
    items = equip(items, items[0].instance_id)
    spec = _minimal_spec(enchanted=items)
    mods = active_modifiers(spec, d)
    assert any(m.target == "save:all" for m in mods)


def test_active_modifiers_ignore_unequipped_enchanted(data):
    import copy
    from aose.engine.magic import active_modifiers
    from aose.engine.enchant import add_free_enchanted
    from aose.models import Enchantment, Modifier
    d = copy.deepcopy(data)
    d.enchantments["luck_blade_t9b"] = Enchantment(
        id="luck_blade_t9b", name_template="{base} of Luck", kind="weapon",
        applies_to={"include": ["any_weapon"]},
        modifiers=[Modifier(target="save:all", op="add", value=1)])
    items = add_free_enchanted([], "short_sword", "luck_blade_t9b", d)  # not equipped
    spec = _minimal_spec(enchanted=items)
    assert active_modifiers(spec, d) == []


def _equip_one_enchanted(d, base_id, ench_id, **spec_kwargs):
    from aose.engine.enchant import add_free_enchanted, equip
    spec = _minimal_spec(**spec_kwargs)
    spec.enchanted = add_free_enchanted([], base_id, ench_id, d)
    spec.enchanted = equip(spec.enchanted, spec.enchanted[0].instance_id)
    return spec


def test_ac_enchanted_armour_base(data):
    import copy
    from aose.engine.armor_class import armor_class
    from aose.models import Enchantment
    d = copy.deepcopy(data)
    d.enchantments["armour_plus_1_t10"] = Enchantment(
        id="armour_plus_1_t10", name_template="{base} +1", kind="armor",
        applies_to={"include": ["any_armour"]}, magic_bonus=1)
    spec = _equip_one_enchanted(
        d, "chain_mail", "armour_plus_1_t10",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    desc, _ = armor_class(spec, d)
    assert desc == 4   # chain 5 − 1 magic


def test_ac_enchanted_shield_bonus(data):
    import copy
    from aose.engine.armor_class import armor_class
    from aose.models import Enchantment
    d = copy.deepcopy(data)
    d.enchantments["shield_plus_1_t10"] = Enchantment(
        id="shield_plus_1_t10", name_template="{base} +1", kind="shield",
        applies_to={"include": ["any_shield"]}, magic_bonus=1)
    spec = _equip_one_enchanted(
        d, "shield", "shield_plus_1_t10",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    desc, _ = armor_class(spec, d)
    assert desc == 9 - 2   # unarmoured 9, shield ac_bonus 1 + magic 1


def test_ac_best_base_wins_mundane_vs_enchanted(data):
    """Wearing mundane leather (7) + an enchanted chain (4) → best base 4."""
    import copy
    from aose.engine.armor_class import armor_class
    from aose.models import Enchantment
    d = copy.deepcopy(data)
    d.enchantments["armour_plus_1_t10b"] = Enchantment(
        id="armour_plus_1_t10b", name_template="{base} +1", kind="armor",
        applies_to={"include": ["any_armour"]}, magic_bonus=1)
    spec = _equip_one_enchanted(
        d, "chain_mail", "armour_plus_1_t10b",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    spec.inventory = ["leather_armor"]
    spec.equipped = {"armor": "leather_armor"}   # worse base
    desc, _ = armor_class(spec, d)
    assert desc == 4   # enchanted chain base wins over leather 7
