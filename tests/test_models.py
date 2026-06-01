import pytest
from pydantic import ValidationError

from aose.models import CharacterSpec, RuleSet


def test_default_ruleset():
    rs = RuleSet()
    assert rs.ascending_ac is False
    assert rs.separate_race_class is True
    assert rs.lift_demihuman_restrictions is False
    assert rs.encumbrance == "basic"


def test_ruleset_has_no_removed_flags():
    """max_hp_at_l1, the two split demihuman flags, and ability_roll_method are
    gone; extra='forbid' means passing them raises rather than silently
    accepting."""
    for dead in ("max_hp_at_l1", "demihuman_level_limits",
                 "demihuman_class_restrictions", "ability_roll_method"):
        with pytest.raises(ValidationError):
            RuleSet(**{dead: True})  # type: ignore[arg-type]


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
