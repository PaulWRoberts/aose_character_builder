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


def _treasure_spec():
    from aose.models import GemStack, JewelleryPiece
    return CharacterSpec(
        name="Croesus",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        inventory=["torch", "sword"], equipped={"main_hand": "sword"},
        coins=[CoinStack(denom="gp", count=12,
                         location=StorageLocation(kind="carried"))],
        gems=[GemStack(instance_id="g1", value=100, count=2, label="ruby",
                       location=StorageLocation(kind="carried"))],
        jewellery=[JewelleryPiece(instance_id="j1", value=800, label="necklace",
                                  location=StorageLocation(kind="carried"))],
    )


def test_coin_row_clickable_and_modal_with_actions(tmp_path):
    from aose.characters import save_character
    app = _make_app(tmp_path)
    save_character("tc-coin", _treasure_spec(), tmp_path / "characters")
    body = TestClient(app, follow_redirects=False).get("/character/tc-coin").text
    # Carried gp stack is clickable and opens a coin modal
    assert 'data-modal="modal-coin-carried--gp"' in body
    assert 'id="modal-coin-carried--gp"' in body
    # Modal carries convert, move, and drop actions
    assert "/coins/convert" in body
    assert "/inventory/move" in body
    assert "/coins/add" in body


def test_gem_row_clickable_and_modal_with_actions(tmp_path):
    from aose.characters import save_character
    app = _make_app(tmp_path)
    save_character("tc-gem", _treasure_spec(), tmp_path / "characters")
    body = TestClient(app, follow_redirects=False).get("/character/tc-gem").text
    assert 'data-modal="modal-gem-g1"' in body
    assert 'id="modal-gem-g1"' in body
    for action in ("/gems/sell", "/gems/sell-all", "/gems/adjust",
                   "/gems/remove", "/inventory/move"):
        assert action in body, action


def test_jewellery_row_clickable_and_modal_with_actions(tmp_path):
    from aose.characters import save_character
    app = _make_app(tmp_path)
    save_character("tc-jewel", _treasure_spec(), tmp_path / "characters")
    body = TestClient(app, follow_redirects=False).get("/character/tc-jewel").text
    assert 'data-modal="modal-jewel-j1"' in body
    assert 'id="modal-jewel-j1"' in body
    for action in ("/jewellery/toggle-damaged", "/jewellery/sell",
                   "/jewellery/remove", "/inventory/move"):
        assert action in body, action


def test_carried_item_modal_has_sell_and_drop(tmp_path):
    from aose.characters import save_character
    app = _make_app(tmp_path)
    save_character("tc-sell", _treasure_spec(), tmp_path / "characters")
    body = TestClient(app, follow_redirects=False).get("/character/tc-sell").text
    # The carried torch modal exposes Sell (half/refund) and Drop
    assert 'id="modal-item-carried-torch"' in body
    assert "half price" in body
    assert "Sell…" in body


def test_drawer_treasure_tab_keeps_add_forms_only(tmp_path):
    from aose.characters import save_character
    app = _make_app(tmp_path)
    save_character("tc-drawer", _treasure_spec(), tmp_path / "characters")
    body = TestClient(app, follow_redirects=False).get("/character/tc-drawer").text
    # The Treasure tab keeps acquisition forms…
    assert "/gems/add" in body
    assert "/jewellery/add" in body
    # …but no longer renders the management table ("sell one" was table-only)
    assert "sell one" not in body


# ── Task 9: stowed pointer-types render inside container block ───────────────

def test_container_view_shows_stowed_coins_and_magic(tmp_path):
    from aose.characters import save_character
    from aose.models import (CharacterSpec, ClassEntry, CoinStack, ContainerInstance,
                             MagicItemInstance)
    from aose.models.storage import StorageLocation
    cont_loc = StorageLocation(kind="container", id="c1")
    spec = CharacterSpec(
        name="Bagman",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        inventory=["backpack"],
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=StorageLocation(kind="carried"))],
        coins=[CoinStack(denom="gp", count=7, location=cont_loc)],
        magic_items=[MagicItemInstance(instance_id="m1",
                                       catalog_id="ring_protection_plus_1",
                                       location=cont_loc)],
    )
    app = _make_app(tmp_path)
    save_character("tc-stow", spec, tmp_path / "characters")
    body = TestClient(app, follow_redirects=False).get("/character/tc-stow").text
    assert "7 gp" in body            # stowed coins render inside the container block
    assert 'id="modal-magic-m1"' in body


# ── Task 10: magic/enchanted/ammo bucket by storage location ─────────────────

# ── Task 14: shared macros — magic Move control + no bare buttons ─────────────

# ── Task 11: spell sources bucket by location ─────────────────────────────────

def test_spell_source_buckets_under_its_location():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.sheet.view import build_inventory_groups
    from aose.models import SpellSource, SpellSourceEntry
    data = GameData.load(Path("data"))
    stashed_loc = StorageLocation(kind="stashed")
    scroll = SpellSource(
        instance_id="sc1", kind="scroll", caster_type="arcane",
        entries=[SpellSourceEntry(spell_id="magic_missile")],
        location=stashed_loc,
    )
    spec = CharacterSpec(
        name="Mage",
        abilities={"STR": 10, "INT": 16, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="magic_user", level=1, hp_rolls=[4])],
        alignment="neutral",
        spell_sources=[scroll],
    )
    groups = build_inventory_groups(spec, data)
    carried = next(g for g in groups if g.kind == "carried")
    stashed = next(g for g in groups if g.kind == "stashed")
    carried_ids = {sv.instance_id for sv in carried.spell_sources}
    stashed_ids = {sv.instance_id for sv in stashed.spell_sources}
    assert "sc1" not in carried_ids, "stashed scroll leaked into carried group"
    assert "sc1" in stashed_ids, "stashed scroll missing from stashed group"


def test_magic_modal_has_move_control(tmp_path):
    from aose.characters import save_character
    from aose.models import CharacterSpec, ClassEntry, MagicItemInstance
    spec = CharacterSpec(
        name="Wiz", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        magic_items=[MagicItemInstance(instance_id="m1", catalog_id="ring_protection_plus_1")],
    )
    app = _make_app(tmp_path)
    save_character("tc-mm", spec, tmp_path / "characters")
    body = TestClient(app, follow_redirects=False).get("/character/tc-mm").text
    assert "/inventory/move" in body
    assert 'value="magic"' in body


def test_no_bare_button_in_inventory_action_rows(tmp_path):
    from aose.characters import save_character
    save_character("tc-bare", _treasure_spec(), tmp_path / "characters")
    app = _make_app(tmp_path)
    body = TestClient(app, follow_redirects=False).get("/character/tc-bare").text
    assert '<button type="submit">Unequip</button>' not in body
    assert '<button type="submit">Equip</button>' not in body


def test_wielded_weapon_not_in_equipped_worn():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.sheet.view import build_inventory_groups
    data = GameData.load(Path("data"))
    spec = CharacterSpec(
        name="W", abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral", inventory=["sword"], equipped={"main_hand": "sword"},
    )
    groups = build_inventory_groups(spec, data)
    pc = next(g for g in groups if g.kind == "carried")
    worn_slots = {e.slot for e in pc.equipped_worn}
    assert "main_hand" not in worn_slots and "off_hand" not in worn_slots
    # the weapon still appears as an attack profile
    assert any(a.name.lower().startswith("sword") for a in pc.equipped_attacks)


def test_magic_on_carrier_buckets_under_carrier():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.sheet.view import build_inventory_groups
    from aose.models import (CharacterSpec, ClassEntry, AnimalInstance,
                             MagicItemInstance)
    from aose.models.storage import StorageLocation
    data = GameData.load(Path("data"))
    mule = StorageLocation(kind="animal", id="mule1")
    spec = CharacterSpec(
        name="Packer",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        animals=[AnimalInstance(instance_id="mule1", catalog_id="mule")],
        magic_items=[MagicItemInstance(instance_id="m1",
                                       catalog_id="ring_protection_plus_1",
                                       location=mule)],
    )
    groups = build_inventory_groups(spec, data)
    carried = next(g for g in groups if g.kind == "carried")
    animal = next(g for g in groups if g.kind == "animal")
    assert all(mi.instance_id != "m1" for mi in carried.magic_items)   # not in PC
    assert any(mi.instance_id == "m1" for mi in animal.magic_items)    # under mule
