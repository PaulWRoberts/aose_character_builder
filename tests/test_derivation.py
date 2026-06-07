from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine import ability_mods, armor_class, attack_bonus, hp, saves
from aose.models import CharacterSpec, ClassEntry

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def make_spec(con=14, dex=12, hp_rolls=(5,), level=1, equipped=None):
    return CharacterSpec(
        name="Thorin",
        abilities={
            "STR": 16, "INT": 10, "WIS": 10,
            "DEX": dex, "CON": con, "CHA": 9,
        },
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=level, hp_rolls=list(hp_rolls))],
        alignment="law",
        equipped=equipped or {},
    )


@pytest.mark.parametrize("score,expected", [
    (3, -3), (5, -2), (8, -1), (10, 0), (12, 0),
    (13, 1), (15, 1), (16, 2), (17, 2), (18, 3),
])
def test_ability_modifier(score, expected):
    assert ability_mods.ability_modifier(score) == expected


def test_prime_req_multiplier():
    assert ability_mods.prime_requisite_xp_multiplier(10) == 1.00
    assert ability_mods.prime_requisite_xp_multiplier(14) == 1.05
    assert ability_mods.prime_requisite_xp_multiplier(16) == 1.10
    assert ability_mods.prime_requisite_xp_multiplier(7) == 0.90


def test_max_hp_with_con_bonus(data):
    spec = make_spec(con=14, hp_rolls=[5])
    assert hp.max_hp(spec, data) == 6


def test_max_hp_minimum_1_per_level(data):
    spec = make_spec(con=3, hp_rolls=[1])
    assert hp.max_hp(spec, data) == 1


def test_max_hp_multiple_levels(data):
    spec = make_spec(con=10, hp_rolls=[5, 4, 6])
    assert hp.max_hp(spec, data) == 15


def test_ac_unarmored_no_dex(data):
    spec = make_spec(dex=10)
    desc, asc = armor_class.armor_class(spec, data)
    assert desc == 9
    assert asc == 10


def test_ac_unarmored_with_dex_bonus(data):
    spec = make_spec(dex=16)
    desc, asc = armor_class.armor_class(spec, data)
    assert desc == 7
    assert asc == 12


def test_thac0_fighter_l1(data):
    spec = make_spec()
    assert attack_bonus.thac0(spec, data) == 19
    assert attack_bonus.attack_bonus(spec, data) == 0


def test_thac0_fighter_l4(data):
    spec = make_spec(level=4)
    assert attack_bonus.thac0(spec, data) == 17
    assert attack_bonus.attack_bonus(spec, data) == 2


def test_saves_fighter_l1(data):
    # Thorin is a dwarf (CON 14 → +3 resilience on death/wands/spells).
    spec = make_spec()
    s = saves.saving_throws(spec, data)
    assert s == {"death": 9, "wands": 10, "paralysis": 14, "breath": 15, "spells": 13}


def test_saves_fighter_l4_better(data):
    spec = make_spec(level=4)
    s = saves.saving_throws(spec, data)
    assert s["death"] == 7  # L4 base 10 − 3 dwarf resilience
