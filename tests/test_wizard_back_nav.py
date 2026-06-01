"""Tests for the wizard's back-navigation behaviour: clickable breadcrumb
for completed steps, and downstream clearing when an upstream choice changes."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_draft, save_draft, save_settings
from aose.models import RuleSet
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
    client._drafts_dir = drafts_dir
    return client


@pytest.fixture
def client(tmp_path):
    return _make_client(tmp_path, RuleSet())


def _start(client, abilities=None):
    abilities = abilities or {
        "STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10
    }
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = abilities
    save_draft(draft_id, draft, client._drafts_dir)
    return draft_id


# ── Breadcrumb rendering ───────────────────────────────────────────────────

def test_completed_steps_render_as_links(client):
    """At the class step, the abilities + race breadcrumb entries should be
    clickable links pointing back to those steps."""
    draft_id = _start(client)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    r = client.get(f"/wizard/{draft_id}/class")
    assert f'href="/wizard/{draft_id}/abilities"' in r.text
    assert f'href="/wizard/{draft_id}/race"' in r.text


def test_current_step_is_not_a_link(client):
    """The current step shouldn't be rendered as an <a> in the breadcrumb."""
    draft_id = _start(client)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    r = client.get(f"/wizard/{draft_id}/race")
    # The breadcrumb is the <ol class="wizard-steps">...</ol> block.
    start = r.text.index('wizard-steps')
    end = r.text.index('</ol>', start)
    breadcrumb = r.text[start:end]
    # The current-step list-item (class="current") should not contain an <a>.
    # Find the <li class="current"> and confirm no anchor inside.
    cur_start = breadcrumb.index('class="current"')
    cur_end = breadcrumb.index('</li>', cur_start)
    cur_li = breadcrumb[cur_start:cur_end]
    assert '<a ' not in cur_li


def test_future_steps_are_not_links(client):
    """Steps the user hasn't reached yet should not be clickable."""
    draft_id = _start(client)
    # At abilities only — name not yet set
    r = client.get(f"/wizard/{draft_id}/abilities")
    start = r.text.index('wizard-steps')
    end = r.text.index('</ol>', start)
    breadcrumb = r.text[start:end]
    # No href for /race, /class etc. (since they're future steps)
    assert f'href="/wizard/{draft_id}/race"' not in breadcrumb
    assert f'href="/wizard/{draft_id}/class"' not in breadcrumb


def test_breadcrumb_link_renders_on_review_for_every_done_step(client):
    """At the review step, every earlier step is a clickable link."""
    draft_id = _start(client)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.get(f"/wizard/{draft_id}/equipment")  # seeds gold
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.get(f"/wizard/{draft_id}/review")
    for step in ("abilities", "race", "class", "alignment", "hp", "equipment"):
        assert f'href="/wizard/{draft_id}/{step}"' in r.text, f"{step} not linked"


# ── GET past-step works directly (the URL was always reachable but is now
#    surfaced through the breadcrumb) ──────────────────────────────────────

def test_get_past_step_returns_that_step_not_a_redirect(client):
    """Navigating back to /race after class is picked should land on /race
    (HTTP 200), not redirect forward."""
    draft_id = _start(client)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    r = client.get(f"/wizard/{draft_id}/race")
    assert r.status_code == 200
    assert "Choose Race" in r.text or "Race" in r.text


# ── Downstream clearing ───────────────────────────────────────────────────

def test_changing_race_clears_class_and_below(client):
    """Pick race → class → HP roll → go back to race → pick a different race.
    The class, HP, and proficiencies (if any) should all be cleared."""
    draft_id = _start(client)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    # Confirm we have data downstream
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft.get("class_id") == "fighter"
    assert "hp_roll" in draft

    # Now change race — downstream should clear
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["race_id"] == "human"
    assert "class_id" not in draft
    assert "hp_roll" not in draft


def test_same_race_repick_keeps_downstream(client):
    """Re-posting the same race id should NOT wipe downstream choices —
    the user just re-confirmed the same race."""
    draft_id = _start(client)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")

    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    draft = load_draft(draft_id, client._drafts_dir)
    # Class and HP should still be present
    assert draft.get("class_id") == "fighter"
    assert "hp_roll" in draft


def test_changing_class_clears_hp_and_proficiencies(tmp_path):
    """Switching from one class to another should clear HP and proficiencies."""
    client = _make_client(tmp_path, RuleSet(weapon_proficiency=True))
    draft_id = _start(client)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})  # no class restrictions
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(
        f"/wizard/{draft_id}/proficiencies",
        data={"weapon": ["sword", "spear", "mace", "hand_axe"]},
    )
    client.post(f"/wizard/{draft_id}/hp/roll")
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft.get("proficiencies")
    assert "hp_roll" in draft

    # Need INT 9+ for magic_user; abilities have INT 11 so OK
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "magic_user"})
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft.get("class_id") == "magic_user"
    assert "hp_roll" not in draft
    assert "proficiencies" not in draft


def test_changing_class_in_multiclass_combo_clears_downstream(tmp_path):
    """Multi-class → single-class change must clear HP rolls (which were a list)."""
    client = _make_client(tmp_path, RuleSet(multiclassing=True))
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 12, "INT": 14, "WIS": 11, "DEX": 14, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Tauriel"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "elf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter,magic_user"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "neutral"})
    client.post(f"/wizard/{draft_id}/hp/roll")

    draft = load_draft(draft_id, client._drafts_dir)
    assert "hp_rolls" in draft
    assert "class_ids" in draft

    # Switch back to a single class — should swap storage and clear HP
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft.get("class_id") == "fighter"
    assert "class_ids" not in draft
    assert "hp_rolls" not in draft
    assert "hp_roll" not in draft
