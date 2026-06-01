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
