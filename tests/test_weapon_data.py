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
