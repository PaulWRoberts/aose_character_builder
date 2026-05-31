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
