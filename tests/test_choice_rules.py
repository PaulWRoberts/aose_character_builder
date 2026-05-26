"""Tests for the two ruleset *choice* groups: ability_roll_method and encumbrance.

Each is a non-bool ruleset field (Literal) — these were the last items left
on the optional-rules matrix when the bool toggles all shipped.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, load_draft, save_draft, save_settings
from aose.data.loader import GameData
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.sheet.view import ENCUMBRANCE_DESCRIPTIONS, build_sheet
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
    client._settings_path = settings_path
    client._drafts_dir = drafts_dir
    client._characters_dir = characters_dir
    return client


# ════════════════════════════════════════════════════════════════════════════
# Encumbrance
# ════════════════════════════════════════════════════════════════════════════

def test_sheet_carries_encumbrance_description():
    data = GameData.load(DATA_DIR)
    spec = CharacterSpec(
        name="X",
        abilities={"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10},
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="law",
        ruleset=RuleSet(encumbrance="detailed"),
    )
    sheet = build_sheet(spec, data)
    assert sheet.encumbrance_mode == "detailed"
    assert sheet.encumbrance_description == ENCUMBRANCE_DESCRIPTIONS["detailed"]


def test_sheet_html_renders_encumbrance_description(tmp_path):
    client = _make_client(tmp_path, RuleSet(encumbrance="none"))
    # Build a character via the wizard with encumbrance=none
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "X"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    r = client.get(f"/character/{char_id}")
    assert ENCUMBRANCE_DESCRIPTIONS["none"] in r.text


# ════════════════════════════════════════════════════════════════════════════
# Ability roll method
# ════════════════════════════════════════════════════════════════════════════

def test_new_wizard_uses_3d6_in_order_by_default(tmp_path):
    client = _make_client(tmp_path, RuleSet())
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    # All scores in 3-18 range
    for v in draft["abilities"].values():
        assert 3 <= v <= 18
    # No arrange pool
    assert "abilities_pool" not in draft


def test_new_wizard_4d6_drop_lowest_pools_higher(tmp_path):
    """Across 30 fresh drafts, 4d6-drop-lowest should beat 3d6 in total."""
    client_4d6 = _make_client(tmp_path / "a", RuleSet(ability_roll_method="4d6_drop_lowest"))
    client_3d6 = _make_client(tmp_path / "b", RuleSet(ability_roll_method="3d6_in_order"))
    def grand_total(client, n):
        total = 0
        for _ in range(n):
            r = client.get("/wizard/new")
            did = r.headers["location"].split("/")[2]
            draft = load_draft(did, client._drafts_dir)
            total += sum(draft["abilities"].values())
        return total
    assert grand_total(client_4d6, 30) > grand_total(client_3d6, 30)


def test_arrange_mode_seeds_pool_on_new_draft(tmp_path):
    client = _make_client(tmp_path, RuleSet(ability_roll_method="3d6_arrange"))
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    assert "abilities_pool" in draft
    assert len(draft["abilities_pool"]) == 6
    # Initial assignment is just the pool in some order — the multiset matches
    assert sorted(draft["abilities"].values()) == sorted(draft["abilities_pool"])


def test_arrange_mode_renders_dropdowns(tmp_path):
    client = _make_client(tmp_path, RuleSet(ability_roll_method="3d6_arrange"))
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    r = client.get(f"/wizard/{draft_id}/abilities")
    assert "Assign to taste" in r.text
    # Six <select> elements, one per ability
    assert r.text.count("arrange-pick") >= 6


def test_arrange_mode_accepts_valid_permutation(tmp_path):
    client = _make_client(tmp_path, RuleSet(ability_roll_method="3d6_arrange"))
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    pool = draft["abilities_pool"]
    # Send a reverse-order assignment — still a valid permutation of the pool
    assignment = dict(zip(["STR", "INT", "WIS", "DEX", "CON", "CHA"], reversed(pool)))
    r = client.post(
        f"/wizard/{draft_id}/abilities",
        data={"name": "Permuted", **{k: str(v) for k, v in assignment.items()}},
    )
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["abilities"] == assignment


def test_arrange_mode_rejects_invalid_assignment(tmp_path):
    """Submitting six copies of the highest pool value must 400."""
    client = _make_client(tmp_path, RuleSet(ability_roll_method="3d6_arrange"))
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    pool = load_draft(draft_id, client._drafts_dir)["abilities_pool"]
    high = max(pool)
    r = client.post(
        f"/wizard/{draft_id}/abilities",
        data={
            "name": "Cheater",
            "STR": str(high), "INT": str(high), "WIS": str(high),
            "DEX": str(high), "CON": str(high), "CHA": str(high),
        },
    )
    assert r.status_code == 400


def test_arrange_mode_reroll_regenerates_pool(tmp_path):
    client = _make_client(tmp_path, RuleSet(ability_roll_method="3d6_arrange"))
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    before = load_draft(draft_id, client._drafts_dir)["abilities_pool"]
    for _ in range(8):
        client.post(f"/wizard/{draft_id}/reroll")
        after = load_draft(draft_id, client._drafts_dir)["abilities_pool"]
        if after != before:
            return
    pytest.fail("Re-roll never produced a new pool in 8 attempts")


def test_non_arrange_mode_rejects_no_arrange_pool(tmp_path):
    """Switching from 3d6-in-order should not leave a stale pool around."""
    client = _make_client(tmp_path, RuleSet(ability_roll_method="3d6_in_order"))
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    assert "abilities_pool" not in draft


def test_non_arrange_post_abilities_works_without_score_fields(tmp_path):
    """In-order mode: the abilities form only needs ``name`` — no STR/INT/... fields."""
    client = _make_client(tmp_path, RuleSet(ability_roll_method="3d6_in_order"))
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    r = client.post(f"/wizard/{draft_id}/abilities", data={"name": "Whatever"})
    assert r.status_code == 303


# ════════════════════════════════════════════════════════════════════════════
# Settings page — no rule should still show "pending"
# ════════════════════════════════════════════════════════════════════════════

def test_choice_group_pending_badge_hidden_when_implemented(tmp_path):
    client = _make_client(tmp_path, RuleSet())
    r = client.get("/settings")
    # Find the ability_roll_method legend area
    idx = r.text.index('Ability Score Method')
    snippet = r.text[idx:idx + 400]
    assert ">pending<" not in snippet
