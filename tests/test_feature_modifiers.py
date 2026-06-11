"""Feature-granted modifiers: data-driven class/race bonuses."""
from pathlib import Path

import pytest

from aose.data.loader import GameData

DATA = GameData.load(Path(__file__).parent.parent / "data")


@pytest.fixture
def data():
    return DATA


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


def test_feature_modifiers_no_combat_grants_for_plain_character():
    # Human fighter has no AC/attack/save grants — only the inert initiative
    # target from Decisiveness, which no standard consumer reads.
    from aose.engine.features import all_modifiers, feature_modifiers
    from aose.engine.magic import active_modifiers
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="T", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
    )
    mods = feature_modifiers(spec, DATA)
    # Only the inert Decisiveness initiative grant should appear.
    assert all(m.target == "initiative" for m in mods), mods
    assert all_modifiers(spec, DATA) == active_modifiers(spec, DATA) + mods


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
        alignment="neutral", inventory=["short_bow"], equipped={"main_hand": "short_bow"},
    )
    profs = _profiles(spec)
    assert profs["short_bow"].to_hit_ascending == 1   # +1 missile bonus
    assert profs["unarmed"].to_hit_ascending == 0     # melee: no bonus


def test_non_halfling_has_no_missile_bonus():
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="Hu", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral", inventory=["short_bow"], equipped={"main_hand": "short_bow"},
    )
    assert _profiles(spec)["short_bow"].to_hit_ascending == 0


def test_classic_halfling_missile_bonus_not_doubled():
    # Race-as-class halfling: race_id == "halfling" AND class == halfling.
    # The grant lives on the halfling *class* (self-contained); the race is not
    # read for race-as-class, so the bonus applies exactly once.
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="Hc", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="halfling", classes=[ClassEntry(class_id="halfling", level=1, hp_rolls=[6])],
        alignment="neutral", inventory=["short_bow"], equipped={"main_hand": "short_bow"},
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
    assert dwarf["death"] == base["death"]           # poison-only: NOT in death headline
    assert dwarf["spells"] == base["spells"] - 3
    assert dwarf["wands"] == base["wands"] - 3
    assert dwarf["paralysis"] == base["paralysis"]
    assert dwarf["breath"] == base["breath"]


def test_dwarf_resilience_zero_at_low_con():
    base = _saves("human", "fighter", 6)
    dwarf = _saves("dwarf", "fighter", 6)
    assert dwarf["death"] == base["death"]          # +0 below band


def test_dwarf_resilience_plus5_at_con18():
    base = _saves("human", "fighter", 18)
    dwarf = _saves("dwarf", "fighter", 18)
    assert dwarf["death"] == base["death"]           # headline unchanged (conditional)
    assert dwarf["spells"] == base["spells"] - 5     # full-category bonus stays


def test_gnome_magic_resistance_excludes_poison():
    base = _saves("human", "fighter", 13)
    gnome = _saves("gnome", "fighter", 13)
    assert gnome["spells"] == base["spells"] - 3
    assert gnome["wands"] == base["wands"] - 3
    assert gnome["death"] == base["death"]          # no poison bonus for gnomes


def test_duergar_resilience_includes_paralysis():
    base = _saves("human", "fighter", 13)
    duergar = _saves("duergar", "fighter", 13)
    assert duergar["paralysis"] == base["paralysis"]  # paralysis-only: NOT in headline
    assert duergar["death"] == base["death"]          # poison-only: NOT in headline
    assert duergar["spells"] == base["spells"] - 3    # full-category bonus stays


def test_dwarf_as_class_has_no_resilience():
    """The Dwarf *race* has Resilience; the Dwarf *class* (race-as-class) does
    not — they are distinct stat blocks sharing only a name. A dwarf-as-class
    must therefore get NO Resilience save bonus: the race feature must not bleed
    across. (In split mode, race=dwarf + a normal class, Resilience still applies
    — see test_dwarf_resilience_plus5_at_con18.)"""
    from aose.engine.saves import saving_throws_detail
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="R", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 13, "CHA": 10},
        race_id="dwarf", alignment="neutral",
        classes=[ClassEntry(class_id="dwarf", level=1, hp_rolls=[8])],
    )
    detail = saving_throws_detail(spec, DATA)
    poison_lines = [ln for ln in detail["death"].lines if ln.note.startswith("poison")]
    assert poison_lines == []               # no Resilience poison line
    base = _saves("human", "dwarf", 13)
    assert _saves("dwarf", "dwarf", 13)["spells"] == base["spells"]  # no spells bonus either


# ── Carcass Crawler 1 resilience ─────────────────────────────────────────────

def test_gargantua_resilience_plus3_at_con13():
    base = _saves("human", "fighter", 13)
    garg = _saves("gargantua", "fighter", 13)
    assert garg["spells"] == base["spells"] - 3
    assert garg["wands"] == base["wands"] - 3
    assert garg["death"] == base["death"]      # poison-only; not in headline


def test_goblin_resilience_plus2_at_con9():
    base = _saves("human", "fighter", 9)
    gob = _saves("goblin", "fighter", 9)
    assert gob["spells"] == base["spells"] - 2
    assert gob["wands"] == base["wands"] - 2
    assert gob["death"] == base["death"]       # poison-only; not in headline


# ── Task 7: kineticist AC migrated off the column ───────────────────────────

KINETICIST_AC = {1: 9, 2: 8, 3: 7, 4: 6, 5: 5, 6: 4, 7: 3, 8: 2,
                 9: 1, 10: 0, 11: -1, 12: -2, 13: -3, 14: -3}


@pytest.mark.parametrize("level,expected", KINETICIST_AC.items())
def test_kineticist_ac_matches_old_column(level, expected):
    # DEX 10 (+0) -> unarmoured descending AC == the granted `ac set` value.
    from aose.engine.armor_class import unarmored_ac
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="K", abilities={"STR": 10, "INT": 10, "WIS": 13, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="kineticist", level=level, hp_rolls=[6])],
        alignment="neutral",
    )
    assert unarmored_ac(spec, DATA)[0] == expected


def test_class_level_data_no_longer_has_armor_class_field():
    from aose.models import ClassLevelData
    with pytest.raises(Exception):
        ClassLevelData(xp_required=0, thac0=19, saves={"death": 13}, armor_class=5)


# ── Gargantua: feature weapons (Rock Throwing) ───────────────────────────────

def _spec(race_id, class_id, *, level=1, hp=8, **kw):
    from aose.models import CharacterSpec, ClassEntry
    base = dict(
        name="G",
        abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10, "CON": 12, "CHA": 10},
        race_id=race_id, alignment="neutral",
        classes=[ClassEntry(class_id=class_id, level=level, hp_rolls=[hp])],
    )
    base.update(kw)
    return CharacterSpec(**base)


def test_feature_weapons_gargantua_race():
    from aose.engine.features import feature_weapons
    weapons = dict(feature_weapons(_spec("gargantua", "fighter"), DATA))
    assert "rock_throwing" in weapons
    w = weapons["rock_throwing"]
    assert w["damage"] == "1d6"
    assert w["ranged"] is True and w["melee"] is False
    assert w["range"] == [50, 100, 150]


def test_feature_weapons_gargantua_as_class_once():
    from aose.engine.features import feature_weapons
    # race_id == class_id == "gargantua" → race-as-class: only the class path
    # contributes, so the rock appears exactly once.
    weapons = feature_weapons(_spec("gargantua", "gargantua", hp=10), DATA)
    ids = [wid for wid, _ in weapons]
    assert ids.count("rock_throwing") == 1


def test_feature_weapons_none_for_human():
    from aose.engine.features import feature_weapons
    assert feature_weapons(_spec("human", "fighter"), DATA) == []


# ── Gargantua: Open Doors STR-category bonus ─────────────────────────────────

def test_open_doors_category_bonus_gargantua_race():
    from aose.engine.features import open_doors_category_bonus
    bonus, source = open_doors_category_bonus(_spec("gargantua", "fighter"), DATA)
    assert bonus == 1
    assert source == "Gargantua"


def test_open_doors_category_bonus_gargantua_as_class():
    from aose.engine.features import open_doors_category_bonus
    bonus, source = open_doors_category_bonus(_spec("gargantua", "gargantua", hp=10), DATA)
    assert bonus == 1            # class path only — not doubled
    assert source == "Gargantua"


def test_open_doors_category_bonus_zero_for_human():
    from aose.engine.features import open_doors_category_bonus
    assert open_doors_category_bonus(_spec("human", "fighter"), DATA) == (0, "")


# ── Gargantua: rock attack profile ───────────────────────────────────────────

def test_gargantua_rock_profile_stats():
    profs = _profiles(_spec("gargantua", "fighter"))
    rock = profs["rock_throwing"]
    assert rock.name == "Rock"
    assert rock.ranged is True and rock.melee is False
    assert rock.damage == "1d6"
    assert rock.range_ft == (50, 100, 150)
    assert rock.proficient is True
    assert rock.manageable_item_id is None


def test_gargantua_rock_uses_dex_to_hit():
    # ranged → DEX to hit, no ability damage bonus. DEX 14 = +1; STR 16 = +2.
    spec = _spec("gargantua", "fighter",
                 abilities={"STR": 16, "INT": 10, "WIS": 10, "DEX": 14, "CON": 12, "CHA": 10})
    rock = _profiles(spec)["rock_throwing"]
    assert rock.to_hit_ascending == 1     # DEX +1, not STR +2
    assert rock.damage == "1d6"           # flat (no STR damage)


def test_gargantua_rock_proficient_under_weapon_proficiency():
    from aose.models import RuleSet
    spec = _spec("gargantua", "fighter", ruleset=RuleSet(weapon_proficiency=True))
    assert _profiles(spec)["rock_throwing"].proficient is True


def test_non_gargantua_has_no_rock():
    assert "rock_throwing" not in _profiles(_spec("human", "fighter"))


def test_gargantua_wields_two_handed_melee_one_handed(data):
    from aose.engine.features import one_handed_two_handed_weapons
    from aose.models import CharacterSpec, ClassEntry, Ability

    spec = CharacterSpec(
        name="Krug", abilities={a: 12 for a in Ability},
        race_id="gargantua",
        classes=[ClassEntry(class_id="gargantua", level=1)],
        alignment="neutral",
    )
    assert one_handed_two_handed_weapons(spec, data) is True


def test_non_gargantua_does_not(data):
    from aose.engine.features import one_handed_two_handed_weapons
    from aose.models import CharacterSpec, ClassEntry, Ability

    spec = CharacterSpec(
        name="Bob", abilities={a: 12 for a in Ability},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1)],
        alignment="neutral",
    )
    assert one_handed_two_handed_weapons(spec, data) is False


def test_gargantua_as_class_rock_not_duplicated():
    from aose.engine.attacks import attack_profiles
    ids = [p.weapon_id for p in attack_profiles(_spec("gargantua", "gargantua", hp=10), DATA)]
    assert ids.count("rock_throwing") == 1
