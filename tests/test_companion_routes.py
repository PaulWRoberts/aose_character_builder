"""HTTP route tests for companion (animal & vehicle) play-state actions."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character
from aose.models import (AnimalInstance, CharacterSpec, ClassEntry, CoinStack,
                         ItemInstance, VehicleInstance)
from aose.models.storage import StorageLocation
from aose.web.app import create_app


def _gp(spec):
    return next((s.count for s in spec.coins
                 if s.denom == "gp" and s.location.kind == "carried"), 0)

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


def _save_char(client, *, gold=500.0, animals=None, vehicles=None, items=None):
    coins = [CoinStack(denom="gp", count=int(gold))] if gold else []
    spec = CharacterSpec(
        name="Finn",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        coins=coins,
        animals=animals or [],
        vehicles=vehicles or [],
        items=items or [],
    )
    save_character("finn", spec, client._characters_dir)
    return spec


# ── Animal routes ──────────────────────────────────────────────────────────

def test_animal_buy_deducts_gold(client):
    _save_char(client, gold=200.0)
    r = client.post("/character/finn/animal/buy", data={"item_id": "mule"})
    assert r.status_code == 303
    spec = load_character("finn", client._characters_dir)
    assert len(spec.animals) == 1
    assert spec.animals[0].catalog_id == "mule"
    assert _gp(spec) < 200


def test_animal_buy_insufficient_gold(client):
    _save_char(client, gold=1.0)
    r = client.post("/character/finn/animal/buy", data={"item_id": "war_horse"})
    assert r.status_code == 400


def test_animal_remove_sell(client):
    _save_char(client, gold=0.0, animals=[
        AnimalInstance(instance_id="a1", catalog_id="mule"),
    ])
    r = client.post("/character/finn/animal/remove",
                    data={"instance_id": "a1", "mode": "sell"})
    assert r.status_code == 303
    spec = load_character("finn", client._characters_dir)
    assert spec.animals == []
    assert _gp(spec) > 0


def test_animal_rename(client):
    _save_char(client, animals=[
        AnimalInstance(instance_id="a1", catalog_id="mule"),
    ])
    r = client.post("/character/finn/animal/a1/rename", data={"name": "Biscuit"})
    assert r.status_code == 303
    spec = load_character("finn", client._characters_dir)
    assert spec.animals[0].name == "Biscuit"


def test_animal_hp_damage(client):
    _save_char(client, animals=[
        AnimalInstance(instance_id="a1", catalog_id="mule"),
    ])
    r = client.post("/character/finn/animal/a1/hp", data={"delta": -3})
    assert r.status_code == 303
    spec = load_character("finn", client._characters_dir)
    assert spec.animals[0].hp_damage == 3


def test_animal_hp_heal(client):
    _save_char(client, animals=[
        AnimalInstance(instance_id="a1", catalog_id="mule", hp_damage=3),
    ])
    r = client.post("/character/finn/animal/a1/hp", data={"delta": 2})
    assert r.status_code == 303
    spec = load_character("finn", client._characters_dir)
    assert spec.animals[0].hp_damage == 1


def test_animal_load_and_unload(client):
    _save_char(client,
               items=[ItemInstance(instance_id="torch1", catalog_id="torch")],
               animals=[AnimalInstance(instance_id="a1", catalog_id="mule")])
    # Load torch onto animal
    r = client.post("/character/finn/inventory/move", data={
        "category": "item", "item_id": "torch1",
        "src_kind": "carried", "dest_kind": "animal", "dest_id": "a1",
    })
    assert r.status_code == 303
    spec = load_character("finn", client._characters_dir)
    assert not any(i.instance_id == "torch1" and i.location.kind == "carried"
                   for i in spec.items)
    assert any(i.instance_id == "torch1" and i.location.kind == "animal"
               for i in spec.items)

    # Unload torch back to carried
    r = client.post("/character/finn/inventory/move", data={
        "category": "item", "item_id": "torch1",
        "src_kind": "animal", "src_id": "a1", "dest_kind": "carried",
    })
    assert r.status_code == 303
    spec = load_character("finn", client._characters_dir)
    assert any(i.instance_id == "torch1" and i.location.kind == "carried"
               for i in spec.items)


# ── Shop buy dispatch (generic /equipment/buy) ─────────────────────────────

def test_equipment_buy_animal_creates_instance_not_inventory(client):
    _save_char(client, gold=200.0)
    r = client.post("/character/finn/equipment/buy", data={"item_id": "mule"})
    assert r.status_code == 303
    spec = load_character("finn", client._characters_dir)
    assert len(spec.animals) == 1, "buying an animal in the shop must create a roster instance"
    assert not any(i.catalog_id == "mule" and i.location.kind == "carried"
                   for i in spec.items), "an animal must never land in carried inventory"


def test_equipment_buy_vehicle_creates_instance_not_inventory(client):
    _save_char(client, gold=1000.0)
    r = client.post("/character/finn/equipment/buy", data={"item_id": "cart"})
    assert r.status_code == 303
    spec = load_character("finn", client._characters_dir)
    assert len(spec.vehicles) == 1, "buying a vehicle in the shop must create a roster instance"
    assert spec.vehicles[0].hull_max >= 1, "vehicle instance must resolve hull_max at purchase"
    assert not any(i.catalog_id == "cart" and i.location.kind == "carried"
                   for i in spec.items), "a vehicle must never land in carried inventory"


# ── Vehicle routes ─────────────────────────────────────────────────────────

def test_vehicle_buy_deducts_gold(client):
    _save_char(client, gold=1000.0)
    r = client.post("/character/finn/vehicle/buy", data={"item_id": "cart"})
    assert r.status_code == 303
    spec = load_character("finn", client._characters_dir)
    assert len(spec.vehicles) == 1
    assert spec.vehicles[0].catalog_id == "cart"
    assert _gp(spec) < 1000


def test_vehicle_remove_sell(client):
    _save_char(client, gold=0.0, vehicles=[
        VehicleInstance(instance_id="v1", catalog_id="cart", hull_max=4),
    ])
    r = client.post("/character/finn/vehicle/remove",
                    data={"instance_id": "v1", "mode": "sell"})
    assert r.status_code == 303
    spec = load_character("finn", client._characters_dir)
    assert spec.vehicles == []
    assert _gp(spec) > 0


def test_vehicle_rename(client):
    _save_char(client, vehicles=[
        VehicleInstance(instance_id="v1", catalog_id="cart", hull_max=4),
    ])
    r = client.post("/character/finn/vehicle/v1/rename", data={"name": "Old Rusty"})
    assert r.status_code == 303
    spec = load_character("finn", client._characters_dir)
    assert spec.vehicles[0].name == "Old Rusty"


def test_vehicle_hull_damage(client):
    _save_char(client, vehicles=[
        VehicleInstance(instance_id="v1", catalog_id="cart", hull_max=4),
    ])
    r = client.post("/character/finn/vehicle/v1/hull", data={"delta": -2})
    assert r.status_code == 303
    spec = load_character("finn", client._characters_dir)
    assert spec.vehicles[0].hull_damage == 2


def test_vehicle_load_and_unload(client):
    _save_char(client,
               items=[ItemInstance(instance_id="torch1", catalog_id="torch")],
               vehicles=[VehicleInstance(instance_id="v1", catalog_id="cart", hull_max=4)])
    # Load torch onto vehicle
    r = client.post("/character/finn/inventory/move", data={
        "category": "item", "item_id": "torch1",
        "src_kind": "carried", "dest_kind": "vehicle", "dest_id": "v1",
    })
    assert r.status_code == 303
    spec = load_character("finn", client._characters_dir)
    assert not any(i.instance_id == "torch1" and i.location.kind == "carried"
                   for i in spec.items)
    assert any(i.instance_id == "torch1" and i.location.kind == "vehicle"
               for i in spec.items)

    # Unload torch back to carried
    r = client.post("/character/finn/inventory/move", data={
        "category": "item", "item_id": "torch1",
        "src_kind": "vehicle", "src_id": "v1", "dest_kind": "carried",
    })
    assert r.status_code == 303
    spec = load_character("finn", client._characters_dir)
    assert any(i.instance_id == "torch1" and i.location.kind == "carried"
               for i in spec.items)


def test_animal_unequip_returns_barding_to_inventory(client):
    animals = [AnimalInstance(instance_id="a1", catalog_id="war_horse",
                              armor_id="horse_barding")]
    _save_char(client, animals=animals)
    resp = client.post("/character/finn/animal/a1/unequip")
    assert resp.status_code == 303
    spec = load_character("finn", client._characters_dir)
    assert spec.animals[0].armor_id is None
    assert any(i.catalog_id == "horse_barding" and i.location.kind == "carried"
               for i in spec.items)
