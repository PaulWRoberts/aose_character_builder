from pathlib import Path
from aose.data.loader import GameData
from aose.engine import storage, equip
from aose.models import CharacterSpec, ClassEntry, ItemInstance, Retainer
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))
CARRIED = StorageLocation(kind="carried")


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw); return CharacterSpec(**base)


def test_equip_on_retainer_then_move_to_pc_unequips_and_no_dupe():
    npc = _spec(name="NPC",
                items=[ItemInstance(instance_id="i1", catalog_id="sword", location=CARRIED)])
    pc = _spec(retainers=[Retainer(id="r1", spec=npc, loyalty=7)])
    # equip on the retainer
    equip.equip(pc.retainers[0].spec, "i1", data=DATA)
    assert equip.equipped_ref(pc.retainers[0].spec, "main_hand") == "sword"
    # move the item from the retainer to the PC's carried bucket
    storage.move_thing(pc, "item", "i1", CARRIED, data=DATA)
    # retainer no longer wields it, and exactly one copy exists in the world
    assert equip.equipped_ref(pc.retainers[0].spec, "main_hand") is None
    swords_on_pc = [i for i in pc.items if i.catalog_id == "sword"]
    swords_on_ret = [i for i in pc.retainers[0].spec.items if i.catalog_id == "sword"]
    assert len(swords_on_pc) == 1 and swords_on_ret == []
    assert swords_on_pc[0].equip is None
