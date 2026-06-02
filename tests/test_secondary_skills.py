"""Tests for the Secondary Skills optional rule — skill section lives on identity page."""
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from aose.characters import load_character, load_draft, save_settings
from aose.data.loader import GameData, _load_secondary_skills
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
    # Enable the rule by default for these tests.
    save_settings(settings_path, RuleSet(secondary_skills=True))
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


# ── Loader ─────────────────────────────────────────────────────────────────

def test_loader_reads_real_skills_file():
    skills = _load_secondary_skills(DATA_DIR)
    assert len(skills) > 20
    assert "Blacksmith" in skills
    assert "Healer" in skills


def test_loader_returns_empty_when_file_missing(tmp_path):
    assert _load_secondary_skills(tmp_path) == []


def test_loader_strips_blanks_and_dedupes(tmp_path):
    (tmp_path / "secondary_skills.yaml").write_text(
        yaml.safe_dump(["Healer", "", "Healer", "  Mason  ", "Mason"]),
        encoding="utf-8",
    )
    assert _load_secondary_skills(tmp_path) == ["Healer", "Mason"]


def test_loader_rejects_non_list(tmp_path):
    (tmp_path / "secondary_skills.yaml").write_text("foo: bar", encoding="utf-8")
    with pytest.raises(ValueError):
        _load_secondary_skills(tmp_path)


def test_game_data_exposes_skills():
    data = GameData.load(DATA_DIR)
    assert "Blacksmith" in data.secondary_skills


# ── Wizard flow helpers ─────────────────────────────────────────────────────

def _draft_id_from(redirect_response) -> str:
    return redirect_response.headers["location"].split("/")[2]


def _drive_to_identity(client, abilities=None):
    """New draft, walk through abilities/race/class/adjust/class_setup to land on identity."""
    from aose.characters import save_draft
    abilities = abilities or {
        "STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10
    }
    r = client.get("/wizard/new")
    draft_id = _draft_id_from(r)
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = abilities
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    return draft_id


# ── Identity page shows skill section when rule is active ──────────────────

def test_skill_section_shown_in_identity_breadcrumb_when_rule_active(client):
    draft_id = _drive_to_identity(client)
    r = client.get(f"/wizard/{draft_id}/identity")
    assert "Secondary Skill" in r.text


def test_skill_section_hidden_in_identity_when_rule_inactive(client, tmp_path):
    save_settings(client._settings_path, RuleSet(secondary_skills=False))
    draft_id = _drive_to_identity(client)
    r = client.get(f"/wizard/{draft_id}/identity")
    assert "Secondary Skill" not in r.text


# ── Auto-roll on GET /identity ─────────────────────────────────────────────

def test_identity_get_auto_rolls_skill_on_first_visit(client):
    draft_id = _drive_to_identity(client)
    draft = load_draft(draft_id, client._drafts_dir)
    assert "secondary_skill" not in draft

    r = client.get(f"/wizard/{draft_id}/identity")
    assert r.status_code == 200

    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["secondary_skill"] in GameData.load(DATA_DIR).secondary_skills


def test_identity_get_does_not_replace_existing_skill(client):
    draft_id = _drive_to_identity(client)
    # First visit auto-rolls
    client.get(f"/wizard/{draft_id}/identity")
    first = load_draft(draft_id, client._drafts_dir)["secondary_skill"]
    # Second visit must not re-roll
    client.get(f"/wizard/{draft_id}/identity")
    second = load_draft(draft_id, client._drafts_dir)["secondary_skill"]
    assert first == second


# ── Re-roll via /identity/skill-reroll ────────────────────────────────────

def test_skill_reroll_changes_skill(client):
    draft_id = _drive_to_identity(client)
    client.get(f"/wizard/{draft_id}/identity")
    before = load_draft(draft_id, client._drafts_dir)["secondary_skill"]
    # Try a few times — uniform random over ~50 entries should differ quickly.
    for _ in range(10):
        client.post(f"/wizard/{draft_id}/identity/skill-reroll")
        after = load_draft(draft_id, client._drafts_dir)["secondary_skill"]
        if after != before:
            return
    pytest.fail("Re-roll never changed the skill after 10 tries")


def test_skill_reroll_redirects_to_identity(client):
    draft_id = _drive_to_identity(client)
    client.get(f"/wizard/{draft_id}/identity")
    r = client.post(f"/wizard/{draft_id}/identity/skill-reroll")
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/identity"


# ── POST /identity with skill ──────────────────────────────────────────────

def test_post_identity_persists_skill_and_advances(client):
    draft_id = _drive_to_identity(client)
    client.get(f"/wizard/{draft_id}/identity")  # auto-roll
    r = client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Gloin", "alignment": "law", "secondary_skill": "Healer"},
    )
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/equipment"
    assert load_draft(draft_id, client._drafts_dir)["secondary_skill"] == "Healer"


def test_post_identity_rejects_unknown_skill(client):
    draft_id = _drive_to_identity(client)
    client.get(f"/wizard/{draft_id}/identity")
    r = client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "X", "alignment": "law", "secondary_skill": "Astronaut"},
    )
    assert r.status_code == 400


# ── End-to-end: skill flows into character ─────────────────────────────────

def _finish_wizard(client, draft_id):
    client.get(f"/wizard/{draft_id}/equipment")
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    return r.headers["location"].split("/")[-1]


def test_skill_persists_to_character_and_sheet(client):
    draft_id = _drive_to_identity(client)
    client.get(f"/wizard/{draft_id}/identity")
    client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Gloin", "alignment": "law", "secondary_skill": "Blacksmith"},
    )
    char_id = _finish_wizard(client, draft_id)

    spec = load_character(char_id, client._characters_dir)
    assert spec.secondary_skill == "Blacksmith"

    r = client.get(f"/character/{char_id}")
    assert "Secondary Skill" in r.text
    assert "Blacksmith" in r.text


def test_skill_appears_on_print_page(client):
    draft_id = _drive_to_identity(client)
    client.get(f"/wizard/{draft_id}/identity")
    client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Gloin", "alignment": "law", "secondary_skill": "Scribe"},
    )
    char_id = _finish_wizard(client, draft_id)
    r = client.get(f"/character/{char_id}/print")
    assert "Secondary Skill" in r.text
    assert "Scribe" in r.text


def test_skill_does_not_render_when_absent(client):
    """If a character was built without the rule, the sheet doesn't show the section."""
    save_settings(client._settings_path, RuleSet(secondary_skills=False))
    draft_id = _drive_to_identity(client)
    client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Gloin", "alignment": "law"},
    )
    char_id = _finish_wizard(client, draft_id)
    r = client.get(f"/character/{char_id}")
    assert "Secondary Skill" not in r.text


# ── Review page shows the skill ────────────────────────────────────────────

def test_review_page_includes_skill(client):
    draft_id = _drive_to_identity(client)
    client.get(f"/wizard/{draft_id}/identity")
    client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Gloin", "alignment": "law", "secondary_skill": "Cartographer"},
    )
    client.post(f"/wizard/{draft_id}/equipment/roll-gold")
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.get(f"/wizard/{draft_id}/review")
    assert "Cartographer" in r.text
