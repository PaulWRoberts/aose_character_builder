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
