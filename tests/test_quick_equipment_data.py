from pathlib import Path
from aose.data.loader import GameData
from aose.models import Weapon, Armor, AdventuringGear, Ammunition, Container

DATA = GameData.load(Path("data"))
QE = DATA.quick_equipment


def _grant_ids(tables):
    for rows in tables.values():
        for row in rows:
            for grant in row:
                if "id" in grant:
                    yield grant["id"]
                if "armor" in grant:
                    yield grant["armor"]
                if "ammo" in grant:
                    yield grant["ammo"]


def test_tables_reference_real_items():
    for item_id in _grant_ids(QE["tables"]):
        assert item_id in DATA.items, f"unknown item {item_id}"


def test_class_keys_are_real_classes():
    for class_id in QE["classes"]:
        assert class_id in DATA.classes, f"unknown class {class_id}"


def test_class_extras_and_tables_resolve():
    for class_id, kit in QE["classes"].items():
        for extra in kit.get("extras", []):
            assert extra in DATA.items, f"{class_id} extra {extra} missing"
        w = kit["weapons"]
        if "table" in w:
            assert w["table"] in QE["tables"], f"{class_id} table {w['table']}"
        if "fixed" in w:
            for wid in w["fixed"]:
                assert wid in DATA.items


def test_sprig_of_mistletoe_added():
    assert "sprig_of_mistletoe" in DATA.items


def test_apply_kit_routes_containers_to_instances():
    from aose.engine.quick_equipment import QuickKit, apply_kit
    from aose.models import CharacterSpec, Container
    spec = CharacterSpec(name="K",
                         abilities={"STR": 10, "DEX": 10, "CON": 10,
                                    "INT": 10, "WIS": 10, "CHA": 10},
                         race_id="human",
                         classes=[{"class_id": "fighter", "level": 1}],
                         alignment="neutral")
    kit = QuickKit(inventory=["backpack", "torch", "torch"])
    apply_kit(spec, kit, DATA)
    assert "backpack" not in spec.inventory            # promoted out of loose
    assert spec.inventory.count("torch") == 2          # non-containers stay
    assert [c.catalog_id for c in spec.containers] == ["backpack"]
    assert isinstance(DATA.items["backpack"], Container)  # guard the fixture id
