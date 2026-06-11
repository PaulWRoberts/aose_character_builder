"""Individual-initiative optional rule: DEX modifier, engine breakdown,
feature gating, and sheet rendering."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.data.loader import GameData
from aose.engine.ability_mods import initiative_modifier, ability_table_row
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


# ── DEX → initiative modifier (single source of truth) ──────────────────────
@pytest.mark.parametrize("score,expected", [
    (2, -2), (3, -2),               # clamp below 3
    (4, -1), (8, -1),
    (9, 0), (12, 0),
    (13, 1), (17, 1),
    (18, 2), (19, 2),               # clamp above 18
])
def test_initiative_modifier_table(score, expected):
    assert initiative_modifier(score) == expected


def test_dex_init_display_row_unchanged():
    """The Initiative cell of the DEX reference row still renders the book
    strings (derived from the same numeric source)."""
    def init_cell(score):
        return dict(ability_table_row("DEX", score))["Initiative"]
    assert init_cell(3) == "−2"     # U+2212
    assert init_cell(7) == "−1"
    assert init_cell(10) == "None"
    assert init_cell(15) == "+1"
    assert init_cell(18) == "+2"
