"""Weapon Proficiency optional rule — engine."""
from pathlib import Path

from aose.data.loader import GameData
from aose.engine.proficiency import (
    base_slot_count,
    combat_category,
    improvements_through_level,
    nonproficiency_penalty,
    proficiency_slots,
)

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def test_combat_category_derivation():
    data = GameData.load(DATA_DIR)
    assert combat_category(data.classes["fighter"]) == "martial"
    assert combat_category(data.classes["cleric"]) == "semi_martial"
    assert combat_category(data.classes["magic_user"]) == "non_martial"


def test_base_slot_count_by_category():
    assert base_slot_count("martial") == 4
    assert base_slot_count("semi_martial") == 3
    assert base_slot_count("non_martial") == 1


def test_nonproficiency_penalty_by_category():
    assert nonproficiency_penalty("martial") == -2
    assert nonproficiency_penalty("semi_martial") == -3
    assert nonproficiency_penalty("non_martial") == -5


def test_improvements_through_level_fighter():
    data = GameData.load(DATA_DIR)
    fighter = data.classes["fighter"]
    assert improvements_through_level(fighter, 1) == 0
    assert improvements_through_level(fighter, 4) == 1   # drop at L4
    assert improvements_through_level(fighter, 7) == 2   # +drop at L7
    assert improvements_through_level(fighter, 13) == 4  # L4/7/10/13


def test_proficiency_slots_full_leveling():
    data = GameData.load(DATA_DIR)
    fighter = data.classes["fighter"]
    assert proficiency_slots(fighter, 1) == 4
    assert proficiency_slots(fighter, 7) == 6
    assert proficiency_slots(fighter, 13) == 8
    assert proficiency_slots(data.classes["cleric"], 1) == 3
    assert proficiency_slots(data.classes["magic_user"], 1) == 1
    assert proficiency_slots(data.classes["magic_user"], 6) == 2  # first drop at L6
