"""Tests for the per-character /rules step in the wizard.

Confirms that:
  * /new redirects to /rules
  * /rules renders the full toggle/radio matrix
  * POST /rules applies the new ruleset and cascades into downstream clears
    when a structurally-meaningful rule changes
  * Idempotent re-posts leave the draft alone
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_draft, save_draft, save_settings
from aose.models import RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def _make_client(tmp_path, ruleset):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True)
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
    client._drafts_dir = drafts_dir
    client._settings_path = settings_path
    return client


@pytest.fixture
def client(tmp_path):
    return _make_client(tmp_path, RuleSet())


def _start(client):
    r = client.get("/wizard/new")
    return r.headers["location"].split("/")[2]


# Default bool rules that ship as True in RuleSet().  When building form data
# for POST /rules, you have to include these explicitly or you'll be silently
# turning them off (the form-vs-RuleSet semantics — a missing checkbox is False).
_TRUE_DEFAULTS = ("separate_race_class", "demihuman_level_limits",
                  "demihuman_class_restrictions")


def _rules_form(**overrides):
    """Build form data for POST /wizard/{id}/rules that matches the
    RuleSet() defaults, with optional overrides.  Pass ``rule="on"`` to enable
    a bool, ``rule=None`` to disable, or override the radio choices directly."""
    data = {
        "ability_roll_method": "3d6_in_order",
        "encumbrance": "basic",
    }
    for r in _TRUE_DEFAULTS:
        data[r] = "on"
    for k, v in overrides.items():
        if v is None:
            data.pop(k, None)
        else:
            data[k] = v
    return data


# ── /new redirects to /rules ───────────────────────────────────────────────

def test_new_redirects_to_rules(client):
    r = client.get("/wizard/new")
    assert r.status_code == 303
    assert r.headers["location"].endswith("/rules")


def test_rules_is_first_step_in_breadcrumb(client):
    draft_id = _start(client)
    r = client.get(f"/wizard/{draft_id}/rules")
    start = r.text.index('wizard-steps')
    end = r.text.index('</ol>', start)
    breadcrumb = r.text[start:end]
    # "Rules" appears before "Abilities"
    assert breadcrumb.index("Rules") < breadcrumb.index("Abilities")


# ── GET /rules renders the matrix ─────────────────────────────────────────

def test_get_rules_renders_every_bool_toggle(client):
    draft_id = _start(client)
    r = client.get(f"/wizard/{draft_id}/rules")
    for field in ("ascending_ac", "max_hp_at_l1", "weapon_proficiency",
                  "secondary_skills", "multiclassing", "separate_race_class"):
        assert f'name="{field}"' in r.text, f"missing toggle for {field}"


def test_get_rules_renders_choice_radios(client):
    draft_id = _start(client)
    r = client.get(f"/wizard/{draft_id}/rules")
    assert 'name="ability_roll_method"' in r.text
    assert 'value="4d6_drop_lowest"' in r.text
    assert 'name="encumbrance"' in r.text
    assert 'value="detailed"' in r.text


def test_get_rules_prefills_from_settings(tmp_path):
    """The settings.json defaults flow into a fresh draft."""
    client = _make_client(tmp_path, RuleSet(ascending_ac=True, max_hp_at_l1=True))
    draft_id = _start(client)
    r = client.get(f"/wizard/{draft_id}/rules")
    # ascending_ac checkbox should be 'checked'
    idx = r.text.index('name="ascending_ac"')
    snippet = r.text[idx - 10:idx + 80]
    assert "checked" in snippet


# ── POST /rules: no-op preserves abilities ────────────────────────────────

def test_post_rules_unchanged_does_not_reroll(client):
    draft_id = _start(client)
    abilities_before = load_draft(draft_id, client._drafts_dir)["abilities"]
    r = client.post(f"/wizard/{draft_id}/rules", data=_rules_form())
    assert r.status_code == 303
    assert load_draft(draft_id, client._drafts_dir)["abilities"] == abilities_before


def test_post_rules_advances_to_abilities(client):
    draft_id = _start(client)
    r = client.post(f"/wizard/{draft_id}/rules", data=_rules_form())
    assert r.headers["location"].endswith("/abilities")


# ── Cascading clears: ability_roll_method change ──────────────────────────

def test_changing_ability_method_rerolls_and_clears(client):
    draft_id = _start(client)
    # Walk to alignment so there's downstream data
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form())
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    before = load_draft(draft_id, client._drafts_dir)
    assert "class_id" in before

    # Now switch method on the rules step
    client.post(f"/wizard/{draft_id}/rules",
                data=_rules_form(ability_roll_method="4d6_drop_lowest"))
    after = load_draft(draft_id, client._drafts_dir)
    # Abilities re-rolled (different dict, name preserved)
    assert "class_id" not in after
    assert "race_id" not in after
    assert after.get("name") == "Thorin"  # cosmetic data is preserved
    assert after["ruleset"]["ability_roll_method"] == "4d6_drop_lowest"


def test_arrange_mode_via_rules_step_seeds_pool(client):
    draft_id = _start(client)
    client.post(f"/wizard/{draft_id}/rules",
                data=_rules_form(ability_roll_method="3d6_arrange"))
    draft = load_draft(draft_id, client._drafts_dir)
    assert "abilities_pool" in draft
    assert len(draft["abilities_pool"]) == 6


# ── Cascading clears: separate_race_class toggle ──────────────────────────

def test_toggling_separate_race_class_clears_race_and_class(client):
    draft_id = _start(client)
    # Build up to a class (default mode is separate)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form())
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "T"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})

    # Turn separate_race_class OFF
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(separate_race_class=None))
    draft = load_draft(draft_id, client._drafts_dir)
    assert "race_id" not in draft
    assert "class_id" not in draft


# ── Cascading clears: HP rule changes ─────────────────────────────────────

def test_toggling_max_hp_rule_clears_hp_only(client):
    draft_id = _start(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form())
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "T"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    assert "hp_roll" in load_draft(draft_id, client._drafts_dir)

    # Toggle max_hp_at_l1 on
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(max_hp_at_l1="on"))
    draft = load_draft(draft_id, client._drafts_dir)
    assert "hp_roll" not in draft  # cleared so HP step re-rolls under new rule
    # But race + class + alignment survive
    assert draft.get("race_id") == "dwarf"
    assert draft.get("class_id") == "fighter"
    assert draft.get("alignment") == "law"


# ── Cascading clears: weapon_proficiency toggle ───────────────────────────

def test_toggling_weapon_proficiency_clears_only_proficiencies(client):
    draft_id = _start(client)
    # Start with weapon_proficiency ON so we can pick some
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(weapon_proficiency="on"))
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "T"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/proficiencies", data={
        "proficiency_group": ["sword", "axe"],
    })
    assert load_draft(draft_id, client._drafts_dir).get("proficiencies")

    # Turn weapon_proficiency OFF
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form())
    draft = load_draft(draft_id, client._drafts_dir)
    assert "proficiencies" not in draft
    assert draft.get("class_id") == "fighter"  # everything else survives


# ── Cascading clears: turning multiclassing off drops the combo ───────────

def test_turning_multiclassing_off_drops_combo(client):
    draft_id = _start(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(multiclassing="on"))
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 12, "INT": 14, "WIS": 11, "DEX": 14, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Tauriel"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "elf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter,magic_user"})
    assert "class_ids" in load_draft(draft_id, client._drafts_dir)

    client.post(f"/wizard/{draft_id}/rules", data=_rules_form())
    draft = load_draft(draft_id, client._drafts_dir)
    assert "class_ids" not in draft
    assert "class_id" not in draft  # combo cleared entirely


# ── Per-character ruleset persists into the final character ───────────────

def test_per_character_rules_persist_to_saved_character(tmp_path):
    """Setting one ruleset globally and a different one in the wizard:
    the character snapshot should reflect the wizard's choices."""
    from aose.characters import load_character
    client = _make_client(tmp_path, RuleSet())  # global default
    draft_id = _start(client)
    # Override at /rules: turn ascending_ac on
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(ascending_ac="on"))
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    spec = load_character(char_id, tmp_path / "characters")
    assert spec.ruleset.ascending_ac is True
    # Global settings still unchanged
    from aose.characters import load_settings
    assert load_settings(client._settings_path).ascending_ac is False
