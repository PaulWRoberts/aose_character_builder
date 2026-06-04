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
