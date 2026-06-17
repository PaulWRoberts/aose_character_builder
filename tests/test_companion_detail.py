from pathlib import Path
from aose.data.loader import GameData
from aose.engine.detail import item_card

DATA = GameData.load(Path("data"))


def test_animal_card_shows_derived_ac_and_attacks():
    card = item_card(DATA.items["camel"])
    labels = {s.label: s.value for s in card.stats}
    assert labels["Type"] == "Animal"
    assert labels["AC"] == "7 [12]"      # 19 - 7
    assert labels["HD"] == "2"
    assert "bite" in labels["Attacks"].lower()
    assert card.description


def test_vehicle_card_shows_hull_and_cargo():
    card = item_card(DATA.items["cart"])
    labels = {s.label: s.value for s in card.stats}
    assert labels["Type"] == "Vehicle"
    assert labels["Hull Points"] == "1d4"
    assert "4000" in labels["Cargo"]


def test_animal_armor_card():
    card = item_card(DATA.items["horse_barding"])
    labels = {s.label: s.value for s in card.stats}
    assert labels["Type"] == "Animal Armour"
    assert labels["AC"] == "5 [14]"
