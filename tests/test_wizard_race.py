"""Slice 3 (Race): racial ability-modifier application + wizard wiring."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_draft, save_draft, save_settings
from aose.engine.ability_mods import apply_racial_modifiers
from aose.data.loader import GameData
from aose.models import RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


# ── Pure helper: apply_racial_modifiers ───────────────────────────────────

def _base():
    return {"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 14, "CHA": 9}


def test_apply_dwarf_modifiers(data):
    result = apply_racial_modifiers(_base(), data.races["dwarf"])
    assert result["CON"] == 15  # +1
    assert result["CHA"] == 8   # -1
    assert result["STR"] == 10


def test_apply_does_not_mutate_input(data):
    base = _base()
    apply_racial_modifiers(base, data.races["dwarf"])
    assert base["CON"] == 14


def test_clamp_high_at_18(data):
    base = {"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 18, "CHA": 9}
    result = apply_racial_modifiers(base, data.races["dwarf"])
    assert result["CON"] == 18


def test_clamp_low_at_3(data):
    base = {"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 14, "CHA": 3}
    result = apply_racial_modifiers(base, data.races["dwarf"])
    assert result["CHA"] == 3


def test_apply_half_orc_multi_stat(data):
    base = {"STR": 12, "INT": 10, "WIS": 10, "DEX": 10, "CON": 13, "CHA": 11}
    result = apply_racial_modifiers(base, data.races["half_orc"])
    assert result["STR"] == 13  # +1
    assert result["CON"] == 14  # +1
    assert result["CHA"] == 9   # -2


def test_apply_no_modifier_race_is_identity(data):
    base = _base()
    assert apply_racial_modifiers(base, data.races["gnome"]) == base


# ── Integration helpers ───────────────────────────────────────────────────

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
    client._drafts_dir = drafts_dir
    client._characters_dir = characters_dir
    return client


def _new_draft(client):
    r = client.get("/wizard/new")
    return r.headers["location"].split("/")[2]


def _set_abilities(client, draft_id, abilities):
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = abilities
    save_draft(draft_id, draft, client._drafts_dir)


_DWARF_ABILITIES = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}


def _drive_dwarf_fighter_to_finalize(client):
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, dict(_DWARF_ABILITIES))
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Gloin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.get(f"/wizard/{draft_id}/equipment")
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    return r.headers["location"].split("/")[-1]


# ── Finalize stores creation-final abilities ──────────────────────────────

def test_advanced_finalize_stores_modified_abilities(tmp_path):
    import json
    client = _make_client(tmp_path)
    char_id = _drive_dwarf_fighter_to_finalize(client)
    saved = json.loads((client._characters_dir / f"{char_id}.json").read_text())
    assert saved["abilities"]["CON"] == 15  # 14 +1
    assert saved["abilities"]["CHA"] == 9    # 10 -1
    assert saved["abilities"]["STR"] == 15   # unchanged


def test_basic_race_as_class_finalize_has_no_racial_mods(tmp_path):
    import json
    client = _make_client(tmp_path, ruleset=RuleSet(separate_race_class=False))
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, dict(_DWARF_ABILITIES))
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Gloin"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.get(f"/wizard/{draft_id}/equipment")
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    saved = json.loads((client._characters_dir / f"{char_id}.json").read_text())
    assert saved["abilities"]["CON"] == 14  # no racial mod in Basic
    assert saved["abilities"]["CHA"] == 10


# ── Requirement gating: race pre-modifier, class post-modifier ────────────

def test_race_minimum_checked_pre_modifier(tmp_path):
    # Dwarf requires CON 9. CON 8 must fail even though +1 would reach 9.
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, {
        "STR": 12, "INT": 11, "WIS": 12, "DEX": 13, "CON": 8, "CHA": 12,
    })
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Gloin"})
    r = client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    assert r.status_code == 400


_KNIGHT_BORDERLINE = {"STR": 12, "INT": 11, "WIS": 12, "DEX": 9, "CON": 8, "CHA": 12}


def test_class_minimum_passes_after_racial_bonus(tmp_path):
    # half_orc CON +1: base CON 8 fails knight's CON 9, effective 9 passes.
    client = _make_client(tmp_path, ruleset=RuleSet(lift_demihuman_restrictions=True))
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, dict(_KNIGHT_BORDERLINE))
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Grok"})
    r = client.post(f"/wizard/{draft_id}/race", data={"race_id": "half_orc"})
    assert r.status_code == 303
    r = client.post(f"/wizard/{draft_id}/class", data={"class_id": "knight"})
    assert r.status_code == 303


def test_class_minimum_fails_without_racial_bonus(tmp_path):
    # Negative control: human has no CON modifier, base CON 8 still fails.
    client = _make_client(tmp_path, ruleset=RuleSet(lift_demihuman_restrictions=True))
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, dict(_KNIGHT_BORDERLINE))
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Otto"})
    r = client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    assert r.status_code == 303
    r = client.post(f"/wizard/{draft_id}/class", data={"class_id": "knight"})
    assert r.status_code == 400


# ── Race step display ─────────────────────────────────────────────────────

def test_race_step_shows_ability_change_for_dwarf(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, dict(_DWARF_ABILITIES))  # CON 14, CHA 10
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Gloin"})
    r = client.get(f"/wizard/{draft_id}/race")
    assert r.status_code == 200
    assert "14 → 15" in r.text or "14 &rarr; 15" in r.text
    assert "10 → 9" in r.text or "10 &rarr; 9" in r.text


def test_race_step_no_change_block_for_human(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, dict(_DWARF_ABILITIES))
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Nim"})
    r = client.get(f"/wizard/{draft_id}/race")
    assert r.status_code == 200
    # The dwarf card has at least one "Ability changes:" block.
    assert r.text.count("Ability changes:") >= 1


# ── HP step reads effective CON ───────────────────────────────────────────

def test_hp_step_con_mod_reflects_racial_bonus(tmp_path):
    # Dwarf +1 CON: base CON 15 (mod +1) → effective 16 (mod +2).
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, {
        "STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 15, "CHA": 12,
    })
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Gloin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    r = client.get(f"/wizard/{draft_id}/hp")
    assert r.status_code == 200
    assert "+2" in r.text
