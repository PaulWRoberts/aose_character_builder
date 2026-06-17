from pathlib import Path
from aose.data.loader import GameData
from aose.sheet.companions_view import companions_block
from aose.models import CharacterSpec, AnimalInstance, VehicleInstance

DATA = GameData.load(Path("data"))


def _spec(**kw):
    return CharacterSpec(
        name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                             "CON": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": "fighter"}],
        alignment="neutral", **kw)


def test_empty_when_no_companions():
    assert companions_block(_spec(), DATA) is None


def test_animal_card_derives_stats():
    spec = _spec(animals=[AnimalInstance(instance_id="a1", catalog_id="war_horse",
                                         armor_id="horse_barding")])
    block = companions_block(spec, DATA)
    card = block.animals[0]
    assert card.name == "War horse"
    assert card.ac_descending == 5         # barding overrides natural 7
    assert card.thac0 == 17                # HD 3
    assert card.saves["death"] == 12       # save-as 2 → band 1-3
    assert card.hp_current == 13 and card.hp_max == 13


def test_vehicle_card_capacity_meter():
    spec = _spec(vehicles=[VehicleInstance(instance_id="v1", catalog_id="cart",
                                           hull_max=4)])
    block = companions_block(spec, DATA)
    card = block.vehicles[0]
    assert card.cargo_capacity == 4000
    assert card.cargo_used == 0
    assert card.hull_current == 4
