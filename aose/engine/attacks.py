"""Attack profiles for equipped weapons.

Per OSE Advanced, melee attacks get STR modifier to both the attack roll and
damage; ranged attacks get DEX modifier to the attack roll and no STR
modifier to damage (except thrown weapons — those are a niche we don't model
yet).  When ``weapon_proficiency`` is in effect and the character lacks the
relevant proficiency group, a flat -2 penalty applies to the attack roll.

Damage uses ``damage.variable`` when the Variable Weapon Damage rule is on,
otherwise ``damage.default`` (1d6 for everything under the standard rule).
"""
from __future__ import annotations

from collections import Counter

from pydantic import BaseModel

from aose.data.loader import GameData
from aose.engine.ability_mods import ability_modifier
from aose.engine.attack_bonus import thac0
from aose.engine.proficiency import is_proficient_with
from aose.models import Ability, CharacterSpec, Weapon


class AttackProfile(BaseModel):
    weapon_id: str
    name: str
    count: int                # number of identical equipped copies (e.g. dual daggers → 2)
    melee: bool
    ranged: bool
    proficient: bool          # always True when the rule is off
    to_hit_thac0: int         # final THAC0 after mods (lower = better)
    to_hit_ascending: int     # final attack-bonus (higher = better; +0 baseline)
    damage: str               # e.g. "1d8+1" or "1d6"
    range_ft: tuple[int, int, int] | None  # short / medium / long


def _format_damage(base: str, mod: int) -> str:
    if mod == 0:
        return base
    sign = "+" if mod > 0 else "-"
    return f"{base}{sign}{abs(mod)}"


def _profile_for(weapon: Weapon, spec: CharacterSpec, data: GameData,
                 count: int) -> AttackProfile:
    str_mod = ability_modifier(spec.abilities[Ability.STR])
    dex_mod = ability_modifier(spec.abilities[Ability.DEX])
    base_thac0 = thac0(spec, data)
    base_attack = 19 - base_thac0

    # Choose the relevant ability mod: melee weapons use STR; pure-ranged use DEX.
    if weapon.melee:
        atk_mod = str_mod
        dmg_mod = str_mod
    else:
        atk_mod = dex_mod
        dmg_mod = 0

    # Proficiency penalty applies only when the rule is on AND we lack the group.
    proficient = True
    prof_pen = 0
    if spec.ruleset.weapon_proficiency:
        proficient = is_proficient_with(weapon, spec.chosen_proficiencies)
        if not proficient:
            prof_pen = -2

    use_variable = spec.ruleset.variable_weapon_damage
    base_damage = weapon.damage.variable if use_variable else weapon.damage.default

    rng = None
    if weapon.ranged and weapon.range_short is not None:
        rng = (weapon.range_short, weapon.range_medium or 0, weapon.range_long or 0)

    return AttackProfile(
        weapon_id=weapon.id,
        name=weapon.name,
        count=count,
        melee=weapon.melee,
        ranged=weapon.ranged,
        proficient=proficient,
        to_hit_thac0=base_thac0 - atk_mod - prof_pen,
        to_hit_ascending=base_attack + atk_mod + prof_pen,
        damage=_format_damage(base_damage, dmg_mod),
        range_ft=rng,
    )


def attack_profiles(spec: CharacterSpec, data: GameData) -> list[AttackProfile]:
    """One profile per *unique* equipped weapon, with the ``count`` field
    reflecting how many identical copies are ready.  Profiles are sorted by
    weapon name for stable rendering."""
    counts = Counter(spec.equipped_weapons)
    profiles: list[AttackProfile] = []
    for weapon_id, count in counts.items():
        item = data.items.get(weapon_id)
        if not isinstance(item, Weapon):
            continue  # equipped_weapons should only contain weapons, defensive
        profiles.append(_profile_for(item, spec, data, count))
    profiles.sort(key=lambda p: p.name)
    return profiles
