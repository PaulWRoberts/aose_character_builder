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


@pytest.mark.skip(reason="enabled in Task 9 after old routes deleted")
def test_old_equipment_equip_route_is_gone(client):
    _save_hero(client, [ItemInstance(
        instance_id="i1", catalog_id="sword",
        location=StorageLocation(kind="carried"))])
    resp = client.post("/character/hero/equipment/equip",
                       data={"instance_id": "i1"})
    assert resp.status_code == 404
