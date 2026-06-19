"""HTTP route tests for inventory move/convert/add routes."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character
from aose.models import CharacterSpec, ClassEntry, ContainerInstance
from aose.models.storage import StorageLocation
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


def _save_char(client, *, inventory=None, stashed=None, containers=None, coins=None):
    from aose.models import CoinStack
    spec = CharacterSpec(
        name="Hero",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        inventory=inventory or [],
        stashed=stashed or [],
        containers=containers or [],
        coins=[CoinStack(**c) if isinstance(c, dict) else c for c in (coins or [])],
    )
    save_character("hero", spec, client._characters_dir)
    return spec


def _load(client):
    return load_character("hero", client._characters_dir)


def test_move_item_carried_to_stashed(client):
    _save_char(client, inventory=["torch"])
    r = client.post("/character/hero/inventory/move-item", data={
        "item_id": "torch", "src_kind": "carried", "src_id": "",
        "dest_kind": "stashed", "dest_id": "",
    })
    assert r.status_code == 303
    spec = _load(client)
    assert spec.stashed == ["torch"]
    assert spec.inventory == []


def test_move_item_into_container(client):
    c = ContainerInstance(instance_id="c1", catalog_id="backpack")
    _save_char(client, inventory=["torch"], containers=[c])
    r = client.post("/character/hero/inventory/move-item", data={
        "item_id": "torch", "src_kind": "carried", "src_id": "",
        "dest_kind": "container", "dest_id": "c1",
    })
    assert r.status_code == 303
    spec = _load(client)
    assert spec.inventory == []
    assert "torch" in spec.containers[0].contents


def test_move_item_missing_raises_400(client):
    _save_char(client, inventory=["torch"])
    r = client.post("/character/hero/inventory/move-item", data={
        "item_id": "rope", "src_kind": "carried", "src_id": "",
        "dest_kind": "stashed", "dest_id": "",
    })
    assert r.status_code == 400


def test_move_container_to_stashed(client):
    c = ContainerInstance(instance_id="c1", catalog_id="backpack")
    _save_char(client, containers=[c])
    r = client.post("/character/hero/inventory/move-container", data={
        "container_id": "c1", "dest_kind": "stashed", "dest_id": "",
    })
    assert r.status_code == 303
    spec = _load(client)
    assert spec.containers[0].location == StorageLocation(kind="stashed")


def test_move_coins_route(client):
    from aose.models import CoinStack
    _save_char(client, coins=[CoinStack(denom="gp", count=10)])
    r = client.post("/character/hero/inventory/move-coins", data={
        "denom": "gp", "src_kind": "carried", "src_id": "",
        "dest_kind": "stashed", "dest_id": "", "count": "4",
    })
    assert r.status_code == 303
    spec = _load(client)
    by = {(s.denom, s.location.kind): s.count for s in spec.coins}
    assert by[("gp", "carried")] == 6
    assert by[("gp", "stashed")] == 4


def test_animal_group_renders_on_sheet(client):
    """The carrier's top-level inventory group must appear in the inventory
    section of the live sheet (not only in the companions card / print sheet)."""
    from aose.models import AnimalInstance, CoinStack
    spec = CharacterSpec(
        name="Hero",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        animals=[AnimalInstance(instance_id="a1", catalog_id="mule", contents=["torch"])],
        coins=[CoinStack(denom="gp", count=5,
                         location=StorageLocation(kind="animal", id="a1"))],
    )
    save_character("hero", spec, client._characters_dir)
    r = client.get("/character/hero")
    assert r.status_code == 200
    # Structural marker unique to the inventory-group rendering.
    assert 'data-inv-group="animal:a1"' in r.text


def test_convert_route_per_stack(client):
    from aose.models import CoinStack
    _save_char(client, coins=[CoinStack(denom="gp", count=3)])
    r = client.post("/character/hero/coins/convert", data={
        "loc_kind": "carried", "loc_id": "", "frm": "gp", "to": "sp", "count": "2",
    })
    assert r.status_code == 303
    spec = _load(client)
    by = {s.denom: s.count for s in spec.coins}
    assert by["gp"] == 1
    assert by["sp"] == 20
