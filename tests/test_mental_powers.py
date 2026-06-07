"""Mental Powers caster type + Kineticist class + level-based AC column."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def _data():
    from aose.data.loader import GameData
    return GameData.load(DATA_DIR)


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
    return c


def _save_kineticist(client, level=2, spellbook=None, powers_used=0):
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="Kin",
        abilities={"STR": 10, "INT": 10, "WIS": 13, "DEX": 13, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="kineticist", level=level, hp_rolls=[6],
                            spellbook=list(spellbook or ["kinetic_fist"]),
                            powers_used=powers_used)],
        alignment="neutral",
    )
    save_character("kin1", spec, client._characters_dir)
    return spec


# ── Task 1: Source ─────────────────────────────────────────────────────────

# ── Task 2: Models ─────────────────────────────────────────────────────────

def test_spell_list_accepts_mental_caster_type():
    from aose.models import SpellList
    sl = SpellList(id="x", name="X", caster_type="mental")
    assert sl.caster_type == "mental"


def test_class_level_data_powers_known_defaults_none():
    from aose.models.character_class import ClassLevelData
    ld = ClassLevelData(xp_required=0, thac0=19, saves={"death": 13})
    assert ld.powers_known is None
    ld2 = ClassLevelData(xp_required=0, thac0=19, saves={"death": 13}, powers_known=4)
    assert ld2.powers_known == 4


def test_class_entry_powers_used_defaults_zero():
    from aose.models import ClassEntry
    e = ClassEntry(class_id="x", level=1)
    assert e.powers_used == 0


# ── Task 1 (cont.) ──────────────────────────────────────────────────────────

def test_carcass_crawler_source_loaded_and_non_core():
    data = _data()
    src = data.sources["carcass_crawler_1"]
    assert src.name == "Carcass Crawler Issue 1"
    assert src.publisher == "Necrotic Gnome"
    assert src.core is False


# ── Task 3: Data ────────────────────────────────────────────────────────────

# ── Task 5: Spells engine ──────────────────────────────────────────────────

def _kin_entry(level=1, spellbook=None):
    from aose.models import ClassEntry
    return ClassEntry(class_id="kineticist", level=level, hp_rolls=[6],
                      spellbook=list(spellbook or []))


def test_mental_caster_type_detected():
    from aose.engine import spells
    data = _data()
    cls = data.classes["kineticist"]
    assert spells.caster_type_of(cls, data) == "mental"


def test_powers_known_cap_reads_column():
    from aose.engine import spells
    data = _data()
    cls = data.classes["kineticist"]
    assert spells.powers_known_cap(_kin_entry(level=1), cls) == 3
    assert spells.powers_known_cap(_kin_entry(level=3), cls) == 4


def test_mental_known_and_learnable():
    from aose.engine import spells
    data = _data()
    cls = data.classes["kineticist"]
    entry = _kin_entry(level=1, spellbook=["kinetic_fist"])
    assert [s.id for s in spells.known_spells(entry, cls, data)] == ["kinetic_fist"]
    learnable_ids = {s.id for s in spells.learnable_spells(entry, cls, data)}
    assert "kinetic_fist" not in learnable_ids
    assert "accelerated_motion" in learnable_ids


def test_mental_learn_enforces_cap():
    from aose.engine import spells
    from aose.models import RuleSet
    data = _data()
    cls = data.classes["kineticist"]
    ruleset = RuleSet()
    entry = _kin_entry(level=1, spellbook=["kinetic_fist", "kinetic_leap", "kinetic_wave"])
    with pytest.raises(spells.SpellError):
        spells.learn(entry, cls, data, ruleset, "crush_life")


def test_mental_learn_then_forget():
    from aose.engine import spells
    from aose.models import RuleSet
    data = _data()
    cls = data.classes["kineticist"]
    ruleset = RuleSet()
    entry = spells.learn(_kin_entry(level=1), cls, data, ruleset, "kinetic_fist")
    assert entry.spellbook == ["kinetic_fist"]
    entry = spells.forget(entry, "kinetic_fist")
    assert entry.spellbook == []


def test_mental_beginning_spell_count_is_cap():
    from aose.engine import spells
    from aose.models import RuleSet
    data = _data()
    cls = data.classes["kineticist"]
    assert spells.beginning_spell_count(_kin_entry(level=1), cls, 10, RuleSet()) == 3


# ── Task 7: Sheet view ─────────────────────────────────────────────────────

def _kin_full_spec(level=1, spellbook=None, powers_used=0):
    from aose.models import CharacterSpec, ClassEntry
    return CharacterSpec(
        name="K",
        abilities={"STR": 10, "INT": 10, "WIS": 13, "DEX": 13, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="kineticist", level=level, hp_rolls=[6],
                            spellbook=list(spellbook or []), powers_used=powers_used)],
        alignment="neutral",
    )


def test_spell_views_skip_mental():
    from aose.sheet.view import spells_view, spellbook_view
    data = _data()
    spec = _kin_full_spec(spellbook=["kinetic_fist"])
    assert spells_view(spec, data) == []
    assert spellbook_view(spec, data) == []


def test_mental_powers_view_shape():
    from aose.sheet.view import mental_powers_view
    data = _data()
    spec = _kin_full_spec(level=2, spellbook=["kinetic_fist"], powers_used=1)
    blocks = mental_powers_view(spec, data)
    assert len(blocks) == 1
    b = blocks[0]
    assert b.class_id == "kineticist"
    assert b.cap == 3
    assert [r.power_id for r in b.known] == ["kinetic_fist"]
    assert "kinetic_fist" not in {r.power_id for r in b.addable}
    assert b.can_add is True
    assert b.uses_total == 4
    assert b.uses_used == 1
    assert b.uses_remaining == 3


def test_build_sheet_exposes_mental_powers():
    from aose.sheet.view import build_sheet
    data = _data()
    sheet = build_sheet(_kin_full_spec(spellbook=["kinetic_fist"]), data)
    assert len(sheet.mental_powers) == 1
    assert sheet.spells == []


# ── Task 6: Power pool helpers ─────────────────────────────────────────────

def test_power_pool_is_two_per_level():
    from aose.engine import spells
    assert spells.power_pool(_kin_entry(level=1)) == 2
    assert spells.power_pool(_kin_entry(level=3)) == 6


def test_spend_restore_reset_powers():
    from aose.engine import spells
    e = _kin_entry(level=2)              # pool = 4
    e = spells.spend_power(e)
    e = spells.spend_power(e)
    assert e.powers_used == 2
    e = spells.restore_power(e)
    assert e.powers_used == 1
    e = spells.reset_powers(e)
    assert e.powers_used == 0


def test_spend_beyond_pool_raises():
    from aose.engine import spells
    e = _kin_entry(level=1)              # pool = 2
    e = spells.spend_power(e)
    e = spells.spend_power(e)
    with pytest.raises(spells.SpellError):
        spells.spend_power(e)


def test_restore_below_zero_raises():
    from aose.engine import spells
    with pytest.raises(spells.SpellError):
        spells.restore_power(_kin_entry(level=1))


# ── Task 3 (cont.) ─────────────────────────────────────────────────────────

def test_kineticist_spell_list_loaded():
    data = _data()
    sl = data.spell_lists["kineticist"]
    assert sl.caster_type == "mental"
    assert sl.source == "carcass_crawler_1"


def test_kineticist_powers_loaded():
    data = _data()
    powers = [s for s in data.spells.values()
              if "kineticist" in s.spell_lists]
    assert len(powers) == 9
    assert all(p.source == "carcass_crawler_1" for p in powers)
    assert "accelerated_motion" in data.spells
    assert "throw_weapon" in data.spells


# ── Task 4: AC engine ──────────────────────────────────────────────────────

def _kin_spec(level=1, dex=10, **kw):
    from aose.models import CharacterSpec, ClassEntry
    base = dict(
        name="K",
        abilities={"STR": 10, "INT": 10, "WIS": 13, "DEX": dex, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="kineticist", level=level, hp_rolls=[6])],
        alignment="neutral",
    )
    base.update(kw)
    return CharacterSpec(**base)


def test_class_granted_ac_drives_unarmored_ac():
    from aose.engine.armor_class import unarmored_ac
    data = _data()
    # L5 kineticist: class AC column = 5 descending; DEX 10 -> +0.
    desc, asc = unarmored_ac(_kin_spec(level=5), data)
    assert desc == 5
    assert asc == 14


def test_class_granted_ac_still_applies_dex():
    from aose.engine.armor_class import unarmored_ac
    data = _data()
    # L5 class AC 5, DEX 13 -> +1 -> descending 4.
    desc, _ = unarmored_ac(_kin_spec(level=5, dex=13), data)
    assert desc == 4


def test_class_granted_ac_applies_in_armored_call_too():
    from aose.engine.armor_class import armor_class
    data = _data()
    # Kineticist cannot wear armour; armored call still reflects the class AC.
    desc, _ = armor_class(_kin_spec(level=10), data)
    assert desc == 0  # L10 column is 0


def test_class_with_no_ac_column_unaffected():
    from aose.engine.armor_class import unarmored_ac
    from aose.models import CharacterSpec, ClassEntry
    data = _data()
    spec = CharacterSpec(
        name="F",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=5, hp_rolls=[8])],
        alignment="neutral")
    assert unarmored_ac(spec, data) == (9, 10)  # unchanged baseline


def test_kineticist_class_loaded():
    from aose.models import Ability
    data = _data()
    cls = data.classes["kineticist"]
    assert cls.source == "carcass_crawler_1"
    assert cls.spell_lists == ["kineticist"]
    assert cls.hit_die == "1d6"
    assert cls.armor_allowed == []
    assert cls.shields_allowed is False
    assert cls.prime_requisites == [Ability.DEX, Ability.WIS]
    assert cls.progression[1].powers_known == 3
    assert cls.progression[14].powers_known == 9
    assert cls.progression[1].spell_slots is None


# ── Task 11: Source gating ──────────────────────────────────────────────────

def test_caster_entries_hide_powers_when_source_disabled():
    from aose.web.wizard import _caster_entries
    data = _data()
    draft = {
        "abilities": {"STR": 10, "INT": 10, "WIS": 13, "DEX": 13, "CON": 10, "CHA": 10},
        "class_id": "kineticist",
        "ruleset": {"disabled_sources": ["carcass_crawler_1"]},
        "spellbooks": {},
    }
    rows = _caster_entries(draft, data)
    row = next(r for r in rows if r["class_id"] == "kineticist")
    assert row["candidates"] == []


# ── Task 9: Wizard ──────────────────────────────────────────────────────────

def test_kineticist_triggers_spellcasting_step():
    from aose.web.wizard import _casts_at_level_1
    data = _data()
    assert _casts_at_level_1(data.classes["kineticist"]) is True
    assert _casts_at_level_1(data.classes["fighter"]) is False
    assert _casts_at_level_1(data.classes["magic_user"]) is True


def test_caster_entries_mental_required_and_candidates():
    from aose.web.wizard import _caster_entries
    data = _data()
    draft = {
        "abilities": {"STR": 10, "INT": 10, "WIS": 13, "DEX": 13, "CON": 10, "CHA": 10},
        "class_id": "kineticist",
        "ruleset": {},
        "spellbooks": {},
    }
    rows = _caster_entries(draft, data)
    row = next(r for r in rows if r["class_id"] == "kineticist")
    assert row["caster_type"] == "mental"
    assert row["required"] == 3
    assert len(row["candidates"]) == 9


# ── Task 8: Routes ──────────────────────────────────────────────────────────

def test_power_learn_and_forget_routes(client):
    _save_kineticist(client)
    r = client.post("/character/kin1/powers/learn",
                    data={"class_id": "kineticist", "power_id": "kinetic_leap"})
    assert r.status_code == 303
    spec = load_character("kin1", client._characters_dir)
    assert "kinetic_leap" in spec.classes[0].spellbook
    r = client.post("/character/kin1/powers/forget",
                    data={"class_id": "kineticist", "power_id": "kinetic_fist"})
    assert r.status_code == 303
    assert "kinetic_fist" not in load_character("kin1", client._characters_dir).classes[0].spellbook


def test_power_spend_restore_reset_routes(client):
    _save_kineticist(client, level=2, powers_used=0)
    client.post("/character/kin1/powers/spend", data={"class_id": "kineticist"})
    assert load_character("kin1", client._characters_dir).classes[0].powers_used == 1
    client.post("/character/kin1/powers/restore", data={"class_id": "kineticist"})
    assert load_character("kin1", client._characters_dir).classes[0].powers_used == 0
    client.post("/character/kin1/powers/spend", data={"class_id": "kineticist"})
    client.post("/character/kin1/powers/reset", data={"class_id": "kineticist"})
    assert load_character("kin1", client._characters_dir).classes[0].powers_used == 0


def test_rest_night_resets_power_pool(client):
    _save_kineticist(client, level=2, powers_used=3)
    client.post("/character/kin1/rest/night", data={"mode": "restore"})
    assert load_character("kin1", client._characters_dir).classes[0].powers_used == 0


def test_sheet_renders_mental_powers_section(client):
    _save_kineticist(client)
    html = client.get("/character/kin1").text
    assert "Mental Powers" in html
    assert "/powers/spend" in html
    assert "Kinetic Fist" in html
