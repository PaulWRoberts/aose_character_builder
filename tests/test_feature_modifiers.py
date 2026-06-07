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


# ── Task 2: resolver ────────────────────────────────────────────────────────

def test_band_lookup():
    from aose.engine.features import _band_lookup
    t = {7: 2, 11: 3, 15: 4, 18: 5}
    assert _band_lookup(t, 6) == 0      # below lowest band
    assert _band_lookup(t, 7) == 2
    assert _band_lookup(t, 10) == 2
    assert _band_lookup(t, 11) == 3
    assert _band_lookup(t, 18) == 5
    assert _band_lookup(t, 20) == 5     # above highest band


def test_resolve_value_flat():
    from aose.engine.features import resolve_value
    from aose.models import GrantedModifier
    g = GrantedModifier(target="attack", op="add", value=1)
    assert resolve_value(g, level=3, eff={}) == 1


def test_resolve_value_by_level():
    from aose.engine.features import resolve_value
    from aose.models import GrantedModifier, Scaling
    g = GrantedModifier(target="ac", op="add",
                        scale=Scaling(by="level", table={4: 1, 6: 2}))
    assert resolve_value(g, level=5, eff={}) == 1
    assert resolve_value(g, level=6, eff={}) == 2


def test_resolve_value_by_ability_uses_effective():
    from aose.engine.features import resolve_value
    from aose.models import Ability, GrantedModifier, Scaling
    g = GrantedModifier(target="save:spells", op="add",
                        scale=Scaling(by="ability:CON", table={7: 2, 11: 3}))
    assert resolve_value(g, level=None, eff={Ability.CON: 13}) == 3


def test_resolve_value_level_scale_on_race_feature_raises():
    from aose.engine.features import resolve_value
    from aose.models import GrantedModifier, Scaling
    g = GrantedModifier(target="ac", op="add",
                        scale=Scaling(by="level", table={1: 1}))
    with pytest.raises(ValueError):
        resolve_value(g, level=None, eff={})


def test_feature_modifiers_empty_for_plain_character():
    # Human fighter has no granted modifiers anywhere → all_modifiers == magic only.
    from aose.engine.features import all_modifiers, feature_modifiers
    from aose.engine.magic import active_modifiers
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="T", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
    )
    assert feature_modifiers(spec, DATA) == []
    assert all_modifiers(spec, DATA) == active_modifiers(spec, DATA)


# ── Task 3: consumer wiring + conditions ────────────────────────────────────

def test_ac_set_modifier_shows_in_unarmored_display():
    # An `ac set 6` magic item now reflects in the unarmoured value (was ignored
    # when ac-set lived inside the worn-armour gate). DEX 10 -> +0 -> descending 6.
    from aose.engine.armor_class import unarmored_ac
    from aose.models import CharacterSpec, ClassEntry, MagicItemInstance, Modifier
    spec = CharacterSpec(
        name="T", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        magic_items=[MagicItemInstance(
            instance_id="i1", catalog_id="bracers_of_armour", equipped=True,
            extra_modifiers=[Modifier(target="ac", op="set", value=6)],
        )],
    )
    assert unarmored_ac(spec, DATA) == (6, 13)
