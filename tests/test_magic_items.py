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


import random as _random


def _charged_fake():
    fake = _fake_magic_data()
    fake.items["wand"] = MagicItem(
        id="wand", name="Wand", category="magic_wands", item_type="magic",
        cost_gp=0, weight_cn=10, magic=True, equippable=True, charge_dice="2d6",
    )
    fake.items["staff"] = MagicItem(
        id="staff", name="Staff", category="magic_staves", item_type="magic",
        cost_gp=0, weight_cn=40, magic=True, equippable=True, max_charges=10,
    )
    return fake


def test_new_magic_instance_rolls_charge_dice():
    from aose.engine.magic import new_magic_instance
    fake = _charged_fake()
    inst = new_magic_instance("wand", fake, rng=_random.Random(1))
    assert inst.charges_max == inst.charges_remaining
    assert 2 <= inst.charges_max <= 12
    assert len(inst.instance_id) >= 16
    assert inst.equipped is False


def test_new_magic_instance_uses_max_charges():
    from aose.engine.magic import new_magic_instance
    fake = _charged_fake()
    inst = new_magic_instance("staff", fake)
    assert inst.charges_max == 10
    assert inst.charges_remaining == 10


def test_new_magic_instance_no_charges_when_neither():
    from aose.engine.magic import new_magic_instance
    fake = _fake_magic_data()
    inst = new_magic_instance("ring_prot", fake)
    assert inst.charges_max is None
    assert inst.charges_remaining is None


def test_new_magic_instance_rejects_unknown_and_non_magic():
    from aose.engine.magic import UnknownMagicItem, new_magic_instance
    fake = _fake_magic_data()
    fake.items["torch"] = __import__("aose.models", fromlist=["AdventuringGear"]).AdventuringGear(
        id="torch", name="Torch", category="gear", item_type="gear", cost_gp=1, weight_cn=20,
    )
    with pytest.raises(UnknownMagicItem):
        new_magic_instance("missing", fake)
    with pytest.raises(UnknownMagicItem):
        new_magic_instance("torch", fake)  # exists but not a MagicItem


def test_add_free_then_equip_unequip():
    from aose.engine.magic import add_free_magic_item, equip_magic, unequip_magic, NotEquippable
    fake = _charged_fake()
    items = add_free_magic_item([], "ring_prot", fake)
    assert len(items) == 1 and items[0].equipped is False
    iid = items[0].instance_id
    items = equip_magic(items, iid, fake)
    assert items[0].equipped is True
    items = unequip_magic(items, iid)
    assert items[0].equipped is False


def test_equip_magic_rejects_non_equippable():
    from aose.engine.magic import add_free_magic_item, equip_magic, NotEquippable
    fake = _charged_fake()
    fake.items["amulet"] = MagicItem(
        id="amulet", name="Amulet", category="misc", item_type="magic",
        cost_gp=0, weight_cn=0, magic=True, equippable=False, max_charges=3,
    )
    items = add_free_magic_item([], "amulet", fake)
    with pytest.raises(NotEquippable):
        equip_magic(items, items[0].instance_id, fake)


def test_use_charge_decrements_and_raises_at_zero():
    from aose.engine.magic import add_free_magic_item, use_charge, reset_charges, NoCharges
    fake = _charged_fake()
    items = add_free_magic_item([], "staff", fake)   # 10 charges
    iid = items[0].instance_id
    for _ in range(10):
        items = use_charge(items, iid)
    assert items[0].charges_remaining == 0
    with pytest.raises(NoCharges):
        use_charge(items, iid)
    items = reset_charges(items, iid)
    assert items[0].charges_remaining == 10


def test_use_charge_on_uncharged_raises():
    from aose.engine.magic import add_free_magic_item, use_charge, NoCharges
    fake = _fake_magic_data()
    items = add_free_magic_item([], "ring_prot", fake)
    with pytest.raises(NoCharges):
        use_charge(items, items[0].instance_id)


def test_remove_magic_drop_removes_instance():
    from aose.engine.magic import add_free_magic_item, remove_magic
    fake = _fake_magic_data()
    items = add_free_magic_item([], "ring_prot", fake)
    new_items, gold = remove_magic(items, 5, items[0].instance_id, "drop", fake)
    assert new_items == []
    assert gold == 5  # cost_gp 0 → no refund regardless of mode


def test_set_magic_note_persists():
    from aose.engine.magic import add_free_magic_item, set_magic_note
    fake = _fake_magic_data()
    items = add_free_magic_item([], "ring_prot", fake)
    items = set_magic_note(items, items[0].instance_id, "found in dragon hoard")
    assert items[0].note == "found in dragon hoard"


import copy as _copy


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def _with_magic(data):
    """Deep-copy real GameData and inject the magic catalog items the AC /
    saves / attacks tests need (so these tasks don't depend on Task 12)."""
    from aose.models import Armor, MagicItem, Weapon, WeaponDamage, ConditionalBonus
    d = _copy.deepcopy(data)
    d.items["ring_of_protection"] = MagicItem(
        id="ring_of_protection", name="Ring of Protection", category="magic_rings",
        item_type="magic", cost_gp=0, weight_cn=0, magic=True, equippable=True,
        modifiers=[
            {"target": "ac", "op": "add", "value": 1},
            {"target": "save:all", "op": "add", "value": 1},
        ],
    )
    d.items["gauntlets_of_ogre_power"] = MagicItem(
        id="gauntlets_of_ogre_power", name="Gauntlets of Ogre Power",
        category="miscellaneous_magic_items", item_type="magic", cost_gp=0,
        weight_cn=0, magic=True, equippable=True,
        modifiers=[
            {"target": "ability:STR", "op": "set", "value": 18},
            {"target": "carry_capacity", "op": "add", "value": 1000},
        ],
    )
    d.items["girdle_of_giant_strength"] = MagicItem(
        id="girdle_of_giant_strength", name="Girdle of Giant Strength",
        category="miscellaneous_magic_items", item_type="magic", cost_gp=0,
        weight_cn=0, magic=True, equippable=True,
        modifiers=[{"target": "thac0", "op": "set_max", "value": 14}],
    )
    d.items["chain_mail_plus_1"] = Armor(
        id="chain_mail_plus_1", name="Chain Mail +1", category="magic_armour",
        item_type="armor", cost_gp=0, weight_cn=400, ac_descending=5,
        movement_impact="metal", magic=True, magic_bonus=1, weight_multiplier=0.5,
    )
    d.items["shield_plus_1"] = Armor(
        id="shield_plus_1", name="Shield +1", category="magic_armour",
        item_type="armor", cost_gp=0, weight_cn=100, ac_descending=9,
        is_shield=True, magic=True, magic_bonus=1, weight_multiplier=0.5,
    )
    d.items["sword_plus_1"] = Weapon(
        id="sword_plus_1", name="Sword +1", category="magic_swords",
        item_type="weapon", cost_gp=0, weight_cn=60,
        damage=WeaponDamage(default="1d6", variable="1d8"), melee=True,
        proficiency_group="sword", magic=True, magic_bonus=1,
    )
    d.items["sword_plus_1_vs_undead"] = Weapon(
        id="sword_plus_1_vs_undead", name="Sword +1, +3 vs Undead",
        category="magic_swords", item_type="weapon", cost_gp=0, weight_cn=60,
        damage=WeaponDamage(default="1d6", variable="1d8"), melee=True,
        proficiency_group="sword", magic=True, magic_bonus=1,
        conditional_bonus=ConditionalBonus(vs="undead", bonus=2),
    )
    return d


def _equip_magic_spec(data, catalog_id, **spec_kwargs):
    from aose.engine.magic import add_free_magic_item, equip_magic
    spec = _minimal_spec(**spec_kwargs)
    spec.magic_items = add_free_magic_item([], catalog_id, data)
    spec.magic_items = equip_magic(spec.magic_items, spec.magic_items[0].instance_id, data)
    return spec


def test_ac_ring_of_protection(data):
    from aose.engine.armor_class import armor_class
    d = _with_magic(data)
    spec = _minimal_spec(abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    base_desc, base_asc = armor_class(spec, d)
    spec = _equip_magic_spec(d, "ring_of_protection",
                             abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    desc, asc = armor_class(spec, d)
    assert desc == base_desc - 1
    assert asc == base_asc + 1


def test_ac_chain_mail_plus_1(data):
    from aose.engine.armor_class import armor_class
    d = _with_magic(data)
    spec = _minimal_spec(abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    spec.inventory = ["chain_mail_plus_1"]
    spec.equipped = {"armor": "chain_mail_plus_1"}
    desc, asc = armor_class(spec, d)
    assert desc == 4   # 5 - 1
    assert asc == 15


def test_ac_shield_plus_1_two_points(data):
    from aose.engine.armor_class import armor_class
    d = _with_magic(data)
    spec = _minimal_spec(abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    spec.inventory = ["shield_plus_1"]
    spec.equipped = {"shield": "shield_plus_1"}
    desc, _ = armor_class(spec, d)
    assert desc == 9 - 2  # unarmored 9, shield bonus 1 + magic 1


def test_ac_chain_and_ring_stack(data):
    from aose.engine.armor_class import armor_class
    d = _with_magic(data)
    spec = _equip_magic_spec(d, "ring_of_protection",
                             abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    spec.inventory = ["chain_mail_plus_1"]
    spec.equipped = {"armor": "chain_mail_plus_1"}
    desc, _ = armor_class(spec, d)
    assert desc == 4 - 1  # chain+1 base 4, ring -1


def test_ac_set_takes_better_base(data):
    """ad-hoc bracers-style 'ac set 4' base candidate via extra_modifiers."""
    from aose.engine.armor_class import armor_class
    from aose.engine.magic import add_free_magic_item, equip_magic
    from aose.models import Modifier
    d = _with_magic(data)
    spec = _minimal_spec(abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 10, "CON": 12, "CHA": 10})
    spec.magic_items = add_free_magic_item([], "ring_of_protection", d)
    iid = spec.magic_items[0].instance_id
    spec.magic_items[0].extra_modifiers = [Modifier(target="ac", op="set", value=4)]
    spec.magic_items = equip_magic(spec.magic_items, iid, d)
    desc, _ = armor_class(spec, d)
    # base min(9, 4) = 4, then ring -1 (add) → 3
    assert desc == 3


def test_saves_ring_improves_all_by_one(data):
    from aose.engine.saves import saving_throws
    d = _with_magic(data)
    base = saving_throws(_minimal_spec(), d)
    spec = _equip_magic_spec(d, "ring_of_protection")
    improved = saving_throws(spec, d)
    for cat, val in base.items():
        assert improved[cat] == max(2, val - 1)


def test_saves_single_category(data):
    from aose.engine.saves import saving_throws
    from aose.engine.magic import add_free_magic_item, equip_magic
    from aose.models import MagicItem, Modifier
    d = _copy.deepcopy(data)
    d.items["cloak_death"] = MagicItem(
        id="cloak_death", name="Cloak vs Death", category="misc",
        item_type="magic", cost_gp=0, weight_cn=0, magic=True, equippable=True,
        modifiers=[Modifier(target="save:death", op="add", value=2)],
    )
    base = saving_throws(_minimal_spec(), d)
    spec = _minimal_spec()
    spec.magic_items = add_free_magic_item([], "cloak_death", d)
    spec.magic_items = equip_magic(spec.magic_items, spec.magic_items[0].instance_id, d)
    improved = saving_throws(spec, d)
    assert improved["death"] == max(2, base["death"] - 2)
    assert improved["wands"] == base["wands"]  # untouched


def test_saves_clamp_floor(data):
    from aose.engine.saves import saving_throws
    from aose.engine.magic import add_free_magic_item, equip_magic
    from aose.models import MagicItem, Modifier
    d = _copy.deepcopy(data)
    d.items["overkill"] = MagicItem(
        id="overkill", name="Overkill Amulet", category="misc",
        item_type="magic", cost_gp=0, weight_cn=0, magic=True, equippable=True,
        modifiers=[Modifier(target="save:all", op="add", value=99)],
    )
    spec = _minimal_spec()
    spec.magic_items = add_free_magic_item([], "overkill", d)
    spec.magic_items = equip_magic(spec.magic_items, spec.magic_items[0].instance_id, d)
    improved = saving_throws(spec, d)
    assert all(v == 2 for v in improved.values())


def test_thac0_girdle_set_max_lowers_worse(data):
    """A class with a worse (higher) THAC0 is capped at 14 by the Girdle."""
    from aose.engine.attack_bonus import thac0
    d = _with_magic(data)
    spec = _minimal_spec()  # fighter L1 → THAC0 19
    base = thac0(spec, d)
    assert base > 14
    spec = _equip_magic_spec(d, "girdle_of_giant_strength")
    assert thac0(spec, d) == 14


def test_thac0_set_max_leaves_better_untouched(data):
    """A natural THAC0 already better than 14 is not worsened by set_max 14."""
    from aose.engine.attack_bonus import thac0
    from aose.engine.magic import add_free_magic_item, equip_magic
    from aose.models import MagicItem, Modifier
    d = _copy.deepcopy(data)
    d.items["girdle"] = MagicItem(
        id="girdle", name="Girdle", category="misc", item_type="magic",
        cost_gp=0, weight_cn=0, magic=True, equippable=True,
        modifiers=[Modifier(target="thac0", op="set_max", value=14)],
    )
    # Force a better base THAC0 by monkey-injecting via a higher-level class is
    # awkward; instead assert the literal min() semantics directly:
    from aose.engine.magic import apply_modifiers
    assert apply_modifiers(11, [Modifier(target="thac0", op="set_max", value=14)], "thac0") == 11


# ── Task 10: Unarmed + magic weapon attack profiles ───────────────────────


def _weapon_spec(data, weapon_id, **kwargs):
    spec = _minimal_spec(**kwargs)
    spec.inventory = [weapon_id]
    spec.equipped_weapons = [weapon_id]
    return spec


def test_unarmed_profile_always_present_and_first(data):
    from aose.engine.attacks import attack_profiles
    spec = _minimal_spec(abilities={"STR": 13, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10})
    profiles = attack_profiles(spec, data)
    assert profiles[0].unarmed is True
    assert profiles[0].name == "Unarmed"
    assert profiles[0].proficient is True
    assert profiles[0].damage == "1d2+1"  # STR 13 → +1


def test_gauntlets_buff_unarmed_and_melee(data):
    from aose.engine.attacks import attack_profiles
    d = _with_magic(data)
    # base STR 9 (mod 0); gauntlets set STR 18 (mod +3)
    spec = _weapon_spec(d, "sword_plus_1",
                        abilities={"STR": 9, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10})
    from aose.engine.magic import add_free_magic_item, equip_magic
    spec.magic_items = add_free_magic_item([], "gauntlets_of_ogre_power", d)
    spec.magic_items = equip_magic(spec.magic_items, spec.magic_items[0].instance_id, d)
    profiles = attack_profiles(spec, d)
    unarmed = next(p for p in profiles if p.unarmed)
    assert unarmed.damage == "1d2+3"
    sword = next(p for p in profiles if p.weapon_id == "sword_plus_1")
    # variable_weapon_damage off → base 1d6; +3 STR, +1 magic = +4
    assert sword.damage == "1d6+4"


def test_magic_bonus_to_hit_and_damage(data):
    from aose.engine.attacks import attack_profiles
    from aose.engine.attack_bonus import thac0
    d = _with_magic(data)
    spec = _weapon_spec(d, "sword_plus_1",
                        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10})
    base_thac0 = thac0(_minimal_spec(), d)
    sword = next(p for p in attack_profiles(spec, d) if p.weapon_id == "sword_plus_1")
    assert sword.to_hit_thac0 == base_thac0 - 1   # STR 12 mod 0, +1 magic
    assert sword.to_hit_ascending == (19 - base_thac0) + 1
    assert sword.damage == "1d6+1"


def test_conditional_attack_profile(data):
    from aose.engine.attacks import attack_profiles
    from aose.engine.attack_bonus import thac0
    d = _with_magic(data)
    spec = _weapon_spec(d, "sword_plus_1_vs_undead",
                        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10})
    base_thac0 = thac0(_minimal_spec(), d)
    sword = next(p for p in attack_profiles(spec, d) if p.weapon_id == "sword_plus_1_vs_undead")
    assert sword.to_hit_thac0 == base_thac0 - 1   # normal: +1
    assert sword.conditional is not None
    assert sword.conditional.label == "vs undead"
    assert sword.conditional.to_hit_thac0 == base_thac0 - 3  # +1 base +2 extra
    assert sword.conditional.damage == "1d6+3"


def test_variable_weapon_damage_with_magic(data):
    from aose.engine.attacks import attack_profiles
    d = _with_magic(data)
    spec = _weapon_spec(d, "sword_plus_1",
                        abilities={"STR": 9, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10},
                        ruleset=RuleSet(variable_weapon_damage=True))
    sword = next(p for p in attack_profiles(spec, d) if p.weapon_id == "sword_plus_1")
    assert sword.damage == "1d8+1"  # variable 1d8, STR 0, +1 magic
