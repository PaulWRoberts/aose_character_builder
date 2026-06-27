"""HTTP route tests for inventory move/convert/add routes."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character
from aose.models import CharacterSpec, ClassEntry, ContainerInstance, ItemInstance
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


def _save_char(client, *, items=None, containers=None, coins=None):
    from aose.models import CoinStack
    spec = CharacterSpec(
        name="Hero",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        items=items or [],
        containers=containers or [],
        coins=[CoinStack(**c) if isinstance(c, dict) else c for c in (coins or [])],
    )
    save_character("hero", spec, client._characters_dir)
    return spec


def _load(client):
    return load_character("hero", client._characters_dir)


def _item(catalog_id, kind="carried", loc_id=None):
    loc = StorageLocation(kind=kind, id=loc_id) if loc_id else StorageLocation(kind=kind)
    return ItemInstance(instance_id=catalog_id, catalog_id=catalog_id, location=loc)


def test_move_item_carried_to_stashed(client):
    _save_char(client, items=[_item("torch")])
    r = client.post("/character/hero/inventory/move", data={
        "category": "item", "item_id": "torch",
        "src_kind": "carried", "src_id": "",
        "dest_kind": "stashed", "dest_id": "",
    })
    assert r.status_code == 303
    spec = _load(client)
    assert any(i.catalog_id == "torch" and i.location.kind == "stashed" for i in spec.items)
    assert not any(i.catalog_id == "torch" and i.location.kind == "carried" for i in spec.items)


def test_move_item_into_container(client):
    c = ContainerInstance(instance_id="c1", catalog_id="backpack")
    _save_char(client, items=[_item("torch")], containers=[c])
    r = client.post("/character/hero/inventory/move", data={
        "category": "item", "item_id": "torch",
        "src_kind": "carried", "src_id": "",
        "dest_kind": "container", "dest_id": "c1",
    })
    assert r.status_code == 303
    spec = _load(client)
    assert not any(i.catalog_id == "torch" and i.location.kind == "carried" for i in spec.items)
    assert any(i.catalog_id == "torch" and
               i.location == StorageLocation(kind="container", id="c1") for i in spec.items)


def test_move_item_missing_raises_400(client):
    _save_char(client, items=[_item("torch")])
    r = client.post("/character/hero/inventory/move", data={
        "category": "item", "item_id": "rope",
        "src_kind": "carried", "src_id": "",
        "dest_kind": "stashed", "dest_id": "",
    })
    assert r.status_code == 400


def test_move_container_to_stashed(client):
    c = ContainerInstance(instance_id="c1", catalog_id="backpack")
    _save_char(client, containers=[c])
    r = client.post("/character/hero/inventory/move", data={
        "category": "container", "item_id": "c1",
        "dest_kind": "stashed", "dest_id": "",
    })
    assert r.status_code == 303
    spec = _load(client)
    assert spec.containers[0].location == StorageLocation(kind="stashed")


def test_move_coins_route(client):
    from aose.models import CoinStack
    _save_char(client, coins=[CoinStack(denom="gp", count=10)])
    r = client.post("/character/hero/inventory/move", data={
        "category": "coin", "denom": "gp",
        "src_kind": "carried", "src_id": "",
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
        animals=[AnimalInstance(instance_id="a1", catalog_id="mule")],
        items=[ItemInstance(instance_id="torch1", catalog_id="torch",
                            location=StorageLocation(kind="animal", id="a1"))],
        coins=[CoinStack(denom="gp", count=5,
                         location=StorageLocation(kind="animal", id="a1"))],
    )
    save_character("hero", spec, client._characters_dir)
    r = client.get("/character/hero")
    assert r.status_code == 200
    assert 'data-pane-kind="animal"' in r.text


def test_carried_item_offers_move_to_carrier(client):
    """A loose Carried item must expose a Move control that can target a carrier."""
    from aose.models import AnimalInstance, ClassEntry
    spec = CharacterSpec(
        name="Hero",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        items=[ItemInstance(instance_id="torch", catalog_id="torch")],
        animals=[AnimalInstance(instance_id="a1", catalog_id="mule")],
    )
    save_character("hero", spec, client._characters_dir)
    r = client.get("/character/hero")
    assert r.status_code == 200
    assert "/character/hero/inventory/move" in r.text
    assert 'data-kind="animal"' in r.text


def test_move_coins_invalid_dest_returns_400(client):
    """A bad/empty dest_kind must surface as a 400, never a 500."""
    from aose.models import CoinStack
    _save_char(client, coins=[CoinStack(denom="gp", count=10,
                                        location=StorageLocation(kind="stashed"))])
    r = client.post("/character/hero/inventory/move", data={
        "category": "coin", "denom": "gp",
        "src_kind": "stashed", "src_id": "",
        "dest_kind": "", "dest_id": "", "count": "4",
    })
    assert r.status_code == 400


def test_stashed_coins_appear_in_inventory_box(client):
    """Stashed coins must appear in the stashed inventory pane in the box."""
    from aose.models import AnimalInstance, CoinStack
    spec = CharacterSpec(
        name="Hero",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        animals=[AnimalInstance(instance_id="a1", catalog_id="mule")],
        coins=[CoinStack(denom="gp", count=10,
                         location=StorageLocation(kind="stashed"))],
    )
    save_character("hero", spec, client._characters_dir)
    r = client.get("/character/hero")
    assert r.status_code == 200
    assert 'data-pane-kind="stashed"' in r.text
    assert "10 gp" in r.text
    assert 'id="pop-coins"' not in r.text


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


def test_use_as_container_promotes_loose_item(client):
    _save_char(client, items=[_item("backpack")])
    r = client.post("/character/hero/inventory/use-as-container", data={
        "owner_kind": "carried", "owner_id": "", "item_id": "backpack",
    })
    assert r.status_code == 303
    spec = _load(client)
    assert not any(i.catalog_id == "backpack" for i in spec.items)
    assert any(c.catalog_id == "backpack" for c in spec.containers)


def test_single_move_route_moves_item_to_container(client):
    from aose.models.storage import StorageLocation
    _save_char(client,
               items=[_item("torch")],
               containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                             location=StorageLocation(kind="carried"))])
    r = client.post("/character/hero/inventory/move", data={
        "category": "item", "item_id": "torch",
        "src_kind": "carried", "src_id": "",
        "dest_kind": "container", "dest_id": "c1",
    })
    assert r.status_code == 303
    spec = _load(client)
    assert any(i.catalog_id == "torch" and
               i.location == StorageLocation(kind="container", id="c1") for i in spec.items)


def test_old_typed_move_routes_are_gone(client):
    _save_char(client, items=[_item("torch")])
    r = client.post("/character/hero/inventory/move-item", data={
        "item_id": "torch", "src_kind": "carried", "dest_kind": "stashed"})
    assert r.status_code == 404
