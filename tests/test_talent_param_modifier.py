from pathlib import Path

from aose.data.loader import GameData
from aose.engine.features import feature_modifiers
from aose.models import CharacterSpec, ClassEntry, RuleSet

DATA = GameData.load(Path(__file__).parent.parent / "data")


def _slayer_fighter(enemy="undead"):
    # Requires Task B5 (slayer option with condition "vs {param}").
    return CharacterSpec(
        name="S", abilities={"STR": 12, "INT": 9, "WIS": 9, "DEX": 12, "CON": 12, "CHA": 9},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1)],
        alignment="neutral", ruleset=RuleSet(combat_talents=True),
        feature_choices={"combat_talents": ["slayer"]},
        choice_params={"slayer": enemy},
    )


def test_slayer_condition_substitutes_chosen_enemy_type():
    mods = feature_modifiers(_slayer_fighter("dragons"), DATA)
    atk = [m for m in mods if m.target == "attack" and m.value == 1]
    assert any(m.condition == "vs dragons" for m in atk)
    assert not any("{param}" in (m.condition or "") for m in mods)
