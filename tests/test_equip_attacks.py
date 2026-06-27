"""Tests for the equip/unequip flow and the attack-profile engine."""
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character, save_settings
from aose.data.loader import GameData
from aose.engine.attacks import attack_profiles
from aose.engine.equip import equip, unequip
from aose.models import CharacterSpec, ClassEntry, ItemInstance, RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def _make_client(tmp_path, ruleset=None):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True)
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, ruleset or RuleSet())
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._characters_dir = characters_dir
    return client


@pytest.fixture
def client(tmp_path):
    return _make_client(tmp_path)


def _modal_html(body: str, modal_id: str) -> str:
    """Return just the HTML of the overlay whose id is `modal_id`."""
    start = body.index(f'id="{modal_id}"')
    nxt = body.find('class="overlay', start + 10)
    return body[start:nxt if nxt != -1 else len(body)]


def _iid():
    return uuid.uuid4().hex


def _make_item(catalog_id, equip=None, count=1, iid=None, enchantment_id=None):
    return ItemInstance(
        instance_id=iid or _iid(),
        catalog_id=catalog_id,
        equip=equip,
        count=count,
        enchantment_id=enchantment_id,
    )


def _spec(abilities=None, items=None, ruleset=None,
          weapon_proficiencies=None, weapon_specialisations=None,
          # Legacy convenience: auto-build items from catalog_ids
          inventory=None, equipped=None):
    """Build a test CharacterSpec.  Either pass ``items`` directly or use
    ``inventory`` (list of catalog_ids) + ``equipped`` (slot→catalog_id dict)
    as a convenience shorthand."""
    if items is None:
        built = []
        eq = dict(equipped or {})
        inv = list(inventory or [])
        for slot, cid in eq.items():
            built.append(_make_item(cid, equip=slot))
            if cid in inv:
                inv.remove(cid)
        for cid in inv:
            built.append(_make_item(cid))
        items = built
    return CharacterSpec(
        name="Thorin",
        abilities=abilities or {"STR": 16, "INT": 10, "WIS": 11, "DEX": 12, "CON": 14, "CHA": 9},
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[7])],
        alignment="law",
        items=items,
        weapon_proficiencies=list(weapon_proficiencies or []),
        weapon_specialisations=list(weapon_specialisations or []),
        ruleset=ruleset or RuleSet(),
    )


def _seed(client, items=None, inventory=None, equipped=None, **kwargs) -> tuple[str, CharacterSpec]:
    spec = _spec(items=items, inventory=inventory, equipped=equipped, **kwargs)
    save_character("test", spec, client._characters_dir)
    return "test", spec


# ════════════════════════════════════════════════════════════════════════════
# Engine: equip / unequip (new instance-based API)
# ════════════════════════════════════════════════════════════════════════════

def test_equip_armor_takes_armor_slot(data):
    iid = _iid()
    spec = _spec(items=[_make_item("chain_mail", iid=iid)])
    equip(spec, iid, data=data)
    assert spec.items[0].equip == "armor"


def test_equip_shield_takes_off_hand_slot(data):
    iid = _iid()
    spec = _spec(items=[_make_item("shield", iid=iid)])
    equip(spec, iid, data=data)
    assert spec.items[0].equip == "off_hand"


def test_equip_armor_replaces_existing_armor(data):
    old_iid = _iid()
    new_iid = _iid()
    spec = _spec(items=[
        _make_item("leather_armor", equip="armor", iid=old_iid),
        _make_item("plate_mail", iid=new_iid),
    ])
    equip(spec, new_iid, data=data)
    assert next(i for i in spec.items if i.instance_id == new_iid).equip == "armor"
    assert next(i for i in spec.items if i.instance_id == old_iid).equip is None


def test_equip_weapon_goes_to_main_hand(data):
    iid = _iid()
    spec = _spec(items=[_make_item("sword", iid=iid)])
    equip(spec, iid, data=data)
    assert spec.items[0].equip == "main_hand"


def test_equip_second_dagger_goes_to_off_hand_with_two_weapon(data):
    iid1 = _iid()
    iid2 = _iid()
    spec = _spec(items=[
        _make_item("dagger", equip="main_hand", iid=iid1),
        _make_item("dagger", iid=iid2),
    ], ruleset=RuleSet(two_weapon_fighting=True))
    equip(spec, iid2, data=data, slot="off_hand",
          two_weapon=True, eligible=True)
    assert next(i for i in spec.items if i.instance_id == iid2).equip == "off_hand"


def test_equip_rejects_unknown_instance(data):
    spec = _spec(items=[_make_item("chain_mail")])
    with pytest.raises(ValueError):
        equip(spec, "no-such-id", data=data)


def test_equip_rejects_unequippable(data):
    iid = _iid()
    spec = _spec(items=[_make_item("torch", iid=iid)])
    with pytest.raises(ValueError, match="not equippable"):
        equip(spec, iid, data=data)


def test_unequip_armor(data):
    iid = _iid()
    spec = _spec(items=[_make_item("chain_mail", equip="armor", iid=iid)])
    unequip(spec, iid)
    assert spec.items[0].equip is None


def test_unequip_weapon_from_main_hand(data):
    iid = _iid()
    spec = _spec(items=[_make_item("dagger", equip="main_hand", iid=iid)])
    unequip(spec, iid)
    assert spec.items[0].equip is None


def test_unequip_unowned_raises(data):
    spec = _spec(items=[])
    with pytest.raises(ValueError, match="not equipped"):
        unequip(spec, "no-such-id")




# ════════════════════════════════════════════════════════════════════════════
# Attack profiles
# ════════════════════════════════════════════════════════════════════════════

def test_no_weapons_yields_empty_profile_list(data):
    profiles = attack_profiles(_spec(), data)
    weapons = [p for p in profiles if not p.unarmed]
    assert weapons == []
    assert len(profiles) == 1
    assert profiles[0].unarmed is True


def test_melee_weapon_adds_str_mod_to_to_hit_and_damage(data):
    all_profiles = attack_profiles(
        _spec(inventory=["sword"], equipped={"main_hand": "sword"}), data)
    weapons = [p for p in all_profiles if not p.unarmed]
    assert len(weapons) == 1
    p = weapons[0]
    assert p.name == "Sword"
    assert p.melee is True
    assert p.to_hit_thac0 == 17
    assert p.to_hit_ascending == 2
    assert "1d6" in p.damage
    assert p.damage.endswith("+2")


def test_ranged_weapon_uses_dex_mod_for_to_hit_only(data):
    all_profiles = attack_profiles(
        _spec(inventory=["short_bow"], equipped={"main_hand": "short_bow"}), data)
    weapons = [p for p in all_profiles if not p.unarmed]
    p = weapons[0]
    assert p.melee is False
    assert p.ranged is True
    assert p.to_hit_thac0 == 19
    assert p.damage == "1d6"
    assert p.range_ft == (50, 100, 150)


def test_ranged_weapon_with_high_dex(data):
    abilities = {"STR": 10, "INT": 10, "WIS": 10, "DEX": 18, "CON": 10, "CHA": 10}
    all_profiles = attack_profiles(
        _spec(abilities=abilities, inventory=["short_bow"], equipped={"main_hand": "short_bow"}),
        data)
    bow = next(p for p in all_profiles if p.weapon_id == "short_bow")
    assert bow.to_hit_thac0 == 16
    assert bow.to_hit_ascending == 3


def test_variable_damage_rule_swaps_damage_die(data):
    all_profiles = attack_profiles(
        _spec(inventory=["sword"], equipped={"main_hand": "sword"},
              ruleset=RuleSet(variable_weapon_damage=True)), data)
    sword = next(p for p in all_profiles if p.weapon_id == "sword")
    assert sword.damage == "1d8+2"


def test_non_proficiency_applies_martial_penalty(data):
    all_profiles = attack_profiles(
        _spec(inventory=["sword"], equipped={"main_hand": "sword"},
              ruleset=RuleSet(weapon_proficiency=True),
              weapon_proficiencies=["hand_axe"]), data)
    sword = next(p for p in all_profiles if p.weapon_id == "sword")
    assert sword.proficient is False
    assert sword.to_hit_thac0 == 19


def test_proficient_user_takes_no_penalty(data):
    all_profiles = attack_profiles(
        _spec(inventory=["sword"], equipped={"main_hand": "sword"},
              ruleset=RuleSet(weapon_proficiency=True),
              weapon_proficiencies=["sword"]), data)
    sword = next(p for p in all_profiles if p.weapon_id == "sword")
    assert sword.proficient is True
    assert sword.to_hit_thac0 == 17


def test_specialisation_adds_plus_one_to_hit_and_damage(data):
    all_profiles = attack_profiles(
        _spec(inventory=["sword"], equipped={"main_hand": "sword"},
              ruleset=RuleSet(weapon_proficiency=True, variable_weapon_damage=True),
              weapon_proficiencies=["sword"],
              weapon_specialisations=["sword"]), data)
    sword = next(p for p in all_profiles if p.weapon_id == "sword")
    assert sword.specialised is True
    assert sword.to_hit_thac0 == 16
    assert sword.damage == "1d8+3"


def test_two_hand_slots_produce_two_profiles(data):
    all_profiles = attack_profiles(
        _spec(inventory=["dagger", "dagger"],
              equipped={"main_hand": "dagger", "off_hand": "dagger"}), data)
    weapons = [p for p in all_profiles if not p.unarmed]
    assert len(weapons) == 2
    assert all(w.name == "Dagger" for w in weapons)


# ════════════════════════════════════════════════════════════════════════════
# HTTP routes (sheet)
# ════════════════════════════════════════════════════════════════════════════

def test_sheet_equip_armor_updates_ac(client):
    iid = _iid()
    _seed(client, items=[_make_item("chain_mail", iid=iid)])
    spec_before = load_character("test", client._characters_dir)
    assert all(i.equip != "armor" for i in spec_before.items)

    r = client.post("/character/test/equipment/equip",
                    data={"instance_id": iid})
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert any(i.equip == "armor" and i.catalog_id == "chain_mail" for i in spec.items)

    r = client.get("/character/test")
    assert "Chain Mail" in r.text


def test_sheet_unequip_armor(client):
    iid = _iid()
    _seed(client, items=[_make_item("chain_mail", equip="armor", iid=iid)])
    r = client.post("/character/test/equipment/unequip", data={"instance_id": iid})
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert all(i.equip != "armor" for i in spec.items)


def test_sheet_equip_weapon_appends(client):
    iid = _iid()
    _seed(client, items=[_make_item("sword", iid=iid)])
    r = client.post("/character/test/equipment/equip", data={"instance_id": iid})
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert any(i.equip == "main_hand" and i.catalog_id == "sword" for i in spec.items)


def test_sheet_attack_profiles_appear_when_weapon_equipped(client):
    iid = _iid()
    _seed(client, items=[_make_item("sword", equip="main_hand", iid=iid)])
    r = client.get("/character/test")
    assert "Attacks" in r.text
    assert "Sword" in r.text
    assert "17" in r.text


def test_sheet_shows_unarmed_when_no_weapons_equipped(client):
    _seed(client, items=[_make_item("sword")])
    r = client.get("/character/test")
    assert "Unarmed" in r.text


def test_sheet_inventory_shows_equipped_section(client):
    iid = _iid()
    _seed(client, items=[_make_item("sword", equip="main_hand", iid=iid)])
    r = client.get("/character/test")
    assert "Equipped" in r.text
    assert 'action="/character/test/inventory/unequip"' in r.text


def test_sheet_equip_rejects_unknown_instance(client):
    _seed(client, items=[])
    r = client.post("/character/test/equipment/equip",
                    data={"instance_id": "no-such-id"})
    assert r.status_code == 400


def test_sheet_equip_rejects_non_equippable(client):
    iid = _iid()
    _seed(client, items=[_make_item("torch", iid=iid)])
    r = client.post("/character/test/equipment/equip", data={"instance_id": iid})
    assert r.status_code == 400


def test_sheet_unequip_rejects_unequipped(client):
    iid = _iid()
    _seed(client, items=[_make_item("sword", iid=iid)])  # not equipped
    r = client.post("/character/test/equipment/unequip", data={"instance_id": iid})
    assert r.status_code == 400


# ════════════════════════════════════════════════════════════════════════════
# AC integration: equipping shield + armor stacks
# ════════════════════════════════════════════════════════════════════════════

def test_ac_drops_with_armor_and_shield(client):
    _seed(client, items=[
        _make_item("chain_mail", equip="armor"),
        _make_item("shield", equip="off_hand"),
    ])
    r = client.get("/character/test")
    assert "Armour Class" in r.text
    idx = r.text.index("Armour Class")
    snippet = r.text[idx:idx + 400]
    assert "4" in snippet


# ════════════════════════════════════════════════════════════════════════════
# Wizard equipment step: equip/unequip work mid-flow
# ════════════════════════════════════════════════════════════════════════════

def test_wizard_equip_and_unequip(tmp_path):
    """Walk a draft to /equipment and exercise equip/unequip endpoints."""
    from aose.characters import load_draft, save_draft
    client = _make_client(tmp_path)
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    client.post(f"/wizard/{draft_id}/rules", data={
        "ability_roll_method": "3d6_in_order", "encumbrance": "basic",
        "separate_race_class": "on",
        "demihuman_level_limits": "on",
        "demihuman_class_restrictions": "on",
    })
    draft = load_draft(draft_id, tmp_path / "drafts")
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, tmp_path / "drafts")
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.post(f"/wizard/{draft_id}/identity", data={"name": "Tester", "alignment": "law"})
    client.get(f"/wizard/{draft_id}/equipment")

    draft = load_draft(draft_id, tmp_path / "drafts")
    draft["gold"] = 200
    save_draft(draft_id, draft, tmp_path / "drafts")
    client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "sword"})

    # Get the instance_id for the sword
    draft = load_draft(draft_id, tmp_path / "drafts")
    sword_items = [i for i in draft.get("items", []) if i.get("catalog_id") == "sword"]
    assert sword_items, "sword should be in draft items after buy"
    sword_iid = sword_items[0]["instance_id"]

    # Equip it by instance_id
    r = client.post(f"/wizard/{draft_id}/equipment/equip",
                    data={"instance_id": sword_iid})
    assert r.status_code == 303
    draft = load_draft(draft_id, tmp_path / "drafts")
    equipped_inst = next((i for i in draft.get("items", [])
                         if i.get("instance_id") == sword_iid), None)
    assert equipped_inst and equipped_inst.get("equip") == "main_hand"

    # Unequip it
    r = client.post(f"/wizard/{draft_id}/equipment/unequip",
                    data={"instance_id": sword_iid})
    draft = load_draft(draft_id, tmp_path / "drafts")
    equipped_inst = next((i for i in draft.get("items", [])
                         if i.get("instance_id") == sword_iid), None)
    assert equipped_inst and equipped_inst.get("equip") is None

    # Re-equip and finalize
    client.post(f"/wizard/{draft_id}/equipment/equip",
                data={"instance_id": sword_iid})
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    spec = load_character(char_id, tmp_path / "characters")
    assert any(i.equip == "main_hand" and i.catalog_id == "sword" for i in spec.items)


def test_plain_equipped_weapon_has_manageable_item_id(data):
    iid = _iid()
    spec = _spec(items=[_make_item("sword", equip="main_hand", iid=iid)])
    profiles = attack_profiles(spec, data)
    sword = next(p for p in profiles if p.weapon_id == "sword")
    assert sword.manageable_item_id == iid
    unarmed = next(p for p in profiles if p.unarmed)
    assert unarmed.manageable_item_id is None


def test_equipped_row_carries_item_id(data):
    from aose.sheet.view import _equipped
    iid = _iid()
    spec = _spec(items=[_make_item("plate_mail", equip="armor", iid=iid)])
    rows = _equipped(spec, data)
    assert rows[0].item_id == iid


def test_sheet_carried_and_stashed_items_are_clickable(tmp_path, data):
    from aose.models.storage import StorageLocation
    client = _make_client(tmp_path)
    rope_iid = _iid()
    torch_iid = _iid()
    spec = CharacterSpec(
        name="Packrat",
        abilities={"STR": 11, "INT": 10, "WIS": 10, "DEX": 11, "CON": 12, "CHA": 9},
        race_id="human", alignment="neutral",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        items=[
            ItemInstance(instance_id=rope_iid, catalog_id="rope_50ft"),
            ItemInstance(instance_id=torch_iid, catalog_id="torch",
                         location=StorageLocation(kind="stashed")),
        ],
    )
    save_character("packrat", spec, client._characters_dir)
    body = client.get("/character/packrat").text

    assert f'data-modal="modal-item-carried-{rope_iid}"' in body
    assert f'id="modal-item-carried-{rope_iid}"' in body
    assert f'data-modal="modal-item-stashed-{torch_iid}"' in body
    assert f'id="modal-item-stashed-{torch_iid}"' in body
    assert "/character/packrat/inventory/move" in body
    assert 'value="stashed"' in body


def test_sheet_equipped_items_are_clickable(tmp_path, data):
    client = _make_client(tmp_path)
    sword_iid = _iid()
    armor_iid = _iid()
    spec = CharacterSpec(
        name="Sir Click",
        abilities={"STR": 13, "INT": 10, "WIS": 10, "DEX": 11, "CON": 12, "CHA": 9},
        race_id="human", alignment="neutral",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        items=[
            ItemInstance(instance_id=sword_iid, catalog_id="sword", equip="main_hand"),
            ItemInstance(instance_id=armor_iid, catalog_id="plate_mail", equip="armor"),
        ],
    )
    save_character("sir-click", spec, client._characters_dir)
    body = client.get("/character/sir-click").text

    assert f'data-modal="modal-item-equipped-{sword_iid}"' in body
    assert f'id="modal-item-equipped-{sword_iid}"' in body
    assert f'data-modal="modal-item-equipped-{armor_iid}"' in body
    assert f'id="modal-item-equipped-{armor_iid}"' in body
    assert "/character/sir-click/inventory/unequip" in body
    assert 'data-modal="modal-item-equipped-unarmed"' not in body


def test_sheet_item_modal_shows_properties_and_no_destructive_actions(tmp_path, data):
    client = _make_client(tmp_path)
    sword_iid = _iid()
    spec = CharacterSpec(
        name="Modal",
        abilities={"STR": 11, "INT": 10, "WIS": 10, "DEX": 11, "CON": 12, "CHA": 9},
        race_id="human", alignment="neutral",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        items=[ItemInstance(instance_id=sword_iid, catalog_id="sword", equip="main_hand")],
    )
    save_character("modal", spec, client._characters_dir)
    body = client.get("/character/modal").text

    modal = _modal_html(body, f"modal-item-equipped-{sword_iid}")
    assert "Damage" in modal
    assert "Weight" in modal
    assert "/character/modal/inventory/unequip" in modal
    assert 'value="drop"' not in modal
    assert 'value="sell"' not in modal
    assert 'value="refund"' not in modal


def test_equipped_launcher_modal_has_load_control(tmp_path, data):
    from aose.models.storage import StorageLocation
    client = _make_client(tmp_path)
    bow_iid = _iid()
    ammo_iid = _iid()
    spec = CharacterSpec(
        name="Archer",
        abilities={"STR": 11, "INT": 10, "WIS": 10, "DEX": 13, "CON": 12, "CHA": 9},
        race_id="human", alignment="neutral",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        items=[
            ItemInstance(instance_id=bow_iid, catalog_id="short_bow", equip="main_hand"),
            ItemInstance(instance_id=ammo_iid, catalog_id="arrow", count=20),
        ],
    )
    save_character("archer", spec, client._characters_dir)
    body = client.get("/character/archer").text

    modal = _modal_html(body, f"modal-item-equipped-{bow_iid}")
    assert "/character/archer/ammo/load" in modal
    assert f'value="{ammo_iid}"' in modal
    assert "/character/archer/ammo/unload" in modal


# ════════════════════════════════════════════════════════════════════════════
# Task 6: Two-weapon penalties + versatile-variant suppression
# ════════════════════════════════════════════════════════════════════════════

def test_dual_wield_applies_minus_2_and_minus_4(data):
    spec = _spec(inventory=["sword", "dagger"],
                 equipped={"main_hand": "sword", "off_hand": "dagger"},
                 ruleset=RuleSet(two_weapon_fighting=True))
    profs = {p.name: p for p in attack_profiles(spec, data)}
    sword = profs["Sword"]
    dagger = profs["Dagger"]
    solo = _spec(inventory=["sword"], equipped={"main_hand": "sword"})
    sword_solo = {p.name: p for p in attack_profiles(solo, data)}["Sword"]
    assert sword.to_hit_ascending == sword_solo.to_hit_ascending - 2
    assert sword.hand == "main"
    assert dagger.hand == "off"
    assert dagger.to_hit_ascending == sword.to_hit_ascending - 2


def test_no_penalty_without_dual_wield(data):
    spec = _spec(inventory=["sword", "shield"],
                 equipped={"main_hand": "sword", "off_hand": "shield"})
    sword = {p.name: p for p in attack_profiles(spec, data)}["Sword"]
    solo = _spec(inventory=["sword"], equipped={"main_hand": "sword"})
    sword_solo = {p.name: p for p in attack_profiles(solo, data)}["Sword"]
    assert sword.to_hit_ascending == sword_solo.to_hit_ascending
    assert sword.hand is None


def test_versatile_two_handed_variant_suppressed_with_off_hand_occupied(data):
    spec = _spec(inventory=["bastard_sword", "shield"],
                 equipped={"main_hand": "bastard_sword", "off_hand": "shield"},
                 ruleset=RuleSet(variable_weapon_damage=True))
    names = [p.name for p in attack_profiles(spec, data)]
    assert "Bastard Sword (Two-handed)" not in names


def test_versatile_two_handed_variant_present_when_off_hand_free(data):
    spec = _spec(inventory=["bastard_sword"], equipped={"main_hand": "bastard_sword"},
                 ruleset=RuleSet(variable_weapon_damage=True))
    names = [p.name for p in attack_profiles(spec, data)]
    assert "Bastard Sword (Two-handed)" in names
