"""HTTP route tests for spell management on the live sheet and in the wizard."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, load_draft, save_character, save_draft
from aose.models import CharacterSpec, ClassEntry, RuleSet, SpellSlot
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


def _save_mu(client, spellbook=None, slots=None, advanced=False):
    spec = CharacterSpec(
        name="Mu", abilities={"STR": 10, "INT": 13, "WIS": 10,
                              "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="magic_user", level=1, hp_rolls=[3],
                            spellbook=spellbook or [], slots=slots or [])],
        alignment="neutral", ruleset=RuleSet(advanced_spell_books=advanced),
    )
    save_character("mu", spec, client._characters_dir)
    return spec


def test_sheet_learn_route(client):
    _save_mu(client, advanced=False)
    r = client.post("/character/mu/spells/learn",
                    data={"class_id": "magic_user", "spell_id": "magic_user_magic_missile"})
    assert r.status_code == 303
    spec = load_character("mu", client._characters_dir)
    assert spec.classes[0].spellbook == ["magic_user_magic_missile"]


def test_sheet_forget_route(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"])
    client.post("/character/mu/spells/forget",
                data={"class_id": "magic_user", "spell_id": "magic_user_magic_missile"})
    assert load_character("mu", client._characters_dir).classes[0].spellbook == []


def test_sheet_renders_spells_section(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"],
             slots=[SpellSlot(level=1, spell_id="magic_user_magic_missile")])
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
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": class_id})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    return draft_id


def test_wizard_skips_spells_for_noncaster(client):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].rsplit("/", 2)[1]
    client.post(f"/wizard/{draft_id}/abilities/roll")
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    r = client.post(f"/wizard/{draft_id}/hp")
    assert r.headers["location"].endswith("/identity")


def test_wizard_arcane_requires_exact_count(client):
    draft_id = _start_caster_draft(client, "magic_user")  # standard -> 1 spell
    r = client.get(f"/wizard/{draft_id}/class_setup")
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
    r = client.get(f"/wizard/{draft_id}/class_setup")
    assert r.status_code == 200 and "know" in r.text.lower()
    r = client.post(f"/wizard/{draft_id}/spells", data={"class_id": "druid"})
    assert r.headers["location"].endswith("/identity")


def test_wizard_finalize_persists_spellbook(client):
    draft_id = _start_caster_draft(client, "magic_user")
    client.post(f"/wizard/{draft_id}/spells",
                data={"class_id": "magic_user", "spell_magic_user": ["magic_user_magic_missile"]})
    client.post(f"/wizard/{draft_id}/identity", data={"name": "Caster", "alignment": "neutral"})
    client.get(f"/wizard/{draft_id}/equipment")
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].rsplit("/", 1)[1]
    spec = load_character(char_id, client._characters_dir)
    assert spec.classes[0].spellbook == ["magic_user_magic_missile"]


# ── Spell-source routes ──────────────────────────────────────────────────────

def _add_scroll(client, spell_ids, caster_type="arcane", kind="scroll"):
    r = client.post("/character/mu/spell-sources/add",
                    data={"kind": kind, "caster_type": caster_type, "name": "",
                          "spell_ids": spell_ids})
    assert r.status_code == 303
    return load_character("mu", client._characters_dir).spell_sources[-1]


def test_add_and_remove_spell_source(client):
    _save_mu(client)
    src = _add_scroll(client, ["magic_user_magic_missile", "magic_user_sleep"])
    assert {e.spell_id for e in src.entries} == {"magic_user_magic_missile", "magic_user_sleep"}
    client.post("/character/mu/spell-sources/remove", data={"instance_id": src.instance_id})
    assert load_character("mu", client._characters_dir).spell_sources == []


def test_add_scroll_ignores_spellbook_list_id(client):
    # Regression: the spellbook "Spell list" <select> is hidden (not disabled) for
    # scrolls, so it still submits a list_id. A scroll spans a whole magic type, so
    # the route must ignore list_id for scrolls — otherwise magic-user spells get
    # rejected against the (alphabetically first) illusionist list.
    _save_mu(client)
    r = client.post("/character/mu/spell-sources/add",
                    data={"kind": "scroll", "caster_type": "arcane", "name": "",
                          "list_id": "illusionist",
                          "spell_ids": ["magic_user_magic_missile", "magic_user_sleep"]})
    assert r.status_code == 303
    src = load_character("mu", client._characters_dir).spell_sources[-1]
    assert {e.spell_id for e in src.entries} == {"magic_user_magic_missile", "magic_user_sleep"}


def test_cast_from_scroll_route(client):
    _save_mu(client)
    src = _add_scroll(client, ["magic_user_magic_missile", "magic_user_sleep"])
    r = client.post("/character/mu/spell-sources/cast",
                    data={"instance_id": src.instance_id,
                          "spell_id": "magic_user_magic_missile"})
    assert r.status_code == 303
    after = load_character("mu", client._characters_dir).spell_sources[0]
    assert [e.spell_id for e in after.entries] == ["magic_user_sleep"]


def test_cast_rejects_caster_type_mismatch(client):
    _save_mu(client)  # arcane caster
    src = _add_scroll(client, ["faerie_fire"], caster_type="divine")
    r = client.post("/character/mu/spell-sources/cast",
                    data={"instance_id": src.instance_id, "spell_id": "faerie_fire"})
    assert r.status_code == 400


def test_copy_route_success(client):
    _save_mu(client, advanced=True)  # INT 13 from _save_mu
    src = _add_scroll(client, ["magic_user_sleep"])
    r = client.post("/character/mu/spell-sources/copy",
                    data={"instance_id": src.instance_id,
                          "class_id": "magic_user", "spell_id": "magic_user_sleep"})
    assert r.status_code == 303
    spec = load_character("mu", client._characters_dir)
    learned = "magic_user_sleep" in spec.classes[0].spellbook
    failed = spec.spell_sources[0].entries[0].copy_failed
    assert learned ^ failed   # exactly one outcome


def test_copy_route_rejected_under_standard_rule(client):
    _save_mu(client, advanced=False)
    src = _add_scroll(client, ["magic_user_sleep"])
    r = client.post("/character/mu/spell-sources/copy",
                    data={"instance_id": src.instance_id,
                          "class_id": "magic_user", "spell_id": "magic_user_sleep"})
    assert r.status_code == 400


def test_sheet_renders_spell_sources_section(client):
    _save_mu(client, advanced=True)
    src = _add_scroll(client, ["magic_user_magic_missile"])
    r = client.get("/character/mu")
    assert r.status_code == 200
    assert "Spell Books &amp; Scrolls" in r.text or "Spell Books & Scrolls" in r.text
    assert "Magic Missile" in r.text
    # cast action present (arcane caster, arcane scroll)
    assert "/spell-sources/cast" in r.text
    # copy action present (advanced rule, spell not yet known)
    assert "/spell-sources/copy" in r.text
