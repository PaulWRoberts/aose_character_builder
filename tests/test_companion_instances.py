from aose.models import (
    CharacterSpec, AnimalInstance, VehicleInstance, ContainerInstance,
)


def _bare_spec(**kw):
    return CharacterSpec(
        name="Hero", abilities={"STR": 10, "INT": 10, "WIS": 10,
                                "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": "fighter"}],
        alignment="neutral", **kw,
    )


def test_spec_defaults_have_empty_companions():
    spec = _bare_spec()
    assert spec.animals == []
    assert spec.vehicles == []


def test_animal_and_vehicle_instances_round_trip():
    spec = _bare_spec(
        animals=[AnimalInstance(instance_id="a1", catalog_id="mule")],
        vehicles=[VehicleInstance(instance_id="v1", catalog_id="cart", hull_max=4)],
    )
    again = CharacterSpec.model_validate(spec.model_dump())
    assert again.animals[0].catalog_id == "mule"
    assert again.vehicles[0].hull_max == 4
    assert again.animals[0].hp_damage == 0
    assert again.animals[0].armor_id is None


def test_container_location_defaults_to_person():
    c = ContainerInstance(instance_id="c1", catalog_id="backpack", state="carried")
    assert c.location == "person"
    assert c.location_id is None


def test_old_save_without_companions_still_loads():
    # A dict shaped like a pre-feature save (no animals/vehicles keys).
    raw = _bare_spec().model_dump()
    raw.pop("animals"); raw.pop("vehicles")
    spec = CharacterSpec.model_validate(raw)
    assert spec.animals == []
