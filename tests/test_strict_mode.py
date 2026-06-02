from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters.drafts import load_draft, save_draft
from aose.models import RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture
def client(tmp_path):
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=tmp_path / "characters",
        drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir,
    )
    c = TestClient(app, follow_redirects=False)
    c._drafts = tmp_path / "drafts"
    return c


def test_strict_mode_defaults_on():
    assert RuleSet().strict_mode is True


def test_strict_mode_no_pending_badge(client):
    r = client.get("/settings")
    assert r.status_code == 200
    assert 'name="strict_mode"' in r.text
    # The strict_mode row must not carry a pending badge.
    idx = r.text.index('name="strict_mode"')
    snippet = r.text[idx:idx + 400]
    assert "pending" not in snippet


def _new(client):
    r = client.get("/wizard/new")
    return r.headers["location"].split("/")[2]


def _force(client, draft_id, abilities):
    d = load_draft(draft_id, client._drafts)
    d["abilities"] = abilities
    save_draft(draft_id, d, client._drafts)


def test_new_does_not_pre_roll_abilities(client):
    draft_id = _new(client)
    d = load_draft(draft_id, client._drafts)
    assert "abilities" not in d


def test_abilities_roll_route_sets_six_scores(client):
    draft_id = _new(client)
    r = client.post(f"/wizard/{draft_id}/abilities/roll")
    assert r.status_code == 303
    d = load_draft(draft_id, client._drafts)
    assert set(d["abilities"]) == {"STR", "INT", "WIS", "DEX", "CON", "CHA"}


def test_strict_locks_abilities_after_roll(client):
    draft_id = _new(client)
    # Non-hopeless scores so the lock applies.
    _force(client, draft_id, {"STR": 13, "INT": 12, "WIS": 11,
                              "DEX": 10, "CON": 14, "CHA": 9})
    r = client.post(f"/wizard/{draft_id}/abilities/roll")
    assert r.status_code == 400


def test_hopeless_reroll_allowed_in_strict(client):
    draft_id = _new(client)
    # rock_bottom: a single 3 must re-enable the roll even under Strict Mode.
    _force(client, draft_id, {"STR": 3, "INT": 12, "WIS": 11,
                              "DEX": 10, "CON": 14, "CHA": 9})
    r = client.post(f"/wizard/{draft_id}/abilities/roll")
    assert r.status_code == 303


def test_subpar_reroll_allowed_in_strict(client):
    draft_id = _new(client)
    _force(client, draft_id, {"STR": 8, "INT": 8, "WIS": 8,
                              "DEX": 8, "CON": 8, "CHA": 8})
    r = client.post(f"/wizard/{draft_id}/abilities/roll")
    assert r.status_code == 303


def test_non_strict_allows_ability_reroll(client):
    draft_id = _new(client)
    client.post(f"/wizard/{draft_id}/rules",
                data={"encumbrance": "basic", "creation_method": "advanced"})
    _force(client, draft_id, {"STR": 13, "INT": 12, "WIS": 11,
                              "DEX": 10, "CON": 14, "CHA": 9})
    r = client.post(f"/wizard/{draft_id}/abilities/roll")
    assert r.status_code == 303  # strict off (checkbox absent) -> free reroll


def _drive_to_equipment(client, draft_id, strict=True):
    form = {"encumbrance": "basic", "creation_method": "advanced"}
    if strict:
        form["strict_mode"] = "on"
    client.post(f"/wizard/{draft_id}/rules", data=form)
    _force(client, draft_id, {"STR": 13, "INT": 12, "WIS": 11,
                              "DEX": 13, "CON": 13, "CHA": 12})
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/identity",
                data={"name": "G", "alignment": "law"})


def test_non_strict_gold_reroll_until_purchase(client):
    draft_id = _new(client)
    _drive_to_equipment(client, draft_id, strict=False)
    client.post(f"/wizard/{draft_id}/equipment/roll-gold")
    d = load_draft(draft_id, client._drafts)
    assert d["gold_locked"] is False
    # Non-strict: re-roll allowed while unlocked.
    r = client.post(f"/wizard/{draft_id}/equipment/roll-gold")
    assert r.status_code == 303


def test_ability_reroll_clears_downstream_and_confirmation(client):
    draft_id = _new(client)
    client.post(f"/wizard/{draft_id}/rules",
                data={"encumbrance": "basic", "creation_method": "advanced"})
    _force(client, draft_id, {"STR": 13, "INT": 12, "WIS": 11,
                              "DEX": 10, "CON": 14, "CHA": 9})
    client.post(f"/wizard/{draft_id}/abilities", data={})  # confirm
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/abilities/roll")       # reroll
    d = load_draft(draft_id, client._drafts)
    assert "race_id" not in d
    assert not d.get("abilities_confirmed")
