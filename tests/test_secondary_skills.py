"""Tests for the Secondary Skills optional rule."""
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


# ── Wizard step ordering & gating ──────────────────────────────────────────

def _draft_id_from(redirect_response) -> str:
    return redirect_response.headers["location"].split("/")[2]


def _start_draft_at(client, abilities=None):
    """New draft, walk past abilities/race/class/alignment to land on skill."""
    abilities = abilities or {
        "STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10
    }
    r = client.get("/wizard/new")
    draft_id = _draft_id_from(r)
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = abilities
    from aose.characters import save_draft
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    return draft_id


def test_skill_step_inserted_into_breadcrumb_when_rule_active(client):
    draft_id = _start_draft_at(client)
    r = client.get(f"/wizard/{draft_id}/alignment")
    assert "Secondary Skill" in r.text


def test_alignment_redirects_to_skill_when_rule_active(client):
    draft_id = _start_draft_at(client)
    r = client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/skill"


def test_alignment_redirects_to_hp_when_rule_inactive(client, tmp_path):
    """Sanity check: the regular path is unchanged when the rule is off."""
    save_settings(client._settings_path, RuleSet(secondary_skills=False))
    draft_id = _start_draft_at(client)
    r = client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    assert r.headers["location"] == f"/wizard/{draft_id}/hp"


def test_skill_step_404_route_when_rule_inactive(client):
    """If the user manually navigates to /skill with the rule off, gate bounces them."""
    save_settings(client._settings_path, RuleSet(secondary_skills=False))
    draft_id = _start_draft_at(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    r = client.get(f"/wizard/{draft_id}/skill")
    assert r.status_code == 303
    assert "/skill" not in r.headers["location"]


# ── Auto-roll on GET ───────────────────────────────────────────────────────

def test_get_skill_auto_rolls_on_first_visit(client):
    from aose.characters import save_draft
    draft_id = _start_draft_at(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})

    draft = load_draft(draft_id, client._drafts_dir)
    assert "secondary_skill" not in draft

    r = client.get(f"/wizard/{draft_id}/skill")
    assert r.status_code == 200

    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["secondary_skill"] in GameData.load(DATA_DIR).secondary_skills


def test_get_skill_does_not_replace_existing(client):
    draft_id = _start_draft_at(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    # First visit auto-rolls
    client.get(f"/wizard/{draft_id}/skill")
    first = load_draft(draft_id, client._drafts_dir)["secondary_skill"]
    # Second visit must not re-roll
    client.get(f"/wizard/{draft_id}/skill")
    second = load_draft(draft_id, client._drafts_dir)["secondary_skill"]
    assert first == second


# ── Re-roll ────────────────────────────────────────────────────────────────

def test_reroll_changes_skill(client):
    draft_id = _start_draft_at(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.get(f"/wizard/{draft_id}/skill")
    before = load_draft(draft_id, client._drafts_dir)["secondary_skill"]
    # Try a few times — uniform random over ~50 entries should differ quickly.
    for _ in range(10):
        client.post(f"/wizard/{draft_id}/skill/reroll")
        after = load_draft(draft_id, client._drafts_dir)["secondary_skill"]
        if after != before:
            return
    pytest.fail("Re-roll never changed the skill after 10 tries")


# ── POST /skill ────────────────────────────────────────────────────────────

def test_post_skill_persists_choice_and_advances(client):
    draft_id = _start_draft_at(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.get(f"/wizard/{draft_id}/skill")
    r = client.post(f"/wizard/{draft_id}/skill", data={"secondary_skill": "Healer"})
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/hp"
    assert load_draft(draft_id, client._drafts_dir)["secondary_skill"] == "Healer"


def test_post_skill_rejects_unknown_skill(client):
    draft_id = _start_draft_at(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.get(f"/wizard/{draft_id}/skill")
    r = client.post(
        f"/wizard/{draft_id}/skill",
        data={"secondary_skill": "Astronaut"},
    )
    assert r.status_code == 400


# ── End-to-end: skill flows into character ─────────────────────────────────

def _finish_wizard(client, draft_id):
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    r = client.post(f"/wizard/{draft_id}/finalize")
    return r.headers["location"].split("/")[-1]


def test_skill_persists_to_character_and_sheet(client):
    draft_id = _start_draft_at(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.get(f"/wizard/{draft_id}/skill")  # auto-roll
    client.post(f"/wizard/{draft_id}/skill", data={"secondary_skill": "Blacksmith"})
    char_id = _finish_wizard(client, draft_id)

    spec = load_character(char_id, client._characters_dir)
    assert spec.secondary_skill == "Blacksmith"

    r = client.get(f"/character/{char_id}")
    assert "Secondary Skill" in r.text
    assert "Blacksmith" in r.text


def test_skill_appears_on_print_page(client):
    draft_id = _start_draft_at(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.get(f"/wizard/{draft_id}/skill")
    client.post(f"/wizard/{draft_id}/skill", data={"secondary_skill": "Scribe"})
    char_id = _finish_wizard(client, draft_id)
    r = client.get(f"/character/{char_id}/print")
    assert "Secondary Skill" in r.text
    assert "Scribe" in r.text


def test_skill_does_not_render_when_absent(client):
    """If a character was built without the rule, the sheet doesn't show the section."""
    save_settings(client._settings_path, RuleSet(secondary_skills=False))
    draft_id = _start_draft_at(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    char_id = _finish_wizard(client, draft_id)
    r = client.get(f"/character/{char_id}")
    assert "Secondary Skill" not in r.text


# ── Review page shows the skill ────────────────────────────────────────────

def test_review_page_includes_skill(client):
    draft_id = _start_draft_at(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.get(f"/wizard/{draft_id}/skill")
    client.post(f"/wizard/{draft_id}/skill", data={"secondary_skill": "Cartographer"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    # Equipment step now sits between HP and review; advance through it.
    client.get(f"/wizard/{draft_id}/equipment")
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.get(f"/wizard/{draft_id}/review")
    assert "Cartographer" in r.text
