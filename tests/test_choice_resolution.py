import pytest

from aose.data.loader import GameData
from aose.engine.features import all_modifiers, feature_weapons, iter_reached, selected_options
from aose.models import (
    Ability, CharacterSpec, CharClass, ClassEntry, ClassFeature,
    ChoiceOption, DailyUses, FeatureChoice, GrantedModifier,
)
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def _data_with_test_class():
    data = GameData.load(DATA_DIR)
    test_cls = CharClass(
        id="ztest", name="ZTest", prime_requisites=[Ability.STR], hit_die="1d6",
        weapons_allowed="all", armor_allowed="all", shields_allowed=True,
        feature_choices=[FeatureChoice(id="grp", name="Grp", pick=2, options=[
            ChoiceOption(id="scales", name="Scales",
                         granted_modifiers=[GrantedModifier(target="ac", op="add", value=2)]),
            ChoiceOption(id="claw", name="Claw",
                         mechanical={"weapon": {"name": "Claw", "damage": "1d6", "melee": True}}),
            ChoiceOption(id="none", name="None"),
        ])],
    )
    data.classes["ztest"] = test_cls
    return data


def _spec(chosen):
    return CharacterSpec(
        name="T", abilities={a: 10 for a in Ability}, race_id="human",
        classes=[ClassEntry(class_id="ztest", level=1)], alignment="neutral",
        feature_choices={"grp": chosen},
    )


def test_chosen_option_grants_modifier():
    data = _data_with_test_class()
    mods = all_modifiers(_spec(["scales", "claw"]), data)
    assert any(m.target == "ac" and m.op == "add" and m.value == 2 for m in mods)


def test_unchosen_option_contributes_nothing():
    data = _data_with_test_class()
    mods = all_modifiers(_spec(["none", "claw"]), data)
    assert not any(m.target == "ac" and m.value == 2 for m in mods)


def test_chosen_option_emits_feature_weapon():
    data = _data_with_test_class()
    weapons = feature_weapons(_spec(["scales", "claw"]), data)
    names = [d["name"] for _id, d in weapons]
    assert "Claw" in names


def test_selected_options_helper():
    data = _data_with_test_class()
    opts = list(selected_options(data.classes["ztest"], {"grp": ["scales"]}))
    assert [o.id for o in opts] == ["scales"]


def test_feature_weapon_scales_with_level():
    data = GameData.load(DATA_DIR)
    from aose.models import ClassFeature
    cls = CharClass(
        id="zscale", name="ZScale", prime_requisites=[Ability.STR], hit_die="1d8",
        weapons_allowed="all", armor_allowed="all", shields_allowed=True,
        features=[ClassFeature(id="fist", name="Fist", text="...",
                  mechanical={"weapon": {"name": "Fist", "melee": True,
                                         "damage_per_level_die": "d4"}})],
    )
    data.classes["zscale"] = cls
    spec = CharacterSpec(name="T", abilities={a: 10 for a in Ability},
                         race_id="human", alignment="neutral",
                         classes=[ClassEntry(class_id="zscale", level=3)])
    weapons = dict((d["name"], d) for _id, d in feature_weapons(spec, data))
    assert weapons["Fist"]["damage"] == "3d4"
    assert "damage_per_level_die" not in weapons["Fist"]
