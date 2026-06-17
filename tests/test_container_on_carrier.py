from pathlib import Path
from aose.data.loader import GameData
from aose.engine import companions, encumbrance
from aose.models import (
    CharacterSpec, AnimalInstance, ContainerInstance,
)

DATA = GameData.load(Path("data"))


def _spec(**kw):
    return CharacterSpec(
        name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                             "CON": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": "fighter"}],
        alignment="neutral", ruleset={"encumbrance": "detailed"}, **kw)


def test_move_container_onto_animal_sets_location():
    spec = _spec(
        animals=[AnimalInstance(instance_id="a1", catalog_id="mule")],
        containers=[ContainerInstance(instance_id="c1", catalog_id="saddle_bags",
                                      state="carried")],
    )
    companions.move_container_to_animal(spec, "c1", "a1", DATA)
    c = spec.containers[0]
    assert c.location == "animal" and c.location_id == "a1"


def test_carrier_container_excluded_from_pc_weight():
    # A carried saddle-bag on the person would add its own weight; once on the
    # mule it must not count toward the PC's carried weight.
    spec = _spec(
        animals=[AnimalInstance(instance_id="a1", catalog_id="mule")],
        containers=[ContainerInstance(instance_id="c1", catalog_id="saddle_bags",
                                      state="carried")],
    )
    before = encumbrance.equipment_weight_cn(spec, DATA)
    companions.move_container_to_animal(spec, "c1", "a1", DATA)
    after = encumbrance.equipment_weight_cn(spec, DATA)
    assert after <= before  # carrier container no longer in PC total
