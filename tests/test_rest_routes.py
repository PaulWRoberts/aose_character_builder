"""HTTP route tests for HP, spell-slot, and rest play-state actions."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character
from aose.models import CharacterSpec, ClassEntry, RuleSet, SpellSlot
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


def _save_fighter(client, damage_taken=0):
    spec = CharacterSpec(
        name="Bran",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[12])],
        alignment="neutral", damage_taken=damage_taken,
    )
    save_character("bran", spec, client._characters_dir)
    return spec


def _save_mu(client, spellbook=None, slots=None):
    spec = CharacterSpec(
        name="Mu",
        abilities={"STR": 10, "INT": 13, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="magic_user", level=1, hp_rolls=[12],
                            spellbook=spellbook or [], slots=slots or [])],
        alignment="neutral",
    )
    save_character("mu", spec, client._characters_dir)
    return spec


def test_hp_damage_route(client):
    _save_fighter(client)
    r = client.post("/character/bran/hp/damage", data={"amount": 5})
    assert r.status_code == 303
    assert load_character("bran", client._characters_dir).damage_taken == 5


def test_hp_heal_route(client):
    _save_fighter(client, damage_taken=5)
    client.post("/character/bran/hp/heal", data={"amount": 3})
    assert load_character("bran", client._characters_dir).damage_taken == 2


def test_hp_set_route_clamps(client):
    _save_fighter(client, damage_taken=4)
    client.post("/character/bran/hp/set", data={"value": 99})
    assert load_character("bran", client._characters_dir).damage_taken == 0


def test_hp_damage_negative_400(client):
    _save_fighter(client)
    r = client.post("/character/bran/hp/damage", data={"amount": -2})
    assert r.status_code == 400


def test_assign_then_cast_and_restore(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"])
    r = client.post("/character/mu/spells/assign",
                    data={"class_id": "magic_user", "level": 1,
                          "spell_id": "magic_user_magic_missile", "reversed": "false"})
    assert r.status_code == 303
    spec = load_character("mu", client._characters_dir)
    assert len(spec.classes[0].slots) == 1 and spec.classes[0].slots[0].spent is False

    client.post("/character/mu/spells/cast",
                data={"class_id": "magic_user", "slot_index": 0})
    assert load_character("mu", client._characters_dir).classes[0].slots[0].spent is True

    client.post("/character/mu/spells/restore",
                data={"class_id": "magic_user", "slot_index": 0})
    assert load_character("mu", client._characters_dir).classes[0].slots[0].spent is False


def test_assign_over_cap_400(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"],
             slots=[SpellSlot(level=1, spell_id="magic_user_magic_missile")])
    r = client.post("/character/mu/spells/assign",
                    data={"class_id": "magic_user", "level": 1,
                          "spell_id": "magic_user_magic_missile", "reversed": "false"})
    assert r.status_code == 400


def test_clear_slot_route(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"],
             slots=[SpellSlot(level=1, spell_id="magic_user_magic_missile")])
    client.post("/character/mu/spells/clear",
                data={"class_id": "magic_user", "slot_index": 0})
    assert load_character("mu", client._characters_dir).classes[0].slots == []


def test_rest_night_restore_unspends_all(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"],
             slots=[SpellSlot(level=1, spell_id="magic_user_magic_missile", spent=True)])
    r = client.post("/character/mu/rest/night", data={"mode": "restore"})
    assert r.status_code == 303
    assert load_character("mu", client._characters_dir).classes[0].slots[0].spent is False


def test_rest_night_clear_empties_slots(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"],
             slots=[SpellSlot(level=1, spell_id="magic_user_magic_missile", spent=True)])
    client.post("/character/mu/rest/night", data={"mode": "clear"})
    assert load_character("mu", client._characters_dir).classes[0].slots == []


def test_rest_full_day_heals_and_restores(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"],
             slots=[SpellSlot(level=1, spell_id="magic_user_magic_missile", spent=True)])
    spec = load_character("mu", client._characters_dir)
    spec.damage_taken = 5
    save_character("mu", spec, client._characters_dir)
    r = client.post("/character/mu/rest/full-day",
                    data={"mode": "restore", "heal_amount": 3})
    assert r.status_code == 303
    after = load_character("mu", client._characters_dir)
    assert after.damage_taken == 2
    assert after.classes[0].slots[0].spent is False


def test_rest_blocked_when_dead(client):
    _save_fighter(client, damage_taken=12)  # 0/12 → dead
    r = client.post("/character/bran/rest/night", data={"mode": "restore"})
    assert r.status_code == 400
    r = client.post("/character/bran/rest/full-day",
                    data={"mode": "restore", "heal_amount": 2})
    assert r.status_code == 400


def test_sheet_renders_hp_and_status(client):
    _save_fighter(client, damage_taken=5)
    r = client.get("/character/bran")
    assert r.status_code == 200
    assert "7 / 12" in r.text       # current / max
    assert "Alive" in r.text


def test_sheet_renders_dead_status(client):
    _save_fighter(client, damage_taken=12)
    r = client.get("/character/bran")
    assert "Dead" in r.text


def test_sheet_renders_slot_cast_button(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"],
             slots=[SpellSlot(level=1, spell_id="magic_user_magic_missile")])
    r = client.get("/character/mu")
    assert "Magic Missile" in r.text
    assert "/character/mu/spells/cast" in r.text
    assert "/character/mu/rest/night" in r.text


def test_temp_ability_modifier_route_sets(client):
    _save_fighter(client)
    r = client.post("/character/bran/abilities/temp-modifier",
                    data={"ability": "STR", "value": -2})
    assert r.status_code == 303
    from aose.models import Ability
    spec = load_character("bran", client._characters_dir)
    assert spec.temp_ability_modifiers[Ability.STR] == -2


def test_temp_ability_modifier_route_zero_clears(client):
    from aose.models import CharacterSpec, ClassEntry
    from aose.characters import save_character
    spec = CharacterSpec(
        name="Bran",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[12])],
        alignment="neutral",
        temp_ability_modifiers={"STR": -2},
    )
    save_character("bran", spec, client._characters_dir)
    client.post("/character/bran/abilities/temp-modifier",
                data={"ability": "STR", "value": 0})
    reloaded = load_character("bran", client._characters_dir)
    assert reloaded.temp_ability_modifiers == {}
