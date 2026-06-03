"""Tests for the leveling-up engine, the XP grant endpoint, and the
level-up routes."""
import random
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character, save_settings
from aose.data.loader import GameData
from aose.engine.hp import max_hp, hp_remainder
from aose.engine.leveling import (
    all_advancement,
    class_advancement,
    grant_xp,
    level_up,
)
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# All prime-requisite scores sit in the 9–12 band → 1.00× XP multiplier, so XP
# awards land unscaled and the class XP thresholds read cleanly.  Tests that
# care about prime-req scaling set their own abilities.
_NEUTRAL_ABILITIES = {"STR": 12, "INT": 12, "WIS": 12, "DEX": 12, "CON": 14, "CHA": 10}


def _spec(level=1, xp=0, hp_rolls=None, multi=False, ruleset=None, abilities=None):
    if ruleset is None:
        ruleset = RuleSet(multiclassing=True) if multi else RuleSet()
    n = 2 if multi else 1
    share = xp // n  # each class starts with its own per-class XP
    if multi:
        classes = [
            ClassEntry(class_id="fighter", level=level, xp=share, hp_rolls=hp_rolls or [8]),
            ClassEntry(class_id="magic_user", level=level, xp=share, hp_rolls=hp_rolls or [4]),
        ]
    else:
        classes = [ClassEntry(class_id="fighter", level=level, xp=share,
                              hp_rolls=hp_rolls or [8])]
    return CharacterSpec(
        name="Test",
        abilities=abilities or dict(_NEUTRAL_ABILITIES),
        race_id="dwarf" if not multi else "elf",
        classes=classes,
        alignment="law",
        ruleset=ruleset,
    )


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


# ── grant_xp ────────────────────────────────────────────────────────────────

def test_grant_xp_single_class_adds_to_the_one_class(data):
    spec = _spec(xp=500)
    grant_xp(spec, data, 1500)
    assert spec.classes[0].xp == 2000


def test_grant_xp_multi_splits_evenly(data):
    spec = _spec(xp=0, multi=True)
    grant_xp(spec, data, 1000)
    assert [e.xp for e in spec.classes] == [500, 500]


def test_grant_xp_multi_integer_truncates(data):
    spec = _spec(xp=0, multi=True)
    grant_xp(spec, data, 999)  # 999 // 2 = 499 per class
    assert [e.xp for e in spec.classes] == [499, 499]


def test_grant_xp_applies_prime_requisite_multiplier(data):
    # Fighter prime req STR 16 → +10% XP; award 1000 → +1100.
    spec = _spec(xp=0, abilities={**_NEUTRAL_ABILITIES, "STR": 16})
    grant_xp(spec, data, 1000)
    assert spec.classes[0].xp == 1100


def test_grant_xp_negative_clamps_at_zero_without_multiplier(data):
    spec = _spec(xp=100, abilities={**_NEUTRAL_ABILITIES, "STR": 16})
    grant_xp(spec, data, -9999)
    assert spec.classes[0].xp == 0


# ── class_advancement ──────────────────────────────────────────────────────

def test_advancement_l1_below_threshold(data):
    spec = _spec(level=1, xp=0)
    adv = class_advancement(spec, data, spec.classes[0])
    assert adv.current_level == 1
    assert adv.next_level == 2
    assert adv.next_threshold == 2000
    assert adv.current_xp == 0
    assert adv.can_level is False
    assert adv.at_max is False


def test_advancement_at_exact_threshold_can_level(data):
    spec = _spec(level=1, xp=2000)
    adv = class_advancement(spec, data, spec.classes[0])
    assert adv.can_level is True


def test_advancement_well_past_threshold_still_only_one_level(data):
    """Even with 100k XP, the next level is only L2 — we don't multi-level."""
    spec = _spec(level=1, xp=100000)
    adv = class_advancement(spec, data, spec.classes[0])
    assert adv.next_level == 2
    assert adv.can_level is True


def test_advancement_at_class_max_blocks_further_levels(data):
    # Fighter max_level is 14; a L14 character cannot advance further.
    spec = _spec(level=14, xp=999999, hp_rolls=[8] * 14)
    adv = class_advancement(spec, data, spec.classes[0])
    assert adv.at_max is True
    assert adv.can_level is False


def test_advancement_respects_race_cap_when_rule_on(data):
    """Synthetic: cap fighter at 2 for dwarves; a L2 dwarf fighter can't go higher."""
    patched_race = data.races["dwarf"].model_copy(update={"class_level_caps": {"fighter": 2}})
    patched = replace(data, races={**data.races, "dwarf": patched_race})
    spec = _spec(level=2, xp=10000, hp_rolls=[8, 8],
                 ruleset=RuleSet(lift_demihuman_restrictions=False))
    adv = class_advancement(spec, patched, spec.classes[0])
    assert adv.at_max is True


def test_advancement_ignores_race_cap_when_rule_off(data):
    patched_race = data.races["dwarf"].model_copy(update={"class_level_caps": {"fighter": 2}})
    patched = replace(data, races={**data.races, "dwarf": patched_race})
    spec = _spec(level=2, xp=10000, hp_rolls=[8, 8],
                 ruleset=RuleSet(lift_demihuman_restrictions=True))
    adv = class_advancement(spec, patched, spec.classes[0])
    assert adv.at_max is False
    assert adv.next_level == 3


# ── level_up mutation ──────────────────────────────────────────────────────

def test_level_up_increments_level_and_appends_hp(data):
    spec = _spec(level=1, xp=2000)
    rng = random.Random(0)
    new_hp = level_up(spec, data, "fighter", rng=rng)
    assert spec.classes[0].level == 2
    assert spec.classes[0].hp_rolls == [8, new_hp]
    assert 1 <= new_hp <= 8


def test_level_up_xp_short_raises(data):
    spec = _spec(level=1, xp=1999)
    with pytest.raises(ValueError, match="Need 2000"):
        level_up(spec, data, "fighter")


def test_level_up_at_max_raises(data):
    spec = _spec(level=14, xp=999999, hp_rolls=[8] * 14)
    with pytest.raises(ValueError, match="maximum level"):
        level_up(spec, data, "fighter")


def test_level_up_unknown_class_raises(data):
    spec = _spec(level=1, xp=2000)
    with pytest.raises(ValueError, match="no class 'cleric'"):
        level_up(spec, data, "cleric")


def test_level_up_multi_advances_one_class_only(data):
    """Multi-class fighter/magic-user: levelling fighter shouldn't touch MU."""
    spec = _spec(level=1, xp=4000, multi=True)  # each class has 2000 → fighter ready, MU not (2500)
    level_up(spec, data, "fighter")
    levels = {e.class_id: e.level for e in spec.classes}
    assert levels == {"fighter": 2, "magic_user": 1}


def test_level_up_multi_blocks_when_class_threshold_higher(data):
    """MU threshold is 2500; with per-class XP 2000 the MU can't level even
    though fighter just did."""
    spec = _spec(level=1, xp=4000, multi=True)
    level_up(spec, data, "fighter")
    with pytest.raises(ValueError, match="Need 2500"):
        level_up(spec, data, "magic_user")


# ── all_advancement ────────────────────────────────────────────────────────

def test_all_advancement_returns_one_per_class(data):
    spec = _spec(level=1, xp=0, multi=True)
    rows = all_advancement(spec, data)
    assert [r.class_id for r in rows] == ["fighter", "magic_user"]


# ── HTTP endpoints ─────────────────────────────────────────────────────────

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


def test_grant_xp_adds(client):
    _seed(client, xp=500)
    r = client.post("/character/test/xp", data={"amount": "1500"})
    assert r.status_code == 303
    assert r.headers["location"] == "/character/test"
    assert load_character("test", client._characters_dir).classes[0].xp == 2000


def test_grant_xp_negative_clamps_at_zero(client):
    _seed(client, xp=100)
    client.post("/character/test/xp", data={"amount": "-9999"})
    assert load_character("test", client._characters_dir).classes[0].xp == 0


def test_grant_xp_missing_character_404s(client):
    r = client.post("/character/nobody/xp", data={"amount": "100"})
    assert r.status_code == 404


def test_level_up_route_advances_class(client):
    _seed(client, level=1, xp=2000)
    r = client.post("/character/test/level-up/fighter")
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.classes[0].level == 2
    assert len(spec.classes[0].hp_rolls) == 2


def test_level_up_route_insufficient_xp_400s(client):
    _seed(client, level=1, xp=500)
    r = client.post("/character/test/level-up/fighter")
    assert r.status_code == 400
    assert "Need 2000" in r.json()["detail"]


def test_level_up_route_unknown_class_400s(client):
    _seed(client, level=1, xp=10000)
    r = client.post("/character/test/level-up/cleric")
    assert r.status_code == 400


def test_level_up_route_max_level_400s(client):
    _seed(client, level=14, xp=999999, hp_rolls=[8] * 14)
    r = client.post("/character/test/level-up/fighter")
    assert r.status_code == 400


# ── Sheet rendering of the new section ────────────────────────────────────

def test_sheet_renders_total_xp_and_thresholds(client):
    _seed(client, level=1, xp=1500)
    r = client.get("/character/test")
    assert "Total XP" in r.text
    assert "1500" in r.text
    assert "2000" in r.text  # next-level threshold


def test_sheet_shows_level_up_button_when_ready(client):
    _seed(client, level=1, xp=2500)
    r = client.get("/character/test")
    assert "Level Up" in r.text
    assert 'action="/character/test/level-up/fighter"' in r.text


def test_sheet_omits_level_up_button_when_short(client):
    _seed(client, level=1, xp=500)
    r = client.get("/character/test")
    assert "/level-up/fighter" not in r.text


def test_sheet_shows_max_level_label(client):
    _seed(client, level=14, xp=999999, hp_rolls=[8] * 14)
    r = client.get("/character/test")
    assert "max level" in r.text.lower()


def test_grant_xp_form_present(client):
    _seed(client, xp=0)
    r = client.get("/character/test")
    assert 'action="/character/test/xp"' in r.text
    assert 'name="amount"' in r.text


# ── End-to-end: grant XP → level up → sheet reflects new level ────────────

def test_full_grant_then_level_flow(client):
    _seed(client, level=1, xp=0)
    client.post("/character/test/xp", data={"amount": "2200"})
    client.post("/character/test/level-up/fighter")
    spec = load_character("test", client._characters_dir)
    assert spec.classes[0].level == 2
    r = client.get("/character/test")
    assert "Fighter 2" in r.text  # class summary


# ── Name-level HP: fixed step, no CON ────────────────────────────────────────

def _fighter_spec(level, hp_rolls, con=14, ruleset=None):
    return CharacterSpec(
        name="Vala",
        abilities={"STR": 12, "INT": 12, "WIS": 12, "DEX": 12, "CON": con, "CHA": 10},
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=level, xp=0, hp_rolls=hp_rolls)],
        alignment="law",
        ruleset=ruleset or RuleSet(),
    )


def test_max_hp_at_name_level_unchanged(data):
    # L9 fighter, CON 14 (+1): 9 rolled events of 8 each + 1 CON each = 9*9 = 81.
    spec = _fighter_spec(9, [8] * 9)
    assert max_hp(spec, data) == 81


def test_max_hp_one_level_past_name_adds_fixed_step_no_con(data):
    # L10 fighter: still 9 rolls (none added past name level) + fixed (10-9)*2 = 2.
    spec = _fighter_spec(10, [8] * 9)
    assert max_hp(spec, data) == 83  # 81 + 2


def test_fixed_step_ignores_con(data):
    # Same as above but CON 18 (+3). Rolled part = 9*(8+3)=99; fixed still +2.
    spec = _fighter_spec(10, [8] * 9, con=18)
    assert max_hp(spec, data) == 101  # 99 + 2 (no CON on the fixed step)


def test_max_hp_at_class_max_full_fixed_run(data):
    # L14 fighter: 9 rolls + (14-9)*2 = 10 fixed. CON +1 -> 9*9 + 10 = 91.
    spec = _fighter_spec(14, [8] * 9)
    assert max_hp(spec, data) == 91


def test_defensive_cap_ignores_overlong_hp_rolls(data):
    # A stale character with 14 rolls at L14 must still count only 9 rolls.
    spec = _fighter_spec(14, [8] * 14)
    assert max_hp(spec, data) == 91  # identical to the 9-roll case


def test_multiclass_fixed_step_divides_and_tracks_fraction(data):
    # Fighter L10 (step 2) + magic_user L10 (step 1), each 9 rolls of value 2.
    # Rolled: creation event sum=4 -> 4/2+1=3; then 8 fighter + 8 MU single
    #   events of 2 each -> (2/2 + 1)=2 apiece, 16 events -> 32; rolled total 35.
    # Fixed: ((10-9)*2 + (10-9)*1) / 2 = 3/2 = 1.5.
    # Total 36.5 -> max_hp 36, remainder 1/2.
    from fractions import Fraction
    spec = CharacterSpec(
        name="Twin",
        abilities={"STR": 12, "INT": 12, "WIS": 12, "DEX": 12, "CON": 14, "CHA": 10},
        race_id="elf",
        classes=[
            ClassEntry(class_id="fighter", level=10, xp=0, hp_rolls=[2] * 9),
            ClassEntry(class_id="magic_user", level=10, xp=0, hp_rolls=[2] * 9),
        ],
        alignment="neutral",
        ruleset=RuleSet(multiclassing=True),
    )
    assert max_hp(spec, data) == 36
    assert hp_remainder(spec, data) == Fraction(1, 2)


# ── level_up past name level ──────────────────────────────────────────────────

def test_level_up_past_name_level_rolls_nothing(data):
    # Fighter at name level (9) with 9 rolls; XP for L10 is 360000.
    spec = _fighter_spec(9, [8] * 9)
    spec.classes[0].xp = 360000
    result = level_up(spec, data, "fighter")
    assert spec.classes[0].level == 10
    assert spec.classes[0].hp_rolls == [8] * 9   # no new roll appended
    assert result == 0                            # no die rolled


def test_level_up_at_name_level_minus_one_still_rolls(data):
    # Leveling 8 -> 9 is the last rolling level; a die is still added.
    spec = _fighter_spec(8, [8] * 8)
    spec.classes[0].xp = 240000
    result = level_up(spec, data, "fighter")
    assert spec.classes[0].level == 9
    assert len(spec.classes[0].hp_rolls) == 9
    assert 1 <= result <= 8
