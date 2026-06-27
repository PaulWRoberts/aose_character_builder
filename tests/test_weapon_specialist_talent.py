from pathlib import Path

from aose.data.loader import GameData
from aose.engine.attacks import attack_profiles
from aose.models import CharacterSpec, ClassEntry, ItemInstance, RuleSet

DATA = GameData.load(Path(__file__).parent.parent / "data")


def _spec(rule_combat=True, rule_prof=False):
    return CharacterSpec(
        name="W", abilities={"STR": 12, "INT": 9, "WIS": 9, "DEX": 12, "CON": 12, "CHA": 9},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1)],
        alignment="neutral",
        ruleset=RuleSet(combat_talents=rule_combat, weapon_proficiency=rule_prof),
        items=[ItemInstance(instance_id="t_sword", catalog_id="sword",
                            equip="main_hand")],
        weapon_specialisations=["sword"],
    )


def _sword(profiles):
    return next(p for p in profiles if p.weapon_id == "sword")


def test_talent_specialisation_applies_plus_one_without_proficiency_rule():
    p = _sword(attack_profiles(_spec(), DATA))
    assert p.specialised is True
    # STR 12 -> +0; spec +1 to hit -> ascending +1, damage +1 over base "1d6".
    assert p.to_hit_ascending == 1
    assert p.damage.endswith("+1")


def test_no_specialisation_when_neither_rule_on():
    spec = _spec(rule_combat=False, rule_prof=False)
    p = _sword(attack_profiles(spec, DATA))
    assert p.specialised is False
