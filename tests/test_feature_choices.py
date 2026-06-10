import pytest
from pydantic import ValidationError

from aose.models.choice import ChoiceOption, DailyUses, FeatureChoice
from aose.models import GrantedModifier


def test_choice_option_minimal():
    opt = ChoiceOption(id="scales", name="Scales")
    assert opt.text == ""
    assert opt.granted_modifiers == []
    assert opt.daily_uses is None
    assert opt.spell_id is None


def test_choice_option_full():
    opt = ChoiceOption(
        id="magic_missile", name="Magic Missile",
        text="Cast magic missile once/day.",
        granted_modifiers=[GrantedModifier(target="ac", op="add", value=2)],
        daily_uses=DailyUses(per_day=1),
        spell_id="magic_user_magic_missile",
    )
    assert opt.daily_uses.per_day == 1
    assert opt.daily_uses.scales_with_level is False
    assert opt.spell_id == "magic_user_magic_missile"


def test_daily_uses_scales():
    du = DailyUses(scales_with_level=True)
    assert du.per_day == 1
    assert du.scales_with_level is True


def test_feature_choice_defaults():
    grp = FeatureChoice(id="mutations", name="Mutations", pick=2,
                        options=[ChoiceOption(id="a", name="A"),
                                 ChoiceOption(id="b", name="B")])
    assert grp.pick == 2
    assert grp.roll_dice is None
    assert grp.cosmetic is False


def test_feature_choice_rejects_unknown_field():
    with pytest.raises(ValidationError):
        FeatureChoice(id="x", name="X", options=[], allow_duplicates=True)


from aose.models import (
    CharacterSpec, CharClass, ClassEntry, ClassFeature, Race, RaceFeature, Ability,
    FeatureChoice, ChoiceOption, DailyUses,
)


def test_class_feature_daily_uses_and_spell():
    f = ClassFeature(id="breath", name="Breath Weapon", text="...",
                     daily_uses=DailyUses(per_day=3))
    assert f.daily_uses.per_day == 3
    assert f.spell_id is None


def test_class_carries_feature_choices():
    c = CharClass(
        id="x", name="X", prime_requisites=[Ability.STR], hit_die="1d6",
        weapons_allowed="all", armor_allowed="all", shields_allowed=True,
        feature_choices=[FeatureChoice(id="g", name="G", options=[
            ChoiceOption(id="o", name="O")])],
    )
    assert c.feature_choices[0].id == "g"


def test_race_feature_daily_uses():
    f = RaceFeature(id="spores", name="Fungal Spores", text="...",
                    daily_uses=DailyUses(scales_with_level=True))
    assert f.daily_uses.scales_with_level is True


def test_spec_feature_choices_and_innate_defaults():
    spec = CharacterSpec(
        name="T", abilities={a: 10 for a in Ability}, race_id="human",
        classes=[ClassEntry(class_id="fighter")], alignment="neutral",
    )
    assert spec.feature_choices == {}
    assert spec.innate_uses == {}
    spec2 = spec.model_copy(update={"feature_choices": {"mutations": ["scales"]}})
    assert spec2.feature_choices["mutations"] == ["scales"]
