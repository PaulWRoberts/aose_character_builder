from pathlib import Path
import random
from aose.data.loader import GameData
from aose.engine import quick_equipment as qe
from aose.models import Weapon, Armor

DATA = GameData.load(Path("data"))


def test_fighter_kit_has_basics_armour_and_two_weapons():
    kit = qe.roll_kit("fighter", DATA, rng=random.Random(1))
    # basic gear
    assert "backpack" in kit.inventory
    assert "tinder_box" in kit.inventory
    assert "waterskin" in kit.inventory
    assert kit.inventory.count("torch") >= 1
    assert kit.inventory.count("iron_rations") >= 1
    assert 3 <= kit.gold <= 18
    # armour equipped from the d6 table
    armor_id = kit.equipped.get("armor")
    assert isinstance(DATA.items[armor_id], Armor)
    # a main-hand weapon was chosen
    assert isinstance(DATA.items[kit.equipped["main_hand"]], Weapon)


def test_magic_user_kit_no_armour_has_dagger():
    kit = qe.roll_kit("magic_user", DATA, rng=random.Random(1))
    assert "armor" not in kit.equipped
    assert "dagger" in kit.inventory


def test_kit_is_deterministic_for_seed():
    a = qe.roll_kit("fighter", DATA, rng=random.Random(42))
    b = qe.roll_kit("fighter", DATA, rng=random.Random(42))
    assert a.model_dump() == b.model_dump()
