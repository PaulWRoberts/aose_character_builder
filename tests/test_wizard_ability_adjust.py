"""Slice 4 (Ability Adjustments): typed restriction field, engine helpers,
and wizard wiring."""
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


# ── Task 1: typed restriction field ───────────────────────────────────────

def test_restricted_classes_forbid_lowering_str(data):
    for cid in ("acrobat", "assassin", "thief"):
        assert data.classes[cid].non_reducible_abilities == [Ability.STR]


def test_other_classes_have_no_restriction(data):
    assert data.classes["fighter"].non_reducible_abilities == []
    assert data.classes["magic_user"].non_reducible_abilities == []


# ── Task 2: adjustable_abilities ───────────────────────────────────────────

from aose.engine.ability_mods import adjustable_abilities


def test_adjustable_fighter(data):
    adj = adjustable_abilities([data.classes["fighter"]])
    assert adj["raisable"] == {"STR"}
    assert adj["lowerable"] == {"INT", "WIS"}


def test_adjustable_magic_user(data):
    adj = adjustable_abilities([data.classes["magic_user"]])
    assert adj["raisable"] == {"INT"}
    assert adj["lowerable"] == {"STR", "WIS"}


def test_adjustable_thief_removes_str_via_restriction(data):
    adj = adjustable_abilities([data.classes["thief"]])
    assert adj["raisable"] == {"DEX"}
    assert adj["lowerable"] == {"INT", "WIS"}  # STR removed by restriction layer


def test_adjustable_multiclass_union(data):
    adj = adjustable_abilities([data.classes["fighter"], data.classes["magic_user"]])
    assert adj["raisable"] == {"STR", "INT"}
    assert adj["lowerable"] == {"WIS"}


# ── Task 3: validate + apply ───────────────────────────────────────────────

from aose.engine.ability_mods import (
    AdjustmentError,
    apply_ability_adjustments,
    validate_ability_adjustments,
)

_POST_RACIAL = {"STR": 12, "INT": 13, "WIS": 13, "DEX": 12, "CON": 12, "CHA": 10}


def test_validate_exact_two_to_one_passes(data):
    validate_ability_adjustments(
        _POST_RACIAL, [data.classes["fighter"]], {"STR": 1, "INT": -2}
    )


def test_validate_odd_single_lower_fails(data):
    # Balance is fine (freed 2 = 2x raised 1) but INT-1, WIS-1 each odd → illegal.
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            _POST_RACIAL, [data.classes["fighter"]],
            {"STR": 1, "INT": -1, "WIS": -1},
        )


def test_validate_even_single_lower_passes(data):
    validate_ability_adjustments(
        _POST_RACIAL, [data.classes["fighter"]], {"STR": 2, "INT": -4}
    )


def test_validate_waste_fails(data):
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            _POST_RACIAL, [data.classes["fighter"]],
            {"STR": 1, "INT": -2, "WIS": -1},
        )


def test_validate_lower_below_nine_fails(data):
    scores = {**_POST_RACIAL, "INT": 10}
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            scores, [data.classes["fighter"]], {"STR": 1, "INT": -2}
        )


def test_validate_raise_above_eighteen_fails(data):
    scores = {**_POST_RACIAL, "STR": 18}
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            scores, [data.classes["fighter"]], {"STR": 1, "INT": -2}
        )


def test_validate_lower_prime_fails(data):
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            _POST_RACIAL, [data.classes["fighter"]], {"INT": 1, "STR": -2}
        )


def test_validate_raise_non_prime_fails(data):
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            _POST_RACIAL, [data.classes["fighter"]], {"WIS": 1, "INT": -2}
        )


def test_validate_lower_restricted_str_fails(data):
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            _POST_RACIAL, [data.classes["thief"]], {"DEX": 1, "STR": -2}
        )


def test_validate_empty_is_valid(data):
    validate_ability_adjustments(_POST_RACIAL, [data.classes["fighter"]], {})


def test_apply_adds_deltas():
    result = apply_ability_adjustments(
        {"STR": 12, "INT": 13, "WIS": 13, "DEX": 12, "CON": 12, "CHA": 10},
        {"STR": 1, "INT": -2},
    )
    assert result["STR"] == 13
    assert result["INT"] == 11
    assert result["WIS"] == 13
    assert result["DEX"] == 12


# ── Task 5/6: wizard integration ───────────────────────────────────────────

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
    return client


def _new_draft(client):
    r = client.get("/wizard/new")
    return r.headers["location"].split("/")[2]


def _set_abilities(client, draft_id, abilities):
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = abilities
    save_draft(draft_id, draft, client._drafts_dir)


# STR 13 so a fighter can spend 2 down (INT/WIS) for 1 up (STR) within floors.
_FIGHTER_ABILITIES = {"STR": 13, "INT": 13, "WIS": 13, "DEX": 12, "CON": 12, "CHA": 10}


def _drive_to_adjust(client, abilities=None, race="human", cls="fighter"):
    """Create a draft and advance it to (but not past) the adjust step."""
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, dict(abilities or _FIGHTER_ABILITIES))
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": race})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": cls})
    return draft_id


def test_adjust_step_between_class_and_class_setup(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    # After picking class, the next incomplete step is adjust (not class_setup/identity).
    r = client.get(f"/wizard/{draft_id}/identity")
    assert r.status_code == 303
    assert r.headers["location"].endswith("/adjust")


def test_adjust_step_present_in_basic_mode(tmp_path):
    client = _make_client(tmp_path, ruleset=RuleSet(separate_race_class=False))
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, dict(_FIGHTER_ABILITIES))
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    r = client.get(f"/wizard/{draft_id}/identity")
    assert r.status_code == 303
    assert r.headers["location"].endswith("/adjust")


def test_adjust_get_renders_scores_and_marks(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    r = client.get(f"/wizard/{draft_id}/adjust")
    assert r.status_code == 200
    # Fighter: STR raisable, INT/WIS lowerable.
    assert "raise_STR" in r.text
    assert "lower_INT" in r.text
    assert "lower_WIS" in r.text
    # STR is a prime — it must not be offered as lowerable.
    assert "lower_STR" not in r.text


def test_adjust_post_valid_stores_and_advances(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    r = client.post(f"/wizard/{draft_id}/adjust", data={
        "raise_STR": "1", "lower_INT": "2",
    })
    assert r.status_code == 303
    assert r.headers["location"].endswith("/class_setup")
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["ability_adjustments"] == {"STR": 1, "INT": -2}


def test_adjust_post_odd_spread_rejected(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    r = client.post(f"/wizard/{draft_id}/adjust", data={
        "raise_STR": "1", "lower_INT": "1", "lower_WIS": "1",
    })
    assert r.status_code == 400


def test_adjust_post_zero_is_valid(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    r = client.post(f"/wizard/{draft_id}/adjust", data={})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["ability_adjustments"] == {}


def test_adjust_post_waste_rejected(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    r = client.post(f"/wizard/{draft_id}/adjust", data={
        "raise_STR": "1", "lower_INT": "2", "lower_WIS": "2",
    })
    assert r.status_code == 400


def test_finalize_reflects_adjustment(tmp_path):
    import json
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    client.post(f"/wizard/{draft_id}/adjust", data={
        "raise_STR": "1", "lower_INT": "2",
    })
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.post(f"/wizard/{draft_id}/identity", data={"name": "Conan", "alignment": "law"})
    client.get(f"/wizard/{draft_id}/equipment")
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    saved = json.loads((client._characters_dir / f"{char_id}.json").read_text())
    assert saved["abilities"]["STR"] == 14  # 13 +1
    assert saved["abilities"]["INT"] == 11  # 13 -2
    assert saved["abilities"]["WIS"] == 13  # unchanged


def test_changing_class_clears_adjustment(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    client.post(f"/wizard/{draft_id}/adjust", data={
        "raise_STR": "1", "lower_INT": "2",
    })
    # Re-pick a different class — the stored adjustment must be cleared.
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "thief"})
    draft = load_draft(draft_id, client._drafts_dir)
    assert "ability_adjustments" not in draft


# ── Task 7: prime-req XP reflects the adjustment ───────────────────────────

from aose.engine.ability_mods import prime_requisite_xp_multiplier


def test_raised_prime_increases_xp_multiplier(data):
    # Fighter prime is STR. Post-racial STR 15 → multiplier 1.05.
    # Raise to 16 (lower INT by 2) → multiplier 1.10.
    post_racial = {"STR": 15, "INT": 13, "WIS": 13, "DEX": 12, "CON": 12, "CHA": 10}
    before = prime_requisite_xp_multiplier(post_racial["STR"])
    creation = apply_ability_adjustments(post_racial, {"STR": 1, "INT": -2})
    after = prime_requisite_xp_multiplier(creation["STR"])
    assert before == 1.05
    assert after == 1.10


# ── Task 2: legal resulting-score options ──────────────────────────────────

def test_adjust_context_legal_options(data):
    from aose.web.wizard import _adjust_context

    draft = {
        "abilities": dict(_FIGHTER_ABILITIES),  # STR/INT/WIS = 13
        "ruleset": RuleSet().model_dump(mode="json"),
        "race_id": "human",
        "class_id": "fighter",
    }
    rows = {r["name"]: r for r in _adjust_context(draft, data)["adjust_rows"]}

    # STR is the prime → raise options step by 1 up to 18, starting at 13.
    assert [o["final"] for o in rows["STR"]["raise_options"]] == list(range(13, 19))
    assert rows["STR"]["raise_options"][0]["amount"] == 0
    assert rows["STR"]["lower_options"] == []  # prime is not lowerable

    # INT is lowerable, floor 9 → resulting scores 13, 11, 9; deltas 0, 2, 4.
    assert [o["final"] for o in rows["INT"]["lower_options"]] == [13, 11, 9]
    assert [o["amount"] for o in rows["INT"]["lower_options"]] == [0, 2, 4]
    assert rows["INT"]["raise_options"] == []  # not a prime → not raisable
