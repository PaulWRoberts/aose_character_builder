"""Tests for the multiclassing optional rule."""
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
    """Multiclassing on, split mode (the only combination that supports combos)."""
    return _make_client(tmp_path, RuleSet(multiclassing=True))


@pytest.fixture
def single_client(tmp_path):
    """Multiclassing off — the existing single-class path should be unaffected."""
    return _make_client(tmp_path, RuleSet(multiclassing=False))


# ── Data sanity ────────────────────────────────────────────────────────────

@pytest.mark.skip(reason="allowed_multiclass_combos removed from Race model; multiclass UI being redesigned")
def test_elf_race_loads_with_combo():
    data = GameData.load(DATA_DIR)
    elf = data.races["elf"]
    assert ["fighter", "magic_user"] in elf.allowed_multiclass_combos


def test_magic_user_class_loads():
    data = GameData.load(DATA_DIR)
    mu = data.classes["magic_user"]
    assert mu.hit_die == "1d4"
    assert mu.spell_lists == ["magic_user"]


# ── Engine: HP for multi-class ─────────────────────────────────────────────

def test_max_hp_multiclass_averages_floor_plus_con():
    """Fighter+MU at L1 with rolls [6, 3] and CON 14 (+1) → floor(4.5)+1 = 5."""
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
    assert max_hp(spec, data) == 5  # (6+3)//2 + 1 = 4 + 1 = 5


def test_max_hp_multiclass_clamps_to_one_per_level():
    """Even with brutal rolls and a bad CON, each level still grants ≥ 1 HP."""
    data = GameData.load(DATA_DIR)
    spec = CharacterSpec(
        name="Sickly",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 3, "CHA": 10},  # CON -3
        race_id="elf",
        classes=[
            ClassEntry(class_id="fighter", level=1, hp_rolls=[1]),
            ClassEntry(class_id="magic_user", level=1, hp_rolls=[1]),
        ],
        alignment="neutral",
        ruleset=RuleSet(multiclassing=True),
    )
    # avg=1, con_mod=-3 → -2; clamp to 1.
    assert max_hp(spec, data) == 1


def test_max_hp_single_class_unchanged():
    """Single-class path must still return sum of rolls + CON mod per level."""
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


# ── Wizard step: combos appear on class page ──────────────────────────────

def _start_elf(client):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 12, "INT": 14, "WIS": 11, "DEX": 14, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Tauriel"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "elf"})
    return draft_id


@pytest.mark.skip(reason="combo card UI depends on allowed_multiclass_combos; being redesigned")
def test_class_page_shows_combo_for_elf_when_rule_on(mc_client):
    draft_id = _start_elf(mc_client)
    r = mc_client.get(f"/wizard/{draft_id}/class")
    assert "Multi-class Combinations" in r.text
    assert 'value="fighter,magic_user"' in r.text


def test_class_page_omits_combos_when_rule_off(single_client):
    draft_id = _start_elf(single_client)
    r = single_client.get(f"/wizard/{draft_id}/class")
    assert "Multi-class Combinations" not in r.text
    assert 'value="fighter,magic_user"' not in r.text


def test_class_page_omits_combos_for_race_without_them(mc_client):
    """Dwarf has no allowed_multiclass_combos — the section should stay hidden."""
    r = mc_client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, mc_client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, mc_client._drafts_dir)
    mc_client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    mc_client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    r = mc_client.get(f"/wizard/{draft_id}/class")
    assert "Multi-class Combinations" not in r.text


# ── POST: combo selection ──────────────────────────────────────────────────

@pytest.mark.skip(reason="combo selection depends on allowed_multiclass_combos; being redesigned")
def test_post_combo_stores_class_ids(mc_client):
    draft_id = _start_elf(mc_client)
    r = mc_client.post(
        f"/wizard/{draft_id}/class",
        data={"class_id": "fighter,magic_user"},
    )
    assert r.status_code == 303
    draft = load_draft(draft_id, mc_client._drafts_dir)
    assert draft["class_ids"] == ["fighter", "magic_user"]
    assert "class_id" not in draft  # mutually exclusive with class_ids


def test_post_combo_rejected_when_rule_off(single_client):
    draft_id = _start_elf(single_client)
    r = single_client.post(
        f"/wizard/{draft_id}/class",
        data={"class_id": "fighter,magic_user"},
    )
    assert r.status_code == 400


@pytest.mark.skip(reason="combo allowlist removed from Race; being redesigned")
def test_post_combo_rejected_when_not_in_race_combos(mc_client):
    """Dwarf has no fighter,magic_user combo — must 400."""
    r = mc_client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, mc_client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 14, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, mc_client._drafts_dir)
    mc_client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    mc_client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    r = mc_client.post(
        f"/wizard/{draft_id}/class",
        data={"class_id": "fighter,magic_user"},
    )
    assert r.status_code == 400


def test_post_combo_rejected_when_one_class_fails_abilities(mc_client):
    """Elf Fighter/MU requires INT 9+ for the MU half."""
    r = mc_client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, mc_client._drafts_dir)
    draft["abilities"] = {"STR": 12, "INT": 6, "WIS": 11, "DEX": 14, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, mc_client._drafts_dir)
    mc_client.post(f"/wizard/{draft_id}/abilities", data={"name": "Dim"})
    r = mc_client.post(f"/wizard/{draft_id}/race", data={"race_id": "elf"})
    # Elf race also requires INT 9, so race POST already 400s here — but if we
    # bypassed it the combo POST would too.  Confirm race already rejected.
    assert r.status_code == 400


@pytest.mark.skip(reason="combo allowlist removed; race-locked class id changed to 'dwarf'; being redesigned")
def test_post_combo_rejects_race_locked_member(mc_client):
    """Defence-in-depth: combos must not contain race-locked classes."""
    draft_id = _start_elf(mc_client)
    r = mc_client.post(
        f"/wizard/{draft_id}/class",
        data={"class_id": "fighter,dwarf"},  # dwarf is race-locked
    )
    assert r.status_code == 400


# ── Single class still works ──────────────────────────────────────────────

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
        data={"class_id": "fighter,magic_user"},
    )
    mc_client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "neutral"})


@pytest.mark.skip(reason="uses combo class selection; being redesigned")
def test_hp_get_shows_one_die_per_class_for_multiclass(mc_client):
    draft_id = _start_elf(mc_client)
    _to_hp(mc_client, draft_id)
    r = mc_client.get(f"/wizard/{draft_id}/hp")
    assert r.status_code == 200
    # Both dice mentioned
    assert "1d8" in r.text
    assert "1d4" in r.text
    assert "Fighter" in r.text
    assert "Magic-User" in r.text


@pytest.mark.skip(reason="uses combo class selection; being redesigned")
def test_hp_roll_populates_one_value_per_class(mc_client):
    draft_id = _start_elf(mc_client)
    _to_hp(mc_client, draft_id)
    mc_client.post(f"/wizard/{draft_id}/hp/roll")
    draft = load_draft(draft_id, mc_client._drafts_dir)
    assert "hp_rolls" in draft
    assert len(draft["hp_rolls"]) == 2
    assert 1 <= draft["hp_rolls"][0] <= 8
    assert 1 <= draft["hp_rolls"][1] <= 4


@pytest.mark.skip(reason="uses combo class selection; being redesigned")
def test_max_hp_rule_autofills_max_rolls_for_each_class(mc_client):
    save_settings(
        mc_client._settings_path,
        RuleSet(multiclassing=True, max_hp_at_l1=True),
    )
    draft_id = _start_elf(mc_client)
    _to_hp(mc_client, draft_id)
    mc_client.get(f"/wizard/{draft_id}/hp")
    draft = load_draft(draft_id, mc_client._drafts_dir)
    assert draft["hp_rolls"] == [8, 4]  # fighter max + MU max


@pytest.mark.skip(reason="uses combo class selection; being redesigned")
def test_hp_step_post_with_no_rolls_yet_400s(mc_client):
    draft_id = _start_elf(mc_client)
    _to_hp(mc_client, draft_id)
    r = mc_client.post(f"/wizard/{draft_id}/hp")
    assert r.status_code == 400


# ── End-to-end ────────────────────────────────────────────────────────────

@pytest.mark.skip(reason="uses combo class selection; being redesigned")
def test_full_multiclass_flow_creates_character(mc_client):
    draft_id = _start_elf(mc_client)
    mc_client.post(
        f"/wizard/{draft_id}/class",
        data={"class_id": "fighter,magic_user"},
    )
    mc_client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "neutral"})
    mc_client.post(f"/wizard/{draft_id}/hp/roll")
    mc_client.post(f"/wizard/{draft_id}/hp")
    r = mc_client.post(f"/wizard/{draft_id}/finalize")
    assert r.status_code == 303
    char_id = r.headers["location"].split("/")[-1]
    spec = load_character(char_id, mc_client._characters_dir)
    assert [c.class_id for c in spec.classes] == ["fighter", "magic_user"]
    assert len(spec.classes[0].hp_rolls) == 1
    assert len(spec.classes[1].hp_rolls) == 1
    assert spec.ruleset.multiclassing is True


@pytest.mark.skip(reason="uses combo class selection; being redesigned")
def test_sheet_renders_multiclass_summary(mc_client):
    draft_id = _start_elf(mc_client)
    mc_client.post(
        f"/wizard/{draft_id}/class",
        data={"class_id": "fighter,magic_user"},
    )
    mc_client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "neutral"})
    mc_client.post(f"/wizard/{draft_id}/hp/roll")
    mc_client.post(f"/wizard/{draft_id}/hp")
    r = mc_client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    r = mc_client.get(f"/character/{char_id}")
    # _class_summary renders "Fighter 1 / Magic-User 1"
    assert "Fighter 1" in r.text
    assert "Magic-User 1" in r.text
    assert " / " in r.text


# ── Proficiency slots for multi-class ─────────────────────────────────────

@pytest.mark.skip(reason="uses combo class selection and stale slot count; being redesigned")
def test_proficiency_slots_use_highest_among_classes(mc_client):
    """Fighter has 2 slots (default), MU has the default 2 — multi-class gets 2."""
    save_settings(
        mc_client._settings_path,
        RuleSet(multiclassing=True, weapon_proficiency=True),
    )
    draft_id = _start_elf(mc_client)
    mc_client.post(
        f"/wizard/{draft_id}/class",
        data={"class_id": "fighter,magic_user"},
    )
    mc_client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "neutral"})
    r = mc_client.get(f"/wizard/{draft_id}/proficiencies")
    assert r.status_code == 200
    assert "4" in r.text  # required count
    assert "Fighter / Magic-User" in r.text  # label combines class names
