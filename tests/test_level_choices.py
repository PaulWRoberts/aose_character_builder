from pathlib import Path

from aose.data.loader import GameData
from aose.engine.level_choices import proficiency_capacity

DATA = GameData.load(Path(__file__).parent.parent / "data")


def _fighter(level: int):
    from aose.models import CharacterSpec, ClassEntry, RuleSet
    return CharacterSpec(
        name="T", abilities={"STR": 12, "INT": 9, "WIS": 9, "DEX": 12, "CON": 12, "CHA": 9},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=level)],
        alignment="neutral", ruleset=RuleSet(weapon_proficiency=True),
    )


def test_proficiency_capacity_off_when_rule_disabled():
    spec = _fighter(1)
    spec.ruleset.weapon_proficiency = False
    assert proficiency_capacity(spec, DATA) is None


def test_proficiency_capacity_level1_fighter_4_slots_none_spent():
    cap = proficiency_capacity(_fighter(1), DATA)
    assert (cap.earned, cap.spent, cap.remaining) == (4, 0, 4)


def test_proficiency_capacity_level7_fighter_earns_two_more():
    # THAC0 improves at 4 and 7 -> 6 slots total at L7.
    cap = proficiency_capacity(_fighter(7), DATA)
    assert cap.earned == 6 and cap.remaining == 6
