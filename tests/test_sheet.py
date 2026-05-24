from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.sheet.view import build_sheet

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def make_spec(**overrides):
    base = dict(
        name="Thorin",
        abilities={"STR": 16, "INT": 10, "WIS": 10, "DEX": 12, "CON": 14, "CHA": 9},
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[7])],
        alignment="law",
    )
    base.update(overrides)
    return CharacterSpec(**base)


def test_build_sheet_basic_fields(data):
    sheet = build_sheet(make_spec(), data)
    assert sheet.name == "Thorin"
    assert sheet.race_name == "Dwarf"
    assert sheet.class_summary == "Fighter 1"
    assert sheet.alignment == "Lawful"


def test_build_sheet_abilities(data):
    sheet = build_sheet(make_spec(), data)
    assert [r.ability for r in sheet.abilities] == ["STR", "INT", "WIS", "DEX", "CON", "CHA"]
    str_row = next(r for r in sheet.abilities if r.ability == "STR")
    assert str_row.score == 16
    assert str_row.modifier == 2


def test_build_sheet_combat(data):
    sheet = build_sheet(make_spec(), data)
    assert sheet.max_hp == 8  # 7 roll + 1 CON mod
    assert sheet.ac_descending == 9  # unarmored, DEX 12 = no mod
    assert sheet.ac_ascending == 10
    assert sheet.thac0 == 19
    assert sheet.attack_bonus == 0


def test_build_sheet_saves_ordered(data):
    sheet = build_sheet(make_spec(), data)
    assert [s.name for s in sheet.saves] == ["death", "wands", "paralysis", "breath", "spells"]
    assert sheet.saves[0].label == "Death / Poison"
    assert sheet.saves[0].target == 12


def test_build_sheet_movement(data):
    sheet = build_sheet(make_spec(), data)
    assert sheet.movement_base == 60
    assert sheet.movement_encounter == 20


def test_build_sheet_xp_to_next(data):
    sheet = build_sheet(make_spec(), data)
    assert sheet.next_level == 2
    assert sheet.xp_to_next == 2000


def test_build_sheet_features_have_source(data):
    sheet = build_sheet(make_spec(), data)
    assert all(f.source.startswith("Race:") for f in sheet.race_features)
    assert all(f.source.startswith("Class:") for f in sheet.class_features)
    assert any(f.name == "Detect Stonework" for f in sheet.race_features)


def test_build_sheet_ascending_flag_follows_ruleset(data):
    sheet = build_sheet(make_spec(ruleset=RuleSet(ascending_ac=True)), data)
    assert sheet.use_ascending is True


def test_build_sheet_enabled_rules_listed(data):
    rs = RuleSet(ascending_ac=True, secondary_skills=True)
    sheet = build_sheet(make_spec(ruleset=rs), data)
    assert "Ascending AC" in sheet.enabled_optional_rules
    assert "Secondary Skills" in sheet.enabled_optional_rules
    assert "Multiclassing" not in sheet.enabled_optional_rules
