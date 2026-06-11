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


from aose.engine.initiative import initiative_detail


def _spec(race_id, class_id, dex, *, individual_init=True, level=1):
    return CharacterSpec(
        name="Pip",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": dex, "CON": 10, "CHA": 10},
        race_id=race_id,
        classes=[ClassEntry(class_id=class_id, level=level, hp_rolls=[5])],
        alignment="law",
        ruleset=RuleSet(individual_initiative=individual_init),
    )


def test_initiative_detail_dex_only():
    data = GameData.load(DATA_DIR)
    # Human fighter, DEX 13 → +1 from DEX, +1 from Decisiveness = +2
    det = initiative_detail(_spec("human", "fighter", 13), data)
    assert det.base == 1
    assert det.total == 2
    assert det.lines[0].source == "Dexterity" and det.lines[0].bonus == 1
    assert any(l.source == "Decisiveness" and l.bonus == 1 for l in det.lines)


def test_initiative_detail_halfling_split():
    data = GameData.load(DATA_DIR)
    # Halfling thief, DEX 9 → 0 from DEX, +1 from race feature = +1
    det = initiative_detail(_spec("halfling", "thief", 9), data)
    assert det.base == 0
    assert det.total == 1
    assert any(l.bonus == 1 for l in det.lines[1:])


def test_initiative_detail_halfling_race_as_class():
    data = GameData.load(DATA_DIR)
    # Halfling-as-class, DEX 18 → +2 DEX, +1 class feature = +3
    spec = CharacterSpec(
        name="Pip",
        abilities={"STR": 9, "INT": 10, "WIS": 10, "DEX": 18, "CON": 12, "CHA": 10},
        race_id="halfling",
        classes=[ClassEntry(class_id="halfling", level=1, hp_rolls=[6])],
        alignment="law",
        ruleset=RuleSet(separate_race_class=False, individual_initiative=True),
    )
    det = initiative_detail(spec, data)
    assert det.base == 2
    assert det.total == 3


from aose.sheet.view import _race_features, _class_features


def test_halfling_initiative_feature_hidden_when_rule_off():
    data = GameData.load(DATA_DIR)
    names = lambda spec: [f.name for f in _race_features(spec, data)]
    off = _spec("halfling", "thief", 12, individual_init=False)
    on = _spec("halfling", "thief", 12, individual_init=True)
    assert "Initiative Bonus (Optional Rule)" not in names(off)
    assert "Initiative Bonus (Optional Rule)" in names(on)


def test_halfling_race_as_class_initiative_feature_gated():
    data = GameData.load(DATA_DIR)
    def cls_names(individual_init):
        spec = CharacterSpec(
            name="Pip",
            abilities={"STR": 9, "INT": 10, "WIS": 10, "DEX": 12, "CON": 12, "CHA": 10},
            race_id="halfling",
            classes=[ClassEntry(class_id="halfling", level=1, hp_rolls=[6])],
            alignment="law",
            ruleset=RuleSet(separate_race_class=False,
                            individual_initiative=individual_init),
        )
        return [f.name for f in _class_features(spec, data)]
    assert "Initiative Bonus (Optional Rule)" not in cls_names(False)
    assert "Initiative Bonus (Optional Rule)" in cls_names(True)


def test_human_decisiveness_always_shown():
    data = GameData.load(DATA_DIR)
    names = lambda spec: [f.name for f in _race_features(spec, data)]
    off = _spec("human", "fighter", 12, individual_init=False)
    assert "Decisiveness" in names(off)


from aose.sheet.view import build_sheet


def test_build_sheet_exposes_initiative_when_rule_on():
    data = GameData.load(DATA_DIR)
    sheet = build_sheet(_spec("human", "fighter", 13, individual_init=True), data)
    assert sheet.individual_initiative is True
    assert sheet.initiative_modifier == 2          # +1 DEX, +1 Decisiveness
    assert sheet.initiative_lines[0].source == "Dexterity"
    assert "Individual Initiative" in sheet.enabled_optional_rules


def test_build_sheet_initiative_off_by_default():
    data = GameData.load(DATA_DIR)
    sheet = build_sheet(_spec("human", "fighter", 13, individual_init=False), data)
    assert sheet.individual_initiative is False
    assert "Individual Initiative" not in sheet.enabled_optional_rules


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
