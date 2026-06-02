"""Tests for the energy-drain engine and route."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character, save_settings
from aose.data.loader import GameData
from aose.engine.energy_drain import energy_drain
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# All prime reqs in the 9-12 band -> 1.00x multiplier, so XP thresholds read cleanly.
_NEUTRAL_ABILITIES = {"STR": 12, "INT": 12, "WIS": 12, "DEX": 12, "CON": 14, "CHA": 10}


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def _spec(level=1, xp=0, hp_rolls=None, multi=False, ruleset=None, abilities=None):
    if ruleset is None:
        ruleset = RuleSet(multiclassing=True) if multi else RuleSet()
    if multi:
        classes = [
            ClassEntry(class_id="fighter", level=level, xp=xp,
                       hp_rolls=hp_rolls or [8] * level),
            ClassEntry(class_id="magic_user", level=level, xp=xp,
                       hp_rolls=hp_rolls or [4] * level),
        ]
    else:
        classes = [ClassEntry(class_id="fighter", level=level, xp=xp,
                              hp_rolls=hp_rolls or [8] * level)]
    return CharacterSpec(
        name="Test",
        abilities=abilities or dict(_NEUTRAL_ABILITIES),
        race_id="dwarf" if not multi else "elf",
        classes=classes,
        alignment="law",
        ruleset=ruleset,
    )


def test_drain_one_level_drops_level_hp_and_xp_new_min(data):
    spec = _spec(level=3, xp=8000, hp_rolls=[8, 5, 6])
    energy_drain(spec, data, levels=1, xp_mode="new_min")
    e = spec.classes[0]
    assert e.level == 2
    assert e.hp_rolls == [8, 5]            # last Hit Die removed
    assert e.xp == 2000                    # fighter L2 threshold (new-level minimum)


def test_drain_one_level_midpoint_lands_in_new_band(data):
    spec = _spec(level=3, xp=8000, hp_rolls=[8, 5, 6])
    energy_drain(spec, data, levels=1, xp_mode="midpoint")
    e = spec.classes[0]
    assert e.level == 2
    # halfway between fighter L2 (2000) and L3 (4000) thresholds
    assert e.xp == 3000


def test_drain_zero_levels_raises(data):
    spec = _spec(level=3, xp=8000)
    with pytest.raises(ValueError, match="at least 1"):
        energy_drain(spec, data, levels=0, xp_mode="new_min")


def test_drain_unknown_xp_mode_raises(data):
    spec = _spec(level=3, xp=8000)
    with pytest.raises(ValueError, match="unknown xp_mode"):
        energy_drain(spec, data, levels=1, xp_mode="bogus")


def test_drain_midpoint_multi_level_raises(data):
    spec = _spec(level=3, xp=8000)
    with pytest.raises(ValueError, match="single-level drain"):
        energy_drain(spec, data, levels=2, xp_mode="midpoint")


def test_drain_multi_level_single_class_cascades(data):
    spec = _spec(level=4, xp=99000, hp_rolls=[8, 5, 6, 7])
    energy_drain(spec, data, levels=2, xp_mode="new_min")
    e = spec.classes[0]
    assert e.level == 2
    assert e.hp_rolls == [8, 5]            # two Hit Dice removed (LIFO)
    assert e.xp == 2000                    # fighter L2 threshold
