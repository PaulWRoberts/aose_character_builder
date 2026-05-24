from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.models import Ability

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def test_dwarf_loaded(data):
    dwarf = data.races["dwarf"]
    assert dwarf.name == "Dwarf"
    assert dwarf.infravision == 60
    assert dwarf.base_movement == 60
    assert dwarf.ability_requirements[Ability.CON] == 9
    assert "fighter" in dwarf.allowed_classes
    assert dwarf.class_level_caps["fighter"] == 9


def test_fighter_loaded(data):
    fighter = data.classes["fighter"]
    assert fighter.name == "Fighter"
    assert fighter.hit_die == "1d8"
    assert fighter.weapons_allowed == "all"
    assert fighter.armor_allowed == "all"
    assert fighter.shields_allowed is True
    assert 1 in fighter.progression
    assert fighter.progression[1].thac0 == 19
    assert fighter.progression[1].saves["death"] == 12
    assert fighter.progression[4].thac0 == 17
