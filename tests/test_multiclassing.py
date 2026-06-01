"""Tests for the Multiple Classes optional rule (free-form, up to 3 classes)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, load_draft, save_draft, save_settings
from aose.data.loader import GameData
from aose.engine.hp import max_hp
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def _make_client(tmp_path, ruleset):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, ruleset)
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


@pytest.fixture
def mc_client(tmp_path):
    """Multiclassing on (split mode is the default and required for combos)."""
    return _make_client(tmp_path, RuleSet(multiclassing=True))


@pytest.fixture
def single_client(tmp_path):
    """Multiclassing off — the single-class path should be unaffected."""
    return _make_client(tmp_path, RuleSet(multiclassing=False))


# ── Data sanity ────────────────────────────────────────────────────────────

def test_magic_user_class_loads():
    data = GameData.load(DATA_DIR)
    mu = data.classes["magic_user"]
    assert mu.hit_die == "1d4"
    assert mu.spell_lists == ["magic_user"]


# ── Engine: HP for multi-class ─────────────────────────────────────────────

def test_max_hp_multiclass_event_sum_floor_with_con():
    """Fighter+MU at L1 with rolls 6 & 3 and CON 14 (+1):
    floor(max(1, (6+3)/2 + 1)) = floor(5.5) = 5."""
    data = GameData.load(DATA_DIR)
    spec = CharacterSpec(
        name="Tauriel",
        abilities={"STR": 12, "INT": 14, "WIS": 11, "DEX": 14, "CON": 14, "CHA": 10},
        race_id="elf",
        classes=[
            ClassEntry(class_id="fighter", level=1, hp_rolls=[6]),
            ClassEntry(class_id="magic_user", level=1, hp_rolls=[3]),
        ],
        alignment="neutral",
        ruleset=RuleSet(multiclassing=True),
    )
    assert max_hp(spec, data) == 5


def test_max_hp_multiclass_min_one_per_event():
    """Even with brutal rolls and a bad CON, the character keeps ≥ 1 HP."""
    data = GameData.load(DATA_DIR)
    spec = CharacterSpec(
        name="Sickly",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 3, "CHA": 10},
        race_id="elf",
        classes=[
            ClassEntry(class_id="fighter", level=1, hp_rolls=[1]),
            ClassEntry(class_id="magic_user", level=1, hp_rolls=[1]),
        ],
        alignment="neutral",
        ruleset=RuleSet(multiclassing=True),
    )
    # floor(max(1, 2/2 - 3)) = floor(max(1, -2)) = 1
    assert max_hp(spec, data) == 1


def test_max_hp_single_class_unchanged():
    data = GameData.load(DATA_DIR)
    spec = CharacterSpec(
        name="Thorin",
        abilities={"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10},
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[7])],
        alignment="law",
        ruleset=RuleSet(),
    )
    assert max_hp(spec, data) == 8  # 7 + 1 (CON)


# ── Wizard helpers ─────────────────────────────────────────────────────────

def _start_elf(client):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 12, "INT": 14, "WIS": 11, "DEX": 14, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "elf"})
    return draft_id


# ── Class step UI ──────────────────────────────────────────────────────────

def test_class_page_uses_checkboxes_when_rule_on(mc_client):
    draft_id = _start_elf(mc_client)
    r = mc_client.get(f"/wizard/{draft_id}/class")
    assert 'type="checkbox"' in r.text
    assert "pick up to 3 classes" in r.text


def test_class_page_uses_radio_when_rule_off(single_client):
    draft_id = _start_elf(single_client)
    r = single_client.get(f"/wizard/{draft_id}/class")
    assert 'type="radio"' in r.text
    assert "pick up to 3 classes" not in r.text


# ── POST: multi-class selection ────────────────────────────────────────────

def test_post_two_classes_stores_class_ids(mc_client):
    draft_id = _start_elf(mc_client)
    r = mc_client.post(
        f"/wizard/{draft_id}/class",
        data={"class_id": ["fighter", "magic_user"]},
    )
    assert r.status_code == 303
    draft = load_draft(draft_id, mc_client._drafts_dir)
    assert draft["class_ids"] == ["fighter", "magic_user"]
    assert "class_id" not in draft  # mutually exclusive with class_ids


def test_post_comma_joined_still_accepted(mc_client):
    draft_id = _start_elf(mc_client)
    r = mc_client.post(
        f"/wizard/{draft_id}/class",
        data={"class_id": "fighter,magic_user"},
    )
    assert r.status_code == 303
    draft = load_draft(draft_id, mc_client._drafts_dir)
    assert draft["class_ids"] == ["fighter", "magic_user"]


def test_post_multi_rejected_when_rule_off(single_client):
    draft_id = _start_elf(single_client)
    r = single_client.post(
        f"/wizard/{draft_id}/class",
        data={"class_id": ["fighter", "magic_user"]},
    )
    assert r.status_code == 400


def test_post_more_than_three_classes_rejected(mc_client):
    draft_id = _start_elf(mc_client)
    r = mc_client.post(
        f"/wizard/{draft_id}/class",
        data={"class_id": ["fighter", "magic_user", "thief", "cleric"]},
    )
    assert r.status_code == 400


def test_post_three_classes_allowed(mc_client):
    draft_id = _start_elf(mc_client)
    r = mc_client.post(
        f"/wizard/{draft_id}/class",
        data={"class_id": ["fighter", "magic_user", "thief"]},
    )
    assert r.status_code == 303
    draft = load_draft(draft_id, mc_client._drafts_dir)
    assert draft["class_ids"] == ["fighter", "magic_user", "thief"]


def test_post_multi_rejected_when_one_class_fails_abilities(mc_client):
    """Low INT fails the elf race POST already (elf needs INT 9)."""
    r = mc_client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, mc_client._drafts_dir)
    draft["abilities"] = {"STR": 12, "INT": 6, "WIS": 11, "DEX": 14, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, mc_client._drafts_dir)
    mc_client.post(f"/wizard/{draft_id}/abilities", data={})
    r = mc_client.post(f"/wizard/{draft_id}/race", data={"race_id": "elf"})
    assert r.status_code == 400


def test_single_class_pick_unaffected_by_multiclass_rule(mc_client):
    draft_id = _start_elf(mc_client)
    r = mc_client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    assert r.status_code == 303
    draft = load_draft(draft_id, mc_client._drafts_dir)
    assert draft["class_id"] == "fighter"
    assert "class_ids" not in draft


# ── HP step for multi-class ───────────────────────────────────────────────

def _to_hp(mc_client, draft_id):
    mc_client.post(
        f"/wizard/{draft_id}/class",
        data={"class_id": ["fighter", "magic_user"]},
    )
    mc_client.post(f"/wizard/{draft_id}/adjust", data={})


def test_hp_get_shows_one_die_per_class_for_multiclass(mc_client):
    draft_id = _start_elf(mc_client)
    _to_hp(mc_client, draft_id)
    r = mc_client.get(f"/wizard/{draft_id}/class_setup")
    assert r.status_code == 200
    assert "1d8" in r.text
    assert "1d4" in r.text


def test_hp_roll_populates_one_value_per_class(mc_client):
    draft_id = _start_elf(mc_client)
    _to_hp(mc_client, draft_id)
    mc_client.post(f"/wizard/{draft_id}/hp/roll")
    draft = load_draft(draft_id, mc_client._drafts_dir)
    assert "hp_rolls" in draft
    assert len(draft["hp_rolls"]) == 2
    assert 1 <= draft["hp_rolls"][0] <= 8
    assert 1 <= draft["hp_rolls"][1] <= 4


# ── End-to-end ────────────────────────────────────────────────────────────

def test_full_multiclass_flow_creates_character(mc_client):
    draft_id = _start_elf(mc_client)
    mc_client.post(
        f"/wizard/{draft_id}/class",
        data={"class_id": ["fighter", "magic_user"]},
    )
    mc_client.post(f"/wizard/{draft_id}/hp/roll")
    mc_client.post(f"/wizard/{draft_id}/hp")
    mc_client.post(f"/wizard/{draft_id}/identity", data={"name": "Tauriel", "alignment": "neutral"})
    r = mc_client.post(f"/wizard/{draft_id}/finalize")
    assert r.status_code == 303
    char_id = r.headers["location"].split("/")[-1]
    spec = load_character(char_id, mc_client._characters_dir)
    assert [c.class_id for c in spec.classes] == ["fighter", "magic_user"]
    assert len(spec.classes[0].hp_rolls) == 1
    assert len(spec.classes[1].hp_rolls) == 1
    assert spec.ruleset.multiclassing is True
    assert all(c.xp == 0 for c in spec.classes)


def test_sheet_renders_multiclass_summary(mc_client):
    draft_id = _start_elf(mc_client)
    mc_client.post(
        f"/wizard/{draft_id}/class",
        data={"class_id": ["fighter", "magic_user"]},
    )
    mc_client.post(f"/wizard/{draft_id}/hp/roll")
    mc_client.post(f"/wizard/{draft_id}/hp")
    mc_client.post(f"/wizard/{draft_id}/identity", data={"name": "Tauriel", "alignment": "neutral"})
    r = mc_client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    r = mc_client.get(f"/character/{char_id}")
    assert "Fighter 1" in r.text
    assert "Magic-User 1" in r.text
    assert " / " in r.text


# ── Proficiency slots for multi-class ─────────────────────────────────────

def test_proficiency_step_combines_class_names(mc_client):
    save_settings(
        mc_client._settings_path,
        RuleSet(multiclassing=True, weapon_proficiency=True),
    )
    draft_id = _start_elf(mc_client)
    mc_client.post(
        f"/wizard/{draft_id}/class",
        data={"class_id": ["fighter", "magic_user"]},
    )
    mc_client.post(f"/wizard/{draft_id}/adjust", data={})
    r = mc_client.get(f"/wizard/{draft_id}/class_setup")
    assert r.status_code == 200
    assert "Fighter / Magic-User" in r.text
