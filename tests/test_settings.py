"""Tests for the ruleset settings page and wizard integration."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, load_settings, save_settings
from aose.models import RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture
def client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    settings_path = tmp_path / "settings.json"
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._settings_path = settings_path  # noqa: SLF001 — test convenience
    return client


# ── load_settings / save_settings ──────────────────────────────────────────

def test_load_returns_defaults_when_missing(tmp_path):
    rs = load_settings(tmp_path / "nope.json")
    assert rs == RuleSet()
    assert rs.ascending_ac is False


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(path, RuleSet(ascending_ac=True, max_hp_at_l1=True))
    rs = load_settings(path)
    assert rs.ascending_ac is True
    assert rs.max_hp_at_l1 is True


def test_save_writes_pretty_json(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(path, RuleSet(ascending_ac=True))
    raw = path.read_text(encoding="utf-8")
    assert "ascending_ac" in raw
    assert json.loads(raw)["ruleset"]["ascending_ac"] is True


# ── /settings page rendering ───────────────────────────────────────────────

def test_get_settings_renders(client):
    r = client.get("/settings")
    assert r.status_code == 200
    assert "Ruleset Settings" in r.text
    assert "Ascending AC" in r.text


def test_get_settings_shows_default_unchecked(client):
    r = client.get("/settings")
    # ascending_ac defaults to False so the checkbox should NOT be checked
    assert 'name="ascending_ac"' in r.text
    # No "checked" attribute next to the ascending_ac input
    snippet = r.text[r.text.index('name="ascending_ac"') - 100:r.text.index('name="ascending_ac"') + 50]
    assert "checked" not in snippet


def test_get_settings_reflects_saved_state(client):
    save_settings(client._settings_path, RuleSet(ascending_ac=True))
    r = client.get("/settings")
    snippet = r.text[r.text.index('name="ascending_ac"') - 100:r.text.index('name="ascending_ac"') + 100]
    assert "checked" in snippet


def test_settings_page_links_in_nav(client):
    r = client.get("/")
    assert 'href="/settings"' in r.text


def test_pending_badge_shown_for_unimplemented_rules(client):
    r = client.get("/settings")
    # weapon_proficiency is not yet implemented — should show pending badge
    idx = r.text.index('name="weapon_proficiency"')
    snippet = r.text[idx:idx + 600]
    assert "pending" in snippet


def test_no_pending_badge_for_ascending_ac(client):
    r = client.get("/settings")
    idx = r.text.index('name="ascending_ac"')
    # The pending badge appears inside the same .rule block, before the next checkbox
    next_idx = r.text.find('type="checkbox"', idx + 10)
    snippet = r.text[idx:next_idx]
    assert "pending" not in snippet


# ── POST /settings ─────────────────────────────────────────────────────────

def test_post_settings_persists_to_disk(client):
    r = client.post("/settings", data={
        "ascending_ac": "on",
        "max_hp_at_l1": "on",
        "ability_roll_method": "3d6_arrange",
        "encumbrance": "detailed",
    })
    assert r.status_code == 303
    assert r.headers["location"] == "/settings?saved=1"

    rs = load_settings(client._settings_path)
    assert rs.ascending_ac is True
    assert rs.max_hp_at_l1 is True
    assert rs.ability_roll_method == "3d6_arrange"
    assert rs.encumbrance == "detailed"
    # Unchecked boxes default to False
    assert rs.weapon_proficiency is False


def test_post_settings_unchecking_clears_flag(client):
    save_settings(client._settings_path, RuleSet(ascending_ac=True))
    client.post("/settings", data={})  # no checkboxes ticked
    rs = load_settings(client._settings_path)
    assert rs.ascending_ac is False


def test_post_settings_ignores_invalid_radio_choice(client):
    r = client.post("/settings", data={"ability_roll_method": "made_up_method"})
    assert r.status_code == 303
    rs = load_settings(client._settings_path)
    # Falls back to the default since the choice was invalid
    assert rs.ability_roll_method == "3d6_in_order"


def test_get_settings_shows_flash_after_save(client):
    r = client.get("/settings?saved=1")
    assert "Settings saved" in r.text


# ── Wizard integration: settings flow into new characters ──────────────────

def _override_abilities(draft_id, drafts_dir, abilities):
    from aose.characters import load_draft, save_draft
    draft = load_draft(draft_id, drafts_dir)
    draft["abilities"] = abilities
    save_draft(draft_id, draft, drafts_dir)


def _run_wizard_to_completion(client, drafts_dir, name="Thorin"):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    _override_abilities(draft_id, drafts_dir, {
        "STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10,
    })
    client.post(f"/wizard/{draft_id}/abilities", data={"name": name})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    return char_id


def test_new_character_inherits_active_ruleset(client, tmp_path):
    save_settings(client._settings_path, RuleSet(ascending_ac=True, max_hp_at_l1=True))
    char_id = _run_wizard_to_completion(client, tmp_path / "drafts")
    spec = load_character(char_id, tmp_path / "characters")
    assert spec.ruleset.ascending_ac is True
    assert spec.ruleset.max_hp_at_l1 is True


def test_changing_settings_does_not_alter_existing_character(client, tmp_path):
    # Build with defaults
    char_id_default = _run_wizard_to_completion(client, tmp_path / "drafts", name="Default")
    # Change settings
    save_settings(client._settings_path, RuleSet(ascending_ac=True))
    # Build a second character
    char_id_asc = _run_wizard_to_completion(client, tmp_path / "drafts", name="Ascending")
    # Old character still has descending AC
    spec_default = load_character(char_id_default, tmp_path / "characters")
    spec_asc = load_character(char_id_asc, tmp_path / "characters")
    assert spec_default.ruleset.ascending_ac is False
    assert spec_asc.ruleset.ascending_ac is True


def test_ascending_ac_renders_on_sheet(client, tmp_path):
    """End-to-end: setting ascending AC should change what the sheet shows."""
    save_settings(client._settings_path, RuleSet(ascending_ac=True))
    char_id = _run_wizard_to_completion(client, tmp_path / "drafts")
    r = client.get(f"/character/{char_id}")
    assert r.status_code == 200
    # Ascending AC sheets show "Attack Bonus", descending sheets show "THAC0"
    assert "Attack Bonus" in r.text
    assert "THAC0" not in r.text
