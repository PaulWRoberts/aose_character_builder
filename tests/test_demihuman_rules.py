"""Tests for the merged lift_demihuman_restrictions rule (class restrictions
+ level caps lifted together)."""
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, load_draft, save_draft, save_settings
from aose.data.loader import GameData
from aose.models import CharacterSpec, ClassEntry, Race, RuleSet
from aose.sheet.view import _xp_to_next
from aose.web.app import create_app
from aose.web.wizard import _class_allowed_for_race

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
    client._settings_path = settings_path
    client._drafts_dir = drafts_dir
    client._characters_dir = characters_dir
    return client


# ── Helper: _class_allowed_for_race ────────────────────────────────────────

def _restrictive_race(allowed: list[str]) -> Race:
    return Race(id="x", name="X", allowed_classes=allowed)


def _open_race() -> Race:
    return Race(id="x", name="X", allowed_classes=[])  # human-style


def test_helper_blocks_unlisted_class_when_restrictions_apply():
    race = _restrictive_race(["fighter"])
    assert _class_allowed_for_race("magic_user", race, RuleSet()) is False


def test_helper_allows_listed_class_when_restrictions_apply():
    race = _restrictive_race(["fighter"])
    assert _class_allowed_for_race("fighter", race, RuleSet()) is True


def test_helper_allows_anything_when_restrictions_lifted():
    race = _restrictive_race(["fighter"])
    rs = RuleSet(lift_demihuman_restrictions=True)
    assert _class_allowed_for_race("magic_user", race, rs) is True
    assert _class_allowed_for_race("anything_at_all", race, rs) is True


def test_helper_treats_empty_allowed_as_unrestricted():
    race = _open_race()
    assert _class_allowed_for_race("anything", race, RuleSet()) is True


# ── Wizard: level-cap display ──────────────────────────────────────────────

def _start_through_race(client, race_id="dwarf"):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": race_id})
    return draft_id


def test_class_page_shows_dwarf_cap_by_default(client):
    draft_id = _start_through_race(client)
    r = client.get(f"/wizard/{draft_id}/class")
    # Dwarf caps Fighter at 9
    assert "max level: 9" in r.text


def test_class_page_hides_cap_when_lifted(client):
    save_settings(client._settings_path, RuleSet(lift_demihuman_restrictions=True))
    draft_id = _start_through_race(client)
    r = client.get(f"/wizard/{draft_id}/class")
    assert "max level" not in r.text


# ── Wizard: class restrictions enforcement ────────────────────────────────

def test_class_card_marked_unavailable_when_restricted(client):
    """All data has only 'fighter', which Dwarf allows.  Patch a synthetic
    class into game_data to exercise the rejection path."""
    from aose.models.character_class import CharClass, ClassLevelData

    fake = CharClass(
        id="magic_user",
        name="Magic-User",
        prime_requisites=[],
        max_level=14,
        hit_die="1d4",
        weapons_allowed=[],
        armor_allowed=[],
        shields_allowed=False,
        progression={
            1: ClassLevelData(
                xp_required=0, thac0=19, hit_dice="1d4",
                saves={"death": 13, "wands": 14, "paralysis": 13, "breath": 16, "spells": 15},
            ),
        },
    )
    original = client.app.state.game_data
    patched_classes = dict(original.classes)
    patched_classes["magic_user"] = fake
    client.app.state.game_data = replace(original, classes=patched_classes)
    try:
        draft_id = _start_through_race(client)  # dwarf
        # Dwarf doesn't allow magic_user → POST should 400
        r = client.post(f"/wizard/{draft_id}/class", data={"class_id": "magic_user"})
        assert r.status_code == 400

        # Now lift restrictions and try again
        save_settings(client._settings_path, RuleSet(lift_demihuman_restrictions=True))
        draft_id = _start_through_race(client)
        r = client.post(f"/wizard/{draft_id}/class", data={"class_id": "magic_user"})
        assert r.status_code == 303
    finally:
        client.app.state.game_data = original


# ── Sheet: _xp_to_next respects the rule ──────────────────────────────────

def _dwarf_fighter(level: int, ruleset: RuleSet, hp_rolls: list[int] | None = None) -> CharacterSpec:
    return CharacterSpec(
        name="Thorin",
        abilities={"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10},
        race_id="dwarf",
        classes=[ClassEntry(
            class_id="fighter",
            level=level,
            hp_rolls=hp_rolls or [8] * level,
        )],
        alignment="law",
        ruleset=ruleset,
    )


def test_xp_to_next_at_l1_unaffected_by_either_rule_setting():
    """L1 → L2 is far below any cap, so both settings yield the same result."""
    data = GameData.load(DATA_DIR)
    on = _dwarf_fighter(1, RuleSet(lift_demihuman_restrictions=False))
    off = _dwarf_fighter(1, RuleSet(lift_demihuman_restrictions=True))
    assert _xp_to_next(on, data) == _xp_to_next(off, data) == (2, 2000)


def test_xp_to_next_returns_none_at_race_cap_by_default(tmp_path):
    """Synthetic race that caps fighter at L2 — at L2 we should see no next."""
    data = GameData.load(DATA_DIR)
    patched_race = data.races["dwarf"].model_copy(update={
        "class_level_caps": {"fighter": 2},
    })
    data = replace(data, races={**data.races, "dwarf": patched_race})

    spec = _dwarf_fighter(2, RuleSet(lift_demihuman_restrictions=False))
    assert _xp_to_next(spec, data) == (None, None)


def test_xp_to_next_ignores_race_cap_when_lifted():
    data = GameData.load(DATA_DIR)
    patched_race = data.races["dwarf"].model_copy(update={
        "class_level_caps": {"fighter": 2},
    })
    data = replace(data, races={**data.races, "dwarf": patched_race})

    spec = _dwarf_fighter(2, RuleSet(lift_demihuman_restrictions=True))
    # With limits lifted, the race cap is ignored — class progression gives L3 = 4000 XP
    assert _xp_to_next(spec, data) == (3, 4000)


def test_xp_to_next_still_bounded_by_class_max_when_lifted():
    """Even with limits lifted, the class's own max_level still applies."""
    data = GameData.load(DATA_DIR)
    patched_cls = data.classes["fighter"].model_copy(update={"max_level": 3})
    data = replace(data, classes={**data.classes, "fighter": patched_cls})

    spec = _dwarf_fighter(3, RuleSet(lift_demihuman_restrictions=True))
    assert _xp_to_next(spec, data) == (None, None)


# ── End-to-end: settings → character snapshot ─────────────────────────────

def test_character_snapshots_lift_rule_choice(client):
    save_settings(client._settings_path, RuleSet(lift_demihuman_restrictions=True))
    draft_id = _start_through_race(client)
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.post(f"/wizard/{draft_id}/identity", data={"name": "Thorin", "alignment": "law"})
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    spec = load_character(char_id, client._characters_dir)
    assert spec.ruleset.lift_demihuman_restrictions is True
