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
    # Dwarf fighter unencumbered: base_movement 120, no armour → movement 120.
    sheet = build_sheet(make_spec(), data)
    assert sheet.movement_base == 120
    assert sheet.movement_encounter == 40


def test_build_sheet_xp_to_next(data):
    sheet = build_sheet(make_spec(), data)
    assert sheet.next_level == 2
    assert sheet.xp_to_next == 2000


def test_build_sheet_features_have_source(data):
    sheet = build_sheet(make_spec(), data)
    assert all(f.source.startswith("Race:") for f in sheet.race_features)
    assert all(f.source.startswith("Class:") for f in sheet.class_features)
    # Book-accurate dwarf features: detect construction tricks and room traps
    assert any(f.name == "Detect Construction Tricks" for f in sheet.race_features)


def test_build_sheet_ascending_flag_follows_ruleset(data):
    sheet = build_sheet(make_spec(ruleset=RuleSet(ascending_ac=True)), data)
    assert sheet.use_ascending is True


def test_build_sheet_enabled_rules_listed(data):
    rs = RuleSet(ascending_ac=True, secondary_skills=True)
    sheet = build_sheet(make_spec(ruleset=rs), data)
    assert "Ascending AC" in sheet.enabled_optional_rules
    assert "Secondary Skills" in sheet.enabled_optional_rules
    assert "Multiclassing" not in sheet.enabled_optional_rules


def test_sheet_composes_native_alignment_and_chosen_languages():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.models import CharacterSpec, ClassEntry
    from aose.sheet.view import build_sheet

    data = GameData.load(Path(__file__).parent.parent / "data")
    spec = CharacterSpec(
        name="Linguist",
        abilities={"STR": 10, "INT": 16, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter")],
        alignment="law", languages=["Dragon", "Ogre"],
    )
    sheet = build_sheet(spec, data)
    assert "common" in sheet.languages          # native
    assert "Lawful" in sheet.languages          # alignment tongue
    assert "Dragon" in sheet.languages and "Ogre" in sheet.languages
    assert sheet.broken_speech is False


def test_sheet_flags_broken_speech_at_int_3():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.models import CharacterSpec, ClassEntry
    from aose.sheet.view import build_sheet

    data = GameData.load(Path(__file__).parent.parent / "data")
    spec = CharacterSpec(
        name="Grog",
        abilities={"STR": 13, "INT": 3, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter")],
        alignment="neutral",
    )
    sheet = build_sheet(spec, data)
    assert sheet.broken_speech is True


def test_ability_row_breakdown_temp_only(data):
    spec = make_spec(temp_ability_modifiers={"STR": -3})  # base STR 16 -> 13
    sheet = build_sheet(spec, data)
    row = next(r for r in sheet.abilities if r.ability == "STR")
    assert row.base_score == 16
    assert row.equip_delta == 0
    assert row.temp_delta == -3
    assert row.score == 13
    assert row.modified is True


def test_ability_row_breakdown_unmodified(data):
    sheet = build_sheet(make_spec(), data)
    row = next(r for r in sheet.abilities if r.ability == "INT")
    assert row.base_score == 10
    assert row.equip_delta == 0
    assert row.temp_delta == 0
    assert row.modified is False



def test_valuables_view_and_zero_weight():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.engine import valuables as v
    from aose.engine.encumbrance import carried_weight_cn
    from aose.models import CharacterSpec
    from aose.sheet.view import build_sheet

    data = GameData.load(Path(__file__).parent.parent / "data")
    spec = CharacterSpec(
        name="T",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[{"class_id": "fighter", "level": 1, "hp_rolls": [8]}],
        alignment="neutral",
    )
    baseline_weight = carried_weight_cn(spec, data)
    spec.gems = v.add_gem([], 100, count=2, label="ruby")
    spec.jewellery = v.add_jewellery([], 700)
    spec.jewellery = v.add_jewellery(spec.jewellery, 200, damaged=True)

    sheet = build_sheet(spec, data)
    assert sheet.valuables.total_value == 1000  # 200 + 700 + 100
    assert len(sheet.valuables.gems) == 1
    assert sheet.valuables.gems[0].stack_value == 200
    assert len(sheet.valuables.jewellery) == 2
    damaged_row = next(j for j in sheet.valuables.jewellery if j.damaged)
    assert damaged_row.effective_value == 100
    # Gems weigh 1 cn each, jewellery 10 cn each (AOSE treasure table).
    # 2 gems + 2 pieces = 2 + 20 = 22 cn
    assert carried_weight_cn(spec, data) == baseline_weight + 22


def test_sheet_exposes_unarmored_and_overland(data):
    sheet = build_sheet(make_spec(), data)
    assert sheet.unarmored_ac_descending >= sheet.ac_descending  # armour only helps
    assert sheet.movement_overland == sheet.movement_base // 5
