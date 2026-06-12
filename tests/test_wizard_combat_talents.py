from pathlib import Path

from aose.data.loader import GameData
from aose.web.wizard import (
    _active_choice_groups, _feature_choices_context, _apply_feature_overrides,
    _apply_rule_changes,
)
from aose.models import RuleSet

DATA = GameData.load(Path(__file__).parent.parent / "data")


def _draft(combat=True, prof=False):
    return {
        "ruleset": RuleSet(combat_talents=combat, weapon_proficiency=prof).model_dump(),
        "class_ids": ["fighter"],
        "abilities": {"STR": 12, "INT": 9, "WIS": 9, "DEX": 12, "CON": 12, "CHA": 9},
        "feature_choices": {},
        "choice_params": {},
        "weapon_specialisations": [],
    }


def test_talent_group_hidden_when_rule_off():
    assert all(g.id != "combat_talents"
               for g in _active_choice_groups(_draft(combat=False), DATA))


def test_talent_group_shown_pick_one_at_creation():
    ctx = _feature_choices_context(_draft(), DATA)
    row = next(r for r in ctx["feature_groups"] if r["id"] == "combat_talents")
    assert row["pick"] == 1  # pick_by_level[1]


def test_weapon_specialist_option_hidden_under_proficiency():
    ctx = _feature_choices_context(_draft(prof=True), DATA)
    row = next(r for r in ctx["feature_groups"] if r["id"] == "combat_talents")
    assert all(o["id"] != "weapon_specialist" for o in row["options"])


def test_apply_slayer_pick_records_param():
    from starlette.datastructures import FormData
    draft = _draft()
    form = FormData([("choice_combat_talents", "slayer"), ("param_slayer", "undead")])
    _apply_feature_overrides(draft, form, DATA)
    assert draft["feature_choices"]["combat_talents"] == ["slayer"]
    assert draft["choice_params"]["slayer"] == "undead"


def test_toggling_combat_talents_off_clears_talent_state():
    draft = _draft()
    draft["feature_choices"]["combat_talents"] = ["weapon_specialist"]
    draft["choice_params"] = {}
    draft["weapon_specialisations"] = ["sword"]
    old = RuleSet(combat_talents=True)
    new = RuleSet(combat_talents=False)
    _apply_rule_changes(draft, old, new, DATA)
    assert "combat_talents" not in draft.get("feature_choices", {})
    assert draft.get("weapon_specialisations", []) == []
