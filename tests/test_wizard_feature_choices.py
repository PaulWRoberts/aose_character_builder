from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_draft, save_draft
from aose.models import RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def _client(tmp_path):
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=tmp_path / "characters",
        drafts_dir=tmp_path / "drafts",
        examples_dir=tmp_path / "examples",
        settings_path=tmp_path / "settings.json",
        seed_from_examples=False,
    )
    return TestClient(app, follow_redirects=False), tmp_path / "drafts"


def _seed_mutoid_draft(drafts_dir, strict=True):
    """A race-as-class Mutoid draft at class_setup, HP already rolled."""
    draft = {
        "ruleset": RuleSet(separate_race_class=False, weapon_proficiency=False,
                           strict_mode=strict, secondary_skills=False).model_dump(),
        "abilities": {"STR": 10, "INT": 10, "WIS": 10, "DEX": 12, "CON": 10, "CHA": 10},
        "abilities_confirmed": True,
        "race_id": "mutoid",
        "class_id": "mutoid",
        "ability_adjustments": {},
        "hp_roll": 4,
    }
    save_draft("d1", draft, drafts_dir)
    return "d1"


def test_strict_does_not_autoroll(tmp_path):
    client, drafts_dir = _client(tmp_path)
    draft_id = _seed_mutoid_draft(drafts_dir, strict=True)
    r = client.get(f"/wizard/{draft_id}/class_setup")
    assert r.status_code == 200
    draft = load_draft(draft_id, drafts_dir)
    assert "feature_choices" not in draft or "mutations" not in draft.get("feature_choices", {})
    # The page offers a Roll button for the table.
    assert "feature-choices/roll" in r.text


def test_roll_route_populates_group(tmp_path):
    client, drafts_dir = _client(tmp_path)
    draft_id = _seed_mutoid_draft(drafts_dir, strict=True)
    r = client.post(f"/wizard/{draft_id}/feature-choices/roll",
                    data={"group_id": "mutations"})
    assert r.status_code in (200, 303)
    draft = load_draft(draft_id, drafts_dir)
    assert len(draft["feature_choices"]["mutations"]) == 2
    assert len(set(draft["feature_choices"]["mutations"])) == 2


def test_strict_locks_after_roll(tmp_path):
    client, drafts_dir = _client(tmp_path)
    draft_id = _seed_mutoid_draft(drafts_dir, strict=True)
    client.post(f"/wizard/{draft_id}/feature-choices/roll", data={"group_id": "mutations"})
    first = load_draft(draft_id, drafts_dir)["feature_choices"]["mutations"]
    # Re-roll refused in strict mode.
    r = client.post(f"/wizard/{draft_id}/feature-choices/roll", data={"group_id": "mutations"})
    assert r.status_code == 400
    assert load_draft(draft_id, drafts_dir)["feature_choices"]["mutations"] == first


def test_non_strict_reroll_allowed(tmp_path):
    client, drafts_dir = _client(tmp_path)
    draft_id = _seed_mutoid_draft(drafts_dir, strict=False)
    client.post(f"/wizard/{draft_id}/feature-choices/roll", data={"group_id": "mutations"})
    before = load_draft(draft_id, drafts_dir)["feature_choices"]["mutations"]
    for _ in range(20):
        client.post(f"/wizard/{draft_id}/feature-choices/roll", data={"group_id": "mutations"})
        after = load_draft(draft_id, drafts_dir)["feature_choices"]["mutations"]
        if after != before:
            return
    pytest.fail("Re-roll never changed the mutation set after 20 tries")


def test_non_strict_manual_override_persists(tmp_path):
    client, drafts_dir = _client(tmp_path)
    draft_id = _seed_mutoid_draft(drafts_dir, strict=False)
    client.post(f"/wizard/{draft_id}/feature-choices/roll", data={"group_id": "mutations"})
    r = client.post(f"/wizard/{draft_id}/feature-choices",
                    data={"choice_mutations": ["scales", "clawed_hand"]})
    assert r.status_code in (200, 303)
    draft = load_draft(draft_id, drafts_dir)
    assert set(draft["feature_choices"]["mutations"]) == {"scales", "clawed_hand"}


def test_roll_route_rejects_unknown_group(tmp_path):
    client, drafts_dir = _client(tmp_path)
    draft_id = _seed_mutoid_draft(drafts_dir, strict=True)
    r = client.post(f"/wizard/{draft_id}/feature-choices/roll", data={"group_id": "bogus"})
    assert r.status_code == 400


def test_strict_manual_save_still_rejected(tmp_path):
    client, drafts_dir = _client(tmp_path)
    draft_id = _seed_mutoid_draft(drafts_dir, strict=True)
    r = client.post(f"/wizard/{draft_id}/feature-choices",
                    data={"choice_mutations": ["scales", "clawed_hand"]})
    assert r.status_code == 400
