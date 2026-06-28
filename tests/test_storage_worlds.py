"""Engine-level tests for world-aware container resolution (PC <-> retainer).

There is no shared conftest in this repo, so spec/retainer construction is done
inline here (mirroring tests/test_retainer_routes.py's _save_char_with_retainer).
"""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine import retainers as retainers_engine
from aose.engine import storage
from aose.engine.shop import new_container_instance
from aose.models import CharacterSpec, ClassEntry, CoinStack, ItemInstance
from aose.models.storage import StorageLocation

DATA_DIR = Path(__file__).parent.parent / "data"
GAME_DATA = GameData.load(DATA_DIR)


def _make_character() -> CharacterSpec:
    return CharacterSpec(
        name="Boss",
        abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 13},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=3, hp_rolls=[8, 8, 8])],
        alignment="neutral",
    )


def _make_character_with_retainer(data: GameData) -> tuple[CharacterSpec, str]:
    spec = _make_character()
    ret = retainers_engine.generate_retainer(
        name="Hench", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=spec, data=data)
    spec.retainers.append(ret)
    return spec, ret.id


# ---------------------------------------------------------------------------
# Task B1 — items into / out of a retainer-owned container
# ---------------------------------------------------------------------------

def test_move_item_into_retainer_container():
    """Moving a PC item into a retainer-owned container must land it in the
    retainer's world at that container (regression: bug 3 'no container with id')."""
    spec, rid = _make_character_with_retainer(GAME_DATA)
    ret = next(r for r in spec.retainers if r.id == rid)
    cont = new_container_instance("backpack", GAME_DATA)
    ret.spec.containers.append(cont)
    spec.items.append(ItemInstance(instance_id="rope-iid", catalog_id="rope_50ft",
                                   count=1, location=StorageLocation(kind="carried")))

    dest = StorageLocation(kind="container", id=cont.instance_id)
    storage.move_item(spec, "rope-iid", dest, data=GAME_DATA)

    # Gone from PC world, present in retainer world at the container.
    assert all(i.instance_id != "rope-iid" for i in spec.items)
    landed = [i for i in ret.spec.items
              if i.catalog_id == "rope_50ft" and i.location == dest]
    assert landed and landed[0].count == 1


def test_move_item_out_of_retainer_container_to_pc():
    spec, rid = _make_character_with_retainer(GAME_DATA)
    ret = next(r for r in spec.retainers if r.id == rid)
    cont = new_container_instance("backpack", GAME_DATA)
    ret.spec.containers.append(cont)
    here = StorageLocation(kind="container", id=cont.instance_id)
    ret.spec.items.append(ItemInstance(instance_id="torch-r", catalog_id="torch",
                                       count=2, location=here))

    storage.move_item(spec, "torch-r", StorageLocation(kind="carried"), data=GAME_DATA)
    assert all(i.instance_id != "torch-r" for i in ret.spec.items)
    assert any(i.catalog_id == "torch" and i.location.kind == "carried"
               for i in spec.items)


def test_move_into_full_retainer_container_rejected():
    """Capacity check must read the container's owning (retainer) world. A full
    retainer-owned backpack must reject a further move INTO it. Regression: before
    the fix, location_load_cn counted the PC's empty lists and approved overfill."""
    spec, rid = _make_character_with_retainer(GAME_DATA)
    ret = next(r for r in spec.retainers if r.id == rid)
    cont = new_container_instance("backpack", GAME_DATA)   # capacity 400 cn
    ret.spec.containers.append(cont)
    here = StorageLocation(kind="container", id=cont.instance_id)
    # Two suits of leather armour (200 cn each) fill the 400 cn backpack exactly.
    ret.spec.items.append(ItemInstance(instance_id="la-1", catalog_id="leather_armor",
                                       count=1, location=here))
    ret.spec.items.append(ItemInstance(instance_id="la-2", catalog_id="leather_armor",
                                       count=1, location=here))
    # A third suit sits in the PC world, waiting to move in.
    spec.items.append(ItemInstance(instance_id="la-3", catalog_id="leather_armor",
                                   count=1, location=StorageLocation(kind="carried")))

    with pytest.raises(storage.StorageError):
        storage.move_item(spec, "la-3", here, data=GAME_DATA)
    # Rejected: still in the PC world, container still holds only the two.
    assert any(i.instance_id == "la-3" for i in spec.items)
    assert sum(1 for i in ret.spec.items
               if i.catalog_id == "leather_armor" and i.location == here) == 2


# ---------------------------------------------------------------------------
# Task B2 — coins / gems into a retainer-owned container
# ---------------------------------------------------------------------------

def test_move_coins_into_retainer_container():
    spec, rid = _make_character_with_retainer(GAME_DATA)
    ret = next(r for r in spec.retainers if r.id == rid)
    cont = new_container_instance("backpack", GAME_DATA)
    ret.spec.containers.append(cont)
    spec.coins = [CoinStack(denom="gp", count=10, location=StorageLocation(kind="carried"))]

    dest = StorageLocation(kind="container", id=cont.instance_id)
    storage.move_coins(spec, "gp", StorageLocation(kind="carried"), dest, 4, GAME_DATA)
    landed = [c for c in ret.spec.coins if c.denom == "gp" and c.location == dest]
    assert landed and landed[0].count == 4
    # And the source stack in the PC world shrank.
    pc_carried = [c for c in spec.coins
                  if c.denom == "gp" and c.location.kind == "carried"]
    assert pc_carried and pc_carried[0].count == 6


def test_move_gems_into_retainer_container():
    from aose.models import GemStack
    spec, rid = _make_character_with_retainer(GAME_DATA)
    ret = next(r for r in spec.retainers if r.id == rid)
    cont = new_container_instance("backpack", GAME_DATA)
    ret.spec.containers.append(cont)
    spec.gems = [GemStack(instance_id="gem-iid", value=50, count=3,
                          location=StorageLocation(kind="carried"))]

    dest = StorageLocation(kind="container", id=cont.instance_id)
    storage.move_valuable(spec, "gem-iid", dest, count=2, data=GAME_DATA)
    landed = [g for g in ret.spec.gems if g.value == 50 and g.location == dest]
    assert landed and landed[0].count == 2
    # Source stack in PC world shrank.
    pc_gems = [g for g in spec.gems if g.instance_id == "gem-iid"]
    assert pc_gems and pc_gems[0].count == 1


# ---------------------------------------------------------------------------
# Task C1 — storage.add_item: the single stackable-aware add front door
# ---------------------------------------------------------------------------

def test_add_item_merges_stackables():
    spec = _make_character()
    carried = StorageLocation(kind="carried")
    storage.add_item(spec, "torch", 3, carried, GAME_DATA)
    storage.add_item(spec, "torch", 2, carried, GAME_DATA)
    torches = [i for i in spec.items if i.catalog_id == "torch"]
    assert len(torches) == 1 and torches[0].count == 5


def test_add_item_keeps_equippables_separate():
    spec = _make_character()
    carried = StorageLocation(kind="carried")
    storage.add_item(spec, "sword", 1, carried, GAME_DATA)
    storage.add_item(spec, "sword", 1, carried, GAME_DATA)
    swords = [i for i in spec.items if i.catalog_id == "sword"]
    assert len(swords) == 2


# ---------------------------------------------------------------------------
# Task D1 — consume_item: remove exactly one unit, drop the stack at zero
# ---------------------------------------------------------------------------

def test_consume_item_removes_one():
    spec = _make_character()
    spec.items.append(ItemInstance(instance_id="t", catalog_id="torch", count=2,
                                   location=StorageLocation(kind="carried")))
    storage.consume_item(spec, "t")
    assert next(i for i in spec.items if i.instance_id == "t").count == 1
    storage.consume_item(spec, "t")
    assert all(i.instance_id != "t" for i in spec.items)


def test_consume_item_searches_retainer_world():
    spec, rid = _make_character_with_retainer(GAME_DATA)
    ret = next(r for r in spec.retainers if r.id == rid)
    ret.spec.items.append(ItemInstance(instance_id="r-t", catalog_id="torch",
                                       count=1, location=StorageLocation(kind="carried")))
    storage.consume_item(spec, "r-t")
    assert all(i.instance_id != "r-t" for i in ret.spec.items)


def test_consume_item_clears_weapon_load_on_last_ammo():
    spec = _make_character()
    spec.items.append(ItemInstance(instance_id="ammo", catalog_id="arrow", count=1,
                                   location=StorageLocation(kind="carried")))
    spec.items.append(ItemInstance(instance_id="bow", catalog_id="long_bow", count=1,
                                   location=StorageLocation(kind="carried"),
                                   loaded_ammo_id="ammo"))
    storage.consume_item(spec, "ammo")
    bow = next(i for i in spec.items if i.instance_id == "bow")
    assert bow.loaded_ammo_id is None


def test_consume_item_missing_raises():
    spec = _make_character()
    with pytest.raises(storage.StorageError):
        storage.consume_item(spec, "nope")
