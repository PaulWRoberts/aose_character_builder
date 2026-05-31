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
