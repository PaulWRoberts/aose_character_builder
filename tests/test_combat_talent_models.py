from aose.models import RuleSet, CharacterSpec, ClassEntry
from aose.models.choice import FeatureChoice, ChoiceOption, OptionParam


def test_ruleset_has_combat_talents_default_off():
    assert RuleSet().combat_talents is False


def test_feature_choice_optional_gating_fields():
    g = FeatureChoice(id="combat_talents", name="Combat Talents",
                      requires_rule="combat_talents", pick_by_level={1: 1, 5: 2, 10: 3},
                      options=[ChoiceOption(id="cleave", name="Cleave")])
    assert g.requires_rule == "combat_talents"
    assert g.pick_by_level[10] == 3


def test_choice_option_param_and_exclusion():
    o = ChoiceOption(id="weapon_specialist", name="Weapon specialist",
                     excluded_when_rule="weapon_proficiency",
                     param=OptionParam(kind="weapon", label="Weapon"))
    assert o.excluded_when_rule == "weapon_proficiency"
    assert o.param.kind == "weapon"


def test_spec_choice_params_default_empty():
    spec = CharacterSpec(name="x", abilities={"STR": 9, "INT": 9, "WIS": 9, "DEX": 9, "CON": 9, "CHA": 9},
                         race_id="human", classes=[ClassEntry(class_id="fighter")], alignment="neutral")
    assert spec.choice_params == {}
