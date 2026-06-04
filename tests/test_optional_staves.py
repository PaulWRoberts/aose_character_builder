"""Optional Staves rule: model fields, engine gating, and data integration."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.models import CharClass, RuleSet

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


def test_ruleset_defaults_optional_staves_off():
    assert RuleSet().optional_staves is False


def test_charclass_optional_weapons_defaults_empty(data):
    # Fighter has no optional weapons in data.
    assert data.classes["fighter"].optional_weapons_allowed == []


def test_charclass_accepts_optional_weapons_list(data):
    cls = data.classes["fighter"].model_copy(
        update={"optional_weapons_allowed": ["staff"]}
    )
    assert cls.optional_weapons_allowed == ["staff"]


from aose.engine.proficiency import allowed_weapon_ids


def _caster_with_optional_staff(data):
    # A constructed class: dagger allowed, staff optional. Independent of the
    # YAML edits in Task 3 so this test is isolated.
    return data.classes["magic_user"].model_copy(
        update={"weapons_allowed": ["dagger"], "optional_weapons_allowed": ["staff"]}
    )


def test_optional_weapon_excluded_when_ruleset_none(data):
    cls = _caster_with_optional_staff(data)
    allowed = allowed_weapon_ids([cls], data)
    assert "dagger" in allowed
    assert "staff" not in allowed


def test_optional_weapon_excluded_when_rule_off(data):
    cls = _caster_with_optional_staff(data)
    allowed = allowed_weapon_ids([cls], data, RuleSet(optional_staves=False))
    assert "staff" not in allowed


def test_optional_weapon_included_when_rule_on(data):
    cls = _caster_with_optional_staff(data)
    allowed = allowed_weapon_ids([cls], data, RuleSet(optional_staves=True))
    assert "dagger" in allowed
    assert "staff" in allowed


def test_optional_weapon_ignored_for_unrestricted_class(data):
    # A class whose weapons_allowed == "all" stays "all" regardless.
    fighter = data.classes["fighter"].model_copy(
        update={"optional_weapons_allowed": ["staff"]}
    )
    assert allowed_weapon_ids([fighter], data, RuleSet(optional_staves=True)) == "all"
