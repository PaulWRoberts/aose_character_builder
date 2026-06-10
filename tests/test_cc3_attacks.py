"""Attack profiles for no-damage and versatile CC3 weapons."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine.attacks import attack_profiles
from aose.models import Ability, CharacterSpec, ClassEntry, RuleSet

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


def _fighter(data, weapon_ids, *, variable):
    equipped = {}
    slots = ("main_hand", "off_hand")
    for i, wid in enumerate(weapon_ids[:2]):
        equipped[slots[i]] = wid
    return CharacterSpec(
        name="T",
        abilities={a: 10 for a in Ability},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", xp=0)],
        alignment="neutral",
        inventory=list(weapon_ids),
        equipped=equipped,
        ruleset=RuleSet(variable_weapon_damage=variable),
    )


def test_net_profile_has_no_damage(data):
    spec = _fighter(data, ["net"], variable=False)
    profs = {p.name: p for p in attack_profiles(spec, data)}
    assert profs["Net"].damage == "—"


def test_versatile_single_profile_under_standard_rule(data):
    spec = _fighter(data, ["bastard_sword"], variable=False)
    names = [p.name for p in attack_profiles(spec, data)]
    assert names.count("Bastard Sword") == 1
    assert not any("Two-handed" in n for n in names)


def test_versatile_splits_under_variable_rule(data):
    spec = _fighter(data, ["bastard_sword"], variable=True)
    profs = {p.name: p for p in attack_profiles(spec, data)}
    assert "Bastard Sword" in profs
    assert "Bastard Sword (Two-handed)" in profs
    # STR 10 → +0; 1H uses variable 1d6+1, 2H uses 1d8+1
    assert profs["Bastard Sword"].damage == "1d6+1"
    assert profs["Bastard Sword (Two-handed)"].damage == "1d8+1"
