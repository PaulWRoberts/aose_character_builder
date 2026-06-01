"""Tests for the pure creation-warning helper used by the abilities step."""
from pathlib import Path

from fastapi.testclient import TestClient

from aose.characters import load_draft, save_draft, save_settings
from aose.engine.ability_mods import ability_warnings
from aose.models import RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


# ── Pure helper tests ─────────────────────────────────────────────────────

def test_all_scores_eight_or_lower_is_subpar():
    scores = {"STR": 8, "INT": 7, "WIS": 6, "DEX": 8, "CON": 5, "CHA": 4}
    result = ability_warnings(scores)
    assert result["subpar"] is True
    assert result["rock_bottom"] == []


def test_one_high_score_is_not_subpar():
    scores = {"STR": 8, "INT": 7, "WIS": 6, "DEX": 9, "CON": 5, "CHA": 4}
    result = ability_warnings(scores)
    assert result["subpar"] is False


def test_rock_bottom_lists_each_three():
    scores = {"STR": 3, "INT": 11, "WIS": 12, "DEX": 3, "CON": 14, "CHA": 10}
    result = ability_warnings(scores)
    assert result["rock_bottom"] == ["STR", "DEX"]


def test_normal_spread_has_no_warnings():
    scores = {"STR": 12, "INT": 11, "WIS": 9, "DEX": 13, "CON": 14, "CHA": 10}
    result = ability_warnings(scores)
    assert result["subpar"] is False
    assert result["rock_bottom"] == []


# ── Page-render integration tests ─────────────────────────────────────────

def _make_client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True)
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, RuleSet())
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


def _new_draft_with_abilities(client, abilities):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = abilities
    save_draft(draft_id, draft, client._drafts_dir)
    return draft_id


def test_abilities_page_shows_subpar_banner(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft_with_abilities(
        client, {"STR": 8, "INT": 7, "WIS": 6, "DEX": 8, "CON": 5, "CHA": 4})
    r = client.get(f"/wizard/{draft_id}/abilities")
    assert "Sub-par character" in r.text


def test_abilities_page_hides_subpar_banner_for_normal_spread(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft_with_abilities(
        client, {"STR": 12, "INT": 11, "WIS": 9, "DEX": 13, "CON": 14, "CHA": 10})
    r = client.get(f"/wizard/{draft_id}/abilities")
    assert "Sub-par character" not in r.text


def test_abilities_page_shows_rock_bottom_note(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft_with_abilities(
        client, {"STR": 3, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10})
    r = client.get(f"/wizard/{draft_id}/abilities")
    assert "STR is 3 — extremely low." in r.text


def test_reroll_route_is_gone(tmp_path):
    client = _make_client(tmp_path)
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    r = client.post(f"/wizard/{draft_id}/reroll")
    assert r.status_code in (404, 405)
