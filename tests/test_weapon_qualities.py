"""Parametric weapon qualities: parsing + computed properties on Weapon."""
from aose.models import QualityRef, Weapon, WeaponQuality


def _weapon(**kw):
    base = dict(id="w", name="W", category="weapons", cost_gp=1, item_type="weapon")
    base.update(kw)
    return Weapon.model_validate(base)


def test_bare_string_quality_parses_to_ref():
    w = _weapon(qualities=["melee", "blunt"])
    assert [q.id for q in w.qualities] == ["melee", "blunt"]
    assert all(q.param is None for q in w.qualities)


def test_missile_param_drives_ranged_and_ranges():
    w = _weapon(qualities=[{"missile": [10, 20, 30]}])
    assert w.ranged is True
    assert w.melee is False
    assert (w.range_short, w.range_medium, w.range_long) == (10, 20, 30)


def test_two_handed_quality_drives_hands():
    assert _weapon(qualities=["melee"]).hands == 1
    assert _weapon(qualities=["melee", "two_handed"]).hands == 2


def test_versatile_param_is_two_handed_damage():
    w = _weapon(qualities=["melee", {"versatile": "1d8+1"}])
    assert w.versatile is True
    assert w.two_handed_damage == "1d8+1"


def test_default_damage_is_1d6_when_omitted():
    w = _weapon()
    assert w.damage.default == "1d6"
    assert w.damage.variable == "1d6"
    assert w.deals_damage is True


def test_empty_damage_is_no_damage():
    w = _weapon(damage={"default": "", "variable": ""})
    assert w.deals_damage is False


def test_quality_registry_has_param_field():
    q = WeaponQuality.model_validate(
        {"id": "missile", "name": "Missile", "param": "ranges", "description": "x"})
    assert q.param == "ranges"
    assert WeaponQuality.model_validate(
        {"id": "blunt", "name": "Blunt", "description": "x"}).param == "none"


import pytest

from aose.data.loader import _validate_weapon_qualities


def _wq():
    return {
        "melee": WeaponQuality(id="melee", name="Melee", description="x"),
        "missile": WeaponQuality(id="missile", name="Missile", description="x", param="ranges"),
        "versatile": WeaponQuality(id="versatile", name="Versatile", description="x", param="damage"),
    }


def test_validate_rejects_unknown_quality():
    items = {"w": _weapon(qualities=["bogus"])}
    with pytest.raises(ValueError, match="unknown quality"):
        _validate_weapon_qualities(items, _wq())


def test_validate_rejects_missile_without_three_ranges():
    items = {"w": _weapon(qualities=[{"missile": [10, 20]}])}
    with pytest.raises(ValueError, match="three integer ranges"):
        _validate_weapon_qualities(items, _wq())


def test_validate_rejects_versatile_without_damage():
    items = {"w": _weapon(qualities=["versatile"])}
    with pytest.raises(ValueError, match="damage string"):
        _validate_weapon_qualities(items, _wq())


def test_validate_rejects_param_on_plain_quality():
    items = {"w": _weapon(qualities=[{"melee": [1, 2, 3]}])}
    with pytest.raises(ValueError, match="takes no parameter"):
        _validate_weapon_qualities(items, _wq())


def test_validate_accepts_good_weapon():
    items = {"w": _weapon(qualities=["melee", {"missile": [10, 20, 30]}])}
    _validate_weapon_qualities(items, _wq())  # no raise
