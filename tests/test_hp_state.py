"""Unit tests for the HP play-state engine (current/damage/heal/set)."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine import hp
from aose.models import CharacterSpec, ClassEntry

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def _fighter(max_roll=12, con=10, damage_taken=0):
    """Single-class fighter whose max HP == max_roll (CON 10 → +0)."""
    return CharacterSpec(
        name="Bran",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": con, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[max_roll])],
        alignment="neutral",
        damage_taken=damage_taken,
    )


def test_current_hp_and_not_dead(data):
    spec = _fighter()
    assert hp.max_hp(spec, data) == 12
    assert hp.current_hp(spec, data) == 12
    assert hp.is_dead(spec, data) is False


def test_apply_damage_5_of_12(data):
    spec = _fighter()
    spec.damage_taken = hp.apply_damage(spec, data, 5)
    assert hp.current_hp(spec, data) == 7
    assert hp.is_dead(spec, data) is False


def test_damage_to_zero_marks_dead(data):
    spec = _fighter(damage_taken=5)  # 7/12
    spec.damage_taken = hp.apply_damage(spec, data, 10)
    assert hp.current_hp(spec, data) == 0
    assert hp.is_dead(spec, data) is True


def test_healing_caps_at_max(data):
    spec = _fighter(damage_taken=3)  # 9/12
    spec.damage_taken = hp.apply_healing(spec, data, 6)
    assert hp.current_hp(spec, data) == 12


def test_set_above_max_clamps_to_max(data):
    spec = _fighter(damage_taken=5)
    spec.damage_taken = hp.set_current_hp(spec, data, 99)
    assert hp.current_hp(spec, data) == 12


def test_set_below_zero_clamps_to_zero(data):
    spec = _fighter()
    spec.damage_taken = hp.set_current_hp(spec, data, -4)
    assert hp.current_hp(spec, data) == 0
    assert hp.is_dead(spec, data) is True


def test_negative_amount_rejected(data):
    spec = _fighter()
    with pytest.raises(ValueError):
        hp.apply_damage(spec, data, -1)
    with pytest.raises(ValueError):
        hp.apply_healing(spec, data, -1)


def test_damage_taken_tracks_max_shift(data):
    # Same damage_taken; a higher CON raises max_hp, so current HP rises with it
    # (the damage-taken model never destructively lowers current).
    low = _fighter(con=10, damage_taken=5)    # max 12 → current 7
    high = _fighter(con=16, damage_taken=5)   # CON 16 → +2 → max 14 → current 9
    assert hp.current_hp(low, data) == 7
    assert hp.max_hp(high, data) == 14
    assert hp.current_hp(high, data) == 9
