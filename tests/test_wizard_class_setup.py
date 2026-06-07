"""Slice 5 (Class Setup / P6): human_racial_abilities flag, Human optional
ability modifiers, Blessed + locked HP, and the consolidated class_setup step."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_draft, save_draft, save_settings
from aose.data.loader import GameData
from aose.models import Ability, RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def _make_client(tmp_path, ruleset=None):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True)
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, ruleset or RuleSet())
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._drafts_dir = drafts_dir
    client._characters_dir = characters_dir
    client._settings_path = settings_path
    return client


def _new_draft(client):
    r = client.get("/wizard/new")
    return r.headers["location"].split("/")[2]


def _set_abilities(client, draft_id, abilities):
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = abilities
    save_draft(draft_id, draft, client._drafts_dir)


# Strong scores so any race/class passes requirements.
_GOOD = {"STR": 13, "INT": 13, "WIS": 13, "DEX": 13, "CON": 13, "CHA": 13}


def _rules_form(**overrides):
    """POST body for /rules matching RuleSet() defaults (Advanced)."""
    data = {"encumbrance": "basic", "creation_method": "advanced",
            "strict_mode": "on"}
    for k, v in overrides.items():
        if v is None:
            data.pop(k, None)
        else:
            data[k] = v
    return data


# ── Task 1: flag gating ────────────────────────────────────────────────────

def test_flag_defaults_off():
    assert RuleSet().human_racial_abilities is False


def test_flag_forced_off_without_lift(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    # Advanced but lift NOT checked -> flag must be forced off.
    client.post(f"/wizard/{draft_id}/rules",
                data=_rules_form(human_racial_abilities="on"))
    rs = load_draft(draft_id, client._drafts_dir)["ruleset"]
    assert rs["human_racial_abilities"] is False


def test_flag_forced_off_in_basic(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(
        creation_method="basic", lift_demihuman_restrictions="on",
        human_racial_abilities="on"))
    rs = load_draft(draft_id, client._drafts_dir)["ruleset"]
    assert rs["human_racial_abilities"] is False


def test_flag_enabled_with_advanced_and_lift(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(
        lift_demihuman_restrictions="on", human_racial_abilities="on"))
    rs = load_draft(draft_id, client._drafts_dir)["ruleset"]
    assert rs["human_racial_abilities"] is True


def test_flag_renders_in_advanced_options(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    r = client.get(f"/wizard/{draft_id}/rules")
    assert 'name="human_racial_abilities"' in r.text


def test_flag_no_pending_badge(tmp_path):
    client = _make_client(tmp_path)
    r = client.get("/settings")
    assert "rule-pending" not in r.text
    assert ">pending<" not in r.text


# ── Task 2: Human optional ability modifiers ───────────────────────────────

from aose.engine.ability_mods import apply_racial_modifiers


def test_human_optional_modifiers_loaded(data):
    human = data.races["human"]
    assert human.optional_ability_modifiers == {Ability.CHA: 1, Ability.CON: 1}


def test_non_human_has_no_optional_modifiers(data):
    for rid in ("elf", "dwarf", "halfling"):
        assert data.races[rid].optional_ability_modifiers == {}


def test_apply_includes_optional_when_requested(data):
    base = {"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10}
    human = data.races["human"]
    without = apply_racial_modifiers(base, human, include_optional=False)
    with_opt = apply_racial_modifiers(base, human, include_optional=True)
    assert without["CON"] == 10 and without["CHA"] == 10
    assert with_opt["CON"] == 11 and with_opt["CHA"] == 11


def test_optional_modifiers_clamp_at_18(data):
    base = {"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 18, "CHA": 18}
    human = data.races["human"]
    result = apply_racial_modifiers(base, human, include_optional=True)
    assert result["CON"] == 18 and result["CHA"] == 18


def test_post_racial_applies_optional_only_when_flag_on(tmp_path):
    # Flag on -> human CON/CHA +1 reflected in the adjust step's post-racial row.
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(
        lift_demihuman_restrictions="on", human_racial_abilities="on"))
    _set_abilities(client, draft_id, dict(_GOOD))
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    r = client.get(f"/wizard/{draft_id}/adjust")
    # CON row shows 14 (13 + 1); CHA row shows 14.
    assert "14" in r.text


def test_post_racial_no_optional_when_flag_off(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form())  # flag off
    _set_abilities(client, draft_id, dict(_GOOD))
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    from aose.web.wizard import _post_racial_abilities
    draft = load_draft(draft_id, client._drafts_dir)
    pr = _post_racial_abilities(draft, GameData.load(DATA_DIR))
    assert pr["CON"] == 13 and pr["CHA"] == 13


# ── Task 3: Blessed / locked HP roll helper ────────────────────────────────

import random
from aose.engine.dice import roll_first_level_hp


def test_non_blessed_single_rolls_once():
    rng = random.Random(1)
    result = roll_first_level_hp(["1d8"], blessed=False, min_die=1, rng=rng)
    # One class -> one roll; reproduce the exact sequence the helper consumed.
    expected = random.Random(1).randint(1, 8)
    assert result == [expected]


def test_blessed_single_keeps_higher():
    # With seed 1 the first two d8 rolls are A then B; helper keeps max(A, B).
    probe = random.Random(1)
    a = probe.randint(1, 8)
    b = probe.randint(1, 8)
    result = roll_first_level_hp(["1d8"], blessed=True, min_die=1,
                                 rng=random.Random(1))
    assert result == [max(a, b)]
    assert a != b  # seed 1 yields distinct rolls so the test is meaningful


def test_blessed_multi_keeps_better_complete_set():
    # Two classes (d8, d4). Blessed rolls set A (two dice) then set B (two dice)
    # and keeps the set with the larger SUM — never a cross-set cherry-pick.
    probe = random.Random(7)
    a = [probe.randint(1, 8), probe.randint(1, 4)]
    b = [probe.randint(1, 8), probe.randint(1, 4)]
    winner = a if sum(a) >= sum(b) else b
    result = roll_first_level_hp(["1d8", "1d4"], blessed=True, min_die=1,
                                 rng=random.Random(7))
    assert result == winner
    # Prove the cross-set cherry-pick (max per die) is NOT what we returned,
    # for a seed where it would differ.
    cherry = [max(a[0], b[0]), max(a[1], b[1])]
    if cherry != winner:
        assert result != cherry


def test_blessed_tie_keeps_first_set():
    # Construct a tie via a fake RNG yielding set A sum == set B sum.
    class _FakeRng:
        def __init__(self, seq):
            self.seq = list(seq)
        def randint(self, lo, hi):
            return self.seq.pop(0)
    # set A = [5, 2] (sum 7), set B = [3, 4] (sum 7) -> keep A.
    fake = _FakeRng([5, 2, 3, 4])
    result = roll_first_level_hp(["1d8", "1d4"], blessed=True, min_die=1, rng=fake)
    assert result == [5, 2]


def test_reroll_min_die_applies():
    # min_die=3 must never yield 1 or 2 on any die across many rolls.
    rng = random.Random(123)
    for _ in range(60):
        result = roll_first_level_hp(["1d8", "1d4"], blessed=True, min_die=3, rng=rng)
        assert all(v >= 3 for v in result)


# ── Task 4: Blessed + locked HP via the roll route ─────────────────────────

def _drive_to_class_setup(client, draft_id, race="human", cls="fighter",
                          flag=False, abilities=None):
    rules = (_rules_form(lift_demihuman_restrictions="on", human_racial_abilities="on")
             if flag else _rules_form())
    client.post(f"/wizard/{draft_id}/rules", data=rules)
    _set_abilities(client, draft_id, dict(abilities or _GOOD))
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": race})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": cls})
    client.post(f"/wizard/{draft_id}/adjust", data={})


def test_hp_locked_after_first_roll(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id)
    r1 = client.post(f"/wizard/{draft_id}/hp/roll")
    assert r1.status_code == 303
    first = load_draft(draft_id, client._drafts_dir)["hp_roll"]
    # A second roll attempt is rejected; the stored roll is unchanged.
    r2 = client.post(f"/wizard/{draft_id}/hp/roll")
    assert r2.status_code == 400
    assert load_draft(draft_id, client._drafts_dir)["hp_roll"] == first


def test_blessed_human_hp_uses_two_sets(tmp_path, monkeypatch):
    import aose.web.wizard as wiz
    captured = {}
    real = wiz.roll_blessed_hp_sets

    def spy(hit_dice, *, min_die, rng=None):
        captured["called"] = True
        return real(hit_dice, min_die=min_die, rng=rng)

    monkeypatch.setattr(wiz, "roll_blessed_hp_sets", spy)
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id, race="human", flag=True)
    client.post(f"/wizard/{draft_id}/hp/roll")
    assert captured.get("called") is True


def test_hp_context_exposes_both_blessed_sets(tmp_path):
    from aose.web.wizard import _hp_context
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id, race="human", flag=True)
    client.post(f"/wizard/{draft_id}/hp/roll")
    draft = load_draft(draft_id, client._drafts_dir)
    assert "hp_blessed_sets" in draft
    ctx = _hp_context(draft, GameData.load(DATA_DIR))
    sets = ctx["blessed_sets"]
    assert len(sets) == 2
    # Exactly one set is flagged higher, and it has the >= total.
    higher = [s for s in sets if s["higher"]]
    assert len(higher) == 1
    assert higher[0]["total"] == max(s["total"] for s in sets)


def test_non_human_not_blessed(tmp_path, monkeypatch):
    import aose.web.wizard as wiz
    captured = {}
    real = wiz.roll_first_level_hp

    def spy(hit_dice, *, blessed, min_die, rng=None):
        captured["blessed"] = blessed
        return real(hit_dice, blessed=blessed, min_die=min_die, rng=rng)

    monkeypatch.setattr(wiz, "roll_first_level_hp", spy)
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    # Elf with the flag on -> Blessed is human-only, so blessed must be False.
    _drive_to_class_setup(client, draft_id, race="elf", cls="fighter", flag=True)
    client.post(f"/wizard/{draft_id}/hp/roll")
    assert captured["blessed"] is False


def test_human_plus_one_con_raises_hp(tmp_path):
    """Effective CON includes Human +1 when the flag is on: HP reflects it."""
    from aose.web.wizard import _draft_to_spec
    from aose.engine.hp import max_hp
    # CON 12 (mod 0) -> 13 (mod +1) with the flag.
    abil = {"STR": 13, "INT": 13, "WIS": 13, "DEX": 13, "CON": 12, "CHA": 13}
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id, race="human", flag=True, abilities=abil)
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/identity", data={"name": "H", "alignment": "law"})
    data = GameData.load(DATA_DIR)
    spec = _draft_to_spec(load_draft(draft_id, client._drafts_dir), data)
    assert spec.abilities["CON"] == 13  # 12 + 1 optional
    # Roll is fixed in storage; HP = roll + effective CON mod (+1), min 1.
    roll = load_draft(draft_id, client._drafts_dir)["hp_roll"]
    assert max_hp(spec, data) == max(1, roll + 1)


# ── Task 5: consolidated step plumbing ─────────────────────────────────────

def _breadcrumb(text):
    start = text.index("wizard-steps")
    return text[start:text.index("</ol>", start)]


def test_breadcrumb_shows_single_class_setup(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id)
    r = client.get(f"/wizard/{draft_id}/class_setup")
    bc = _breadcrumb(r.text)
    assert "HP &amp; Skills" in bc
    assert "Hit Points" not in bc
    assert "Proficiencies" not in bc
    # Exactly one occurrence of the step label in the breadcrumb.
    assert bc.count("HP &amp; Skills") == 1


def test_class_setup_incomplete_until_hp(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id)
    # No HP yet -> equipment bounces back to class_setup.
    r = client.get(f"/wizard/{draft_id}/equipment")
    assert r.status_code == 303
    assert r.headers["location"].endswith("/class_setup")
    client.post(f"/wizard/{draft_id}/hp/roll")
    # HP rolled, no prof/spells required -> past class_setup, now needs identity.
    r = client.get(f"/wizard/{draft_id}/equipment")
    assert r.status_code == 303
    assert r.headers["location"].endswith("/identity")


def test_class_setup_incomplete_until_proficiencies(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(weapon_proficiency="on"))
    _set_abilities(client, draft_id, dict(_GOOD))
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    # HP done but proficiencies still required -> equipment bounces back to class_setup.
    r = client.get(f"/wizard/{draft_id}/equipment")
    assert r.status_code == 303 and r.headers["location"].endswith("/class_setup")
    client.post(f"/wizard/{draft_id}/proficiencies",
                data={"weapon": ["sword", "spear", "mace", "hand_axe"]})
    # Proficiencies done -> class_setup complete, now needs identity.
    r = client.get(f"/wizard/{draft_id}/equipment")
    assert r.status_code == 303 and r.headers["location"].endswith("/identity")


def test_flag_toggle_clears_hp_and_adjustments(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id, race="human", flag=True)
    client.post(f"/wizard/{draft_id}/hp/roll")
    assert "hp_roll" in load_draft(draft_id, client._drafts_dir)
    # Disable strict mode so the rules step is navigable (this test checks
    # cascade clearing, not strict-mode enforcement).
    draft = load_draft(draft_id, client._drafts_dir)
    draft["ruleset"]["strict_mode"] = False
    save_draft(draft_id, draft, client._drafts_dir)
    # Turn the flag off — Blessed eligibility + post-racial scores changed.
    client.post(f"/wizard/{draft_id}/rules",
                data=_rules_form(lift_demihuman_restrictions="on"))  # flag now off
    draft = load_draft(draft_id, client._drafts_dir)
    assert "hp_roll" not in draft
    assert "ability_adjustments" not in draft
    assert draft.get("race_id") == "human"  # race survives


# ── Task 6: unified page rendering ─────────────────────────────────────────

def test_page_shows_hp_section_only_for_plain_fighter(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id)  # human fighter, no prof/spells
    r = client.get(f"/wizard/{draft_id}/class_setup")
    assert r.status_code == 200
    assert "Hit Points" in r.text or "Roll" in r.text
    assert "Weapon Proficiencies" not in r.text
    assert "Spells" not in r.text


def test_page_shows_proficiency_section_when_rule_on(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(weapon_proficiency="on"))
    _set_abilities(client, draft_id, dict(_GOOD))
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    r = client.get(f"/wizard/{draft_id}/class_setup")
    assert "Sword" in r.text  # weapon picker present


def test_page_shows_spell_section_for_caster(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, dict(_GOOD))
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form())
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "magic_user"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    r = client.get(f"/wizard/{draft_id}/class_setup")
    assert "Magic Missile" in r.text


def test_continue_advances_only_when_complete(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id)  # human fighter
    # Continue (POST /hp) before HP rolled -> bounce back to class_setup.
    r = client.post(f"/wizard/{draft_id}/hp")
    assert r.status_code == 303 and r.headers["location"].endswith("/class_setup")
    client.post(f"/wizard/{draft_id}/hp/roll")
    r = client.post(f"/wizard/{draft_id}/hp")
    assert r.headers["location"].endswith("/identity")


# ── Task 7: end-to-end through Class Setup ─────────────────────────────────

def test_full_flow_caster_with_proficiencies_and_blessed(tmp_path):
    import json
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(
        weapon_proficiency="on", lift_demihuman_restrictions="on",
        human_racial_abilities="on"))
    _set_abilities(client, draft_id, dict(_GOOD))
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "magic_user"})
    client.post(f"/wizard/{draft_id}/adjust", data={})

    # All three sections on one page.
    page = client.get(f"/wizard/{draft_id}/class_setup")
    assert "Hit Points" in page.text
    assert "Dagger" in page.text          # magic-user proficiency picker
    assert "Magic Missile" in page.text   # arcane spell section

    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/proficiencies", data={"weapon": ["dagger"]})
    client.post(f"/wizard/{draft_id}/spells",
                data={"class_id": "magic_user", "spell_magic_user": ["magic_user_magic_missile"]})

    # Continue now advances to identity.
    cont = client.post(f"/wizard/{draft_id}/hp")
    assert cont.headers["location"].endswith("/identity")

    client.post(f"/wizard/{draft_id}/identity", data={"name": "Gandalf", "alignment": "neutral"})
    client.get(f"/wizard/{draft_id}/equipment")
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    saved = json.loads((client._characters_dir / f"{char_id}.json").read_text())
    assert saved["abilities"]["CON"] == 14  # 13 + 1 optional CON
    assert saved["weapon_proficiencies"] == ["dagger"]
    assert saved["classes"][0]["spellbook"] == ["magic_user_magic_missile"]
