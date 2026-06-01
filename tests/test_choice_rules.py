"""Tests for the two ruleset *choice* groups: ability_roll_method and encumbrance.

Each is a non-bool ruleset field (Literal) — these were the last items left
on the optional-rules matrix when the bool toggles all shipped.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, load_draft, save_draft, save_settings
from aose.data.loader import GameData
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.sheet.view import ENCUMBRANCE_DESCRIPTIONS, build_sheet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def _make_client(tmp_path, ruleset):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True)
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, ruleset)
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._settings_path = settings_path
    client._drafts_dir = drafts_dir
    client._characters_dir = characters_dir
    return client


# ════════════════════════════════════════════════════════════════════════════
# Encumbrance
# ════════════════════════════════════════════════════════════════════════════

def test_sheet_carries_encumbrance_description():
    data = GameData.load(DATA_DIR)
    spec = CharacterSpec(
        name="X",
        abilities={"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10},
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="law",
        ruleset=RuleSet(encumbrance="detailed"),
    )
    sheet = build_sheet(spec, data)
    assert sheet.encumbrance_mode == "detailed"
    assert sheet.encumbrance_description == ENCUMBRANCE_DESCRIPTIONS["detailed"]


def test_sheet_html_renders_encumbrance_description(tmp_path):
    client = _make_client(tmp_path, RuleSet(encumbrance="none"))
    # Build a character via the wizard with encumbrance=none
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "X"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    r = client.get(f"/character/{char_id}")
    assert ENCUMBRANCE_DESCRIPTIONS["none"] in r.text


# ════════════════════════════════════════════════════════════════════════════
# Abilities are always 3d6 in order (no method choice)
# ════════════════════════════════════════════════════════════════════════════

def test_new_wizard_rolls_3d6_in_order(tmp_path):
    client = _make_client(tmp_path, RuleSet())
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    assert set(draft["abilities"]) == {"STR", "INT", "WIS", "DEX", "CON", "CHA"}
    for v in draft["abilities"].values():
        assert 3 <= v <= 18
    # No arrange pool is ever seeded.
    assert "abilities_pool" not in draft


def test_abilities_form_only_needs_name(tmp_path):
    client = _make_client(tmp_path, RuleSet())
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    r = client.post(f"/wizard/{draft_id}/abilities", data={"name": "Whatever"})
    assert r.status_code == 303


# ════════════════════════════════════════════════════════════════════════════
# Settings page — no rule should still show "pending"
# ════════════════════════════════════════════════════════════════════════════

def test_choice_group_pending_badge_hidden_when_implemented(tmp_path):
    client = _make_client(tmp_path, RuleSet())
    r = client.get("/settings")
    # The Encumbrance group is implemented — no "pending" badge near its legend.
    idx = r.text.index('Encumbrance')
    snippet = r.text[idx:idx + 400]
    assert ">pending<" not in snippet
