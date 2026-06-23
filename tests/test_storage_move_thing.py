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
