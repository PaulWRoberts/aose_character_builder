"""Tests for the Weapon Proficiency optional rule."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, load_draft, save_draft, save_settings
from aose.data.loader import GameData
from aose.engine.proficiency import (
    is_proficient_with,
    proficiency_groups,
    starting_proficiency_count,
)
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.sheet.view import build_sheet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture
def client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, RuleSet(weapon_proficiency=True))
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._settings_path = settings_path
    client._drafts_dir = drafts_dir
    client._characters_dir = characters_dir
    return client


# ── Data loaders ───────────────────────────────────────────────────────────

def test_weapons_load_into_game_data():
    data = GameData.load(DATA_DIR)
    assert "long_sword" in data.items
    assert "short_bow" in data.items
    assert data.items["long_sword"].proficiency_group == "sword"


def test_proficiency_groups_dedupes_and_sorts():
    data = GameData.load(DATA_DIR)
    groups = proficiency_groups(data)
    ids = [g["id"] for g in groups]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))
    # Common AOSE groups present
    assert {"sword", "bow", "axe", "bludgeon"}.issubset(set(ids))


def test_proficiency_group_lists_member_weapons():
    data = GameData.load(DATA_DIR)
    groups = {g["id"]: g for g in proficiency_groups(data)}
    sword = groups["sword"]
    assert "Long Sword" in sword["weapons"]
    assert "Short Sword" in sword["weapons"]
    assert "Two-Handed Sword" in sword["weapons"]


def test_starting_proficiency_count_fighter():
    data = GameData.load(DATA_DIR)
    assert starting_proficiency_count(data.classes["fighter"]) == 4


def test_starting_proficiency_count_defaults_to_two_when_class_has_no_config():
    """A class without a proficiency block should fall back to 2 slots."""
    data = GameData.load(DATA_DIR)
    cls = data.classes["fighter"].model_copy(update={"proficiency": None})
    assert starting_proficiency_count(cls) == 2


def test_is_proficient_with_matches_group():
    data = GameData.load(DATA_DIR)
    long_sword = data.items["long_sword"]
    assert is_proficient_with(long_sword, ["sword"]) is True
    assert is_proficient_with(long_sword, ["axe"]) is False
    assert is_proficient_with(long_sword, []) is False


# ── Wizard step ordering ───────────────────────────────────────────────────

def _start_through_class(client):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    return draft_id


def test_step_inserted_when_rule_active(client):
    draft_id = _start_through_class(client)
    r = client.get(f"/wizard/{draft_id}/class")
    assert "Proficiencies" in r.text


def test_step_skipped_when_rule_off(client):
    save_settings(client._settings_path, RuleSet(weapon_proficiency=False))
    draft_id = _start_through_class(client)
    r = client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    # Should skip straight to /hp, not /proficiencies
    assert r.headers["location"].endswith("/hp")


def test_alignment_redirects_to_proficiencies_when_rule_active(client):
    draft_id = _start_through_class(client)
    r = client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    assert r.headers["location"].endswith("/proficiencies")


def test_proficiencies_gate_when_visited_before_class(client):
    """Hitting /proficiencies before class is picked should bounce back."""
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    r = client.get(f"/wizard/{draft_id}/proficiencies")
    assert r.status_code == 303
    assert "/proficiencies" not in r.headers["location"]


# ── GET /proficiencies page ────────────────────────────────────────────────

def test_get_proficiencies_lists_all_groups(client):
    draft_id = _start_through_class(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    r = client.get(f"/wizard/{draft_id}/proficiencies")
    assert r.status_code == 200
    assert "Sword" in r.text
    assert "Bow" in r.text
    assert "Long Sword" in r.text  # example weapon in description


def test_get_proficiencies_shows_required_count(client):
    """Fighter must pick 4 slots — the count should be visible to the user."""
    draft_id = _start_through_class(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    r = client.get(f"/wizard/{draft_id}/proficiencies")
    assert "4" in r.text


# ── POST /proficiencies ────────────────────────────────────────────────────

def _proficiency_post_data(*groups):
    """Multi-value form payload for the proficiency POST.

    httpx's TestClient ignores ``data=[(k, v), ...]`` for form encoding; use
    the ``data={"k": [v1, v2]}`` form instead.
    """
    return {"proficiency_group": list(groups)}


def test_post_with_correct_count_advances(client):
    draft_id = _start_through_class(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    r = client.post(
        f"/wizard/{draft_id}/proficiencies",
        data=_proficiency_post_data("sword", "axe", "bow", "dagger"),
    )
    assert r.status_code == 303
    assert r.headers["location"].endswith("/hp")
    draft = load_draft(draft_id, client._drafts_dir)
    assert set(draft["proficiencies"]) == {"sword", "axe", "bow", "dagger"}


def test_post_with_too_few_rejected(client):
    draft_id = _start_through_class(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    r = client.post(
        f"/wizard/{draft_id}/proficiencies",
        data=_proficiency_post_data("sword"),
    )
    assert r.status_code == 400


def test_post_with_no_selection_rejected(client):
    """An empty form (the user submitted without ticking anything) → 400."""
    draft_id = _start_through_class(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    r = client.post(f"/wizard/{draft_id}/proficiencies", data={})
    assert r.status_code == 400


def test_post_with_too_many_rejected(client):
    draft_id = _start_through_class(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    r = client.post(
        f"/wizard/{draft_id}/proficiencies",
        data=_proficiency_post_data("sword", "axe", "bow", "dagger", "bludgeon"),
    )
    assert r.status_code == 400


def test_post_with_unknown_group_rejected(client):
    draft_id = _start_through_class(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    r = client.post(
        f"/wizard/{draft_id}/proficiencies",
        data=_proficiency_post_data("sword", "axe", "bow", "lightsaber"),
    )
    assert r.status_code == 400


def test_post_deduplicates_repeated_picks(client):
    """The user submitting 'sword' three times still doesn't satisfy 4 slots."""
    draft_id = _start_through_class(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    r = client.post(
        f"/wizard/{draft_id}/proficiencies",
        data=_proficiency_post_data("sword", "sword", "sword", "sword"),
    )
    assert r.status_code == 400


# ── End-to-end into the character ──────────────────────────────────────────

def _finish_wizard(client, draft_id):
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    r = client.post(f"/wizard/{draft_id}/finalize")
    return r.headers["location"].split("/")[-1]


def test_proficiencies_persist_to_character(client):
    draft_id = _start_through_class(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(
        f"/wizard/{draft_id}/proficiencies",
        data=_proficiency_post_data("sword", "axe", "bow", "dagger"),
    )
    char_id = _finish_wizard(client, draft_id)
    spec = load_character(char_id, client._characters_dir)
    assert set(spec.chosen_proficiencies) == {"sword", "axe", "bow", "dagger"}


def test_sheet_shows_proficiencies_when_rule_active(client):
    draft_id = _start_through_class(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(
        f"/wizard/{draft_id}/proficiencies",
        data=_proficiency_post_data("sword", "axe", "bow", "dagger"),
    )
    char_id = _finish_wizard(client, draft_id)
    r = client.get(f"/character/{char_id}")
    assert "Weapon Proficiencies" in r.text
    assert "Sword" in r.text
    assert "&minus;2 to hit" in r.text


def test_sheet_hides_proficiency_section_when_rule_off(client):
    """A character built without the rule shouldn't show the section."""
    save_settings(client._settings_path, RuleSet(weapon_proficiency=False))
    draft_id = _start_through_class(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    char_id = _finish_wizard(client, draft_id)
    r = client.get(f"/character/{char_id}")
    assert "Weapon Proficiencies" not in r.text


def test_print_page_shows_proficiencies(client):
    draft_id = _start_through_class(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(
        f"/wizard/{draft_id}/proficiencies",
        data=_proficiency_post_data("sword", "polearm", "crossbow", "sling"),
    )
    char_id = _finish_wizard(client, draft_id)
    r = client.get(f"/character/{char_id}/print")
    assert "Weapon Proficiencies" in r.text
    assert "Crossbow" in r.text


# ── Sheet builder directly ─────────────────────────────────────────────────

def test_build_sheet_maps_group_ids_to_names():
    data = GameData.load(DATA_DIR)
    spec = CharacterSpec(
        name="X",
        abilities={"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10},
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="law",
        chosen_proficiencies=["sword", "bow"],
        ruleset=RuleSet(weapon_proficiency=True),
    )
    sheet = build_sheet(spec, data)
    assert [p.name for p in sheet.proficiencies] == ["Sword", "Bow"]
    assert sheet.weapon_proficiency_active is True


def test_build_sheet_omits_proficiencies_when_rule_off():
    data = GameData.load(DATA_DIR)
    spec = CharacterSpec(
        name="X",
        abilities={"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10},
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="law",
        chosen_proficiencies=["sword"],  # spec still has the value but rule is off
        ruleset=RuleSet(weapon_proficiency=False),
    )
    sheet = build_sheet(spec, data)
    assert sheet.proficiencies == []
    assert sheet.weapon_proficiency_active is False


# ── Variable Weapon Damage: per-weapon damage on proficiency display ──────

def test_proficiency_display_shows_default_damage_when_variable_off():
    data = GameData.load(DATA_DIR)
    spec = CharacterSpec(
        name="X",
        abilities={"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10},
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="law",
        chosen_proficiencies=["sword"],
        ruleset=RuleSet(weapon_proficiency=True, variable_weapon_damage=False),
    )
    sheet = build_sheet(spec, data)
    sword = next(p for p in sheet.proficiencies if p.name == "Sword")
    # Every sword shows the default-rule 1d6
    for w in sword.weapons:
        assert w.damage == "1d6", f"{w.name} should be 1d6 under default damage"


def test_proficiency_display_shows_variable_damage_when_rule_on():
    data = GameData.load(DATA_DIR)
    spec = CharacterSpec(
        name="X",
        abilities={"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10},
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="law",
        chosen_proficiencies=["sword"],
        ruleset=RuleSet(weapon_proficiency=True, variable_weapon_damage=True),
    )
    sheet = build_sheet(spec, data)
    sword = next(p for p in sheet.proficiencies if p.name == "Sword")
    damages = {w.name: w.damage for w in sword.weapons}
    assert damages["Short Sword"] == "1d6"
    assert damages["Long Sword"] == "1d8"
    assert damages["Two-Handed Sword"] == "1d10"


def test_sheet_renders_variable_damages_inline(client):
    """Smoke test against the HTML route — the rendered sheet should mention
    a non-1d6 damage when the rule is on."""
    save_settings(
        client._settings_path,
        RuleSet(weapon_proficiency=True, variable_weapon_damage=True),
    )
    draft_id = _start_through_class(client)
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(
        f"/wizard/{draft_id}/proficiencies",
        data=_proficiency_post_data("sword", "axe", "bow", "sling"),
    )
    char_id = _finish_wizard(client, draft_id)
    r = client.get(f"/character/{char_id}")
    assert "1d8" in r.text  # long sword variable
    assert "1d10" in r.text  # two-handed sword variable
