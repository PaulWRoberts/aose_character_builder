from pathlib import Path
from aose.data.loader import GameData
from aose.models import Animal, Vehicle, AnimalArmor, Container
from aose.engine import monster_stats as ms

DATA = GameData.load(Path("data"))

ANIMAL_IDS = {"camel", "draft_horse", "riding_horse", "war_horse", "mule",
              "hunting_dog", "war_dog"}
LAND_VEHICLE_IDS = {"cart", "wagon"}


def test_all_animals_load():
    for aid in ANIMAL_IDS:
        assert isinstance(DATA.items[aid], Animal), aid


def test_land_vehicles_load():
    for vid in LAND_VEHICLE_IDS:
        v = DATA.items[vid]
        assert isinstance(v, Vehicle) and v.vehicle_category == "land_vehicle"


def test_tack_loads_and_armor_fits_resolve():
    assert isinstance(DATA.items["horse_barding"], AnimalArmor)
    assert isinstance(DATA.items["dog_armour"], AnimalArmor)
    assert isinstance(DATA.items["saddle_bags"], Container)
    assert DATA.items["saddle_bags"].capacity_cn == 300
    # every armor_fits / fits cross-reference resolves to a real catalog id
    for a in (i for i in DATA.items.values() if isinstance(i, Animal)):
        for armor_id in a.armor_fits:
            assert armor_id in DATA.items, f"{a.id} fits unknown {armor_id}"


def test_every_animal_hd_resolves_in_tables():
    for a in (i for i in DATA.items.values() if isinstance(i, Animal)):
        ms.attack_for_hd(a.hd, DATA)        # raises KeyError if a band is missing
        ms.saves_for_hd(a.save_as_hd, DATA)
