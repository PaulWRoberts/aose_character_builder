"""HTTP tests for the unified /inventory/* action family.
Fixture style copied verbatim from tests/test_inventory_move_routes.py."""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character
from aose.models import CharacterSpec, ClassEntry, ItemInstance
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


def _save_hero(client, items):
    spec = CharacterSpec(
        name="Hero", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
        "CON": 10, "CHA": 10}, race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral", items=items)
    save_character("hero", spec, client._characters_dir)


def test_equip_route_accepts_instance_id(client):
    _save_hero(client, [ItemInstance(
        instance_id="i1", catalog_id="sword",
        location=StorageLocation(kind="carried"))])
    resp = client.post("/character/hero/inventory/equip",
                       data={"category": "item", "instance_id": "i1"})
    assert resp.status_code == 303
    assert load_character("hero", client._characters_dir).items[0].equip == "main_hand"


def test_old_equipment_equip_route_is_gone(client):
    _save_hero(client, [ItemInstance(
        instance_id="i1", catalog_id="sword",
        location=StorageLocation(kind="carried"))])
    resp = client.post("/character/hero/equipment/equip",
                       data={"instance_id": "i1"})
    assert resp.status_code == 404


def test_consume_route_removes_one(client):
    _save_hero(client, [ItemInstance(
        instance_id="t", catalog_id="torch", count=2,
        location=StorageLocation(kind="carried"))])
    resp = client.post("/character/hero/inventory/consume",
                       data={"category": "item", "instance_id": "t"})
    assert resp.status_code == 303
    reloaded = load_character("hero", client._characters_dir)
    assert next(i for i in reloaded.items if i.instance_id == "t").count == 1


def test_consume_route_drops_stack_at_zero(client):
    _save_hero(client, [ItemInstance(
        instance_id="t", catalog_id="torch", count=1,
        location=StorageLocation(kind="carried"))])
    resp = client.post("/character/hero/inventory/consume",
                       data={"category": "item", "instance_id": "t"})
    assert resp.status_code == 303
    reloaded = load_character("hero", client._characters_dir)
    assert all(i.instance_id != "t" for i in reloaded.items)


def test_consume_route_missing_instance_400(client):
    _save_hero(client, [])
    resp = client.post("/character/hero/inventory/consume",
                       data={"category": "item", "instance_id": "nope"})
    assert resp.status_code == 400


def test_sell_route_threads_count(client):
    """The sell route reads `count` and forwards it to the item branch: selling
    4 of a 6-stack leaves 2 (regression guard for count threading)."""
    _save_hero(client, [ItemInstance(
        instance_id="t", catalog_id="torch", count=6,
        location=StorageLocation(kind="carried"))])
    resp = client.post("/character/hero/inventory/sell",
                       data={"category": "item", "instance_id": "t",
                             "mode": "drop", "count": "4"})
    assert resp.status_code == 303
    reloaded = load_character("hero", client._characters_dir)
    assert next(i for i in reloaded.items if i.instance_id == "t").count == 2
