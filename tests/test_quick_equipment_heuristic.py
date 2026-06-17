from pathlib import Path
import random
from aose.data.loader import GameData
from aose.engine import quick_equipment as qe
from aose.models import Weapon, Armor

DATA = GameData.load(Path("data"))

# pick a class id that is NOT in quick_equipment.yaml's classes map
UNLISTED = next(cid for cid in DATA.classes
                if cid not in DATA.quick_equipment.get("classes", {}))


def test_unlisted_class_gets_basic_gear_and_a_weapon():
    kit = qe.roll_kit(UNLISTED, DATA, rng=random.Random(1))
    assert "backpack" in kit.inventory
    weapons = [i for i in kit.inventory if isinstance(DATA.items.get(i), Weapon)]
    assert weapons, f"{UNLISTED} got no weapon"


def test_heuristic_armour_respects_class_allowance():
    # for every unlisted class, any equipped armour must be one the class allows
    from aose.engine.proficiency import allowed_armor_ids
    for cid, cls in DATA.classes.items():
        if cid in DATA.quick_equipment.get("classes", {}):
            continue
        kit = qe.roll_kit(cid, DATA, rng=random.Random(3))
        armor_id = kit.equipped.get("armor")
        if armor_id:
            allowed = allowed_armor_ids([cls], DATA)
            assert allowed == "all" or armor_id in allowed, f"{cid}: {armor_id}"


def test_heuristic_weapon_respects_class_allowance():
    from aose.engine.proficiency import allowed_weapon_ids, base_weapon_id
    for cid, cls in DATA.classes.items():
        if cid in DATA.quick_equipment.get("classes", {}):
            continue
        kit = qe.roll_kit(cid, DATA, rng=random.Random(3))
        allowed = allowed_weapon_ids([cls], DATA)
        if allowed == "all":
            continue
        for wid in (i for i in kit.inventory
                    if isinstance(DATA.items.get(i), Weapon)):
            assert base_weapon_id(DATA.items[wid]) in allowed, f"{cid}: {wid}"
