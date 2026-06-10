"""Full plate AC: tailored (2 [17]) vs untailored (3 [16])."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine.armor_class import armor_class
from aose.models import Ability, CharacterSpec, ClassEntry

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


def _knight_in_plate(tailored):
    return CharacterSpec(
        name="T",
        abilities={a: 10 for a in Ability},   # DEX 10 → +0
        race_id="human",
        classes=[ClassEntry(class_id="fighter", xp=0)],
        alignment="neutral",
        inventory=["full_plate"],
        equipped={"armor": "full_plate"},
        armor_tailored=tailored,
    )


def test_full_plate_tailored_is_ac2(data):
    desc, asc = armor_class(_knight_in_plate(True), data, use_shield=False)
    assert desc == 2 and asc == 17


def test_full_plate_untailored_is_ac3(data):
    desc, asc = armor_class(_knight_in_plate(False), data, use_shield=False)
    assert desc == 3 and asc == 16


def test_default_armor_tailored_is_true(data):
    spec = _knight_in_plate(True)
    assert spec.armor_tailored is True
