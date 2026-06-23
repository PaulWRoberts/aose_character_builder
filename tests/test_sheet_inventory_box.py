from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.models import (AnimalInstance, CharacterSpec, ClassEntry, CoinStack,
                         ContainerInstance, Retainer)
from aose.models.storage import StorageLocation
from aose.web.app import create_app

DATA_DIR = Path(__file__).parent.parent / "data"


def _make_app(tmp_path):
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    return create_app(
        data_dir=DATA_DIR,
        characters_dir=tmp_path / "characters",
        drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir,
        settings_path=tmp_path / "settings.json",
    )


def _spec():
    npc = CharacterSpec(
        name="Hireling",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[5])],
        alignment="neutral", inventory=["dagger"], equipped={"main_hand": "dagger"},
    )
    return CharacterSpec(
        name="Boxtest",
        abilities={"STR": 13, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        inventory=["torch", "sword"], equipped={"main_hand": "sword"},
        coins=[CoinStack(denom="gp", count=5,
                         location=StorageLocation(kind="animal", id="a1"))],
        animals=[AnimalInstance(instance_id="a1", catalog_id="mule")],
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      contents=["torch"],
                                      location=StorageLocation(kind="animal", id="a1"))],
        retainers=[Retainer(id="r1", spec=npc, loyalty=7)],
        other_possessions=["bronze key"],
    )


def test_inventory_box_renders_all_panes(tmp_path):
    from aose.characters import save_character
    app = _make_app(tmp_path)
    save_character("tc-inv", _spec(), tmp_path / "characters")
    body = TestClient(app, follow_redirects=False).get("/character/tc-inv").text

    assert "Other Possessions" in body
    assert "bronze key" in body
    # Coins shown on a carrier (the animal)
    assert "5" in body and "gp" in body
    # A move-dest control exists (generalized Move form)
    assert "move-dest" in body
    # Custom item add form lives only inside the Other Possessions pane
    assert body.count('name="text"') >= 1
    # Carried pane is open by default
    assert 'data-pane-kind="carried"' in body
    # Animal pane present
    assert 'data-pane-kind="animal"' in body
    # Retainer pane present
    assert 'data-pane-kind="retainer"' in body


def test_inventory_box_carried_shows_equipped_attacks(tmp_path):
    from aose.characters import save_character
    app = _make_app(tmp_path)
    save_character("tc-inv2", _spec(), tmp_path / "characters")
    body = TestClient(app, follow_redirects=False).get("/character/tc-inv2").text
    # Carried pane shows weapon attack row (sword equipped main hand)
    assert "Sword" in body or "sword" in body
    # Attack stats present (+N · dmg)
    assert "·" in body


def test_inventory_box_container_content_modal_exists(tmp_path):
    from aose.characters import save_character
    app = _make_app(tmp_path)
    save_character("tc-inv3", _spec(), tmp_path / "characters")
    body = TestClient(app, follow_redirects=False).get("/character/tc-inv3").text
    # Container content modal exists (torch inside container c1 on animal a1)
    assert 'id="modal-item-container-c1-torch"' in body


def test_toplevelgroup_has_caps_and_extra_collections():
    from aose.engine.shop import TopLevelGroup, OwnerCaps
    g = TopLevelGroup(kind="vehicle", label="Cart",
                      caps=OwnerCaps(has_equipped=False, can_wield=False,
                                     can_stash=False, bucket_label="Stowed"))
    assert g.caps.bucket_label == "Stowed"
    assert g.magic_items == [] and g.enchanted == []
    assert g.spell_sources == [] and g.ammo == []


def test_carried_caps_and_label_is_character_name():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.sheet.view import build_inventory_groups
    data = GameData.load(Path("data"))
    spec = CharacterSpec(
        name="Aldric",
        abilities={"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="neutral",
    )
    groups = build_inventory_groups(spec, data)
    carried = next(g for g in groups if g.kind == "carried")
    stashed = next(g for g in groups if g.kind == "stashed")
    assert carried.caps.has_equipped
    assert carried.caps.can_wield
    assert carried.caps.bucket_label == "Carried"
    assert carried.label == "Aldric"          # PC pane titled by character name
    assert not stashed.caps.can_wield
    assert stashed.caps.bucket_label == "Stowed"


def test_vehicle_group_stowed_animal_carried():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.sheet.view import build_inventory_groups
    from aose.models import AnimalInstance, VehicleInstance
    data = GameData.load(Path("data"))
    spec = CharacterSpec(
        name="Traveler",
        abilities={"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="neutral",
        animals=[AnimalInstance(instance_id="a1", catalog_id="mule")],
        vehicles=[VehicleInstance(instance_id="v1", catalog_id="cart", hull_max=10)],
    )
    groups = build_inventory_groups(spec, data)
    veh = next(g for g in groups if g.kind == "vehicle")
    ani = next(g for g in groups if g.kind == "animal")
    assert veh.caps.bucket_label == "Stowed" and not veh.caps.has_equipped
    assert ani.caps.bucket_label == "Carried" and ani.caps.has_equipped


def test_retainer_group_caps_and_containers():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.sheet.view import build_inventory_groups
    from aose.engine.shop import new_container_instance
    data = GameData.load(Path("data"))
    npc = CharacterSpec(
        name="Henchman",
        abilities={"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[5])],
        alignment="neutral",
    )
    npc.containers.append(new_container_instance("backpack", data))
    spec = CharacterSpec(
        name="Boss",
        abilities={"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        retainers=[Retainer(id="r1", spec=npc, loyalty=7)],
    )
    groups = build_inventory_groups(spec, data)
    ret = next(g for g in groups if g.kind == "retainer")
    assert any(c.catalog_id == "backpack" for c in ret.containers)
    assert ret.caps.can_wield
    assert ret.caps.class_filter_equip is False


def test_attack_rows_have_expected_fields():
    """Characterization: attack_profiles returns AttackProfile with required fields."""
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.engine.attacks import attack_profiles
    data = GameData.load(Path("data"))
    spec = CharacterSpec(
        name="Swordsman",
        abilities={"STR": 13, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        inventory=["sword"], equipped={"main_hand": "sword"},
    )
    profiles = attack_profiles(spec, data)
    sword_profiles = [p for p in profiles if p.weapon_id == "sword"]
    assert sword_profiles, "expected sword attack profile"
    p = sword_profiles[0]
    assert hasattr(p, "to_hit_ascending")
    assert hasattr(p, "damage")
    assert hasattr(p, "range_ft")


def test_inventory_box_retainer_item_modal_exists(tmp_path):
    from aose.characters import save_character
    app = _make_app(tmp_path)
    save_character("tc-inv4", _spec(), tmp_path / "characters")
    body = TestClient(app, follow_redirects=False).get("/character/tc-inv4").text
    # Retainer loose-item modal exists (dagger carried by retainer r1)
    assert 'id="modal-item-retainer-r1-dagger"' in body
