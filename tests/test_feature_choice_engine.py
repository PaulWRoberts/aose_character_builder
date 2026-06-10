import random

import pytest

from aose.engine.feature_choices import ChoiceError, roll_choice, validate_choice
from aose.models import ChoiceOption, FeatureChoice


def _grp(pick=2):
    return FeatureChoice(id="g", name="G", pick=pick, options=[
        ChoiceOption(id="a", name="A"), ChoiceOption(id="b", name="B"),
        ChoiceOption(id="c", name="C"),
    ])


def test_roll_returns_distinct_pick_count():
    rng = random.Random(1)
    chosen = roll_choice(_grp(2), rng)
    assert len(chosen) == 2
    assert len(set(chosen)) == 2
    assert set(chosen) <= {"a", "b", "c"}


def test_roll_caps_at_option_count():
    chosen = roll_choice(_grp(pick=5), random.Random(0))
    assert len(chosen) == 3


def test_validate_ok():
    validate_choice(_grp(2), ["a", "b"])   # no raise


def test_validate_wrong_count():
    with pytest.raises(ChoiceError):
        validate_choice(_grp(2), ["a"])


def test_validate_duplicate():
    with pytest.raises(ChoiceError):
        validate_choice(_grp(2), ["a", "a"])


def test_validate_unknown_id():
    with pytest.raises(ChoiceError):
        validate_choice(_grp(2), ["a", "z"])
