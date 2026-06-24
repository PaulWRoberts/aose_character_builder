from pathlib import Path
from aose.data.loader import GameData
from aose.engine import retainers
from aose.models import CharacterSpec, RuleSet
from aose.sheet.view import _retainer_class_options, _retainer_race_options

DATA = GameData.load(Path("data"))


def _pc(cls, level):
    return CharacterSpec(
        name="PC", abilities={"STR": 12, "INT": 12, "WIS": 10, "DEX": 12,
                              "CON": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": cls, "level": level}],
        alignment="neutral")


def test_fighter_unrestricted():
    assert retainers.allowed_retainer_classes(_pc("fighter", 1), DATA) == "any"


def test_assassin_tiers():
    assert retainers.allowed_retainer_classes(_pc("assassin", 2), DATA) == set()
    assert retainers.allowed_retainer_classes(_pc("assassin", 5), DATA) == {"assassin"}
    assert retainers.allowed_retainer_classes(_pc("assassin", 9), DATA) == {"assassin", "thief"}
    assert retainers.allowed_retainer_classes(_pc("assassin", 12), DATA) == "any"


def _pc_rs(cls, level, ruleset):
    return CharacterSpec(
        name="PC", abilities={"STR": 12, "INT": 12, "WIS": 10, "DEX": 12,
                              "CON": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": cls, "level": level}],
        alignment="neutral", ruleset=ruleset)


def test_class_ids_always_include_normal_human():
    pc = _pc_rs("fighter", 1, RuleSet())
    assert "normal_human" in retainers.retainer_class_ids(pc, DATA)


def test_class_ids_exclude_disabled_content():
    pc = _pc_rs("fighter", 1, RuleSet(disabled_content=["carcass_crawler_1:classes"]))
    assert "acolyte" not in retainers.retainer_class_ids(pc, DATA)


def test_class_ids_exclude_race_as_class_in_advanced():
    pc = _pc_rs("fighter", 1, RuleSet(separate_race_class=True))
    ids = retainers.retainer_class_ids(pc, DATA)
    assert "elf" not in ids
    assert "fighter" in ids


def test_class_ids_include_race_as_class_in_basic():
    pc = _pc_rs("fighter", 1, RuleSet(separate_race_class=False))
    assert "elf" in retainers.retainer_class_ids(pc, DATA)


def test_class_ids_intersect_allowed_retainer_classes():
    # An assassin L5 PC may only hire assassins (per allowed_retainer_classes),
    # plus normal_human is always allowed.
    pc = _pc_rs("assassin", 5, RuleSet())
    ids = retainers.retainer_class_ids(pc, DATA)
    assert ids == {"assassin", "normal_human"}


def test_race_options_empty_in_basic():
    pc = _pc_rs("fighter", 1, RuleSet(separate_race_class=False))
    assert _retainer_race_options(pc, DATA) == []


def test_race_options_advanced_filtered_by_content():
    pc = _pc_rs("fighter", 1, RuleSet(separate_race_class=True))
    ids = {r["id"] for r in _retainer_race_options(pc, DATA)}
    assert "human" in ids and "dwarf" in ids
    pc2 = _pc_rs("fighter", 1,
                 RuleSet(separate_race_class=True,
                         disabled_content=["ose_advanced_fantasy:classes"]))
    ids2 = {r["id"] for r in _retainer_race_options(pc2, DATA)}
    assert "dwarf" not in ids2
    assert "human" in ids2
