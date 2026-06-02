from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters.drafts import load_draft, save_draft
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture
def client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"  # empty so no bootstrap noise
    examples_dir.mkdir()
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        examples_dir=examples_dir,
    )
    return TestClient(app, follow_redirects=False)


def _start_draft(client) -> str:
    r = client.get("/wizard/new")
    assert r.status_code == 303
    location = r.headers["location"]
    # Expected shape: /wizard/{id}/abilities
    parts = location.strip("/").split("/")
    return parts[1]


def test_new_does_not_pre_roll_abilities(client, tmp_path):
    draft_id = _start_draft(client)
    draft = load_draft(draft_id, tmp_path / "drafts")
    assert "abilities" not in draft


def test_abilities_page_shows_roll_button_before_rolling(client):
    draft_id = _start_draft(client)
    r = client.get(f"/wizard/{draft_id}/abilities")
    assert r.status_code == 200
    assert "Abilities" in r.text
    assert f'/wizard/{draft_id}/abilities/roll' in r.text


def test_abilities_page_shows_scores_after_rolling(client):
    draft_id = _start_draft(client)
    client.post(f"/wizard/{draft_id}/abilities/roll")
    r = client.get(f"/wizard/{draft_id}/abilities")
    assert "Continue" in r.text


def _override_abilities(tmp_path, draft_id, abilities):
    draft = load_draft(draft_id, tmp_path / "drafts")
    draft["abilities"] = abilities
    save_draft(draft_id, draft, tmp_path / "drafts")


def test_full_wizard_flow_creates_character(client, tmp_path):
    draft_id = _start_draft(client)
    # Force abilities that meet Dwarf (CON 9+)
    _override_abilities(tmp_path, draft_id, {
        "STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10
    })

    # Abilities (name moved to identity step)
    r = client.post(f"/wizard/{draft_id}/abilities", data={})
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/race"

    # Race
    r = client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/class"

    # Class
    r = client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/adjust"

    # Ability adjustments (skip)
    r = client.post(f"/wizard/{draft_id}/adjust", data={})
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/class_setup"

    # HP roll
    r = client.post(f"/wizard/{draft_id}/hp/roll")
    assert r.status_code == 303
    draft = load_draft(draft_id, tmp_path / "drafts")
    assert 1 <= draft["hp_roll"] <= 8

    # HP advances to identity
    r = client.post(f"/wizard/{draft_id}/hp")
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/identity"

    # Identity (name + alignment)
    r = client.post(f"/wizard/{draft_id}/identity", data={"name": "Thorin", "alignment": "law"})
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/equipment"

    # Visit equipment to roll starting gold, then continue to review.
    client.get(f"/wizard/{draft_id}/equipment")  # seeds gold on first GET
    r = client.post(f"/wizard/{draft_id}/equipment")
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/review"

    # Review renders the built sheet
    r = client.get(f"/wizard/{draft_id}/review")
    assert r.status_code == 200
    assert "Thorin" in r.text
    assert "Dwarf" in r.text
    assert "Fighter 1" in r.text

    # Finalize
    r = client.post(f"/wizard/{draft_id}/finalize")
    assert r.status_code == 303
    assert r.headers["location"] == "/character/thorin"

    # Draft is gone, character file exists
    char_path = tmp_path / "characters" / "thorin.json"
    assert char_path.exists()
    draft_path = tmp_path / "drafts" / f"{draft_id}.json"
    assert not draft_path.exists()


def test_unique_id_on_name_collision(client, tmp_path):
    # Pre-existing character with the same slug
    # (the fixture's create_app already created characters/ during bootstrap)
    (tmp_path / "characters").mkdir(exist_ok=True)
    (tmp_path / "characters" / "thorin.json").write_text("{}")

    draft_id = _start_draft(client)
    _override_abilities(tmp_path, draft_id, {
        "STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10
    })
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.post(f"/wizard/{draft_id}/identity", data={"name": "Thorin", "alignment": "law"})
    r = client.post(f"/wizard/{draft_id}/finalize")
    assert r.headers["location"] == "/character/thorin-2"


def test_race_rejected_if_abilities_too_low(client, tmp_path):
    draft_id = _start_draft(client)
    _override_abilities(tmp_path, draft_id, {
        "STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 5, "CHA": 10
    })
    client.post(f"/wizard/{draft_id}/abilities", data={})
    r = client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    assert r.status_code == 400


def test_gate_redirects_to_first_incomplete_step(client):
    draft_id = _start_draft(client)
    # Jump straight to review without completing prerequisites
    r = client.get(f"/wizard/{draft_id}/review")
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/abilities"


def test_cancel_deletes_draft(client, tmp_path):
    draft_id = _start_draft(client)
    r = client.post(f"/wizard/{draft_id}/cancel")
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    assert not (tmp_path / "drafts" / f"{draft_id}.json").exists()


def test_index_has_new_character_button(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "New Character" in r.text
    assert 'href="/wizard/new"' in r.text


def test_bootstrap_seeds_from_examples(tmp_path):
    characters_dir = tmp_path / "characters"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    (examples_dir / "sample.json").write_text('{"name": "Sample"}')

    create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir,
    )
    assert (characters_dir / "sample.json").exists()


def test_bootstrap_skipped_when_characters_present(tmp_path):
    characters_dir = tmp_path / "characters"
    characters_dir.mkdir()
    (characters_dir / "existing.json").write_text("{}")
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    (examples_dir / "sample.json").write_text("{}")

    create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir,
    )
    assert (characters_dir / "existing.json").exists()
    assert not (characters_dir / "sample.json").exists()
