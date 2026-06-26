from pathlib import Path
from aose.data.loader import GameData
from aose.characters.migrate_items import migrate_legacy_items
from aose.models import CharacterSpec

DATA = GameData.load(Path("data"))


def _legacy(**kw):
    base = dict(
        name="Old", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
        "CON": 10, "CHA": 10}, race_id="human",
        classes=[{"class_id": "fighter", "level": 1, "hp_rolls": [8]}],
        alignment="neutral",
    )
    base.update(kw); return base


def test_loose_strings_become_instances():
    raw = migrate_legacy_items(_legacy(inventory=["sword", "torch", "torch"]), DATA)
    spec = CharacterSpec(**raw)
    by_cat = {i.catalog_id: i for i in spec.items}
    assert by_cat["sword"].count == 1                 # equippable, per-instance
    assert by_cat["torch"].count == 2                 # stackable, collapsed


def test_equipped_dict_becomes_equip_field():
    raw = migrate_legacy_items(
        _legacy(inventory=["sword"], equipped={"main_hand": "sword"}), DATA)
    spec = CharacterSpec(**raw)
    sword = next(i for i in spec.items if i.catalog_id == "sword")
    assert sword.equip == "main_hand"


def test_two_equipped_copies_become_two_instances():
    raw = migrate_legacy_items(
        _legacy(inventory=["dagger", "dagger"],
                equipped={"main_hand": "dagger", "off_hand": "dagger"}), DATA)
    spec = CharacterSpec(**raw)
    daggers = [i for i in spec.items if i.catalog_id == "dagger"]
    assert len(daggers) == 2
    assert {d.equip for d in daggers} == {"main_hand", "off_hand"}


def test_stashed_and_container_contents_relocate():
    raw = migrate_legacy_items(_legacy(
        inventory=["backpack"], stashed=["rope"],
        containers=[{"instance_id": "c1", "catalog_id": "backpack",
                     "location": {"kind": "carried"}, "contents": ["torch", "torch"]}],
    ), DATA)
    spec = CharacterSpec(**raw)
    locs = {(i.catalog_id, i.location.kind, i.location.id): i for i in spec.items}
    assert ("rope", "stashed", None) in locs
    assert locs[("torch", "container", "c1")].count == 2


def test_loaded_ammo_and_tailored_become_instance_fields():
    raw = migrate_legacy_items(_legacy(
        inventory=["short_bow", "plate_mail"], armor_tailored=False,
        equipped={"main_hand": "short_bow", "armor": "plate_mail"},
        ammo=[{"instance_id": "a1", "base_id": "arrow", "count": 20}],
        loaded_ammo={"short_bow": "a1"},
    ), DATA)
    spec = CharacterSpec(**raw)
    bow = next(i for i in spec.items if i.catalog_id == "short_bow")
    plate = next(i for i in spec.items if i.catalog_id == "plate_mail")
    arrow = next(i for i in spec.items if i.catalog_id == "arrow")
    assert bow.loaded_ammo_id == "a1"
    assert plate.tailored is False
    assert arrow.instance_id == "a1" and arrow.count == 20


def test_enchanted_list_folds_into_items_with_slot():
    raw = migrate_legacy_items(_legacy(
        enchanted=[
            {"instance_id": "e1", "base_id": "sword",
             "enchantment_id": "sword_plus_1", "equipped": False,
             "location": {"kind": "carried"}},
            {"instance_id": "e2", "base_id": "chain_mail",
             "enchantment_id": "armour_plus_1", "equipped": True,
             "location": {"kind": "carried"}},
        ],
        equipped={"main_hand": "e1"},
    ), DATA)
    spec = CharacterSpec(**raw)
    assert not hasattr(spec, "enchanted")
    by_id = {i.instance_id: i for i in spec.items}
    assert by_id["e1"].catalog_id == "sword" and by_id["e1"].enchantment_id == "sword_plus_1"
    assert by_id["e1"].equip == "main_hand"    # reconciled from the equipped dict
    assert by_id["e2"].equip == "armor"        # reconciled from the equipped bool + kind


def test_retainer_items_also_migrated():
    raw = migrate_legacy_items(_legacy(
        retainers=[{"id": "r1", "loyalty": 7, "role": "",
                    "spec": _legacy(name="NPC", inventory=["sword"],
                                    equipped={"main_hand": "sword"})}]), DATA)
    spec = CharacterSpec(**raw)
    npc = spec.retainers[0].spec
    assert npc.items[0].catalog_id == "sword" and npc.items[0].equip == "main_hand"


def test_new_shape_passes_through_untouched():
    raw = migrate_legacy_items(_legacy(
        items=[{"instance_id": "i1", "catalog_id": "sword", "equip": "main_hand"}]), DATA)
    assert raw["items"][0]["catalog_id"] == "sword"
