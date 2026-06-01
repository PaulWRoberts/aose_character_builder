"""HTTP route tests for spell management on the live sheet and in the wizard."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, load_draft, save_character, save_draft
from aose.models import CharacterSpec, ClassEntry, RuleSet
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
        data_dir=DATA_DIR, characters_dir=characters_dir, drafts_dir=drafts_dir,
        examples_dir=examples_dir, settings_path=settings_path,
    )
    c = TestClient(app, follow_redirects=False)
    c._characters_dir = characters_dir
    c._drafts_dir = drafts_dir
    return c


def _save_mu(client, spellbook=None, prepared=None, advanced=False):
    spec = CharacterSpec(
        name="Mu", abilities={"STR": 10, "INT": 13, "WIS": 10,
                              "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="magic_user", level=1, hp_rolls=[3],
                            spellbook=spellbook or [], prepared=prepared or [])],
        alignment="neutral", ruleset=RuleSet(advanced_spell_books=advanced),
    )
    save_character("mu", spec, client._characters_dir)
    return spec


def test_sheet_learn_route(client):
    _save_mu(client, advanced=True)
    r = client.post("/character/mu/spells/learn",
                    data={"class_id": "magic_user", "spell_id": "magic_user_magic_missile"})
    assert r.status_code == 303
    spec = load_character("mu", client._characters_dir)
    assert spec.classes[0].spellbook == ["magic_user_magic_missile"]


def test_sheet_prepare_and_unprepare(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"])
    client.post("/character/mu/spells/prepare",
                data={"class_id": "magic_user", "spell_id": "magic_user_magic_missile"})
    assert load_character("mu", client._characters_dir).classes[0].prepared == ["magic_user_magic_missile"]
    client.post("/character/mu/spells/unprepare",
                data={"class_id": "magic_user", "spell_id": "magic_user_magic_missile"})
    assert load_character("mu", client._characters_dir).classes[0].prepared == []


def test_sheet_prepare_over_cap_400(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"], prepared=["magic_user_magic_missile"])
    r = client.post("/character/mu/spells/prepare",
                    data={"class_id": "magic_user", "spell_id": "magic_user_magic_missile"})
    assert r.status_code == 400


def test_sheet_forget_route(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"])
    client.post("/character/mu/spells/forget",
                data={"class_id": "magic_user", "spell_id": "magic_user_magic_missile"})
    assert load_character("mu", client._characters_dir).classes[0].spellbook == []


def test_sheet_renders_spells_section(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"], prepared=["magic_user_magic_missile"])
    r = client.get("/character/mu")
    assert r.status_code == 200
    assert "Magic Missile" in r.text


def _start_caster_draft(client, class_id, int_score=13, advanced=False):
    """Drive the wizard to just-before the spells step for a single caster."""
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].rsplit("/", 2)[1]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 10, "INT": int_score, "WIS": 13,
                          "DEX": 10, "CON": 10, "CHA": 10}
    draft["ruleset"]["advanced_spell_books"] = advanced
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Caster"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": class_id})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "neutral"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    return draft_id


def test_wizard_skips_spells_for_noncaster(client):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].rsplit("/", 2)[1]
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Grog"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    r = client.post(f"/wizard/{draft_id}/hp")
    assert r.headers["location"].endswith("/equipment")


def test_wizard_arcane_requires_exact_count(client):
    draft_id = _start_caster_draft(client, "magic_user")  # standard -> 1 spell
    r = client.get(f"/wizard/{draft_id}/spells")
    assert r.status_code == 200 and "Magic Missile" in r.text
    bad = client.post(f"/wizard/{draft_id}/spells",
                      data={"class_id": "magic_user",
                            "spell_magic_user": ["magic_user_magic_missile", "magic_user_sleep"]})
    assert bad.status_code == 400
    ok = client.post(f"/wizard/{draft_id}/spells",
                     data={"class_id": "magic_user", "spell_magic_user": ["magic_user_magic_missile"]})
    assert ok.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["spellbooks"]["magic_user"] == ["magic_user_magic_missile"]


def test_wizard_divine_autocompletes(client):
    draft_id = _start_caster_draft(client, "druid", int_score=10)
    r = client.get(f"/wizard/{draft_id}/spells")
    assert r.status_code == 200 and "know" in r.text.lower()
    r = client.post(f"/wizard/{draft_id}/spells", data={"class_id": "druid"})
    assert r.headers["location"].endswith("/equipment")


def test_wizard_finalize_persists_spellbook(client):
    draft_id = _start_caster_draft(client, "magic_user")
    client.post(f"/wizard/{draft_id}/spells",
                data={"class_id": "magic_user", "spell_magic_user": ["magic_user_magic_missile"]})
    client.get(f"/wizard/{draft_id}/equipment")
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].rsplit("/", 1)[1]
    spec = load_character(char_id, client._characters_dir)
    assert spec.classes[0].spellbook == ["magic_user_magic_missile"]
