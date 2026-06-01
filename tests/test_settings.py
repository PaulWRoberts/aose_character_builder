"""Tests for the ruleset settings page and wizard integration."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, load_settings, save_settings
from aose.models import RuleSet
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
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._settings_path = settings_path  # noqa: SLF001 — test convenience
    return client


# ── load_settings / save_settings ──────────────────────────────────────────

def test_load_returns_defaults_when_missing(tmp_path):
    rs = load_settings(tmp_path / "nope.json")
    assert rs == RuleSet()
    assert rs.ascending_ac is False


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(path, RuleSet(ascending_ac=True, max_hp_at_l1=True))
    rs = load_settings(path)
    assert rs.ascending_ac is True
    assert rs.max_hp_at_l1 is True


def test_save_writes_pretty_json(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(path, RuleSet(ascending_ac=True))
    raw = path.read_text(encoding="utf-8")
    assert "ascending_ac" in raw
    assert json.loads(raw)["ruleset"]["ascending_ac"] is True


# ── /settings page rendering ───────────────────────────────────────────────

def test_get_settings_renders(client):
    r = client.get("/settings")
    assert r.status_code == 200
    assert "Ruleset Settings" in r.text
    assert "Ascending AC" in r.text


def test_get_settings_shows_default_unchecked(client):
    r = client.get("/settings")
    # ascending_ac defaults to False so the checkbox should NOT be checked
    assert 'name="ascending_ac"' in r.text
    # No "checked" attribute next to the ascending_ac input
    snippet = r.text[r.text.index('name="ascending_ac"') - 100:r.text.index('name="ascending_ac"') + 50]
    assert "checked" not in snippet


def test_get_settings_reflects_saved_state(client):
    save_settings(client._settings_path, RuleSet(ascending_ac=True))
    r = client.get("/settings")
    snippet = r.text[r.text.index('name="ascending_ac"') - 100:r.text.index('name="ascending_ac"') + 100]
    assert "checked" in snippet


def test_settings_page_links_in_nav(client):
    r = client.get("/")
    assert 'href="/settings"' in r.text


def test_no_pending_badges_when_all_rules_implemented(client):
    """Regression guard for the matrix of optional rules.

    Every bool rule is in IMPLEMENTED_RULES, every choice group in
    IMPLEMENTED_CHOICE_GROUPS — so the settings page should not render the
    'pending' badge anywhere any more.  If a new rule is added without
    integration, this test will fail and remind the author to either
    integrate it or explicitly add a new pending guard test.
    """
    r = client.get("/settings")
    assert "rule-pending" not in r.text
    assert ">pending<" not in r.text


def test_no_pending_badge_for_ascending_ac(client):
    r = client.get("/settings")
    idx = r.text.index('name="ascending_ac"')
    # The pending badge appears inside the same .rule block, before the next checkbox
    next_idx = r.text.find('type="checkbox"', idx + 10)
    snippet = r.text[idx:next_idx]
    assert "pending" not in snippet


# ── POST /settings ─────────────────────────────────────────────────────────

def test_post_settings_persists_to_disk(client):
    r = client.post("/settings", data={
        "ascending_ac": "on",
        "max_hp_at_l1": "on",
        "ability_roll_method": "3d6_arrange",
        "encumbrance": "detailed",
    })
    assert r.status_code == 303
    assert r.headers["location"] == "/settings?saved=1"

    rs = load_settings(client._settings_path)
    assert rs.ascending_ac is True
    assert rs.max_hp_at_l1 is True
    assert rs.ability_roll_method == "3d6_arrange"
    assert rs.encumbrance == "detailed"
    # Unchecked boxes default to False
    assert rs.weapon_proficiency is False


def test_post_settings_unchecking_clears_flag(client):
    save_settings(client._settings_path, RuleSet(ascending_ac=True))
    client.post("/settings", data={})  # no checkboxes ticked
    rs = load_settings(client._settings_path)
    assert rs.ascending_ac is False


def test_post_settings_ignores_invalid_radio_choice(client):
    r = client.post("/settings", data={"ability_roll_method": "made_up_method"})
    assert r.status_code == 303
    rs = load_settings(client._settings_path)
    # Falls back to the default since the choice was invalid
    assert rs.ability_roll_method == "3d6_in_order"


def test_get_settings_shows_flash_after_save(client):
    r = client.get("/settings?saved=1")
    assert "Settings saved" in r.text


# ── Wizard integration: settings flow into new characters ──────────────────

def _override_abilities(draft_id, drafts_dir, abilities):
    from aose.characters import load_draft, save_draft
    draft = load_draft(draft_id, drafts_dir)
    draft["abilities"] = abilities
    save_draft(draft_id, draft, drafts_dir)


def _run_wizard_to_completion(client, drafts_dir, name="Thorin"):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    _override_abilities(draft_id, drafts_dir, {
        "STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10,
    })
    client.post(f"/wizard/{draft_id}/abilities", data={"name": name})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    return char_id


def test_new_character_inherits_active_ruleset(client, tmp_path):
    save_settings(client._settings_path, RuleSet(ascending_ac=True, max_hp_at_l1=True))
    char_id = _run_wizard_to_completion(client, tmp_path / "drafts")
    spec = load_character(char_id, tmp_path / "characters")
    assert spec.ruleset.ascending_ac is True
    assert spec.ruleset.max_hp_at_l1 is True


def test_changing_settings_does_not_alter_existing_character(client, tmp_path):
    # Build with defaults
    char_id_default = _run_wizard_to_completion(client, tmp_path / "drafts", name="Default")
    # Change settings
    save_settings(client._settings_path, RuleSet(ascending_ac=True))
    # Build a second character
    char_id_asc = _run_wizard_to_completion(client, tmp_path / "drafts", name="Ascending")
    # Old character still has descending AC
    spec_default = load_character(char_id_default, tmp_path / "characters")
    spec_asc = load_character(char_id_asc, tmp_path / "characters")
    assert spec_default.ruleset.ascending_ac is False
    assert spec_asc.ruleset.ascending_ac is True


def test_ascending_ac_renders_on_sheet(client, tmp_path):
    """End-to-end: setting ascending AC should change what the sheet shows."""
    save_settings(client._settings_path, RuleSet(ascending_ac=True))
    char_id = _run_wizard_to_completion(client, tmp_path / "drafts")
    r = client.get(f"/character/{char_id}")
    assert r.status_code == 200
    # Ascending AC sheets show "Attack Bonus", descending sheets show "THAC0"
    assert "Attack Bonus" in r.text
    assert "THAC0" not in r.text


# ── Max HP at L1 ───────────────────────────────────────────────────────────

def _start_draft_with(client, drafts_dir):
    """Start a draft and walk it up to the HP step."""
    from aose.characters import load_draft, save_draft
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    return draft_id


def test_max_hp_rule_auto_fills_on_get(client, tmp_path):
    """With max_hp_at_l1 active, GET /hp should populate hp_roll to die max."""
    from aose.characters import load_draft
    save_settings(client._settings_path, RuleSet(max_hp_at_l1=True))
    draft_id = _start_draft_with(client, tmp_path / "drafts")

    # Before visiting /hp, no roll exists
    draft = load_draft(draft_id, tmp_path / "drafts")
    assert "hp_roll" not in draft

    r = client.get(f"/wizard/{draft_id}/hp")
    assert r.status_code == 200
    assert "Max HP at L1" in r.text

    # Fighter has 1d8, so max is 8
    draft = load_draft(draft_id, tmp_path / "drafts")
    assert draft["hp_roll"] == 8


def test_max_hp_rule_hides_roll_button(client, tmp_path):
    save_settings(client._settings_path, RuleSet(max_hp_at_l1=True))
    draft_id = _start_draft_with(client, tmp_path / "drafts")
    r = client.get(f"/wizard/{draft_id}/hp")
    # Roll button form action should not be present
    assert f'/wizard/{draft_id}/hp/roll' not in r.text


def test_max_hp_rule_persists_to_character(client, tmp_path):
    save_settings(client._settings_path, RuleSet(max_hp_at_l1=True))
    char_id = _run_wizard_to_completion(client, tmp_path / "drafts")
    spec = load_character(char_id, tmp_path / "characters")
    # Fighter d8 → 8 on the die + CON 14 (mod +1) = 9 max HP
    assert spec.classes[0].hp_rolls == [8]
    assert spec.ruleset.max_hp_at_l1 is True


# ── Reroll 1s & 2s ─────────────────────────────────────────────────────────

def test_reroll_rule_shows_banner(client, tmp_path):
    save_settings(client._settings_path, RuleSet(reroll_1s_2s_hp_l1=True))
    draft_id = _start_draft_with(client, tmp_path / "drafts")
    r = client.get(f"/wizard/{draft_id}/hp")
    assert "Reroll 1s &amp; 2s at L1" in r.text


def test_reroll_rule_never_yields_1_or_2_after_many_rolls(client, tmp_path):
    """Statistical: with reroll active, hp_roll on a d8 must stay ≥ 3."""
    from aose.characters import load_draft
    save_settings(client._settings_path, RuleSet(reroll_1s_2s_hp_l1=True))
    draft_id = _start_draft_with(client, tmp_path / "drafts")
    for _ in range(40):
        client.post(f"/wizard/{draft_id}/hp/roll")
        draft = load_draft(draft_id, tmp_path / "drafts")
        assert draft["hp_roll"] >= 3, f"got {draft['hp_roll']} which should have been rerolled"


def test_reroll_rule_still_shows_roll_button(client, tmp_path):
    """Reroll rule keeps the user in control of clicking Roll."""
    save_settings(client._settings_path, RuleSet(reroll_1s_2s_hp_l1=True))
    draft_id = _start_draft_with(client, tmp_path / "drafts")
    r = client.get(f"/wizard/{draft_id}/hp")
    assert f'/wizard/{draft_id}/hp/roll' in r.text


# ── No-rule baseline (regression guard) ───────────────────────────────────

def test_default_ruleset_keeps_normal_hp_roll_flow(client, tmp_path):
    """With no HP rules, the user still clicks Roll and any 1-8 result is valid."""
    from aose.characters import load_draft
    draft_id = _start_draft_with(client, tmp_path / "drafts")
    r = client.get(f"/wizard/{draft_id}/hp")
    # No rule banner
    assert "Max HP at L1" not in r.text
    assert "Reroll 1s" not in r.text
    # hp_roll not auto-populated
    draft = load_draft(draft_id, tmp_path / "drafts")
    assert "hp_roll" not in draft


# ── Creation method + Basic enforcement (Slice 1) ─────────────────────────

from aose.web.settings_routes import parse_ruleset_from_form


class _Form(dict):
    """Minimal stand-in for a Starlette FormData: supports `in` and `.get`.
    The parser only uses membership tests and `.get`, so a dict suffices."""


def test_parser_advanced_method_sets_separate_race_class_true():
    rs = parse_ruleset_from_form(_Form({"creation_method": "advanced"}))
    assert rs.separate_race_class is True


def test_parser_basic_method_sets_separate_race_class_false():
    rs = parse_ruleset_from_form(_Form({"creation_method": "basic"}))
    assert rs.separate_race_class is False


def test_parser_missing_method_defaults_to_advanced():
    rs = parse_ruleset_from_form(_Form({}))
    assert rs.separate_race_class is True


def test_parser_basic_forces_advanced_only_rules_off():
    """Even if multiclassing / lift_demihuman_restrictions are posted true,
    Basic mode forces them off server-side."""
    rs = parse_ruleset_from_form(_Form({
        "creation_method": "basic",
        "multiclassing": "on",
        "lift_demihuman_restrictions": "on",
    }))
    assert rs.separate_race_class is False
    assert rs.multiclassing is False
    assert rs.lift_demihuman_restrictions is False


def test_parser_advanced_keeps_advanced_only_rules():
    rs = parse_ruleset_from_form(_Form({
        "creation_method": "advanced",
        "multiclassing": "on",
        "lift_demihuman_restrictions": "on",
    }))
    assert rs.multiclassing is True
    assert rs.lift_demihuman_restrictions is True
