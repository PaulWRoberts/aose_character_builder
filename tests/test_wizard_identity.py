"""Tests for the consolidated Identity & Background step + new flow order."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_draft, save_draft, save_settings
from aose.models import RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def _make_client(tmp_path, ruleset=None):
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, ruleset or RuleSet())
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=tmp_path / "characters",
        drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._drafts_dir = tmp_path / "drafts"
    client._characters_dir = tmp_path / "characters"
    client._settings_path = settings_path
    return client


def _drive_to_identity(client, abilities=None, race="human", cls="fighter"):
    """New draft walked through to the Identity step (abilities/race/class/
    adjust/class_setup all done)."""
    abilities = abilities or {
        "STR": 13, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 13
    }
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = abilities
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": race})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": cls})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    return draft_id


# ── abilities no longer collects name ──────────────────────────────────────

def test_abilities_completes_without_name(tmp_path):
    client = _make_client(tmp_path)
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 13, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 13}
    save_draft(draft_id, draft, client._drafts_dir)
    r = client.post(f"/wizard/{draft_id}/abilities", data={})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft.get("abilities_confirmed") is True
    assert "name" not in draft


def test_abilities_page_has_no_name_field(tmp_path):
    client = _make_client(tmp_path)
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    r = client.get(f"/wizard/{draft_id}/abilities")
    assert 'name="name"' not in r.text


# ── flow order: identity after class_setup; old steps gone ─────────────────

def test_identity_step_sits_after_class_setup(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client)
    r = client.get(f"/wizard/{draft_id}/identity")
    assert r.status_code == 200
    # Breadcrumb order: Class Setup precedes Identity precedes Equipment.
    body = r.text
    assert body.index("Class Setup") < body.index("Identity")
    assert body.index("Identity") < body.index("Equipment")


def test_standalone_alignment_and_skill_steps_are_gone(tmp_path):
    client = _make_client(tmp_path, RuleSet(secondary_skills=True))
    draft_id = _drive_to_identity(client)
    # The old routes no longer exist.
    assert client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"}).status_code in (404, 405)
    assert client.get(f"/wizard/{draft_id}/skill").status_code in (404, 405)


def test_adjust_redirects_to_class_setup_not_alignment(tmp_path):
    client = _make_client(tmp_path)
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 13, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 13}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    r = client.post(f"/wizard/{draft_id}/adjust", data={})
    assert r.headers["location"] == f"/wizard/{draft_id}/class_setup"


# ── identity page content + validation ─────────────────────────────────────

def test_identity_requires_name(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client)
    r = client.post(f"/wizard/{draft_id}/identity", data={"name": "", "alignment": "law"})
    assert r.status_code == 400


def test_identity_persists_name_and_alignment_then_advances(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client)
    r = client.post(
        f"/wizard/{draft_id}/identity", data={"name": "Aragorn", "alignment": "law"}
    )
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/equipment"
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["name"] == "Aragorn"
    assert draft["alignment"] == "law"


def test_identity_filters_alignment_options_to_class_intersection(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, cls="paladin",
                                  abilities={"STR": 13, "INT": 11, "WIS": 13,
                                             "DEX": 13, "CON": 14, "CHA": 13})
    r = client.get(f"/wizard/{draft_id}/identity")
    assert r.status_code == 200
    assert 'value="law"' in r.text
    assert 'value="chaos"' not in r.text
    assert 'value="neutral"' not in r.text


def test_identity_rejects_out_of_set_alignment(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, cls="paladin",
                                  abilities={"STR": 13, "INT": 11, "WIS": 13,
                                             "DEX": 13, "CON": 14, "CHA": 13})
    r = client.post(
        f"/wizard/{draft_id}/identity", data={"name": "Bad", "alignment": "chaos"}
    )
    assert r.status_code == 400


# ── secondary skill section gating ─────────────────────────────────────────

def test_identity_hides_skill_section_when_rule_off(tmp_path):
    client = _make_client(tmp_path, RuleSet(secondary_skills=False))
    draft_id = _drive_to_identity(client)
    r = client.get(f"/wizard/{draft_id}/identity")
    assert "Secondary Skill" not in r.text


def test_identity_shows_and_autorolls_skill_when_rule_on(tmp_path):
    from aose.data.loader import GameData
    client = _make_client(tmp_path, RuleSet(secondary_skills=True))
    draft_id = _drive_to_identity(client)
    r = client.get(f"/wizard/{draft_id}/identity")
    assert "Secondary Skill" in r.text
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["secondary_skill"] in GameData.load(DATA_DIR).secondary_skills


def test_identity_skill_reroll_changes_value(tmp_path):
    client = _make_client(tmp_path, RuleSet(secondary_skills=True))
    draft_id = _drive_to_identity(client)
    client.get(f"/wizard/{draft_id}/identity")
    before = load_draft(draft_id, client._drafts_dir)["secondary_skill"]
    for _ in range(10):
        client.post(f"/wizard/{draft_id}/identity/skill-reroll")
        after = load_draft(draft_id, client._drafts_dir)["secondary_skill"]
        if after != before:
            return
    pytest.fail("Re-roll never changed the skill after 10 tries")


def test_identity_requires_skill_when_rule_on(tmp_path):
    client = _make_client(tmp_path, RuleSet(secondary_skills=True))
    draft_id = _drive_to_identity(client)
    # Post a non-skill payload; skill must be supplied and valid.
    r = client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "X", "alignment": "law", "secondary_skill": "Astronaut"},
    )
    assert r.status_code == 400


# ── class change clears alignment but keeps name + secondary_skill ─────────

def test_class_change_clears_alignment_keeps_name_and_skill(tmp_path):
    client = _make_client(tmp_path, RuleSet(secondary_skills=True))
    draft_id = _drive_to_identity(client)
    client.get(f"/wizard/{draft_id}/identity")  # auto-rolls skill
    client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Keeper", "alignment": "law",
              "secondary_skill": load_draft(draft_id, client._drafts_dir)["secondary_skill"]},
    )
    # Go back and change the class.
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "thief"})
    draft = load_draft(draft_id, client._drafts_dir)
    assert "alignment" not in draft
    assert draft["name"] == "Keeper"
    assert "secondary_skill" in draft
