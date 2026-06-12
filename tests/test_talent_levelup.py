from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import save_settings
from aose.characters.storage import load_character, save_character, slugify, unique_character_id
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture
def client(tmp_path):
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
        seed_from_examples=False,
    )
    c = TestClient(app, follow_redirects=False)
    c._characters_dir = characters_dir
    return c


def _save(client, level=5, picked=("cleave",)):
    spec = CharacterSpec(
        name="Tal", abilities={"STR": 13, "INT": 9, "WIS": 9, "DEX": 12, "CON": 12, "CHA": 9},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=level)],
        alignment="neutral", ruleset=RuleSet(combat_talents=True),
        feature_choices={"combat_talents": list(picked)},
    )
    cid = unique_character_id(slugify(spec.name), client._characters_dir)
    save_character(cid, spec, client._characters_dir)
    return cid


def test_add_second_talent_at_level5(client):
    cid = _save(client, level=5, picked=["cleave"])  # earned 2, spent 1
    r = client.post(f"/character/{cid}/talent/add",
                    data={"group_id": "combat_talents", "option_id": "defender"},
                    follow_redirects=False)
    assert r.status_code == 303
    spec = load_character(cid, client._characters_dir)
    assert spec.feature_choices["combat_talents"] == ["cleave", "defender"]


def test_slayer_requires_param(client):
    cid = _save(client, level=5, picked=["cleave"])
    r = client.post(f"/character/{cid}/talent/add",
                    data={"group_id": "combat_talents", "option_id": "slayer"},
                    follow_redirects=False)
    assert r.status_code == 400  # missing enemy type


def test_cannot_exceed_earned_talents(client):
    cid = _save(client, level=4, picked=["cleave"])  # earned 1, spent 1
    r = client.post(f"/character/{cid}/talent/add",
                    data={"group_id": "combat_talents", "option_id": "defender"},
                    follow_redirects=False)
    assert r.status_code == 400
