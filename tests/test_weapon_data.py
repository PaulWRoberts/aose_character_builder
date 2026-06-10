"""Book-accurate weapon data + weapon-quality catalog."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.models import WeaponQuality

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def test_weapon_quality_model_fields():
    q = WeaponQuality(id="blunt", name="Blunt", description="May be used by clerics.")
    assert q.id == "blunt"
    assert q.name == "Blunt"
    assert q.description == "May be used by clerics."


def test_weapon_qualities_load_into_game_data():
    data = GameData.load(DATA_DIR)
    assert "blunt" in data.qualities
    assert isinstance(data.qualities["blunt"], WeaponQuality)
    assert data.qualities["blunt"].description == "May be used by clerics."
    # All nine book qualities present.
    assert {
        "blunt", "brace", "charge", "melee", "missile",
        "reload", "slow", "splash_weapon", "two_handed",
    }.issubset(set(data.qualities))


def test_qualities_not_loaded_as_items():
    data = GameData.load(DATA_DIR)
    assert "blunt" not in data.items


def test_weapons_match_book_table():
    data = GameData.load(DATA_DIR)
    # Renames applied.
    assert "long_sword" not in data.items
    assert "light_crossbow" not in data.items
    assert "sword" in data.items
    assert "crossbow" in data.items
    # New ids present.
    for new_id in ("javelin", "lance", "staff", "silver_dagger"):
        assert new_id in data.items, f"missing {new_id}"

    sword = data.items["sword"]
    assert sword.name == "Sword"
    assert sword.cost_gp == 10
    assert sword.weight_cn == 60
    assert sword.damage.variable == "1d8"
    assert sword.quality_ids == {"melee"}

    crossbow = data.items["crossbow"]
    assert crossbow.cost_gp == 30
    assert crossbow.melee is False
    assert crossbow.ranged is True
    assert (crossbow.range_short, crossbow.range_medium, crossbow.range_long) == (80, 160, 240)
    assert crossbow.quality_ids == {"missile", "reload", "slow", "two_handed"}


def test_every_weapon_quality_is_defined():
    data = GameData.load(DATA_DIR)
    from aose.models import Weapon
    for item in data.items.values():
        if isinstance(item, Weapon):
            for qid in item.quality_ids:
                assert qid in data.qualities, f"{item.id} references unknown quality {qid!r}"


def test_proficiency_group_field_removed():
    from aose.models import Weapon
    assert "proficiency_group" not in Weapon.model_fields
