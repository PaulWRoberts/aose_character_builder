from pathlib import Path

from aose.data.loader import GameData
from aose.engine import storage
from aose.models import AmmoStack, CharacterSpec, ClassEntry
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))
CARRIED = StorageLocation(kind="carried")
STASHED = StorageLocation(kind="stashed")


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


def test_unload_if_loaded_drops_the_weapon_key():
    spec = _spec(
        inventory=["short_bow", "arrow"],
        equipped={"main_hand": "short_bow"},
        ammo=[AmmoStack(instance_id="a1", base_id="arrow", count=20)],
        loaded_ammo={"short_bow": "a1"},
    )
    storage.unload_if_loaded(spec, "short_bow")
    assert "short_bow" not in spec.loaded_ammo


def test_unload_if_loaded_is_noop_when_not_loaded():
    spec = _spec(inventory=["sword"], loaded_ammo={})
    storage.unload_if_loaded(spec, "sword")  # must not raise
    assert spec.loaded_ammo == {}


# ── Task 4: move_valuable with count (gem split/merge) ──────────────────────

from aose.models import GemStack


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
    assert len(stashed) == 1 and stashed[0].count == 3   # merged, not fragmented


def test_gem_full_move_without_count_moves_whole_stack():
    spec = _spec(gems=[GemStack(instance_id="g1", value=50, count=4, label="opal",
                                location=CARRIED)])
    storage.move_valuable(spec, "g1", STASHED)   # count=None → whole stack
    assert all(g.location == STASHED for g in spec.gems)
    assert len(spec.gems) == 1 and spec.gems[0].count == 4


# ── Task 5: move_ammo ────────────────────────────────────────────────────────

from aose.models import AnimalInstance

MULE = StorageLocation(kind="animal", id="mule1")


def _spec_with_mule(**kw):
    kw.setdefault("animals", [AnimalInstance(instance_id="mule1", catalog_id="mule")])
    return _spec(**kw)


def test_ammo_partial_move_keeps_loaded_remainder():
    spec = _spec_with_mule(
        inventory=["short_bow"], equipped={"main_hand": "short_bow"},
        ammo=[AmmoStack(instance_id="a1", base_id="arrow", count=20, location=CARRIED)],
        loaded_ammo={"short_bow": "a1"},
    )
    storage.move_ammo(spec, "a1", MULE, count=5)
    assert spec.loaded_ammo.get("short_bow") == "a1"        # still loaded
    carried = [s for s in spec.ammo if s.location == CARRIED]
    mule = [s for s in spec.ammo if s.location == MULE]
    assert carried[0].count == 15 and mule[0].count == 5


def test_ammo_full_move_unloads_then_relocates():
    spec = _spec_with_mule(
        inventory=["short_bow"], equipped={"main_hand": "short_bow"},
        ammo=[AmmoStack(instance_id="a1", base_id="arrow", count=20, location=CARRIED)],
        loaded_ammo={"short_bow": "a1"},
    )
    storage.move_ammo(spec, "a1", MULE, count=20)
    assert "short_bow" not in spec.loaded_ammo               # unloaded
    assert all(s.location == MULE for s in spec.ammo)


def test_ammo_full_move_merges_into_destination_stack():
    spec = _spec_with_mule(ammo=[
        AmmoStack(instance_id="a1", base_id="arrow", count=20, location=CARRIED),
        AmmoStack(instance_id="a2", base_id="arrow", count=3, location=MULE),
    ])
    storage.move_ammo(spec, "a1", MULE, count=20)
    mule = [s for s in spec.ammo if s.location == MULE]
    assert len(mule) == 1 and mule[0].count == 23            # merged, no fragment


# ── Task 6: move_instance ────────────────────────────────────────────────────

from aose.models import ContainerInstance, EnchantedInstance, MagicItemInstance, Retainer


def test_magic_move_to_container_repoints_location():
    spec = _spec(
        inventory=["backpack"],
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=CARRIED)],
        magic_items=[MagicItemInstance(instance_id="m1",
                                       catalog_id="ring_protection_plus_1",
                                       equipped=True)],
    )
    dest = StorageLocation(kind="container", id="c1")
    storage.move_instance(spec, "magic", "m1", dest)
    m = spec.magic_items[0]
    assert m.location == dest and m.equipped is False          # auto-unequipped


def test_enchanted_move_to_retainer_is_list_to_list():
    npc = _spec(name="Hench")
    spec = _spec(
        enchanted=[EnchantedInstance(instance_id="e1", base_id="sword",
                                     enchantment_id="generic_plus_1", equipped=False)],
        retainers=[Retainer(id="r1", spec=npc, loyalty=7)],
    )
    dest = StorageLocation(kind="retainer", id="r1")
    storage.move_instance(spec, "enchanted", "e1", dest)
    assert spec.enchanted == []                                 # left PC world
    moved = spec.retainers[0].spec.enchanted
    assert len(moved) == 1 and moved[0].location == CARRIED     # reset in retainer world


def test_magic_move_clears_equipped_slot_for_weapon():
    # A magic item whose catalog_id matches an equipped slot key should
    # have that slot cleared when moved away.
    spec = _spec(
        inventory=["ring_protection_plus_1"],
        equipped={"main_hand": "ring_protection_plus_1"},
        magic_items=[MagicItemInstance(instance_id="m1",
                                       catalog_id="ring_protection_plus_1",
                                       equipped=True)],
    )
    storage.move_instance(spec, "magic", "m1", STASHED)
    assert spec.equipped.get("main_hand") != "ring_protection_plus_1"


# ── Task 7: move_thing dispatcher + move_targets ─────────────────────────────

from aose.models import CoinStack


def test_move_thing_dispatches_each_category():
    spec = _spec_with_mule(
        inventory=["torch", "backpack"],
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=CARRIED)],
        coins=[CoinStack(denom="gp", count=10, location=CARRIED)],
        gems=[GemStack(instance_id="g1", value=50, count=2, label="", location=CARRIED)],
        ammo=[AmmoStack(instance_id="a1", base_id="arrow", count=20, location=CARRIED)],
        magic_items=[MagicItemInstance(instance_id="m1",
                                       catalog_id="ring_protection_plus_1")],
    )
    cont = StorageLocation(kind="container", id="c1")
    storage.move_thing(spec, "item", "torch", cont,
                       src=CARRIED, data=DATA)
    storage.move_thing(spec, "coin", "gp", MULE, count=4, data=DATA)
    storage.move_thing(spec, "gem", "g1", MULE, count=1, data=DATA)
    storage.move_thing(spec, "ammo", "a1", MULE, count=20, data=DATA)
    storage.move_thing(spec, "magic", "m1", MULE, data=DATA)
    # torch moved into container c1
    assert "torch" in spec.containers[0].contents
    # coins split: 6 carried, 4 on mule
    assert sum(c.count for c in spec.coins if c.location == CARRIED) == 6
    assert sum(c.count for c in spec.coins if c.location == MULE) == 4
    assert any(s.location == MULE for s in spec.ammo)
    assert spec.magic_items[0].location == MULE


def test_move_targets_lists_inventories_and_containers():
    spec = _spec_with_mule(
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=CARRIED)],
    )
    targets = storage.move_targets(spec, DATA)
    kinds = {(t["kind"], t.get("id")) for t in targets}
    assert ("carried", None) in kinds
    assert ("stashed", None) in kinds
    assert ("animal", "mule1") in kinds
    assert ("container", "c1") in kinds


# ── Task 5 (plan): move_item auto-unequip ────────────────────────────────────

def test_moving_last_copy_of_equipped_item_unequips_it():
    spec = _spec(inventory=["sword"], equipped={"main_hand": "sword"})
    storage.move_item(spec, "sword", CARRIED, STASHED)
    assert "main_hand" not in spec.equipped
    assert spec.stashed == ["sword"]


def test_moving_one_of_two_copies_keeps_the_equipped_one():
    spec = _spec(inventory=["sword", "sword"], equipped={"main_hand": "sword"})
    storage.move_item(spec, "sword", CARRIED, STASHED)
    assert spec.equipped.get("main_hand") == "sword"   # a carried copy remains


# ── Task 6 (plan): move_spell_source + source category ───────────────────────

from aose.models import SpellSource, SpellSourceEntry, Retainer


def _scroll(iid="s1", loc=None):
    return SpellSource(instance_id=iid, kind="scroll", caster_type="arcane",
                       entries=[SpellSourceEntry(spell_id="magic_user_magic_missile")],
                       location=loc or CARRIED)


def test_move_spell_source_repoints_location_same_world():
    spec = _spec(spell_sources=[_scroll()])
    storage.move_thing(spec, "source", "s1", STASHED, data=DATA)
    assert spec.spell_sources[0].location == STASHED


def test_move_spell_source_to_container():
    spec = _spec(
        spell_sources=[_scroll()],
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=CARRIED)],
    )
    dest = StorageLocation(kind="container", id="c1")
    storage.move_thing(spec, "source", "s1", dest, data=DATA)
    assert spec.spell_sources[0].location == dest


# ── Task 7 (plan): capacity gate on all move categories ──────────────────────

import pytest


def test_move_thing_item_into_full_container_rejected():
    spec = _spec(
        inventory=["sword"],
        containers=[ContainerInstance(instance_id="p1", catalog_id="belt_pouch",
                                      location=CARRIED)],   # cap 50; sword 60
    )
    dest = StorageLocation(kind="container", id="p1")
    with pytest.raises(storage.StorageError):
        storage.move_thing(spec, "item", "sword", dest, src=CARRIED, data=DATA)
    assert spec.inventory == ["sword"]   # unchanged on rejection


def test_move_thing_coins_onto_retainer_never_blocked():
    ret_spec = _spec(name="Hench")
    spec = _spec(coins=[CoinStack(denom="gp", count=500, location=CARRIED)],
                 retainers=[Retainer(id="r1", spec=ret_spec, loyalty=7, role="torchbearer")])
    dest = StorageLocation(kind="retainer", id="r1")
    storage.move_thing(spec, "coin", "gp", dest, count=500, src=CARRIED, data=DATA)
    # accepted; coins now on the retainer
    assert any(c.location == dest and c.count == 500 for c in spec.coins)


# ── Task 8 (new model): move_thing item by instance_id + capacity check ──────

from aose.models import ItemInstance, ContainerInstance


def test_move_thing_item_by_instance_id_into_container():
    spec = _spec(
        items=[ItemInstance(instance_id="i1", catalog_id="torch", count=3, location=CARRIED),
               ItemInstance(instance_id="i2", catalog_id="backpack", location=CARRIED)],
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=CARRIED)],
    )
    dest = StorageLocation(kind="container", id="c1")
    storage.move_thing(spec, "item", "i1", dest, count=2, data=DATA)
    inside = storage.items_at(spec, dest)
    assert inside[0].catalog_id == "torch" and inside[0].count == 2


def test_check_capacity_reads_policy_descriptor():
    spec = _spec(
        items=[ItemInstance(instance_id="i1", catalog_id="sword", location=CARRIED)],
        containers=[ContainerInstance(instance_id="p1", catalog_id="belt_pouch",
                                      location=CARRIED)],   # cap 50 < sword 60
    )
    dest = StorageLocation(kind="container", id="p1")
    with pytest.raises(storage.StorageError):
        storage.move_thing(spec, "item", "i1", dest, data=DATA)
