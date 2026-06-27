"""storage.move_item / move_valuable / move_thing dispatcher tests.

Migrated from old AmmoStack/EnchantedInstance model to unified ItemInstance.
"""
import uuid
from pathlib import Path

from aose.data.loader import GameData
from aose.engine import storage
from aose.models import (
    AnimalInstance, CharacterSpec, ClassEntry, ContainerInstance,
    GemStack, ItemInstance, MagicItemInstance, Retainer,
)
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))
CARRIED = StorageLocation(kind="carried")
STASHED = StorageLocation(kind="stashed")
MULE = StorageLocation(kind="animal", id="mule1")


def _spec(**kw):
    base = dict(
        name="Mover",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
    )
    base.update(kw)
    return CharacterSpec(**base)


def _item(catalog_id, location=None, count=1, equip=None, loaded_ammo_id=None, iid=None,
          enchantment_id=None):
    return ItemInstance(
        instance_id=iid or uuid.uuid4().hex,
        catalog_id=catalog_id,
        location=location or CARRIED,
        count=count,
        equip=equip,
        loaded_ammo_id=loaded_ammo_id,
        enchantment_id=enchantment_id,
    )


def _spec_with_mule(**kw):
    kw.setdefault("animals", [AnimalInstance(instance_id="mule1", catalog_id="mule")])
    return _spec(**kw)


# ── Gem move (move_valuable) ────────────────────────────────────────────────

def test_gem_partial_move_splits_and_merges():
    spec = _spec(gems=[GemStack(instance_id="g1", value=100, count=5, label="ruby",
                                location=CARRIED)])
    storage.move_valuable(spec, "g1", STASHED, count=2)
    carried = [g for g in spec.gems if g.location == CARRIED]
    stashed = [g for g in spec.gems if g.location == STASHED]
    assert carried[0].count == 3
    assert len(stashed) == 1 and stashed[0].count == 2 and stashed[0].value == 100


def test_gem_partial_move_merges_into_existing_destination_stack():
    spec = _spec(gems=[
        GemStack(instance_id="g1", value=100, count=5, label="ruby", location=CARRIED),
        GemStack(instance_id="g2", value=100, count=1, label="ruby", location=STASHED),
    ])
    storage.move_valuable(spec, "g1", STASHED, count=2)
    stashed = [g for g in spec.gems if g.location == STASHED]
    assert len(stashed) == 1 and stashed[0].count == 3


def test_gem_full_move_without_count_moves_whole_stack():
    spec = _spec(gems=[GemStack(instance_id="g1", value=50, count=4, label="opal",
                                location=CARRIED)])
    storage.move_valuable(spec, "g1", STASHED)
    assert all(g.location == STASHED for g in spec.gems)
    assert len(spec.gems) == 1 and spec.gems[0].count == 4


# ── Ammo move (now move_item, ammo is ItemInstance) ─────────────────────────

def test_ammo_partial_move_splits_and_keeps_remainder():
    bow_iid = uuid.uuid4().hex
    ammo_iid = "a1"
    spec = _spec_with_mule(items=[
        _item("short_bow", equip="main_hand", loaded_ammo_id=ammo_iid, iid=bow_iid),
        _item("arrow", count=20, iid=ammo_iid),
    ])
    storage.move_item(spec, ammo_iid, MULE, count=5, data=DATA)
    bow = next(i for i in spec.items if i.catalog_id == "short_bow")
    assert bow.loaded_ammo_id == ammo_iid   # still loaded (partial move)
    carried = [i for i in spec.items if i.catalog_id == "arrow" and i.location == CARRIED]
    mule = [i for i in spec.items if i.catalog_id == "arrow" and i.location == MULE]
    assert carried[0].count == 15 and mule[0].count == 5


def test_ammo_full_move_clears_loaded_state():
    bow_iid = uuid.uuid4().hex
    ammo_iid = "a1"
    spec = _spec_with_mule(items=[
        _item("short_bow", equip="main_hand", loaded_ammo_id=ammo_iid, iid=bow_iid),
        _item("arrow", count=20, iid=ammo_iid),
    ])
    storage.move_item(spec, ammo_iid, MULE, count=20, data=DATA)
    bow = next(i for i in spec.items if i.catalog_id == "short_bow")
    assert bow.loaded_ammo_id is None   # cleared when whole stack leaves


def test_ammo_full_move_merges_into_destination_stack():
    ammo_a = "a1"
    ammo_b = "a2"
    spec = _spec_with_mule(items=[
        _item("arrow", count=20, iid=ammo_a),
        _item("arrow", count=3, location=MULE, iid=ammo_b),
    ])
    storage.move_item(spec, ammo_a, MULE, count=20, data=DATA)
    mule = [i for i in spec.items if i.catalog_id == "arrow" and i.location == MULE]
    assert len(mule) == 1 and mule[0].count == 23


# ── Enchanted item move (now move_item, enchanted is ItemInstance) ───────────

def test_enchanted_move_to_retainer_crosses_worlds():
    npc = _spec(name="Hench")
    ench_iid = "e1"
    spec = _spec(
        items=[_item("sword", iid=ench_iid,
                     **{"enchantment_id": None})],  # plain for simplicity
        retainers=[Retainer(id="r1", spec=npc, loyalty=7)],
    )
    # Use a plain sword instance_id
    spec.items[0] = ItemInstance(
        instance_id=ench_iid, catalog_id="sword",
        enchantment_id=None, location=CARRIED,
    )
    dest = StorageLocation(kind="retainer", id="r1")
    storage.move_item(spec, ench_iid, dest, data=DATA)
    assert all(i.instance_id != ench_iid for i in spec.items)   # left PC world
    moved = spec.retainers[0].spec.items
    assert len(moved) == 1 and moved[0].location == CARRIED


# ── Magic item move (move_instance, still separate) ─────────────────────────

def test_magic_move_to_container_auto_unequips():
    spec = _spec(
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=CARRIED)],
        magic_items=[MagicItemInstance(instance_id="m1",
                                       catalog_id="ring_protection_plus_1",
                                       equipped=True)],
    )
    dest = StorageLocation(kind="container", id="c1")
    storage.move_instance(spec, "magic", "m1", dest)
    m = spec.magic_items[0]
    assert m.location == dest and m.equipped is False


# ── move_thing dispatcher ────────────────────────────────────────────────────

from aose.models import CoinStack


def test_move_thing_dispatches_each_category():
    ammo_iid = "a1"
    torch_iid = "t1"
    spec = _spec_with_mule(
        items=[
            _item("torch", iid=torch_iid),
            _item("arrow", count=20, iid=ammo_iid),
        ],
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=CARRIED)],
        coins=[CoinStack(denom="gp", count=10, location=CARRIED)],
        gems=[GemStack(instance_id="g1", value=50, count=2, label="", location=CARRIED)],
        magic_items=[MagicItemInstance(instance_id="m1",
                                       catalog_id="ring_protection_plus_1")],
    )
    cont = StorageLocation(kind="container", id="c1")
    storage.move_thing(spec, "item", torch_iid, cont, src=CARRIED, data=DATA)
    storage.move_thing(spec, "coin", "gp", MULE, count=4, data=DATA)
    storage.move_thing(spec, "gem", "g1", MULE, count=1, data=DATA)
    storage.move_thing(spec, "ammo", ammo_iid, MULE, count=20, data=DATA)
    storage.move_thing(spec, "magic", "m1", MULE, data=DATA)

    # torch moved into container c1
    torch_in_cont = [i for i in spec.items
                     if i.catalog_id == "torch" and i.location == cont]
    assert len(torch_in_cont) == 1
    # coins split: 6 carried, 4 on mule
    assert sum(c.count for c in spec.coins if c.location == CARRIED) == 6
    assert sum(c.count for c in spec.coins if c.location == MULE) == 4
    # ammo all moved to mule
    assert all(i.location == MULE for i in spec.items if i.catalog_id == "arrow")
