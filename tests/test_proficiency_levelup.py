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


def _save_fighter(client, level=4):
    spec = CharacterSpec(
        name="Prof", abilities={"STR": 13, "INT": 9, "WIS": 9, "DEX": 12, "CON": 12, "CHA": 9},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=level)],
        alignment="neutral", ruleset=RuleSet(weapon_proficiency=True),
        weapon_proficiencies=["sword", "dagger", "spear", "mace"],  # 4 spent
    )
    cid = unique_character_id(slugify(spec.name), client._characters_dir)
    save_character(cid, spec, client._characters_dir)
    return cid


def test_add_proficiency_spends_an_earned_slot(client):
    cid = _save_fighter(client, level=4)  # 5 slots earned, 4 spent -> 1 remaining
    r = client.post(f"/character/{cid}/proficiency/add",
                    data={"weapon_id": "battle_axe"}, follow_redirects=False)
    assert r.status_code == 303
    spec = load_character(cid, client._characters_dir)
    assert "battle_axe" in spec.weapon_proficiencies


def test_add_proficiency_refused_when_no_slot_remaining(client):
    cid = _save_fighter(client, level=1)  # 4 earned, 4 spent -> 0 remaining
    r = client.post(f"/character/{cid}/proficiency/add",
                    data={"weapon_id": "battle_axe"}, follow_redirects=False)
    assert r.status_code == 400
