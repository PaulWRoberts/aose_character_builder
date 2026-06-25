"""HTTP route tests for magic/enchanted equip forms and equipped-item move.

Covers three reported bugs:
  1. The equip-magic / equip-enchanted (and remove-*) forms doubled the
     ``equipment/`` URL segment → 404.
  2. Equipping an enchanted item bypassed class weapon/armour allowances.
  3. An equipped item's Move control offered the PC's own carried bucket.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character
from aose.models import (
    CharacterSpec,
    ClassEntry,
    EnchantedInstance,
    MagicItemInstance,
)
from aose.web.app import create_app

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    app = create_app(
        data_dir=DATA_DIR, characters_dir=characters_dir, drafts_dir=drafts_dir,
        examples_dir=examples_dir, settings_path=tmp_path / "settings.json",
    )
    c = TestClient(app, follow_redirects=False)
    c._characters_dir = characters_dir
    return c


def _save(client, *, class_id="fighter", inventory=None, equipped=None,
          enchanted=None, magic_items=None):
    spec = CharacterSpec(
        name="Christopher",
        abilities={"STR": 12, "INT": 12, "WIS": 12, "DEX": 12, "CON": 12, "CHA": 12},
        race_id="human",
        classes=[ClassEntry(class_id=class_id, level=1, hp_rolls=[8])],
        alignment="neutral",
        inventory=inventory or [],
        equipped=equipped or {},
        enchanted=enchanted or [],
        magic_items=magic_items or [],
    )
    save_character("christopher", spec, client._characters_dir)
    return spec


def _load(client):
    return load_character("christopher", client._characters_dir)


# ── Bug 1: form action URLs must not double the "equipment/" segment ────────

def test_equip_forms_do_not_double_equipment_segment(client):
    _save(
        client,
        enchanted=[EnchantedInstance(instance_id="e1", base_id="sword",
                                     enchantment_id="generic_plus_1")],
        magic_items=[MagicItemInstance(
            instance_id="m1", catalog_id="amulet_of_protection_against_possession")],
    )
    r = client.get("/character/christopher")
    assert r.status_code == 200
    assert "/equipment/equipment/" not in r.text


def test_equip_enchanted_route_exists(client):
    """The route the modal posts to must resolve (not 404)."""
    _save(
        client,
        enchanted=[EnchantedInstance(instance_id="e1", base_id="sword",
                                     enchantment_id="generic_plus_1")],
    )
    r = client.post("/character/christopher/equipment/equip-enchanted",
                    data={"instance_id": "e1"})
    assert r.status_code == 303


# ── Bug 2: enchanted equip honours class weapon/armour allowances ───────────

def test_equip_enchanted_armor_rejected_for_disallowed_class(client):
    # magic_user cannot wear chain mail; an enchanted chain mail is no different.
    _save(
        client,
        class_id="magic_user",
        enchanted=[EnchantedInstance(instance_id="e1", base_id="chain_mail",
                                     enchantment_id="armour_plus_1")],
    )
    r = client.post("/character/christopher/equipment/equip-enchanted",
                    data={"instance_id": "e1"})
    assert r.status_code == 400
    spec = _load(client)
    assert spec.enchanted[0].equipped is False


def test_equip_enchanted_weapon_rejected_for_disallowed_class(client):
    # magic_user cannot wield a sword, enchanted or not.
    _save(
        client,
        class_id="magic_user",
        enchanted=[EnchantedInstance(instance_id="e1", base_id="sword",
                                     enchantment_id="generic_plus_1")],
    )
    r = client.post("/character/christopher/equipment/equip-enchanted",
                    data={"instance_id": "e1"})
    assert r.status_code == 400
    assert _load(client).equipped.get("main_hand") != "e1"


def test_equip_enchanted_armor_allowed_for_fighter(client):
    _save(
        client,
        class_id="fighter",
        enchanted=[EnchantedInstance(instance_id="e1", base_id="chain_mail",
                                     enchantment_id="armour_plus_1")],
    )
    r = client.post("/character/christopher/equipment/equip-enchanted",
                    data={"instance_id": "e1"})
    assert r.status_code == 303
    assert _load(client).enchanted[0].equipped is True


# ── Bug 3: an equipped item must not offer its own carried bucket ───────────

def _ench_modal(html, instance_id):
    start = html.index(f'id="modal-magic-{instance_id}"')
    nxt = html.find('class="overlay modal"', start + 1)
    return html[start:nxt if nxt != -1 else len(html)]


def test_enchanted_armor_modal_hides_equip_when_disallowed(client):
    _save(
        client,
        class_id="magic_user",
        enchanted=[EnchantedInstance(instance_id="e1", base_id="chain_mail",
                                     enchantment_id="armour_plus_1")],
    )
    r = client.get("/character/christopher")
    modal = _ench_modal(r.text, "e1")
    assert "Not usable" in modal
    assert "/equip-enchanted" not in modal


def test_enchanted_weapon_modal_hides_equip_when_disallowed(client):
    _save(
        client,
        class_id="magic_user",
        enchanted=[EnchantedInstance(instance_id="e1", base_id="sword",
                                     enchantment_id="generic_plus_1")],
    )
    r = client.get("/character/christopher")
    modal = _ench_modal(r.text, "e1")
    assert "Not usable" in modal
    assert "/equip-enchanted" not in modal


def test_enchanted_armor_modal_shows_equip_when_allowed(client):
    _save(
        client,
        class_id="fighter",
        enchanted=[EnchantedInstance(instance_id="e1", base_id="chain_mail",
                                     enchantment_id="armour_plus_1")],
    )
    r = client.get("/character/christopher")
    modal = _ench_modal(r.text, "e1")
    assert "/equip-enchanted" in modal
    assert "Not usable" not in modal


def test_equipped_item_move_excludes_own_carried_bucket(client):
    _save(
        client,
        class_id="fighter",
        inventory=["war_hammer"],
        equipped={"main_hand": "war_hammer"},
    )
    r = client.get("/character/christopher")
    assert r.status_code == 200
    # Slice out just the equipped item's modal.
    start = r.text.index('id="modal-item-equipped-war_hammer"')
    nxt = r.text.find('class="overlay modal"', start + 1)
    modal = r.text[start:nxt if nxt != -1 else len(r.text)]
    assert "Move to" in modal                      # the Move control rendered
    assert 'data-kind="carried"' not in modal      # but not the PC's own bucket
