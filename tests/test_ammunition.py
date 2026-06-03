"""Ammunition model + engine tests."""
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).parent.parent / "data"


def test_ammunition_parses_minimal():
    from aose.models import Ammunition
    a = Ammunition(id="arrow", name="Arrows", category="ammunition",
                   item_type="ammunition", cost_gp=5)
    assert a.weight_cn == 0          # ammo never weighs in
    assert a.bundle_count == 1
    assert a.groups == []


def test_ammunition_full_fields():
    from aose.models import Ammunition
    a = Ammunition(id="arrow", name="Arrows (quiver of 20)", category="ammunition",
                   item_type="ammunition", cost_gp=5, bundle_count=20,
                   groups=["arrow"], description="A quiver of 20 arrows.")
    assert a.bundle_count == 20 and a.groups == ["arrow"]


def test_ammunition_is_in_item_union():
    from pydantic import TypeAdapter
    from aose.models import Ammunition, Item
    parsed = TypeAdapter(Item).validate_python(
        {"id": "arrow", "name": "Arrows", "category": "ammunition",
         "item_type": "ammunition", "cost_gp": 5, "groups": ["arrow"]})
    assert isinstance(parsed, Ammunition)


def test_weapon_accepts_ammo_defaults_empty():
    from aose.models import Weapon, WeaponDamage
    w = Weapon(id="sword", name="Sword", category="weapons", item_type="weapon",
               cost_gp=10, damage=WeaponDamage())
    assert w.accepts_ammo == []


def test_enchantment_kind_allows_ammunition():
    from aose.models import Enchantment
    e = Enchantment(id="arrows_plus_1", name_template="{base} +1",
                    kind="ammunition", applies_to={"include": ["arrow"]},
                    magic_bonus=1)
    assert e.kind == "ammunition"


def test_ammo_stack_and_spec_fields():
    from aose.models import AmmoStack, CharacterSpec, ClassEntry
    s = AmmoStack(instance_id="x", base_id="arrow", count=20)
    assert s.enchantment_id is None and s.count == 20
    spec = CharacterSpec(name="A", abilities={}, race_id="human",
                         classes=[ClassEntry(class_id="fighter")], alignment="law")
    assert spec.ammo == [] and spec.loaded_ammo == {}


def _ammo(id, groups=()):
    from aose.models import Ammunition
    return Ammunition(id=id, name=id.title(), category="ammunition",
                      item_type="ammunition", cost_gp=1, groups=list(groups))


def _ammo_ench(id, include, exclude=()):
    from aose.models import Enchantment
    return Enchantment(id=id, name_template="{base} +1", kind="ammunition",
                       applies_to={"include": list(include), "exclude": list(exclude)})


def test_ammunition_nature_and_wildcard():
    from aose.engine.enchant import matches, is_compatible
    arrow = _ammo("arrow", groups=["arrow"])
    assert matches(arrow, "any_ammunition")
    assert matches(arrow, "arrow")
    assert is_compatible(arrow, _ammo_ench("arrows_plus_1", ["arrow"]))


def test_silver_arrow_takes_arrow_slaying():
    from aose.engine.enchant import is_compatible
    silver = _ammo("silver_arrow", groups=["arrow"])
    assert is_compatible(silver, _ammo_ench("arrow_slaying", ["arrow"]))


def test_ammo_enchantment_not_compatible_with_weapon():
    from aose.engine.enchant import is_compatible
    from aose.models import Weapon, WeaponDamage
    bow = Weapon(id="short_bow", name="Short Bow", category="weapons",
                 item_type="weapon", cost_gp=25, damage=WeaponDamage(), ranged=True)
    assert not is_compatible(bow, _ammo_ench("arrows_plus_1", ["arrow"]))


def test_resolve_weapon_preserves_accepts_ammo():
    from aose.engine.enchant import resolve_weapon
    from aose.models import Enchantment, Weapon, WeaponDamage
    bow = Weapon(id="short_bow", name="Short Bow", category="weapons",
                 item_type="weapon", cost_gp=25, damage=WeaponDamage(),
                 ranged=True, groups=["bow"], accepts_ammo=["arrow"])
    ench = Enchantment(id="bow_plus_1", name_template="{base} +1", kind="weapon",
                       applies_to={"include": ["bow"]}, magic_bonus=1)
    resolved = resolve_weapon(bow, ench, "iid")
    assert resolved.accepts_ammo == ["arrow"]
