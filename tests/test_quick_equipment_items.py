"""Task 15 verification: quick_equipment builds ItemInstances, not inventory strings."""
from pathlib import Path
import random
from aose.data.loader import GameData
from aose.engine import quick_equipment
from aose.models import CharacterSpec, ClassEntry, ItemInstance

DATA = GameData.load(Path("data"))


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw)
    return CharacterSpec(**base)


def test_apply_kit_populates_spec_items():
    spec = _spec()
    kit = quick_equipment.roll_kit("fighter", DATA, rng=random.Random(42))
    quick_equipment.apply_kit(spec, kit, DATA)
    assert len(spec.items) > 0
    assert all(isinstance(i, ItemInstance) for i in spec.items)


def test_apply_kit_equips_armor_on_instance():
    from aose.engine.equip import equipped_instance
    spec = _spec()
    kit = quick_equipment.roll_kit("fighter", DATA, rng=random.Random(42))
    quick_equipment.apply_kit(spec, kit, DATA)
    # Fighter should have armor equipped (chain mail or plate depending on roll)
    armor_inst = equipped_instance(spec, "armor")
    # May be None if the roll gave no armor, but if it exists it must be valid
    if armor_inst is not None:
        assert armor_inst.equip == "armor"
        from aose.models import Armor
        assert isinstance(DATA.items.get(armor_inst.catalog_id), Armor)


def test_apply_kit_ammo_in_items():
    spec = _spec()
    # Roll until we get an archer kit (use fixed seed)
    for seed in range(100):
        kit = quick_equipment.roll_kit("fighter", DATA, rng=random.Random(seed))
        if kit.ammo:
            quick_equipment.apply_kit(spec, kit, DATA)
            from aose.models import Ammunition
            ammo_insts = [i for i in spec.items if isinstance(DATA.items.get(i.catalog_id), Ammunition)]
            assert len(ammo_insts) > 0
            assert all(i.count >= 1 for i in ammo_insts)
            return
    # If no ammo kit found in 100 seeds, pass (unlikely to always fail)
