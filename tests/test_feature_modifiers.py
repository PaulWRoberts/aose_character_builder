"""Feature-granted modifiers: data-driven class/race bonuses."""
from pathlib import Path

import pytest

from aose.data.loader import GameData

DATA = GameData.load(Path(__file__).parent.parent / "data")


# ── Task 1: models ──────────────────────────────────────────────────────────

def test_granted_modifier_flat_value_ok():
    from aose.models import GrantedModifier
    g = GrantedModifier(target="ac", op="add", value=1)
    assert g.value == 1 and g.scale is None


def test_granted_modifier_scaled_ok():
    from aose.models import GrantedModifier, Scaling
    g = GrantedModifier(target="save:spells", op="add",
                        scale=Scaling(by="ability:CON", table={7: 2, 11: 3}))
    assert g.scale.by == "ability:CON"


def test_granted_modifier_rejects_both_value_and_scale():
    from aose.models import GrantedModifier, Scaling
    with pytest.raises(ValueError):
        GrantedModifier(target="ac", op="add", value=1,
                        scale=Scaling(by="level", table={1: 1}))


def test_granted_modifier_rejects_neither():
    from aose.models import GrantedModifier
    with pytest.raises(ValueError):
        GrantedModifier(target="ac", op="add")


def test_modifier_condition_and_source_default():
    from aose.models import Modifier
    m = Modifier(target="ac", op="add", value=1)
    assert m.condition is None and m.source == ""


def test_features_accept_granted_modifiers():
    from aose.models import ClassFeature, GrantedModifier, RaceFeature
    cf = ClassFeature(id="x", name="X", text="",
                      granted_modifiers=[GrantedModifier(target="ac", op="add", value=1)])
    rf = RaceFeature(id="y", name="Y", text="",
                     granted_modifiers=[GrantedModifier(target="attack", op="add", value=1)])
    assert cf.granted_modifiers[0].target == "ac"
    assert rf.granted_modifiers[0].target == "attack"


def test_features_default_no_granted_modifiers():
    from aose.models import ClassFeature, RaceFeature
    assert ClassFeature(id="x", name="X", text="").granted_modifiers == []
    assert RaceFeature(id="y", name="Y", text="").granted_modifiers == []
