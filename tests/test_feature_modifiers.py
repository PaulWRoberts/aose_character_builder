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


# ── Task 4: barbarian agile AC ──────────────────────────────────────────────

def _barbarian(level, *, dex=10, **kw):
    from aose.models import CharacterSpec, ClassEntry
    base = dict(
        name="B", abilities={"STR": 13, "INT": 10, "WIS": 10, "DEX": dex, "CON": 13, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="barbarian", level=level, hp_rolls=[8])],
        alignment="neutral",
    )
    base.update(kw)
    return CharacterSpec(**base)


def test_barbarian_agile_ac_unarmored_at_l4():
    from aose.engine.armor_class import armor_class
    # L4, no armour, DEX 10 -> +0: descending 9 - 1 (agile) = 8.
    assert armor_class(_barbarian(4), DATA)[0] == 8


def test_barbarian_agile_ac_absent_before_l4():
    from aose.engine.armor_class import armor_class
    # gained_at_level 4: L3 has no bonus -> descending 9.
    assert armor_class(_barbarian(3), DATA)[0] == 9


def test_barbarian_agile_ac_dropped_when_armoured():
    from aose.engine.armor_class import armor_class
    # With chain_mail worn, the unarmored-conditioned bonus drops: a barbarian
    # L4 in chainmail has the same AC as a fighter L1 in the same chainmail.
    from aose.models import CharacterSpec, ClassEntry
    barb = _barbarian(4, equipped={"armor": "chain_mail"})
    fighter = CharacterSpec(
        name="F", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral", equipped={"armor": "chain_mail"},
    )
    assert armor_class(barb, DATA)[0] == armor_class(fighter, DATA)[0]


def test_barbarian_agile_ac_shows_in_unarmored_display_even_when_armoured():
    from aose.engine.armor_class import unarmored_ac
    # The unarmoured display reflects the no-armour scenario -> bonus applies.
    barb = _barbarian(4, equipped={"armor": "chain_mail"})
    assert unarmored_ac(barb, DATA)[0] == 8


# ── Task 5: halfling missile bonus ──────────────────────────────────────────

def _profiles(spec):
    from aose.engine.attacks import attack_profiles
    return {p.weapon_id: p for p in attack_profiles(spec, DATA)}


def test_halfling_missile_bonus_applies_to_ranged_only():
    from aose.models import CharacterSpec, ClassEntry
    # Halfling fighter, STR/DEX 10 (+0). short_bow is ranged; unarmed is melee.
    spec = CharacterSpec(
        name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="halfling", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral", equipped_weapons=["short_bow"],
    )
    profs = _profiles(spec)
    assert profs["short_bow"].to_hit_ascending == 1   # +1 missile bonus
    assert profs["unarmed"].to_hit_ascending == 0     # melee: no bonus


def test_non_halfling_has_no_missile_bonus():
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="Hu", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral", equipped_weapons=["short_bow"],
    )
    assert _profiles(spec)["short_bow"].to_hit_ascending == 0


def test_classic_halfling_missile_bonus_not_doubled():
    # Race-as-class halfling: race_id == "halfling" AND class == halfling.
    # The bonus must apply exactly once (race grant only).
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="Hc", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="halfling", classes=[ClassEntry(class_id="halfling", level=1, hp_rolls=[6])],
        alignment="neutral", equipped_weapons=["short_bow"],
    )
    assert _profiles(spec)["short_bow"].to_hit_ascending == 1   # +1, not +2


# ── Task 6: CON-scaled resilience saves ─────────────────────────────────────

def _saves(race_id, class_id, con, *, level=1, hp=8):
    from aose.engine.saves import saving_throws
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="R", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": con, "CHA": 10},
        race_id=race_id, classes=[ClassEntry(class_id=class_id, level=level, hp_rolls=[hp])],
        alignment="neutral",
    )
    return saving_throws(spec, DATA)


def test_dwarf_resilience_plus3_at_con13():
    base = _saves("human", "fighter", 13)
    dwarf = _saves("dwarf", "fighter", 13)
    assert dwarf["death"] == base["death"] - 3      # poison/death
    assert dwarf["spells"] == base["spells"] - 3
    assert dwarf["wands"] == base["wands"] - 3
    assert dwarf["paralysis"] == base["paralysis"]  # unaffected
    assert dwarf["breath"] == base["breath"]


def test_dwarf_resilience_zero_at_low_con():
    base = _saves("human", "fighter", 6)
    dwarf = _saves("dwarf", "fighter", 6)
    assert dwarf["death"] == base["death"]          # +0 below band


def test_dwarf_resilience_plus5_at_con18():
    base = _saves("human", "fighter", 18)
    dwarf = _saves("dwarf", "fighter", 18)
    assert dwarf["death"] == base["death"] - 5


def test_gnome_magic_resistance_excludes_poison():
    base = _saves("human", "fighter", 13)
    gnome = _saves("gnome", "fighter", 13)
    assert gnome["spells"] == base["spells"] - 3
    assert gnome["wands"] == base["wands"] - 3
    assert gnome["death"] == base["death"]          # no poison bonus for gnomes


def test_duergar_resilience_includes_paralysis():
    base = _saves("human", "fighter", 13)
    duergar = _saves("duergar", "fighter", 13)
    assert duergar["paralysis"] == base["paralysis"] - 3
    assert duergar["death"] == base["death"] - 3


def test_classic_dwarf_resilience_not_doubled():
    # Race-as-class dwarf: race_id == "dwarf" AND class == dwarf. Bonus once.
    high = _saves("dwarf", "dwarf", 13, hp=8)   # +3
    low = _saves("dwarf", "dwarf", 6, hp=8)     # +0
    assert low["death"] - high["death"] == 3    # exactly 3 (not 6)
