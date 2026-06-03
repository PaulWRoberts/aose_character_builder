"""Tests for the energy-drain engine and route."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character, save_settings
from aose.data.loader import GameData
from aose.engine.energy_drain import energy_drain
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# All prime reqs in the 9-12 band -> 1.00x multiplier, so XP thresholds read cleanly.
_NEUTRAL_ABILITIES = {"STR": 12, "INT": 12, "WIS": 12, "DEX": 12, "CON": 14, "CHA": 10}


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def _spec(level=1, xp=0, hp_rolls=None, multi=False, ruleset=None, abilities=None):
    if ruleset is None:
        ruleset = RuleSet(multiclassing=True) if multi else RuleSet()
    if multi:
        classes = [
            ClassEntry(class_id="fighter", level=level, xp=xp,
                       hp_rolls=hp_rolls or [8] * level),
            ClassEntry(class_id="magic_user", level=level, xp=xp,
                       hp_rolls=hp_rolls or [4] * level),
        ]
    else:
        classes = [ClassEntry(class_id="fighter", level=level, xp=xp,
                              hp_rolls=hp_rolls or [8] * level)]
    return CharacterSpec(
        name="Test",
        abilities=abilities or dict(_NEUTRAL_ABILITIES),
        race_id="dwarf" if not multi else "elf",
        classes=classes,
        alignment="law",
        ruleset=ruleset,
    )


def test_drain_one_level_drops_level_hp_and_xp_new_min(data):
    spec = _spec(level=3, xp=8000, hp_rolls=[8, 5, 6])
    energy_drain(spec, data, levels=1, xp_mode="new_min")
    e = spec.classes[0]
    assert e.level == 2
    assert e.hp_rolls == [8, 5]            # last Hit Die removed
    assert e.xp == 2000                    # fighter L2 threshold (new-level minimum)


def test_drain_one_level_midpoint_lands_in_new_band(data):
    spec = _spec(level=3, xp=8000, hp_rolls=[8, 5, 6])
    energy_drain(spec, data, levels=1, xp_mode="midpoint")
    e = spec.classes[0]
    assert e.level == 2
    # halfway between fighter L2 (2000) and L3 (4000) thresholds
    assert e.xp == 3000


def test_drain_zero_levels_raises(data):
    spec = _spec(level=3, xp=8000)
    with pytest.raises(ValueError, match="at least 1"):
        energy_drain(spec, data, levels=0, xp_mode="new_min")


def test_drain_unknown_xp_mode_raises(data):
    spec = _spec(level=3, xp=8000)
    with pytest.raises(ValueError, match="unknown xp_mode"):
        energy_drain(spec, data, levels=1, xp_mode="bogus")


def test_drain_midpoint_multi_level_raises(data):
    spec = _spec(level=3, xp=8000)
    with pytest.raises(ValueError, match="single-level drain"):
        energy_drain(spec, data, levels=2, xp_mode="midpoint")


def test_drain_multi_level_single_class_cascades(data):
    spec = _spec(level=4, xp=99000, hp_rolls=[8, 5, 6, 7])
    energy_drain(spec, data, levels=2, xp_mode="new_min")
    e = spec.classes[0]
    assert e.level == 2
    assert e.hp_rolls == [8, 5]            # two Hit Dice removed (LIFO)
    assert e.xp == 2000                    # fighter L2 threshold


def test_drain_multi_class_targets_most_recently_leveled(data):
    # Both at L3, neutral abilities (1.0x). magic_user L3 threshold (5000) >
    # fighter L3 (4000), so the magic-user leveled most recently -> drained first.
    spec = _spec(level=3, xp=6000, multi=True,
                 hp_rolls=None)  # fighter [8,8,8], magic_user [4,4,4]
    energy_drain(spec, data, levels=1, xp_mode="new_min")
    levels = {e.class_id: e.level for e in spec.classes}
    assert levels == {"fighter": 3, "magic_user": 2}
    mu = next(e for e in spec.classes if e.class_id == "magic_user")
    assert mu.hp_rolls == [4, 4]           # one Hit Die removed from the MU
    assert mu.xp == 2500                   # magic_user L2 threshold
    fighter = next(e for e in spec.classes if e.class_id == "fighter")
    assert fighter.xp == 6000              # untouched class keeps its XP


def test_drain_below_level_one_kills_single_class(data):
    spec = _spec(level=2, xp=5000, hp_rolls=[8, 5])
    energy_drain(spec, data, levels=3, xp_mode="new_min")  # only 1 level to lose
    e = spec.classes[0]
    assert e.level == 1
    assert e.hp_rolls == [8]               # back to the creation roll only
    assert e.xp == 0
    from aose.engine.hp import current_hp, is_dead
    assert current_hp(spec, data) == 0
    assert is_dead(spec, data) is True


def test_drain_exhausting_all_classes_kills_multi(data):
    spec = _spec(level=2, xp=5000, multi=True)  # fighter+MU both L2
    energy_drain(spec, data, levels=5, xp_mode="new_min")
    assert [e.level for e in spec.classes] == [1, 1]
    assert all(e.xp == 0 for e in spec.classes)
    assert all(len(e.hp_rolls) == 1 for e in spec.classes)
    from aose.engine.hp import is_dead
    assert is_dead(spec, data) is True


def _arcane_spell_at_level(data, level):
    """An arbitrary magic_user spell id at the given spell level, from seed data."""
    for s in sorted(data.spells.values(), key=lambda s: s.id):
        if s.level == level and "magic_user" in s.spell_lists:
            return s.id
    raise AssertionError(f"no magic_user level-{level} spell in seed data")


def test_drain_trims_inaccessible_spells(data):
    from aose.models import SpellSlot
    lvl1 = _arcane_spell_at_level(data, 1)
    lvl2 = _arcane_spell_at_level(data, 2)
    # Magic-user level 3 can cast 2nd-level spells; level 1 cannot.
    spec = _spec(level=3, xp=99000, hp_rolls=[4, 3, 2])
    spec.classes[0] = spec.classes[0].model_copy(update={
        "class_id": "magic_user",
        "spellbook": [lvl1, lvl2],
        "slots": [SpellSlot(level=1, spell_id=lvl1), SpellSlot(level=2, spell_id=lvl2)],
    })
    energy_drain(spec, data, levels=2, xp_mode="new_min")  # -> magic_user L1
    e = spec.classes[0]
    assert e.level == 1
    assert lvl2 not in e.spellbook         # 2nd-level spell no longer accessible
    assert lvl1 in e.spellbook
    assert all(slot.level == 1 for slot in e.slots)   # 2nd-level slot dropped


# ── Route tests ────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, RuleSet())
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    c = TestClient(app, follow_redirects=False)
    c._characters_dir = characters_dir
    return c


def _seed(client, **overrides):
    spec = _spec(**overrides)
    save_character("test", spec, client._characters_dir)
    return spec


def test_energy_drain_route_reduces_level(client):
    _seed(client, level=3, xp=8000, hp_rolls=[8, 5, 6])
    r = client.post("/character/test/energy-drain",
                    data={"levels": "1", "xp_mode": "new_min"})
    assert r.status_code == 303
    assert r.headers["location"] == "/character/test"
    spec = load_character("test", client._characters_dir)
    assert spec.classes[0].level == 2
    assert spec.classes[0].xp == 2000


def test_energy_drain_route_midpoint_multi_level_400s(client):
    _seed(client, level=3, xp=8000)
    r = client.post("/character/test/energy-drain",
                    data={"levels": "2", "xp_mode": "midpoint"})
    assert r.status_code == 400


def test_energy_drain_route_missing_character_404s(client):
    r = client.post("/character/nobody/energy-drain",
                    data={"levels": "1", "xp_mode": "new_min"})
    assert r.status_code == 404


def test_sheet_renders_energy_drain_form(client):
    _seed(client, level=3, xp=8000, hp_rolls=[8, 5, 6])
    r = client.get("/character/test")
    assert 'action="/character/test/energy-drain"' in r.text
    assert 'name="levels"' in r.text
    assert 'name="xp_mode"' in r.text
    assert 'value="midpoint"' in r.text
    assert 'value="new_min"' in r.text


# ── Energy drain across name level ────────────────────────────────────────────

def test_drain_past_name_level_keeps_all_hit_dice(data):
    # L11 fighter has only 9 rolls (none past name level). Draining 11 -> 10 -> 9
    # must NOT pop a real Hit Die — those levels never had one.
    spec = _spec(level=11, xp=480000, hp_rolls=[8] * 9)
    energy_drain(spec, data, 2, "new_min")
    e = spec.classes[0]
    assert e.level == 9
    assert e.hp_rolls == [8] * 9        # all 9 dice intact


def test_drain_across_name_level_boundary_pops_only_real_dice(data):
    # L10 fighter (9 rolls). Drain 2 levels: 10 -> 9 (no pop), 9 -> 8 (pop one).
    spec = _spec(level=10, xp=360000, hp_rolls=[8] * 9)
    energy_drain(spec, data, 2, "new_min")
    e = spec.classes[0]
    assert e.level == 8
    assert e.hp_rolls == [8] * 8        # exactly one real die removed
