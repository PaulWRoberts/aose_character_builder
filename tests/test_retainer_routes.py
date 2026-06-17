"""HTTP route tests for retainer actions."""
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


def _save_char(client) -> str:
    spec = CharacterSpec(
        name="Boss",
        abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 13},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=3, hp_rolls=[8, 8, 8])],
        alignment="neutral",
        gold=50,
    )
    save_character("boss", spec, client._characters_dir)
    return "boss"


def test_add_retainer_route(client):
    cid = _save_char(client)
    resp = client.post(f"/character/{cid}/retainer/add", data={
        "name": "Sten", "class_id": "fighter", "level": "1",
        "race_id": "human", "alignment": "neutral"})
    assert resp.status_code == 303
    spec = load_character(cid, client._characters_dir)
    assert len(spec.retainers) == 1
    assert spec.retainers[0].spec.name == "Sten"


def test_add_normal_human_retainer(client):
    cid = _save_char(client)
    resp = client.post(f"/character/{cid}/retainer/add", data={
        "name": "Boy", "class_id": "normal_human", "level": "1",
        "race_id": "human", "alignment": "neutral"})
    assert resp.status_code == 303
    spec = load_character(cid, client._characters_dir)
    assert spec.retainers[0].spec.classes[0].class_id == "normal_human"
