"""Slice 4 (Ability Adjustments): typed restriction field, engine helpers,
and wizard wiring."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_draft, save_draft, save_settings
from aose.data.loader import GameData
from aose.models import Ability, RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


# ── Task 1: typed restriction field ───────────────────────────────────────

def test_restricted_classes_forbid_lowering_str(data):
    for cid in ("acrobat", "assassin", "thief"):
        assert data.classes[cid].non_reducible_abilities == [Ability.STR]


def test_other_classes_have_no_restriction(data):
    assert data.classes["fighter"].non_reducible_abilities == []
    assert data.classes["magic_user"].non_reducible_abilities == []


# ── Task 2: adjustable_abilities ───────────────────────────────────────────

from aose.engine.ability_mods import adjustable_abilities


def test_adjustable_fighter(data):
    adj = adjustable_abilities([data.classes["fighter"]])
    assert adj["raisable"] == {"STR"}
    assert adj["lowerable"] == {"INT", "WIS"}


def test_adjustable_magic_user(data):
    adj = adjustable_abilities([data.classes["magic_user"]])
    assert adj["raisable"] == {"INT"}
    assert adj["lowerable"] == {"STR", "WIS"}


def test_adjustable_thief_removes_str_via_restriction(data):
    adj = adjustable_abilities([data.classes["thief"]])
    assert adj["raisable"] == {"DEX"}
    assert adj["lowerable"] == {"INT", "WIS"}  # STR removed by restriction layer


def test_adjustable_multiclass_union(data):
    adj = adjustable_abilities([data.classes["fighter"], data.classes["magic_user"]])
    assert adj["raisable"] == {"STR", "INT"}
    assert adj["lowerable"] == {"WIS"}


# ── Task 3: validate + apply ───────────────────────────────────────────────

from aose.engine.ability_mods import (
    AdjustmentError,
    apply_ability_adjustments,
    validate_ability_adjustments,
)

_POST_RACIAL = {"STR": 12, "INT": 13, "WIS": 13, "DEX": 12, "CON": 12, "CHA": 10}


def test_validate_exact_two_to_one_passes(data):
    validate_ability_adjustments(
        _POST_RACIAL, [data.classes["fighter"]], {"STR": 1, "INT": -1, "WIS": -1}
    )


def test_validate_waste_fails(data):
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            _POST_RACIAL, [data.classes["fighter"]],
            {"STR": 1, "INT": -2, "WIS": -1},
        )


def test_validate_lower_below_nine_fails(data):
    scores = {**_POST_RACIAL, "INT": 9, "WIS": 13}
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            scores, [data.classes["fighter"]], {"STR": 1, "INT": -1, "WIS": -1}
        )


def test_validate_raise_above_eighteen_fails(data):
    scores = {**_POST_RACIAL, "STR": 18}
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            scores, [data.classes["fighter"]], {"STR": 1, "INT": -1, "WIS": -1}
        )


def test_validate_lower_prime_fails(data):
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            _POST_RACIAL, [data.classes["fighter"]], {"INT": 1, "STR": -2}
        )


def test_validate_raise_non_prime_fails(data):
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            _POST_RACIAL, [data.classes["fighter"]], {"WIS": 1, "INT": -2}
        )


def test_validate_lower_restricted_str_fails(data):
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            _POST_RACIAL, [data.classes["thief"]], {"DEX": 1, "STR": -2}
        )


def test_validate_empty_is_valid(data):
    validate_ability_adjustments(_POST_RACIAL, [data.classes["fighter"]], {})


def test_apply_adds_deltas():
    result = apply_ability_adjustments(
        {"STR": 12, "INT": 13, "WIS": 13, "DEX": 12, "CON": 12, "CHA": 10},
        {"STR": 1, "INT": -1, "WIS": -1},
    )
    assert result["STR"] == 13
    assert result["INT"] == 12
    assert result["WIS"] == 12
    assert result["DEX"] == 12
