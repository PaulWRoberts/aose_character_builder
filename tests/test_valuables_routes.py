"""HTTP route tests for gem & jewellery play-state actions."""
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


def _save_fighter(client, gold=0):
    spec = CharacterSpec(
        name="Bran",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral", gold=gold,
    )
    save_character("bran", spec, client._characters_dir)
    return spec


def test_gem_add_route(client):
    _save_fighter(client)
    r = client.post("/character/bran/gems/add",
                    data={"value": 100, "count": 2, "label": "ruby"})
    assert r.status_code == 303
    spec = load_character("bran", client._characters_dir)
    assert len(spec.gems) == 1
    assert spec.gems[0].count == 2


def test_gem_add_custom_value(client):
    _save_fighter(client)
    client.post("/character/bran/gems/add", data={"value": 250, "count": 1})
    spec = load_character("bran", client._characters_dir)
    assert spec.gems[0].value == 250


def test_gem_sell_route_adds_gold(client):
    _save_fighter(client, gold=5)
    client.post("/character/bran/gems/add", data={"value": 100, "count": 2})
    spec = load_character("bran", client._characters_dir)
    iid = spec.gems[0].instance_id
    client.post("/character/bran/gems/sell", data={"instance_id": iid})
    spec = load_character("bran", client._characters_dir)
    assert spec.gold == 105
    assert spec.gems[0].count == 1


def test_gem_sell_all_route(client):
    _save_fighter(client, gold=0)
    client.post("/character/bran/gems/add", data={"value": 100, "count": 3})
    spec = load_character("bran", client._characters_dir)
    iid = spec.gems[0].instance_id
    client.post("/character/bran/gems/sell-all", data={"instance_id": iid})
    spec = load_character("bran", client._characters_dir)
    assert spec.gold == 300
    assert spec.gems == []


def test_gem_adjust_and_remove(client):
    _save_fighter(client)
    client.post("/character/bran/gems/add", data={"value": 50, "count": 2})
    spec = load_character("bran", client._characters_dir)
    iid = spec.gems[0].instance_id
    client.post("/character/bran/gems/adjust", data={"instance_id": iid, "delta": 3})
    assert load_character("bran", client._characters_dir).gems[0].count == 5
    client.post("/character/bran/gems/remove", data={"instance_id": iid})
    assert load_character("bran", client._characters_dir).gems == []


def test_jewellery_add_set_value(client):
    _save_fighter(client)
    client.post("/character/bran/jewellery/add",
                data={"mode": "set", "value": 700, "label": "necklace"})
    spec = load_character("bran", client._characters_dir)
    assert spec.jewellery[0].value == 700


def test_jewellery_add_random_in_range(client):
    _save_fighter(client)
    client.post("/character/bran/jewellery/add", data={"mode": "random"})
    spec = load_character("bran", client._characters_dir)
    assert 300 <= spec.jewellery[0].value <= 1800


def test_jewellery_toggle_damaged(client):
    _save_fighter(client)
    client.post("/character/bran/jewellery/add", data={"mode": "set", "value": 700})
    spec = load_character("bran", client._characters_dir)
    iid = spec.jewellery[0].instance_id
    client.post("/character/bran/jewellery/toggle-damaged",
                data={"instance_id": iid, "damaged": "true"})
    assert load_character("bran", client._characters_dir).jewellery[0].damaged is True
    client.post("/character/bran/jewellery/toggle-damaged",
                data={"instance_id": iid, "damaged": "false"})
    assert load_character("bran", client._characters_dir).jewellery[0].damaged is False


def test_jewellery_sell_damaged_halves(client):
    _save_fighter(client, gold=0)
    client.post("/character/bran/jewellery/add",
                data={"mode": "set", "value": 700})
    spec = load_character("bran", client._characters_dir)
    iid = spec.jewellery[0].instance_id
    client.post("/character/bran/jewellery/toggle-damaged",
                data={"instance_id": iid, "damaged": "true"})
    client.post("/character/bran/jewellery/sell", data={"instance_id": iid})
    spec = load_character("bran", client._characters_dir)
    assert spec.gold == 350
    assert spec.jewellery == []


def test_jewellery_drop_no_gold(client):
    _save_fighter(client, gold=0)
    client.post("/character/bran/jewellery/add",
                data={"mode": "set", "value": 700})
    spec = load_character("bran", client._characters_dir)
    iid = spec.jewellery[0].instance_id
    client.post("/character/bran/jewellery/remove", data={"instance_id": iid})
    spec = load_character("bran", client._characters_dir)
    assert spec.gold == 0
    assert spec.jewellery == []
