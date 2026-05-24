import pytest
from pydantic import ValidationError

from aose.models import CharacterSpec, RuleSet


def test_default_ruleset():
    rs = RuleSet()
    assert rs.ascending_ac is False
    assert rs.separate_race_class is True
    assert rs.demihuman_level_limits is True
    assert rs.encumbrance == "basic"
    assert rs.ability_roll_method == "3d6_in_order"


def test_ruleset_rejects_unknown_field():
    with pytest.raises(ValidationError):
        RuleSet(does_not_exist=True)  # type: ignore[call-arg]


def test_character_requires_at_least_one_class():
    with pytest.raises(ValidationError):
        CharacterSpec(
            name="Nobody",
            abilities={
                "STR": 10, "INT": 10, "WIS": 10,
                "DEX": 10, "CON": 10, "CHA": 10,
            },
            race_id="dwarf",
            classes=[],
            alignment="law",
        )
