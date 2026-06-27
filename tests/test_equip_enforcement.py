"""Class weapon/armour/shield allowance resolver + equip enforcement."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine.proficiency import (
    allowed_armor_ids,
    allowed_weapon_ids,
    shields_allowed,
)

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


def test_fighter_unrestricted(data):
    fighter = data.classes["fighter"]
    assert allowed_weapon_ids([fighter], data) == "all"
    assert allowed_armor_ids([fighter], data) == "all"
    assert shields_allowed([fighter]) is True


def test_cleric_weapon_list_resolved_with_spaces(data):
    cleric = data.classes["cleric"]
    ids = allowed_weapon_ids([cleric], data)
    # "war hammer" normalised to war_hammer; staff/club/mace/sling present
    assert ids != "all"
    assert {"club", "mace", "sling", "staff", "war_hammer"}.issubset(ids)


def test_thief_armor_leather_resolved(data):
    thief = data.classes["thief"]
    armor = allowed_armor_ids([thief], data)
    assert armor != "all"
    assert "leather_armor" in armor
    assert shields_allowed([thief]) is False


def test_freeform_allowance_fails_open(data):
    # A class with an unresolvable entry → unrestricted for that category.
    bogus = data.classes["fighter"].model_copy(
        update={"weapons_allowed": ["any appropriate to size"]}
    )
    assert allowed_weapon_ids([bogus], data) == "all"


def test_multiclass_union_unrestricted_wins(data):
    cleric = data.classes["cleric"]      # weapon list
    fighter = data.classes["fighter"]    # all
    assert allowed_weapon_ids([cleric, fighter], data) == "all"


def test_leather_shorthand_resolves_not_failopen(data):
    # Every class that lists "leather" must resolve it, NOT fail open to "all".
    for cls_id in ("thief", "assassin", "acrobat", "druid", "gnome"):
        armor = allowed_armor_ids([data.classes[cls_id]], data)
        assert armor != "all", f"{cls_id} wrongly fails open"
        assert "leather_armor" in armor


def test_chainmail_and_plate_shorthand_resolve(data):
    barbarian = allowed_armor_ids([data.classes["barbarian"]], data)
    assert barbarian != "all"
    assert {"leather_armor", "chain_mail"}.issubset(barbarian)
    knight = allowed_armor_ids([data.classes["knight"]], data)
    assert knight != "all"
    assert "plate_mail" in knight


def test_war_hammer_still_resolves(data):
    cleric = allowed_weapon_ids([data.classes["cleric"]], data)
    assert cleric != "all"
    assert "war_hammer" in cleric


def test_freeform_armor_still_fails_open(data):
    # "any appropriate to size" must remain unresolvable → unrestricted.
    halfling = allowed_armor_ids([data.classes["halfling"]], data)
    assert halfling == "all"


# ── equip() enforcement tests ──────────────────────────────────────────────

from aose.engine.equip import equip, equipped_ref
from aose.models.character import CharacterSpec, ClassEntry, ItemInstance


def _spec_with(catalog_id: str) -> CharacterSpec:
    """A minimal spec owning a single carried instance of catalog_id."""
    return CharacterSpec(
        name="T", abilities={}, race_id="human",
        classes=[ClassEntry(class_id="fighter")], alignment="neutral",
        items=[ItemInstance(instance_id=f"t_{catalog_id}", catalog_id=catalog_id)],
    )


def test_equip_rejects_disallowed_weapon(data):
    # cleric: weapons limited; a sword is not allowed.
    allowed = allowed_weapon_ids([data.classes["cleric"]], data)
    spec = _spec_with("sword")
    with pytest.raises(ValueError, match="cannot use"):
        equip(spec, "t_sword", data=data, allowed_weapons=allowed)


def test_equip_allows_allowed_weapon(data):
    allowed = allowed_weapon_ids([data.classes["cleric"]], data)
    spec = _spec_with("mace")
    equip(spec, "t_mace", data=data, allowed_weapons=allowed)
    assert equipped_ref(spec, "main_hand") == "mace"


def test_equip_rejects_disallowed_armor(data):
    allowed = allowed_armor_ids([data.classes["thief"]], data)  # leather only
    spec = _spec_with("plate_mail")
    with pytest.raises(ValueError, match="cannot use"):
        equip(spec, "t_plate_mail", data=data, allowed_armor=allowed)


def test_equip_rejects_shield_when_not_allowed(data):
    spec = _spec_with("shield")
    with pytest.raises(ValueError, match="shield"):
        equip(spec, "t_shield", data=data, allow_shields=False)


def test_equip_unrestricted_by_default(data):
    # No allowance args → no enforcement.
    spec = _spec_with("sword")
    equip(spec, "t_sword", data=data)
    assert equipped_ref(spec, "main_hand") == "sword"


# ── inventory_view class_allowed flag (drives the UI Equip button) ──────────

from aose.engine.shop import inventory_view


def _carried_row(view, item_id):
    return next(r for r in view.carried if r.id == item_id)


def test_inventory_view_flags_disallowed_armor_for_magic_user(data):
    classes = [data.classes["magic_user"]]
    view = inventory_view(
        ["chain_mail", "dagger"], [], {}, None, data,
        allowed_weapons=allowed_weapon_ids(classes, data),
        allowed_armor=allowed_armor_ids(classes, data),
        allow_shields=shields_allowed(classes),
    )
    assert _carried_row(view, "chain_mail").class_allowed is False
    assert _carried_row(view, "dagger").class_allowed is True


def test_two_weapon_eligible_by_prime_requisite(data):
    from aose.engine.proficiency import two_weapon_eligible
    # Fighter: STR prime requisite -> eligible.
    assert two_weapon_eligible([data.classes["fighter"]]) is True
    # Magic-user: INT prime requisite -> not eligible.
    assert two_weapon_eligible([data.classes["magic_user"]]) is False


def test_two_weapon_eligible_multiclass_any_qualifies(data):
    from aose.engine.proficiency import two_weapon_eligible
    assert two_weapon_eligible(
        [data.classes["magic_user"], data.classes["fighter"]]
    ) is True


def test_inventory_view_allowed_by_default(data):
    # No allowance args → everything allowed (backward compatible).
    view = inventory_view(["chain_mail"], [], {}, None, data)
    assert _carried_row(view, "chain_mail").class_allowed is True
