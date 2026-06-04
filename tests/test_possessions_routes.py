"""HTTP route tests for other-possessions + notes sheet actions."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character
from aose.models import CharacterSpec, ClassEntry
from aose.web.app import create_app

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    app = create_app(
        data_dir=DATA_DIR, characters_dir=characters_dir, drafts_dir=drafts_dir,
        examples_dir=examples_dir, settings_path=tmp_path / "settings.json",
    )
    c = TestClient(app, follow_redirects=False)
    c._characters_dir = characters_dir
    return c


def _save_fighter(client):
    spec = CharacterSpec(
        name="Bran",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
    )
    save_character("bran", spec, client._characters_dir)
    return spec


def test_possession_add_route(client):
    _save_fighter(client)
    r = client.post("/character/bran/possessions/add",
                    data={"text": "a bronze key"})
    assert r.status_code == 303
    spec = load_character("bran", client._characters_dir)
    assert spec.other_possessions == ["a bronze key"]


def test_possession_add_blank_is_noop(client):
    _save_fighter(client)
    client.post("/character/bran/possessions/add", data={"text": "   "})
    spec = load_character("bran", client._characters_dir)
    assert spec.other_possessions == []


def test_possession_remove_route(client):
    _save_fighter(client)
    client.post("/character/bran/possessions/add", data={"text": "key"})
    client.post("/character/bran/possessions/add", data={"text": "map"})
    client.post("/character/bran/possessions/remove", data={"index": 0})
    spec = load_character("bran", client._characters_dir)
    assert spec.other_possessions == ["map"]


def test_possession_remove_bad_index_400(client):
    _save_fighter(client)
    r = client.post("/character/bran/possessions/remove", data={"index": 9})
    assert r.status_code == 400


def test_notes_set_route(client):
    _save_fighter(client)
    r = client.post("/character/bran/notes/set",
                    data={"notes": "met a talking owl"})
    assert r.status_code == 303
    spec = load_character("bran", client._characters_dir)
    assert spec.notes == "met a talking owl"
