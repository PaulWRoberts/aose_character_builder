from pathlib import Path
from aose.data.loader import GameData
from aose.web import wizard

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _mu_draft():
    return {
        "abilities": {"STR": 9, "DEX": 9, "CON": 9, "INT": 12, "WIS": 9, "CHA": 9},
        "class_id": "magic_user",
        "ruleset": {"cantrips": True},
        "spellbooks": {},
    }


def test_caster_entries_exposes_cantrip_block():
    data = GameData.load(DATA_DIR)
    rows = wizard._caster_entries(_mu_draft(), data)
    row = next(r for r in rows if r["class_id"] == "magic_user")
    assert row["cantrip_required"] == 2
    cantrip_ids = {c["id"] for c in row["cantrip_candidates"]}
    assert "cantrip_spark" in cantrip_ids
    # read_magic_cantrip OFF -> it is a selectable cantrip candidate
    assert "read_magic_cantrip" in cantrip_ids


def test_apply_spells_stores_cantrips_with_spells():
    data = GameData.load(DATA_DIR)
    draft = _mu_draft()

    class FakeForm:
        def __init__(self, d): self._d = d
        def getlist(self, k): return self._d.get(k, [])

    form = FakeForm({
        "spell_magic_user": ["magic_user_magic_missile"],
        "cantrip_magic_user": ["cantrip_spark", "cantrip_vanish"],
    })
    wizard._apply_spells(draft, form, data)
    book = draft["spellbooks"]["magic_user"]
    assert "magic_user_magic_missile" in book
    assert "cantrip_spark" in book and "cantrip_vanish" in book


def _mu_draft_rm():
    """Draft with both cantrips and read_magic_cantrip on."""
    d = _mu_draft()
    d["ruleset"] = {"cantrips": True, "read_magic_cantrip": True}
    return d


def test_read_magic_hidden_from_level1_candidates_when_rule_on():
    data = GameData.load(DATA_DIR)
    rows = wizard._caster_entries(_mu_draft_rm(), data)
    row = next(r for r in rows if r["class_id"] == "magic_user")
    candidate_ids = {c["id"] for c in row["candidates"]}
    assert "magic_user_read_magic" not in candidate_ids


def test_read_magic_cantrip_hidden_from_cantrip_candidates_when_auto_granted():
    data = GameData.load(DATA_DIR)
    rows = wizard._caster_entries(_mu_draft_rm(), data)
    row = next(r for r in rows if r["class_id"] == "magic_user")
    cantrip_ids = {c["id"] for c in row["cantrip_candidates"]}
    assert "read_magic_cantrip" not in cantrip_ids


def test_apply_spells_rejects_demoted_read_magic():
    from fastapi import HTTPException
    import pytest
    data = GameData.load(DATA_DIR)
    draft = _mu_draft_rm()

    class FakeForm:
        def __init__(self, d): self._d = d
        def getlist(self, k): return self._d.get(k, [])

    form = FakeForm({
        "spell_magic_user": ["magic_user_read_magic"],  # demoted — must be rejected
        "cantrip_magic_user": ["cantrip_spark", "cantrip_vanish"],
    })
    with pytest.raises(HTTPException):
        wizard._apply_spells(draft, form, data)


def test_toggle_cantrips_off_clears_level_zero():
    from aose.models import RuleSet
    data = GameData.load(DATA_DIR)
    draft = _mu_draft()
    draft["spellbooks"] = {"magic_user": ["cantrip_spark", "magic_user_magic_missile"]}
    wizard._apply_rule_changes(draft, RuleSet(cantrips=True), RuleSet(cantrips=False), data)
    book = draft["spellbooks"]["magic_user"]
    assert "cantrip_spark" not in book
    assert "magic_user_magic_missile" in book
