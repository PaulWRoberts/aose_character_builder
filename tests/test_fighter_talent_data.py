from pathlib import Path

from aose.data.loader import GameData

DATA = GameData.load(Path(__file__).parent.parent / "data")


def test_fighter_has_combat_talents_group():
    fighter = DATA.classes["fighter"]
    g = next(g for g in fighter.feature_choices if g.id == "combat_talents")
    assert g.requires_rule == "combat_talents"
    assert g.pick_by_level == {1: 1, 5: 2, 10: 3}
    ids = {o.id for o in g.options}
    assert ids == {"cleave", "defender", "leader", "main_gauche", "slayer", "weapon_specialist"}


def test_slayer_option_has_text_param_and_conditional_modifiers():
    g = next(g for g in DATA.classes["fighter"].feature_choices if g.id == "combat_talents")
    slayer = next(o for o in g.options if o.id == "slayer")
    assert slayer.param.kind == "text"
    conds = {m.condition for m in slayer.granted_modifiers}
    assert conds == {"vs {param}"}
    assert {m.target for m in slayer.granted_modifiers} == {"attack", "damage"}


def test_weapon_specialist_excluded_under_proficiency_rule():
    g = next(g for g in DATA.classes["fighter"].feature_choices if g.id == "combat_talents")
    ws = next(o for o in g.options if o.id == "weapon_specialist")
    assert ws.excluded_when_rule == "weapon_proficiency"
    assert ws.param.kind == "weapon"
