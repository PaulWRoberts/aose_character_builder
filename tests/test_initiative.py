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


def test_initiative_grants_present_in_data():
    data = GameData.load(DATA_DIR)

    def init_grant(feature):
        return [g for g in feature.granted_modifiers if g.target == "initiative"]

    halfling_race = data.races["halfling"]
    feat = next(f for f in halfling_race.features
                if f.id == "initiative_bonus_optional_rule")
    assert init_grant(feat) and init_grant(feat)[0].value == 1
    assert (feat.mechanical or {}).get("requires_rule") == "individual_initiative"

    halfling_class = data.classes["halfling"]
    cfeat = next(f for f in halfling_class.features
                 if f.id == "initiative_bonus_optional_rule")
    assert init_grant(cfeat) and init_grant(cfeat)[0].value == 1
    assert (cfeat.mechanical or {}).get("requires_rule") == "individual_initiative"

    human = data.races["human"]
    dec = next(f for f in human.features if f.id == "decisiveness")
    assert init_grant(dec) and init_grant(dec)[0].value == 1
    # Decisiveness always shows — it must NOT carry requires_rule.
    assert (dec.mechanical or {}).get("requires_rule") is None
