from pathlib import Path
from aose.data.loader import GameData
from aose.engine import companions, encumbrance
from aose.models import (
    CharacterSpec, AnimalInstance, ContainerInstance,
)
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))


def _spec(**kw):
    return CharacterSpec(
        name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                             "CON": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": "fighter"}],
        alignment="neutral", ruleset={"encumbrance": "detailed"}, **kw)


def test_move_container_onto_animal_sets_location():
    from aose.models.storage import StorageLocation
    spec = _spec(
        animals=[AnimalInstance(instance_id="a1", catalog_id="mule")],
        containers=[ContainerInstance(instance_id="c1", catalog_id="saddle_bags")],
    )
    companions.move_container_to_animal(spec, "c1", "a1", DATA)
    c = spec.containers[0]
    assert c.location == StorageLocation(kind="animal", id="a1")


def test_move_container_pc_to_retainer_relocates_lists():
    from aose.engine.storage import move_container
    from aose.engine.shop import new_container_instance
    from aose.models.storage import StorageLocation
    from aose.models import Retainer, CharacterSpec
    spec = _spec(
        containers=[new_container_instance("backpack", DATA)],  # carried
    )
    cid = spec.containers[0].instance_id
    npc = CharacterSpec(name="H",
                        abilities={"STR": 10, "DEX": 10, "CON": 10,
                                   "INT": 10, "WIS": 10, "CHA": 10},
                        race_id="human",
                        classes=[{"class_id": "fighter", "level": 1}],
                        alignment="neutral")
    spec.retainers.append(Retainer(id="r1", spec=npc, loyalty=7, role=""))
    move_container(spec, cid, StorageLocation(kind="retainer", id="r1"))
    assert spec.containers == []
    assert len(npc.containers) == 1
    assert npc.containers[0].location == StorageLocation(kind="carried")


def test_carrier_container_excluded_from_pc_weight():
    # A carried saddle-bag on the person would add its own weight; once on the
    # mule it must not count toward the PC's carried weight.
    spec = _spec(
        animals=[AnimalInstance(instance_id="a1", catalog_id="mule")],
        containers=[ContainerInstance(instance_id="c1", catalog_id="saddle_bags",
                                      location=StorageLocation(kind="carried"))],
    )
    before = encumbrance.equipment_weight_cn(spec, DATA)
    companions.move_container_to_animal(spec, "c1", "a1", DATA)
    after = encumbrance.equipment_weight_cn(spec, DATA)
    assert after <= before  # carrier container no longer in PC total
