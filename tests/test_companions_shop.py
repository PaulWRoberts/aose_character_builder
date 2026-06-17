from pathlib import Path
import random
import pytest
from aose.data.loader import GameData
from aose.engine import companions
from aose.engine.shop import InsufficientGold, UnknownItem

DATA = GameData.load(Path("data"))


def test_buy_animal_creates_instance_and_deducts_gold():
    animals, gold = companions.buy_animal([], 100, "mule", DATA)
    assert gold == 70
    assert len(animals) == 1 and animals[0].catalog_id == "mule"
    assert animals[0].instance_id  # uuid assigned


def test_buy_animal_insufficient_gold():
    with pytest.raises(InsufficientGold):
        companions.buy_animal([], 10, "war_horse", DATA)


def test_buy_animal_rejects_non_animal():
    with pytest.raises(ValueError):
        companions.buy_animal([], 1000, "cart", DATA)


def test_buy_vehicle_resolves_hull_from_dice():
    rng = random.Random(1)
    vehicles, gold = companions.buy_vehicle([], 100, "cart", DATA, rng=rng)
    assert gold == 0
    assert 1 <= vehicles[0].hull_max <= 4


def test_buy_vehicle_resolves_hull_from_range_to_max():
    vehicles, _ = companions.buy_vehicle([], 99999, "longship", DATA)
    assert vehicles[0].hull_max == 80   # max of "60-80"


def test_remove_animal_refund_returns_full_cost():
    animals, gold = companions.buy_animal([], 100, "mule", DATA)
    iid = animals[0].instance_id
    animals, gold = companions.remove_animal(animals, gold, iid, "refund", DATA)
    assert animals == [] and gold == 100


def test_remove_animal_sell_returns_half():
    animals, gold = companions.buy_animal([], 100, "mule", DATA)
    iid = animals[0].instance_id
    animals, gold = companions.remove_animal(animals, gold, iid, "sell", DATA)
    assert gold == 70 + 15
