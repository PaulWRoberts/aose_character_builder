"""Languages section on the Identity page + draft clears."""
from pathlib import Path

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
    return client


def _drive_to_identity(client, abilities, race="human", cls="fighter"):
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


HIGH_INT = {"STR": 13, "INT": 16, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 13}
LOW_INT = {"STR": 13, "INT": 9, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 13}


# ── GET: Languages section renders correctly ─────────────────────────────────

def test_identity_renders_language_section_with_native_and_pickers(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, HIGH_INT)  # INT 16 -> 2 additional
    r = client.get(f"/wizard/{draft_id}/identity")
    assert r.status_code == 200
    assert "Languages" in r.text
    assert "common" in r.text                       # native tongue shown
    assert "up to 2" in r.text                      # slot hint in template
    assert 'name="language"' in r.text              # at least one checkbox


def test_identity_no_pickers_when_int_low(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, LOW_INT)  # INT 9 -> 0 additional
    r = client.get(f"/wizard/{draft_id}/identity")
    assert 'name="language"' not in r.text


# ── POST: store, validate, advance ───────────────────────────────────────────

def test_identity_stores_chosen_languages(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, HIGH_INT)  # INT 16 -> 2 allowed
    r = client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Sage", "alignment": "law", "language": ["Dragon", "Ogre"]},
    )
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["languages"] == ["Dragon", "Ogre"]


def test_identity_allows_fewer_than_max_languages(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, HIGH_INT)  # 2 allowed, choose 0
    r = client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Quiet", "alignment": "law"},
    )
    assert r.status_code == 303
    assert load_draft(draft_id, client._drafts_dir)["languages"] == []


def test_identity_rejects_too_many_languages(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, {"STR": 13, "INT": 13, "WIS": 12,
                                           "DEX": 13, "CON": 14, "CHA": 13})  # 1 allowed
    r = client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Greedy", "alignment": "law", "language": ["Dragon", "Ogre"]},
    )
    assert r.status_code == 400


def test_identity_rejects_unknown_language(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, HIGH_INT)
    r = client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Faker", "alignment": "law", "language": ["Klingon"]},
    )
    assert r.status_code == 400


# ── Round-trip: finalized character keeps languages ──────────────────────────

def test_finalized_character_keeps_languages(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, HIGH_INT)
    client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Polyglot", "alignment": "law", "language": ["Dragon"]},
    )
    client.get(f"/wizard/{draft_id}/equipment")          # rolls gold
    client.post(f"/wizard/{draft_id}/equipment", data={})  # -> review
    r = client.post(f"/wizard/{draft_id}/finalize")
    assert r.status_code == 303
    char_url = r.headers["location"]
    page = client.get(char_url)
    assert "Dragon" in page.text
    assert "Lawful" in page.text


# ── Downstream clears ─────────────────────────────────────────────────────────

def test_languages_cleared_when_race_changes(tmp_path):
    client = _make_client(tmp_path, RuleSet(strict_mode=False))
    draft_id = _drive_to_identity(client, HIGH_INT)
    client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Shifter", "alignment": "law", "language": ["Dragon"]},
    )
    assert load_draft(draft_id, client._drafts_dir)["languages"] == ["Dragon"]
    # Go back and change race (elf meets INT 16).
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "elf"})
    assert "languages" not in load_draft(draft_id, client._drafts_dir)


def test_languages_cleared_when_adjustments_change(tmp_path):
    client = _make_client(tmp_path, RuleSet(strict_mode=False))
    draft_id = _drive_to_identity(client, HIGH_INT)
    client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Tuner", "alignment": "law", "language": ["Dragon"]},
    )
    # Re-submitting the adjust step clears languages (final INT may move).
    client.post(f"/wizard/{draft_id}/adjust", data={})
    assert "languages" not in load_draft(draft_id, client._drafts_dir)
