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
    save_settings(path, RuleSet(ascending_ac=True, reroll_1s_2s_hp_l1=True))
    rs = load_settings(path)
    assert rs.ascending_ac is True
    assert rs.reroll_1s_2s_hp_l1 is True


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
    assert "Strict Mode" in r.text
    assert "Carcass Crawler Issue 3" in r.text  # a source panel header


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
        "reroll_1s_2s_hp_l1": "on",
        "encumbrance": "detailed",
    })
    assert r.status_code == 303
    assert r.headers["location"] == "/settings?saved=1"

    rs = load_settings(client._settings_path)
    assert rs.ascending_ac is True
    assert rs.reroll_1s_2s_hp_l1 is True
    assert rs.encumbrance == "detailed"
    assert rs.weapon_proficiency is False


def test_post_settings_unchecking_clears_flag(client):
    save_settings(client._settings_path, RuleSet(ascending_ac=True))
    client.post("/settings", data={})  # no checkboxes ticked
    rs = load_settings(client._settings_path)
    assert rs.ascending_ac is False


def test_post_settings_ignores_invalid_radio_choice(client):
    r = client.post("/settings", data={"encumbrance": "made_up_mode"})
    assert r.status_code == 303
    rs = load_settings(client._settings_path)
    # Falls back to the default since the choice was invalid.
    assert rs.encumbrance == "basic"


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
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.post(f"/wizard/{draft_id}/identity", data={"name": name, "alignment": "law"})
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    return char_id


def test_new_character_inherits_active_ruleset(client, tmp_path):
    save_settings(client._settings_path, RuleSet(ascending_ac=True, reroll_1s_2s_hp_l1=True))
    char_id = _run_wizard_to_completion(client, tmp_path / "drafts")
    spec = load_character(char_id, tmp_path / "characters")
    assert spec.ruleset.ascending_ac is True
    assert spec.ruleset.reroll_1s_2s_hp_l1 is True


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
    # Check the combat tab label, not the whole page — item descriptions in the
    # shop expander may legitimately mention "THAC0".
    assert 'class="tab">THAC0' not in r.text


def _start_draft_with(client, drafts_dir):
    """Start a draft and walk it up to the HP step."""
    from aose.characters import load_draft, save_draft
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    return draft_id


# ── Reroll 1s & 2s ─────────────────────────────────────────────────────────

def test_reroll_rule_shows_banner(client, tmp_path):
    save_settings(client._settings_path, RuleSet(reroll_1s_2s_hp_l1=True))
    draft_id = _start_draft_with(client, tmp_path / "drafts")
    r = client.get(f"/wizard/{draft_id}/class_setup")
    assert "Reroll 1s &amp; 2s at L1" in r.text


def test_reroll_rule_never_yields_1_or_2_after_many_rolls(client, tmp_path):
    """Statistical: with reroll active, hp_roll on a d8 must stay ≥ 3."""
    from aose.characters import load_draft
    save_settings(client._settings_path, RuleSet(reroll_1s_2s_hp_l1=True))
    # HP is locked after the first roll, so each iteration uses a fresh draft.
    for _ in range(40):
        fresh = _start_draft_with(client, tmp_path / "drafts")
        client.post(f"/wizard/{fresh}/hp/roll")
        draft = load_draft(fresh, tmp_path / "drafts")
        assert draft["hp_roll"] >= 3, f"got {draft['hp_roll']} which should have been rerolled"


def test_reroll_rule_still_shows_roll_button(client, tmp_path):
    """Reroll rule keeps the user in control of clicking Roll."""
    save_settings(client._settings_path, RuleSet(reroll_1s_2s_hp_l1=True))
    draft_id = _start_draft_with(client, tmp_path / "drafts")
    r = client.get(f"/wizard/{draft_id}/class_setup")
    assert f'/wizard/{draft_id}/hp/roll' in r.text


# ── No-rule baseline (regression guard) ───────────────────────────────────

def test_default_ruleset_keeps_normal_hp_roll_flow(client, tmp_path):
    """With no HP rules, the user still clicks Roll and any 1-8 result is valid."""
    from aose.characters import load_draft
    draft_id = _start_draft_with(client, tmp_path / "drafts")
    r = client.get(f"/wizard/{draft_id}/class_setup")
    # No rule banner
    assert "Max HP at L1" not in r.text
    assert "Reroll 1s" not in r.text
    # hp_roll not auto-populated
    draft = load_draft(draft_id, tmp_path / "drafts")
    assert "hp_roll" not in draft


# ── Parser: checkbox-driven rules ──────────────────────────────────────────

from aose.web.settings_routes import parse_ruleset_from_form


class _Form(dict):
    """Minimal stand-in for a Starlette FormData: supports `in` and `.get`.
    The parser only uses membership tests and `.get`, so a dict suffices."""


def test_parser_separate_race_class_checkbox_on():
    rs = parse_ruleset_from_form(_Form({"separate_race_class": "on"}))
    assert rs.separate_race_class is True


def test_parser_separate_race_class_unchecked_is_basic():
    rs = parse_ruleset_from_form(_Form({}))
    assert rs.separate_race_class is False


def test_parser_basic_forces_descendant_rules_off():
    """separate_race_class off forces its whole subtree off, even if posted."""
    rs = parse_ruleset_from_form(_Form({
        "multiclassing": "on",
        "lift_demihuman_restrictions": "on",
        "human_racial_abilities": "on",
    }))
    assert rs.separate_race_class is False
    assert rs.multiclassing is False
    assert rs.lift_demihuman_restrictions is False
    assert rs.human_racial_abilities is False


def test_parser_lift_off_forces_human_off():
    rs = parse_ruleset_from_form(_Form({
        "separate_race_class": "on",
        "human_racial_abilities": "on",
    }))  # lift not checked
    assert rs.lift_demihuman_restrictions is False
    assert rs.human_racial_abilities is False


def test_parser_full_advanced_chain_kept():
    rs = parse_ruleset_from_form(_Form({
        "separate_race_class": "on",
        "lift_demihuman_restrictions": "on",
        "human_racial_abilities": "on",
        "multiclassing": "on",
    }))
    assert rs.lift_demihuman_restrictions is True
    assert rs.human_racial_abilities is True
    assert rs.multiclassing is True


def test_parser_strict_mode_is_standalone():
    assert parse_ruleset_from_form(_Form({"strict_mode": "on"})).strict_mode is True
    assert parse_ruleset_from_form(_Form({})).strict_mode is False


def test_parser_disables_unchecked_content_categories():
    rs = parse_ruleset_from_form(
        _Form({}),
        content_keys=["carcass_crawler_3:classes", "carcass_crawler_3:equipment"],
    )
    assert set(rs.disabled_content) == {
        "carcass_crawler_3:classes", "carcass_crawler_3:equipment",
    }


def test_parser_keeps_checked_content_categories():
    rs = parse_ruleset_from_form(
        _Form({"content_carcass_crawler_3:classes": "on"}),
        content_keys=["carcass_crawler_3:classes", "carcass_crawler_3:equipment"],
    )
    assert rs.disabled_content == ["carcass_crawler_3:equipment"]


# ── optional_staves rule ───────────────────────────────────────────────────

import re


def test_optional_staves_toggle_rendered(client):
    r = client.get("/settings")
    assert r.status_code == 200
    assert "Spellcasters and Staves" in r.text


def test_optional_staves_round_trips(client):
    # Post the settings form with the toggle on; reload and confirm it persisted.
    r = client.post("/settings", data={"optional_staves": "on"})
    assert r.status_code == 303
    r2 = client.get("/settings")
    # Precise: the optional_staves checkbox itself is rendered checked. (A bare
    # `"checked" in text` would be always-true since other rules default on.)
    assert re.search(
        r'name="optional_staves"[^>]*\bchecked\b', r2.text, re.DOTALL
    )


def _new_draft_with_sources(client, drafts_dir, disabled):
    """Start a draft, confirm abilities, and set disabled_sources directly."""
    from aose.characters import load_draft, save_draft
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, drafts_dir)
    draft["abilities"] = {"STR": 13, "INT": 13, "WIS": 13, "DEX": 13, "CON": 13, "CHA": 13}
    draft["abilities_confirmed"] = True
    draft["ruleset"]["disabled_sources"] = disabled
    save_draft(draft_id, draft, drafts_dir)
    return draft_id


def test_race_step_hides_advanced_when_disabled(client, tmp_path):
    draft_id = _new_draft_with_sources(client, tmp_path / "drafts", ["ose_advanced_fantasy"])
    r = client.get(f"/wizard/{draft_id}/race")
    assert 'value="human"' in r.text
    assert 'value="elf"' not in r.text


def test_race_step_shows_advanced_when_enabled(client, tmp_path):
    draft_id = _new_draft_with_sources(client, tmp_path / "drafts", [])
    r = client.get(f"/wizard/{draft_id}/race")
    assert 'value="elf"' in r.text


def test_class_step_hides_advanced_when_disabled(client, tmp_path):
    # Basic creation so the class step renders without a race pick.
    from aose.characters import load_draft, save_draft
    draft_id = _new_draft_with_sources(client, tmp_path / "drafts", ["ose_advanced_fantasy"])
    draft = load_draft(draft_id, tmp_path / "drafts")
    draft["ruleset"]["separate_race_class"] = False
    save_draft(draft_id, draft, tmp_path / "drafts")
    r = client.get(f"/wizard/{draft_id}/class")
    assert 'value="fighter"' in r.text
    assert 'value="druid"' not in r.text


def test_disabling_content_clears_orphaned_race(client, tmp_path):
    from aose.characters import load_draft, save_draft
    drafts = tmp_path / "drafts"
    draft_id = _new_draft_with_sources(client, drafts, [])
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "elf"})  # advanced race
    draft = load_draft(draft_id, drafts)
    draft["ruleset"]["strict_mode"] = False
    save_draft(draft_id, draft, drafts)
    keys = _content_keys_for(client)
    data = {"separate_race_class": "on"}
    data.update({f"content_{k}": "on" for k in keys
                 if k != "ose_advanced_fantasy:classes"})
    client.post(f"/wizard/{draft_id}/rules", data=data)
    draft = load_draft(draft_id, drafts)
    assert "race_id" not in draft


def test_source_rules_attributes_rules_to_sources():
    from aose.web.settings_routes import SOURCE_RULES, flatten_rule_fields
    classic = flatten_rule_fields(SOURCE_RULES["ose_classic_fantasy"])
    advanced = flatten_rule_fields(SOURCE_RULES["ose_advanced_fantasy"])
    assert "individual_initiative" in classic
    assert "ascending_ac" in classic
    assert "separate_race_class" in advanced
    assert "multiclassing" in advanced
    # strict_mode is standalone, never inside a source tree.
    assert "strict_mode" not in classic and "strict_mode" not in advanced
    # Carcass Crawler issues contribute no optional rules.
    assert SOURCE_RULES.get("carcass_crawler_1", []) == []
    assert SOURCE_RULES.get("carcass_crawler_3", []) == []


def test_source_rules_nesting_expresses_dependencies():
    from aose.web.settings_routes import SOURCE_RULES
    # separate_race_class -> {lift -> human, multiclassing}
    srx = next(n for n in SOURCE_RULES["ose_advanced_fantasy"]
               if n["field"] == "separate_race_class")
    child_fields = {c["field"] for c in srx["children"]}
    assert {"lift_demihuman_restrictions", "multiclassing"} <= child_fields
    lift = next(c for c in srx["children"]
                if c["field"] == "lift_demihuman_restrictions")
    assert any(g["field"] == "human_racial_abilities" for g in lift["children"])


def test_every_rule_field_has_a_description():
    from aose.web.settings_routes import SOURCE_RULES, RULE_DESCRIPTIONS, flatten_rule_fields
    fields = set()
    for tree in SOURCE_RULES.values():
        fields |= set(flatten_rule_fields(tree))
    fields.discard(None)  # choice nodes have no field
    missing = fields - set(RULE_DESCRIPTIONS)
    assert not missing, f"missing descriptions: {missing}"


def test_content_rows_for_source_locks_classic():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.models import RuleSet
    from aose.web.settings_routes import content_rows_for_source
    data = GameData.load(Path(__file__).parent.parent / "data")
    rows = content_rows_for_source(data, "ose_classic_fantasy", RuleSet())
    assert [r["category"] for r in rows] == ["classes", "equipment", "magic_items"]
    assert all(r["locked"] and r["enabled"] for r in rows)
    # Classic's classes row label is just "Classes" (no "& Races").
    assert next(r for r in rows if r["category"] == "classes")["label"] == "Classes"


def test_content_rows_reflect_disabled_content():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.models import RuleSet
    from aose.web.settings_routes import content_rows_for_source
    data = GameData.load(Path(__file__).parent.parent / "data")
    rs = RuleSet(disabled_content=["carcass_crawler_3:equipment"])
    rows = content_rows_for_source(data, "carcass_crawler_3", rs)
    by_cat = {r["category"]: r for r in rows}
    assert by_cat["classes"]["label"] == "Classes & Races"
    assert by_cat["classes"]["enabled"] is True
    assert by_cat["equipment"]["enabled"] is False
    assert all(not r["locked"] for r in rows)


def test_two_weapon_fighting_flag_is_implemented():
    from aose.models import RuleSet
    from aose.web.settings_routes import RULE_LABELS, IMPLEMENTED_RULES
    rs = RuleSet()
    assert rs.two_weapon_fighting is False
    assert "two_weapon_fighting" in RULE_LABELS
    assert "two_weapon_fighting" in IMPLEMENTED_RULES


def test_individual_initiative_attributed_to_classic():
    from aose.web.settings_routes import SOURCE_RULES, flatten_rule_fields, RULE_LABELS
    from aose.models import RuleSet
    assert RuleSet().individual_initiative is False
    assert "individual_initiative" in RULE_LABELS
    assert "individual_initiative" in flatten_rule_fields(
        SOURCE_RULES["ose_classic_fantasy"]
    )


def test_disabling_content_keeps_classic_race(client, tmp_path):
    from aose.characters import load_draft, save_draft
    drafts = tmp_path / "drafts"
    draft_id = _new_draft_with_sources(client, drafts, [])
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    draft = load_draft(draft_id, drafts)
    draft["ruleset"]["strict_mode"] = False
    save_draft(draft_id, draft, drafts)
    keys = _content_keys_for(client)
    data = {"separate_race_class": "on"}
    data.update({f"content_{k}": "on" for k in keys
                 if k != "ose_advanced_fantasy:classes"})
    client.post(f"/wizard/{draft_id}/rules", data=data)
    draft = load_draft(draft_id, drafts)
    assert draft.get("race_id") == "human"


def _content_keys_for(client):
    from aose.web.settings_routes import _content_keys

    class _Req:
        app = client.app
    return _content_keys(_Req())


def test_settings_renders_content_category_checkbox(client):
    r = client.get("/settings")
    assert 'name="content_carcass_crawler_3:equipment"' in r.text
    # Classic content rows are present but disabled (locked on).
    assert re.search(
        r'name="content_ose_classic_fantasy:classes"[^>]*\bdisabled\b', r.text
    )


def test_post_settings_persists_disabled_content_category(client):
    keys = _content_keys_for(client)
    # Re-check every content category except CC3 equipment -> only that disabled.
    data = {f"content_{k}": "on" for k in keys if k != "carcass_crawler_3:equipment"}
    client.post("/settings", data=data)
    rs = load_settings(client._settings_path)
    assert "carcass_crawler_3:equipment" in rs.disabled_content
    assert "carcass_crawler_3:classes" not in rs.disabled_content


def test_race_step_hides_advanced_via_disabled_content(client, tmp_path):
    from aose.characters import load_draft, save_draft
    drafts = tmp_path / "drafts"
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, drafts)
    draft["abilities"] = {"STR": 13, "INT": 13, "WIS": 13, "DEX": 13, "CON": 13, "CHA": 13}
    draft["abilities_confirmed"] = True
    draft["ruleset"]["disabled_content"] = ["ose_advanced_fantasy:classes"]
    save_draft(draft_id, draft, drafts)
    r = client.get(f"/wizard/{draft_id}/race")
    assert 'value="human"' in r.text
    assert 'value="elf"' not in r.text
