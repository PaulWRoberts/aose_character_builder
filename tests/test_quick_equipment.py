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
    armor_id = kit.equips.get("armor")
    assert isinstance(DATA.items[armor_id], Armor)
    # a main-hand weapon was chosen
    assert isinstance(DATA.items[kit.equips["main_hand"]], Weapon)


def test_magic_user_kit_no_armour_has_dagger():
    kit = qe.roll_kit("magic_user", DATA, rng=random.Random(1))
    assert "armor" not in kit.equips
    assert "dagger" in kit.inventory


def test_kit_is_deterministic_for_seed():
    a = qe.roll_kit("fighter", DATA, rng=random.Random(42))
    b = qe.roll_kit("fighter", DATA, rng=random.Random(42))
    assert a.model_dump() == b.model_dump()


def test_ranged_weapon_yields_ammo_stack():
    # force the sling/bow path by seeding until a launcher appears, or assert
    # over many seeds that whenever a launcher is in inventory an ammo stack exists.
    for seed in range(50):
        kit = qe.roll_kit("fighter", DATA, rng=random.Random(seed))
        launchers = {"short_bow", "crossbow", "sling"} & set(kit.inventory)
        if launchers:
            assert kit.ammo, f"launcher {launchers} but no ammo (seed {seed})"
            assert kit.ammo[0]["count"] == 20
            return
    raise AssertionError("no launcher rolled in 50 seeds")


def test_two_handed_main_leaves_off_hand_empty():
    # polearm is two-handed; when it's the main hand, no shield should be equipped
    for seed in range(50):
        kit = qe.roll_kit("fighter", DATA, rng=random.Random(seed))
        main = kit.equips.get("main_hand")
        if main and "two_handed" in DATA.items[main].quality_ids:
            assert kit.equips.get("off_hand") != "shield"
            return


def test_apply_kit_writes_onto_spec():
    from aose.models import CharacterSpec
    spec = CharacterSpec(
        name="R", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                             "CON": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": "fighter"}], alignment="neutral")
    kit = qe.roll_kit("fighter", DATA, rng=random.Random(1))
    qe.apply_kit(spec, kit, DATA)
    # apply_kit routes Container items to spec.containers; verify all items placed.
    from collections import Counter
    ammo_ids = {g["base_id"] for g in kit.ammo}
    placed = Counter(i.catalog_id for i in spec.items if i.catalog_id not in ammo_ids)
    placed.update(c.catalog_id for c in spec.containers)
    assert placed == Counter(kit.inventory)
    # Equip intentions were applied
    for slot, cid in kit.equips.items():
        assert any(i.catalog_id == cid and i.equip == slot for i in spec.items), \
            f"slot {slot} not equipped with {cid}"
    # Ammo grants landed in spec.items
    for grant in kit.ammo:
        assert any(i.catalog_id == grant["base_id"] for i in spec.items), \
            f"ammo {grant['base_id']} not in spec.items"
    carried_gp = next((s.count for s in spec.coins
                       if s.denom == "gp" and s.location.kind == "carried"), 0)
    assert carried_gp == kit.gold
