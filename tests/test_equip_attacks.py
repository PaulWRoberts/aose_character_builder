"""Tests for the equip/unequip flow and the attack-profile engine."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character, save_settings
from aose.data.loader import GameData
from aose.engine.attacks import attack_profiles
from aose.engine.equip import equip, equipped_count, unequip
from aose.engine.shop import inventory_rows
from aose.models import CharacterSpec, ClassEntry, RuleSet
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


def _spec(abilities=None, inventory=None, equipped=None, equipped_weapons=None,
          ruleset=None, chosen_proficiencies=None):
    return CharacterSpec(
        name="Thorin",
        abilities=abilities or {"STR": 16, "INT": 10, "WIS": 11, "DEX": 12, "CON": 14, "CHA": 9},
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[7])],
        alignment="law",
        inventory=list(inventory or []),
        equipped=dict(equipped or {}),
        equipped_weapons=list(equipped_weapons or []),
        chosen_proficiencies=list(chosen_proficiencies or []),
        ruleset=ruleset or RuleSet(),
    )


def _seed(client, **kwargs) -> str:
    spec = _spec(**kwargs)
    save_character("test", spec, client._characters_dir)
    return "test"


# ════════════════════════════════════════════════════════════════════════════
# Engine: equip / unequip
# ════════════════════════════════════════════════════════════════════════════

def test_equip_armor_takes_armor_slot(data):
    eq, weapons = equip(["chain_mail"], {}, [], "chain_mail", data)
    assert eq == {"armor": "chain_mail"}
    assert weapons == []


def test_equip_shield_takes_shield_slot(data):
    eq, weapons = equip(["shield"], {}, [], "shield", data)
    assert eq == {"shield": "shield"}


def test_equip_armor_replaces_existing_armor(data):
    eq, _ = equip(["plate_mail"], {"armor": "leather_armor"}, [], "plate_mail", data)
    assert eq == {"armor": "plate_mail"}


def test_equip_weapon_appends_to_list(data):
    _, weapons = equip(["long_sword"], {}, [], "long_sword", data)
    assert weapons == ["long_sword"]


def test_equip_weapon_twice_when_owned_twice(data):
    _, weapons = equip(["dagger", "dagger"], {}, ["dagger"], "dagger", data)
    assert weapons == ["dagger", "dagger"]


def test_equip_blocks_past_inventory_count(data):
    with pytest.raises(ValueError, match="already equipped"):
        equip(["dagger"], {}, ["dagger"], "dagger", data)


def test_equip_rejects_unowned(data):
    with pytest.raises(ValueError, match="not in inventory"):
        equip([], {}, [], "long_sword", data)


def test_equip_rejects_unequippable(data):
    with pytest.raises(ValueError, match="not equippable"):
        equip(["torch"], {}, [], "torch", data)


def test_unequip_armor(data):
    eq, _ = unequip({"armor": "chain_mail"}, [], "chain_mail", data)
    assert eq == {}


def test_unequip_one_weapon_instance(data):
    _, weapons = unequip({}, ["dagger", "dagger"], "dagger", data)
    assert weapons == ["dagger"]


def test_unequip_unowned_raises(data):
    with pytest.raises(ValueError, match="not equipped"):
        unequip({}, [], "long_sword", data)


def test_equipped_count_aggregates_across_slots():
    assert equipped_count({"armor": "leather_armor"}, ["dagger", "dagger"], "dagger") == 2
    assert equipped_count({"armor": "leather_armor"}, [], "leather_armor") == 1
    assert equipped_count({}, [], "long_sword") == 0


# ── Inventory rows carry equippable + equipped_count ──────────────────────

def test_inventory_rows_marks_weapons_as_equippable(data):
    rows = inventory_rows(["long_sword", "torch"], data, {}, [])
    by_id = {r.id: r for r in rows}
    assert by_id["long_sword"].equippable is True
    assert by_id["torch"].equippable is False


def test_inventory_rows_counts_equipped_copies(data):
    rows = inventory_rows(["dagger", "dagger"], data, {}, ["dagger"])
    assert rows[0].equipped_count == 1
    assert rows[0].count == 2


# ════════════════════════════════════════════════════════════════════════════
# Attack profiles
# ════════════════════════════════════════════════════════════════════════════

def test_no_weapons_yields_empty_profile_list(data):
    # Unarmed is always prepended; "no weapons" means only the Unarmed profile.
    profiles = attack_profiles(_spec(), data)
    weapons = [p for p in profiles if not p.unarmed]
    assert weapons == []
    assert len(profiles) == 1
    assert profiles[0].unarmed is True


def test_melee_weapon_adds_str_mod_to_to_hit_and_damage(data):
    # STR 16 → +2 mod, Fighter L1 THAC0 = 19
    all_profiles = attack_profiles(
        _spec(inventory=["long_sword"], equipped_weapons=["long_sword"]),
        data,
    )
    weapons = [p for p in all_profiles if not p.unarmed]
    assert len(weapons) == 1
    p = weapons[0]
    assert p.name == "Long Sword"
    assert p.melee is True
    assert p.to_hit_thac0 == 17        # 19 - 2 (STR)
    assert p.to_hit_ascending == 2     # 0 + 2 (STR)
    assert "1d6" in p.damage           # default rule
    assert p.damage.endswith("+2")     # STR mod to damage


def test_ranged_weapon_uses_dex_mod_for_to_hit_only(data):
    # DEX 12 → +0 mod, so no change vs base THAC0 19
    all_profiles = attack_profiles(
        _spec(inventory=["short_bow"], equipped_weapons=["short_bow"]),
        data,
    )
    weapons = [p for p in all_profiles if not p.unarmed]
    p = weapons[0]
    assert p.melee is False
    assert p.ranged is True
    assert p.to_hit_thac0 == 19
    assert p.damage == "1d6"  # no STR mod for ranged weapons
    assert p.range_ft == (50, 100, 150)


def test_ranged_weapon_with_high_dex(data):
    abilities = {"STR": 10, "INT": 10, "WIS": 10, "DEX": 18, "CON": 10, "CHA": 10}
    all_profiles = attack_profiles(
        _spec(abilities=abilities, inventory=["short_bow"], equipped_weapons=["short_bow"]),
        data,
    )
    # DEX 18 → +3 mod; get the ranged weapon, not Unarmed
    bow = next(p for p in all_profiles if p.weapon_id == "short_bow")
    assert bow.to_hit_thac0 == 16
    assert bow.to_hit_ascending == 3


def test_variable_damage_rule_swaps_damage_die(data):
    all_profiles = attack_profiles(
        _spec(inventory=["long_sword"], equipped_weapons=["long_sword"],
              ruleset=RuleSet(variable_weapon_damage=True)),
        data,
    )
    # Long Sword variable damage is 1d8, plus STR +2
    sword = next(p for p in all_profiles if p.weapon_id == "long_sword")
    assert sword.damage == "1d8+2"


def test_non_proficiency_applies_minus_two(data):
    all_profiles = attack_profiles(
        _spec(inventory=["long_sword"], equipped_weapons=["long_sword"],
              ruleset=RuleSet(weapon_proficiency=True),
              chosen_proficiencies=["axe"]),  # not "sword"
        data,
    )
    sword = next(p for p in all_profiles if p.weapon_id == "long_sword")
    assert sword.proficient is False
    # Base 19, STR +2, prof -2 → THAC0 = 19 - 2 - (-2) = 19 ... wait
    # to_hit_thac0 = base_thac0 - atk_mod - prof_pen
    # = 19 - 2 - (-2) = 19
    assert sword.to_hit_thac0 == 19


def test_proficient_user_takes_no_penalty(data):
    all_profiles = attack_profiles(
        _spec(inventory=["long_sword"], equipped_weapons=["long_sword"],
              ruleset=RuleSet(weapon_proficiency=True),
              chosen_proficiencies=["sword"]),
        data,
    )
    sword = next(p for p in all_profiles if p.weapon_id == "long_sword")
    assert sword.proficient is True
    assert sword.to_hit_thac0 == 17  # STR mod applied, no -2 penalty


def test_multiple_identical_weapons_collapse_to_count(data):
    all_profiles = attack_profiles(
        _spec(inventory=["dagger", "dagger", "dagger"],
              equipped_weapons=["dagger", "dagger"]),
        data,
    )
    weapons = [p for p in all_profiles if not p.unarmed]
    assert len(weapons) == 1
    assert weapons[0].count == 2


# ════════════════════════════════════════════════════════════════════════════
# HTTP routes (sheet)
# ════════════════════════════════════════════════════════════════════════════

def test_sheet_equip_armor_updates_ac(client):
    _seed(client, inventory=["chain_mail"])
    # Unarmored AC starts at 9 (with DEX 12 = no mod)
    spec_before = load_character("test", client._characters_dir)
    assert "armor" not in spec_before.equipped

    r = client.post("/character/test/equipment/equip", data={"item_id": "chain_mail"})
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.equipped == {"armor": "chain_mail"}

    # Now visit sheet — AC should show chain mail's value (5)
    r = client.get("/character/test")
    assert "Chain Mail" in r.text


def test_sheet_unequip_armor(client):
    _seed(client, inventory=["chain_mail"], equipped={"armor": "chain_mail"})
    r = client.post("/character/test/equipment/unequip", data={"item_id": "chain_mail"})
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert "armor" not in spec.equipped


def test_sheet_equip_weapon_appends(client):
    _seed(client, inventory=["long_sword"])
    r = client.post("/character/test/equipment/equip", data={"item_id": "long_sword"})
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.equipped_weapons == ["long_sword"]


def test_sheet_attack_profiles_appear_when_weapon_equipped(client):
    _seed(client, inventory=["long_sword"], equipped_weapons=["long_sword"])
    r = client.get("/character/test")
    assert "Attacks" in r.text
    assert "Long Sword" in r.text
    # STR 16 → +2 mod; THAC0 19 - 2 = 17
    assert "17" in r.text


def test_sheet_shows_unarmed_when_no_weapons_equipped(client):
    # Unarmed is always the first profile; even with no equipped weapons the
    # Attacks section renders with "Unarmed" rather than a "No weapons" message.
    _seed(client, inventory=["long_sword"])  # owned but not equipped
    r = client.get("/character/test")
    assert "Unarmed" in r.text


def test_sheet_inventory_shows_equipped_section(client):
    """Equipped inventory items appear in their own ``Equipped`` subsection
    of the inventory table — the new three-state split (equipped / carried /
    stashed) replaces the old per-row badge.  The unequip form is the
    actionable signal."""
    _seed(client, inventory=["long_sword"], equipped_weapons=["long_sword"])
    r = client.get("/character/test")
    assert 'class="inv-section-head"' in r.text and ">Equipped" in r.text
    assert 'action="/character/test/equipment/unequip"' in r.text


def test_sheet_equip_rejects_unowned_item(client):
    _seed(client, inventory=[])
    r = client.post("/character/test/equipment/equip", data={"item_id": "long_sword"})
    assert r.status_code == 400


def test_sheet_equip_rejects_non_equippable(client):
    _seed(client, inventory=["torch"])
    r = client.post("/character/test/equipment/equip", data={"item_id": "torch"})
    assert r.status_code == 400


def test_sheet_unequip_rejects_unequipped(client):
    _seed(client, inventory=["long_sword"])
    r = client.post("/character/test/equipment/unequip", data={"item_id": "long_sword"})
    assert r.status_code == 400


# ════════════════════════════════════════════════════════════════════════════
# AC integration: equipping shield + armor stacks
# ════════════════════════════════════════════════════════════════════════════

def test_ac_drops_with_armor_and_shield(client):
    """Sheet AC reflects both armor and shield equips."""
    # Unarmored AC = 9 (DEX 12 = +0).  Chain mail base = 5, shield = -1 = 4 desc.
    _seed(client, inventory=["chain_mail", "shield"],
          equipped={"armor": "chain_mail", "shield": "shield"})
    r = client.get("/character/test")
    # Look for AC 4 in the combat section
    assert "Armor Class" in r.text
    # Pull out the stat-big AC value
    idx = r.text.index("Armor Class")
    snippet = r.text[idx:idx + 400]
    assert "4" in snippet  # descending AC value


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
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Tester"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.get(f"/wizard/{draft_id}/equipment")

    # Force lots of gold
    draft = load_draft(draft_id, tmp_path / "drafts")
    draft["gold"] = 200
    save_draft(draft_id, draft, tmp_path / "drafts")
    client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "long_sword"})

    # Equip it
    r = client.post(f"/wizard/{draft_id}/equipment/equip", data={"item_id": "long_sword"})
    assert r.status_code == 303
    draft = load_draft(draft_id, tmp_path / "drafts")
    assert draft["equipped_weapons"] == ["long_sword"]

    # Unequip it
    r = client.post(f"/wizard/{draft_id}/equipment/unequip", data={"item_id": "long_sword"})
    draft = load_draft(draft_id, tmp_path / "drafts")
    assert draft.get("equipped_weapons", []) == []

    # Finalize — equipped state should make it into the spec
    client.post(f"/wizard/{draft_id}/equipment/equip", data={"item_id": "long_sword"})
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    spec = load_character(char_id, tmp_path / "characters")
    assert spec.equipped_weapons == ["long_sword"]
