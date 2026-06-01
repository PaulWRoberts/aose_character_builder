"""Tests for the pure creation-warning helper used by the abilities step."""
from aose.engine.ability_mods import ability_warnings


def test_all_scores_eight_or_lower_is_subpar():
    scores = {"STR": 8, "INT": 7, "WIS": 6, "DEX": 8, "CON": 5, "CHA": 4}
    result = ability_warnings(scores)
    assert result["subpar"] is True
    assert result["rock_bottom"] == []


def test_one_high_score_is_not_subpar():
    scores = {"STR": 8, "INT": 7, "WIS": 6, "DEX": 9, "CON": 5, "CHA": 4}
    result = ability_warnings(scores)
    assert result["subpar"] is False


def test_rock_bottom_lists_each_three():
    scores = {"STR": 3, "INT": 11, "WIS": 12, "DEX": 3, "CON": 14, "CHA": 10}
    result = ability_warnings(scores)
    assert result["rock_bottom"] == ["STR", "DEX"]


def test_normal_spread_has_no_warnings():
    scores = {"STR": 12, "INT": 11, "WIS": 9, "DEX": 13, "CON": 14, "CHA": 10}
    result = ability_warnings(scores)
    assert result["subpar"] is False
    assert result["rock_bottom"] == []
