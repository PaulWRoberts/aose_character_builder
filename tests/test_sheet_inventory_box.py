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


def test_inventory_box_retainer_item_modal_exists(tmp_path):
    from aose.characters import save_character
    app = _make_app(tmp_path)
    save_character("tc-inv4", _spec(), tmp_path / "characters")
    body = TestClient(app, follow_redirects=False).get("/character/tc-inv4").text
    # Retainer loose-item modal exists (dagger carried by retainer r1)
    assert 'id="modal-item-retainer-r1-dagger"' in body
