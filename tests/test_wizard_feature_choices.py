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
    return TestClient(app), tmp_path / "drafts"


def _seed_mutoid_draft(drafts_dir, strict=True):
    """A race-as-class Mutoid draft sitting at class_setup, HP already rolled."""
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


@pytest.mark.xfail(reason="content lands in Phase 6 — remove marker after Task 15")
def test_strict_autorolls_and_locks_choices(tmp_path):
    client, drafts_dir = _client(tmp_path)
    draft_id = _seed_mutoid_draft(drafts_dir, strict=True)
    r = client.get(f"/wizard/{draft_id}/class_setup")
    assert r.status_code == 200
    draft = load_draft(draft_id, drafts_dir)
    assert "mutations" in draft["feature_choices"]
    assert len(draft["feature_choices"]["mutations"]) == 2
    assert len(set(draft["feature_choices"]["mutations"])) == 2


@pytest.mark.xfail(reason="content lands in Phase 6 — remove marker after Task 15")
def test_non_strict_pick_persists(tmp_path):
    client, drafts_dir = _client(tmp_path)
    draft_id = _seed_mutoid_draft(drafts_dir, strict=False)
    client.get(f"/wizard/{draft_id}/class_setup")
    r = client.post(f"/wizard/{draft_id}/feature-choices",
                    data=[("choice_mutations", "scales"), ("choice_mutations", "clawed_hand")])
    assert r.status_code in (200, 303)
    draft = load_draft(draft_id, drafts_dir)
    assert set(draft["feature_choices"]["mutations"]) == {"scales", "clawed_hand"}
    assert draft["feature_choices_done"] is True
