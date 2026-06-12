from pathlib import Path

from aose.data.loader import GameData
from aose.engine.feature_choices import effective_pick
from aose.engine.level_choices import talent_capacities
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.models.choice import FeatureChoice, ChoiceOption

DATA = GameData.load(Path(__file__).parent.parent / "data")

GROUP = FeatureChoice(id="combat_talents", name="Combat Talents",
                      requires_rule="combat_talents", pick_by_level={1: 1, 5: 2, 10: 3},
                      options=[ChoiceOption(id=o, name=o) for o in
                               ["cleave", "defender", "leader", "slayer"]])


def test_effective_pick_bands_by_level():
    assert effective_pick(GROUP, 1) == 1
    assert effective_pick(GROUP, 4) == 1
    assert effective_pick(GROUP, 5) == 2
    assert effective_pick(GROUP, 10) == 3
    assert effective_pick(GROUP, 14) == 3


def test_effective_pick_falls_back_to_flat_pick():
    flat = FeatureChoice(id="g", name="g", pick=2,
                         options=[ChoiceOption(id="a", name="a"), ChoiceOption(id="b", name="b")])
    assert effective_pick(flat, 9) == 2


def _fighter(level, picked=(), rule=True):
    return CharacterSpec(
        name="T", abilities={"STR": 12, "INT": 9, "WIS": 9, "DEX": 12, "CON": 12, "CHA": 9},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=level)],
        alignment="neutral", ruleset=RuleSet(combat_talents=rule),
        feature_choices={"combat_talents": list(picked)},
    )


def test_talent_capacity_level5_one_picked_one_remaining():
    # Requires Task B5 fighter data to be loaded.
    caps = talent_capacities(_fighter(5, picked=["cleave"]), DATA)
    cap = next(c for c in caps if c.group_id == "combat_talents")
    assert cap.earned == 2 and cap.spent == 1 and cap.remaining == 1


def test_no_talent_capacity_when_rule_off():
    assert talent_capacities(_fighter(5, rule=False), DATA) == []
