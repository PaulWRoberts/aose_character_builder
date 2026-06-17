from pydantic import TypeAdapter
from aose.models import Animal, Vehicle, AnimalArmor, AnimalAttack, Item


def test_animal_parses_via_item_union():
    raw = {
        "item_type": "animal", "id": "mule", "name": "Mule",
        "category": "animals", "cost_gp": 30, "hd": "2", "save_as_hd": "NH",
        "hp": 9, "ac": 7, "morale": 8, "alignment": "neutral", "xp": 20,
        "movement": "120' (40')",
        "attacks": [{"name": "kick", "damage": "1d4"},
                    {"name": "bite", "damage": "1d3", "note": "or"}],
        "max_load_unencumbered_cn": 2000, "max_load_encumbered_cn": 4000,
        "traits": ["Tenacious", "Defensive"],
    }
    animal = TypeAdapter(Item).validate_python(raw)
    assert isinstance(animal, Animal)
    assert animal.hd == "2"
    assert animal.save_as_hd == "NH"
    assert animal.attacks[0] == AnimalAttack(name="kick", damage="1d4")
    assert animal.source == "ose_classic_fantasy"  # default


def test_vehicle_parses_via_item_union():
    raw = {
        "item_type": "vehicle", "id": "cart", "name": "Cart",
        "category": "vehicles", "cost_gp": 100, "vehicle_category": "land_vehicle",
        "ac": 9, "hull_points": "1d4", "cargo_capacity_cn": 4000,
        "cargo_capacity_extra_cn": 8000, "required_animals": "1 draft horse or 2 mules",
        "movement": "60' (20')", "traits": [],
    }
    vehicle = TypeAdapter(Item).validate_python(raw)
    assert isinstance(vehicle, Vehicle)
    assert vehicle.hull_points == "1d4"
    assert vehicle.cargo_capacity_extra_cn == 8000


def test_animal_armor_parses_via_item_union():
    raw = {
        "item_type": "animal_armor", "id": "horse_barding", "name": "Horse barding",
        "category": "tack_and_harness", "cost_gp": 150, "weight_cn": 600,
        "sets_ac": 5, "fits": ["draft_horse", "riding_horse", "war_horse"],
    }
    armor = TypeAdapter(Item).validate_python(raw)
    assert isinstance(armor, AnimalArmor)
    assert armor.sets_ac == 5
    assert "war_horse" in armor.fits
