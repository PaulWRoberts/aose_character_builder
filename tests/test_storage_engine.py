import pytest
from aose.engine import storage
from aose.engine.currency import CurrencyError
from aose.models import (CharacterSpec, CoinStack, ContainerInstance,
                         AnimalInstance, GemStack, JewelleryPiece)
from aose.models.storage import StorageLocation


def _spec(**extra):
    base = dict(
        name="T", abilities={"STR": 10, "DEX": 10, "CON": 10,
                             "INT": 10, "WIS": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": "fighter", "level": 1}],
        alignment="neutral",
    )
    base.update(extra)
    return CharacterSpec.model_validate(base)


# ── 6a: loose_list ────────────────────────────────────────────────────────────

def test_loose_list_for_carried_is_inventory():
    spec = _spec(inventory=["torch"])
    assert storage.loose_list(spec, StorageLocation(kind="carried")) is spec.inventory


def test_loose_list_for_stashed_is_stashed():
    spec = _spec(stashed=["rope"])
    assert storage.loose_list(spec, StorageLocation(kind="stashed")) is spec.stashed


def test_loose_list_for_container_is_its_contents():
    c = ContainerInstance(instance_id="c1", catalog_id="backpack", contents=["torch"])
    spec = _spec(containers=[c])
    got = storage.loose_list(spec, StorageLocation(kind="container", id="c1"))
    assert got is spec.containers[0].contents


def test_loose_list_for_animal_is_its_contents():
    a = AnimalInstance(instance_id="a1", catalog_id="mule", contents=["sack"])
    spec = _spec(animals=[a])
    assert storage.loose_list(spec, StorageLocation(kind="animal", id="a1")) is spec.animals[0].contents


def test_loose_list_unknown_id_raises():
    spec = _spec()
    with pytest.raises(storage.StorageError):
        storage.loose_list(spec, StorageLocation(kind="animal", id="nope"))


# ── 6b: move_item ─────────────────────────────────────────────────────────────

def test_move_item_carried_to_stashed():
    spec = _spec(inventory=["torch", "rope"])
    storage.move_item(spec, "torch",
                      StorageLocation(kind="carried"), StorageLocation(kind="stashed"))
    assert spec.inventory == ["rope"]
    assert spec.stashed == ["torch"]


def test_move_item_into_container():
    c = ContainerInstance(instance_id="c1", catalog_id="backpack")
    spec = _spec(inventory=["torch"], containers=[c])
    storage.move_item(spec, "torch",
                      StorageLocation(kind="carried"),
                      StorageLocation(kind="container", id="c1"))
    assert spec.inventory == []
    assert spec.containers[0].contents == ["torch"]


def test_move_item_not_at_source_raises():
    spec = _spec(inventory=["torch"])
    with pytest.raises(storage.StorageError):
        storage.move_item(spec, "rope",
                          StorageLocation(kind="carried"), StorageLocation(kind="stashed"))


# ── 6c: move_container ────────────────────────────────────────────────────────

def test_move_container_to_vehicle_carries_contents():
    from aose.models import VehicleInstance
    c = ContainerInstance(instance_id="c1", catalog_id="backpack", contents=["torch"])
    v = VehicleInstance(instance_id="v1", catalog_id="cart", hull_max=10)
    spec = _spec(containers=[c], vehicles=[v])
    storage.move_container(spec, "c1", StorageLocation(kind="vehicle", id="v1"))
    assert spec.containers[0].location == StorageLocation(kind="vehicle", id="v1")
    assert spec.containers[0].contents == ["torch"]   # contents follow for free


def test_move_container_rejects_container_destination():
    c = ContainerInstance(instance_id="c1", catalog_id="backpack")
    spec = _spec(containers=[c])
    with pytest.raises(storage.StorageError):
        storage.move_container(spec, "c1", StorageLocation(kind="container", id="c2"))


# ── 6d: move_coins ────────────────────────────────────────────────────────────

def test_move_coins_splits_and_merges():
    spec = _spec(coins=[CoinStack(denom="gp", count=10)])
    storage.move_coins(spec, "gp",
                       StorageLocation(kind="carried"),
                       StorageLocation(kind="stashed"), 4)
    by = {(c.denom, c.location.kind): c.count for c in spec.coins}
    assert by[("gp", "carried")] == 6
    assert by[("gp", "stashed")] == 4


def test_move_coins_whole_stack_prunes_source():
    spec = _spec(coins=[CoinStack(denom="gp", count=4)])
    storage.move_coins(spec, "gp",
                       StorageLocation(kind="carried"),
                       StorageLocation(kind="stashed"), 4)
    assert all(c.location.kind == "stashed" for c in spec.coins)
    assert len(spec.coins) == 1


def test_move_coins_more_than_available_raises():
    spec = _spec(coins=[CoinStack(denom="gp", count=2)])
    with pytest.raises(storage.StorageError):
        storage.move_coins(spec, "gp",
                           StorageLocation(kind="carried"),
                           StorageLocation(kind="stashed"), 5)


# ── 6e: convert_coins + add_coins ─────────────────────────────────────────────

def test_convert_coins_in_place_at_location():
    spec = _spec(coins=[CoinStack(denom="gp", count=3,
                                  location=StorageLocation(kind="stashed"))])
    storage.convert_coins(spec, StorageLocation(kind="stashed"), "gp", "sp", 2)
    by = {c.denom: c.count for c in spec.coins}
    assert by["gp"] == 1
    assert by["sp"] == 20
    assert all(c.location.kind == "stashed" for c in spec.coins)


def test_convert_coins_non_whole_raises():
    spec = _spec(coins=[CoinStack(denom="cp", count=5)])
    with pytest.raises(CurrencyError):
        storage.convert_coins(spec, StorageLocation(kind="carried"), "cp", "sp", 5)


def test_add_coins_grants_into_location():
    spec = _spec()
    storage.add_coins(spec, "gp", 7, StorageLocation(kind="carried"))
    assert spec.coins[0].count == 7


# ── 6f: move_valuable ─────────────────────────────────────────────────────────

def test_move_gem_stack_merges_at_destination():
    spec = _spec(gems=[
        GemStack(instance_id="g1", value=100, count=2),
        GemStack(instance_id="g2", value=100,
                 location=StorageLocation(kind="stashed")),
    ])
    storage.move_valuable(spec, "g1", StorageLocation(kind="stashed"))
    stashed = [g for g in spec.gems if g.location.kind == "stashed"]
    assert sum(g.count for g in stashed) == 3
    assert all(g.location.kind == "stashed" for g in spec.gems)


def test_move_jewellery_sets_location():
    spec = _spec(jewellery=[JewelleryPiece(instance_id="j1", value=300)])
    storage.move_valuable(spec, "j1", StorageLocation(kind="vehicle", id="v1"))
    assert spec.jewellery[0].location == StorageLocation(kind="vehicle", id="v1")


def test_move_valuable_unknown_raises():
    spec = _spec()
    with pytest.raises(storage.StorageError):
        storage.move_valuable(spec, "missing", StorageLocation(kind="stashed"))


# ── containers_collection ─────────────────────────────────────────────────────

def _spec_with_retainer():
    from aose.models import CharacterSpec, Retainer
    _cls = [{"class_id": "fighter", "level": 1}]
    npc = CharacterSpec(name="Hench",
                        abilities={"STR": 10, "DEX": 10, "CON": 10,
                                   "INT": 10, "WIS": 10, "CHA": 10},
                        race_id="human", classes=_cls, alignment="neutral")
    pc = CharacterSpec(name="Boss",
                       abilities={"STR": 10, "DEX": 10, "CON": 10,
                                  "INT": 10, "WIS": 10, "CHA": 10},
                       race_id="human", classes=_cls, alignment="neutral")
    pc.retainers.append(Retainer(id="ret1", spec=npc, loyalty=7, role=""))
    return pc


def test_containers_collection_resolves_retainer_vs_spec():
    from aose.engine.storage import containers_collection
    spec = _spec_with_retainer()
    pc = containers_collection(spec, StorageLocation(kind="carried"))
    assert pc is spec.containers
    rid = spec.retainers[0].id
    ret = containers_collection(spec, StorageLocation(kind="retainer", id=rid))
    assert ret is spec.retainers[0].spec.containers
