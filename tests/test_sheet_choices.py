from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.sheet.view import build_sheet
from aose.models import (
    Ability, CharacterSpec, CharClass, ClassEntry, ChoiceOption, FeatureChoice,
)

DATA_DIR = Path(__file__).parent.parent / "data"


def _data():
    data = GameData.load(DATA_DIR)
    data.classes["zsheet"] = CharClass(
        id="zsheet", name="ZSheet", prime_requisites=[Ability.STR], hit_die="1d6",
        weapons_allowed="all", armor_allowed="all", shields_allowed=True,
        progression=data.classes["fighter"].progression,
        feature_choices=[FeatureChoice(id="grp", name="Grp", pick=1, options=[
            ChoiceOption(id="picked", name="Picked Trait", text="Chosen."),
            ChoiceOption(id="other", name="Other Trait", text="Not chosen."),
        ])],
    )
    return data


def _spec():
    return CharacterSpec(
        name="T", abilities={a: 10 for a in Ability}, race_id="human",
        alignment="neutral", classes=[ClassEntry(class_id="zsheet", level=1)],
        feature_choices={"grp": ["picked"]},
    )


def test_only_chosen_option_renders_as_feature():
    sheet = build_sheet(_spec(), _data())
    names = [f.name for f in sheet.class_features]
    assert "Picked Trait" in names
    assert "Other Trait" not in names
    assert "Grp" not in names           # the picker container never renders
