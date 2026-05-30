"""Tests for the separate_race_class optional rule (race-as-class mode)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, load_draft, save_draft, save_settings
from aose.data.loader import GameData
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.sheet.view import _is_race_as_class, build_sheet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture
def split_client(tmp_path):
    """Default mode: separate race & class (the rule's 'on' state)."""
    return _make_client(tmp_path, RuleSet(separate_race_class=True))


@pytest.fixture
def rac_client(tmp_path):
    """Race-as-class mode (the rule turned off)."""
    return _make_client(tmp_path, RuleSet(separate_race_class=False))


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


# ── Data ───────────────────────────────────────────────────────────────────

def test_dwarf_loads_with_race_locked():
    data = GameData.load(DATA_DIR)
    cls = data.classes["dwarf"]
    assert cls.name == "Dwarf"
    assert cls.race_locked == "dwarf"
    assert cls.max_level == 12


def test_human_race_loads():
    data = GameData.load(DATA_DIR)
    human = data.races["human"]
    assert human.name == "Human"
    assert human.allowed_classes == []  # any class
    assert human.class_level_caps == {}


# ── Step list / navigation ────────────────────────────────────────────────

def _start(client):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    return draft_id


def test_split_mode_abilities_post_goes_to_race(split_client):
    draft_id = _start(split_client)
    r = split_client.post(f"/wizard/{draft_id}/abilities", data={"name": "X"})
    assert r.headers["location"].endswith("/race")


def test_rac_mode_abilities_post_skips_race(rac_client):
    draft_id = _start(rac_client)
    r = rac_client.post(f"/wizard/{draft_id}/abilities", data={"name": "X"})
    assert r.headers["location"].endswith("/class")


def test_rac_mode_breadcrumb_omits_race(rac_client):
    draft_id = _start(rac_client)
    rac_client.post(f"/wizard/{draft_id}/abilities", data={"name": "X"})
    r = rac_client.get(f"/wizard/{draft_id}/class")
    # The breadcrumb is the <ol class="wizard-steps">...</ol> block.
    start = r.text.index('wizard-steps')
    end = r.text.index('</ol>', start)
    breadcrumb = r.text[start:end]
    assert "Race" not in breadcrumb
    assert "Class" in breadcrumb


# ── Class step display ────────────────────────────────────────────────────

def test_split_mode_class_step_hides_race_locked_entries(split_client):
    draft_id = _start(split_client)
    split_client.post(f"/wizard/{draft_id}/abilities", data={"name": "X"})
    split_client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    r = split_client.get(f"/wizard/{draft_id}/class")
    # Dwarf-as-class entry must not appear as a pickable class
    assert 'value="dwarf"' not in r.text
    # But the regular fighter class is present
    assert 'value="fighter"' in r.text


def test_rac_mode_class_step_shows_all_classes(rac_client):
    draft_id = _start(rac_client)
    rac_client.post(f"/wizard/{draft_id}/abilities", data={"name": "X"})
    r = rac_client.get(f"/wizard/{draft_id}/class")
    assert 'value="dwarf"' in r.text
    assert 'value="fighter"' in r.text


def test_rac_mode_class_step_shows_demihuman_badge(rac_client):
    draft_id = _start(rac_client)
    rac_client.post(f"/wizard/{draft_id}/abilities", data={"name": "X"})
    r = rac_client.get(f"/wizard/{draft_id}/class")
    assert "demihuman" in r.text  # the badge text on race-locked cards


# ── Class POST behaviour ──────────────────────────────────────────────────

def test_rac_mode_picking_race_locked_assigns_race(rac_client):
    draft_id = _start(rac_client)
    rac_client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    r = rac_client.post(f"/wizard/{draft_id}/class", data={"class_id": "dwarf"})
    assert r.status_code == 303
    draft = load_draft(draft_id, rac_client._drafts_dir)
    assert draft["race_id"] == "dwarf"
    assert draft["class_id"] == "dwarf"


def test_rac_mode_picking_human_class_defaults_to_human_race(rac_client):
    draft_id = _start(rac_client)
    rac_client.post(f"/wizard/{draft_id}/abilities", data={"name": "Alice"})
    r = rac_client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    assert r.status_code == 303
    draft = load_draft(draft_id, rac_client._drafts_dir)
    assert draft["race_id"] == "human"


def test_split_mode_rejects_race_locked_class_via_post(split_client):
    """Defence-in-depth: a forged POST of dwarf in split mode must 400."""
    draft_id = _start(split_client)
    split_client.post(f"/wizard/{draft_id}/abilities", data={"name": "X"})
    split_client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    r = split_client.post(f"/wizard/{draft_id}/class", data={"class_id": "dwarf"})
    assert r.status_code == 400


def test_rac_mode_low_con_still_rejects_dwarf(rac_client):
    """Dwarf class requires CON 9 — abilities should still gate it."""
    r = rac_client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, rac_client._drafts_dir)
    draft["abilities"] = {"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 5, "CHA": 10}
    save_draft(draft_id, draft, rac_client._drafts_dir)
    rac_client.post(f"/wizard/{draft_id}/abilities", data={"name": "Weakling"})
    r = rac_client.post(f"/wizard/{draft_id}/class", data={"class_id": "dwarf"})
    assert r.status_code == 400


# ── Sheet rendering ───────────────────────────────────────────────────────

def _dwarf_spec() -> CharacterSpec:
    return CharacterSpec(
        name="Thorin",
        abilities={"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10},
        race_id="dwarf",
        classes=[ClassEntry(class_id="dwarf", level=1, hp_rolls=[8])],
        alignment="law",
        ruleset=RuleSet(separate_race_class=False),
    )


def test_race_as_class_flag_true_for_dwarf_as_class():
    data = GameData.load(DATA_DIR)
    assert _is_race_as_class(_dwarf_spec(), data) is True


def test_race_as_class_flag_false_for_split_dwarf_fighter():
    data = GameData.load(DATA_DIR)
    spec = CharacterSpec(
        name="Thorin",
        abilities={"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10},
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="law",
        ruleset=RuleSet(),
    )
    assert _is_race_as_class(spec, data) is False


def test_sheet_class_summary_for_dwarf_as_class():
    data = GameData.load(DATA_DIR)
    sheet = build_sheet(_dwarf_spec(), data)
    assert sheet.class_summary == "Dwarf 1"
    assert sheet.race_name == "Dwarf"
    assert sheet.race_as_class is True


def test_sheet_subtitle_omits_race_for_race_as_class(rac_client):
    draft_id = _start(rac_client)
    rac_client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    rac_client.post(f"/wizard/{draft_id}/class", data={"class_id": "dwarf"})
    rac_client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    rac_client.post(f"/wizard/{draft_id}/hp/roll")
    rac_client.post(f"/wizard/{draft_id}/hp")
    r = rac_client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    r = rac_client.get(f"/character/{char_id}")
    # Subtitle should be just "Dwarf 1 · Lawful" — not "Dwarf · Dwarf 1 · Lawful"
    # i.e. no double Dwarf in the subtitle.
    subtitle_start = r.text.index('class="subtitle"')
    subtitle_end = r.text.index("</p>", subtitle_start)
    subtitle = r.text[subtitle_start:subtitle_end]
    assert subtitle.count("Dwarf") == 1


def test_sheet_subtitle_keeps_race_in_split_mode(split_client):
    draft_id = _start(split_client)
    split_client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    split_client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    split_client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    split_client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    split_client.post(f"/wizard/{draft_id}/hp/roll")
    split_client.post(f"/wizard/{draft_id}/hp")
    r = split_client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    r = split_client.get(f"/character/{char_id}")
    # Subtitle should be "Dwarf · Fighter 1 · Lawful"
    assert "Dwarf" in r.text and "Fighter 1" in r.text


# ── End-to-end ────────────────────────────────────────────────────────────

def test_full_race_as_class_flow_creates_character(rac_client):
    draft_id = _start(rac_client)
    rac_client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    r = rac_client.post(f"/wizard/{draft_id}/class", data={"class_id": "dwarf"})
    assert r.status_code == 303
    rac_client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    rac_client.post(f"/wizard/{draft_id}/hp/roll")
    rac_client.post(f"/wizard/{draft_id}/hp")
    r = rac_client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    spec = load_character(char_id, rac_client._characters_dir)
    assert spec.race_id == "dwarf"
    assert spec.classes[0].class_id == "dwarf"
    assert spec.ruleset.separate_race_class is False
