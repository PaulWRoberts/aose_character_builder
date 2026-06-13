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


def test_toggle_cantrips_off_clears_level_zero():
    from aose.models import RuleSet
    data = GameData.load(DATA_DIR)
    draft = _mu_draft()
    draft["spellbooks"] = {"magic_user": ["cantrip_spark", "magic_user_magic_missile"]}
    wizard._apply_rule_changes(draft, RuleSet(cantrips=True), RuleSet(cantrips=False), data)
    book = draft["spellbooks"]["magic_user"]
    assert "cantrip_spark" not in book
    assert "magic_user_magic_missile" in book
