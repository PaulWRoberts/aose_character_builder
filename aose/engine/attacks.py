"""Attack profiles for equipped weapons.

Per OSE Advanced, melee attacks get STR modifier to both the attack roll and
damage; ranged attacks get DEX modifier to the attack roll and no STR
modifier to damage (except thrown weapons — those are a niche we don't model
yet).  When ``weapon_proficiency`` is in effect and the character lacks the
relevant weapon proficiency, the class-derived penalty applies to the
attack roll (e.g. -2 for martial classes).  Weapon specialisation adds
+1 to hit and +1 to damage.

Damage uses ``damage.variable`` when the Variable Weapon Damage rule is on,
otherwise ``damage.default`` (1d6 for everything under the standard rule).

A synthetic **Unarmed** profile is always prepended (weapon_id "unarmed",
melee, 1d2 base damage, always proficient). It is always the first element
of the returned list.

Magic weapons: ``weapon.magic_bonus`` is added to both to-hit and damage.
Global ``attack``/``damage`` modifiers from active equipped magic items are
also included. A weapon with ``conditional_bonus`` carries an optional
``ConditionalAttack`` with the total enhanced bonus vs that creature type.
"""
from __future__ import annotations

from collections import Counter

from pydantic import BaseModel

from aose.data.loader import GameData
from aose.engine.ability_mods import ability_modifier
from aose.engine.attack_bonus import thac0
from aose.engine.ammo import is_unloaded, loaded_bonus, loaded_stack, resolve_ammo
from aose.engine.enchant import equipped_enchanted
from aose.engine.features import all_modifiers
from aose.engine.magic import effective_abilities
from aose.engine.proficiency import (
    base_weapon_id,
    is_proficient,
    is_specialised,
    penalty_for_classes,
)
from aose.models import Ability, CharacterSpec, Weapon

UNARMED_DAMAGE = "1d2"


class ConditionalAttack(BaseModel):
    """Bonus attack profile for a weapon with a conditional_bonus (e.g. vs undead)."""
    label: str            # e.g. "vs undead"
    to_hit_thac0: int
    to_hit_ascending: int
    damage: str


class AttackProfile(BaseModel):
    weapon_id: str
    name: str
    count: int                # number of identical equipped copies (e.g. dual daggers → 2)
    melee: bool
    ranged: bool
    proficient: bool          # always True when the rule is off
    specialised: bool = False # weapon-specialisation +1/+1 active
    to_hit_thac0: int         # final THAC0 after mods (lower = better)
    to_hit_ascending: int     # final attack-bonus (higher = better; +0 baseline)
    damage: str               # e.g. "1d8+1" or "1d6"
    range_ft: tuple[int, int, int] | None  # short / medium / long
    conditional: ConditionalAttack | None = None
    unarmed: bool = False
    unloaded: bool = False           # launcher with no ammo loaded
    loaded_ammo_name: str | None = None
    manageable_item_id: str | None = None   # plain catalog weapon id → click-to-manage; None for enchanted/unarmed


def _format_damage(base: str, mod: int) -> str:
    if mod == 0:
        return base
    sign = "+" if mod > 0 else "-"
    return f"{base}{sign}{abs(mod)}"


def _atk_dmg(mods, *, melee: bool, ranged: bool) -> tuple[int, int]:
    """Sum global ``attack``/``damage`` add-modifiers that apply to a weapon of
    this kind.  Unconditional always; ``ranged``/``melee`` gated by the weapon;
    any other condition is situational and excluded from the number."""
    def applies(m) -> bool:
        if m.condition is None:
            return True
        if m.condition == "ranged":
            return ranged
        if m.condition == "melee":
            return melee
        return False
    atk = sum(m.value for m in mods if m.target == "attack" and m.op == "add" and applies(m))
    dmg = sum(m.value for m in mods if m.target == "damage" and m.op == "add" and applies(m))
    return atk, dmg


def _profile_for(weapon: Weapon, spec: CharacterSpec, data: GameData,
                 count: int, eff: dict, base_thac0: int,
                 g_atk: int, g_dmg: int,
                 ammo_bonus: int = 0, ammo_conditional=None,
                 ammo_name: str | None = None, unloaded: bool = False,
                 manageable_item_id: str | None = None) -> AttackProfile:
    str_mod = ability_modifier(eff[Ability.STR])
    dex_mod = ability_modifier(eff[Ability.DEX])
    base_attack = 19 - base_thac0

    # Choose the relevant ability mod: melee weapons use STR; pure-ranged use DEX.
    if weapon.melee:
        atk_mod = str_mod
        dmg_mod = str_mod
    else:
        atk_mod = dex_mod
        dmg_mod = 0

    # Proficiency penalty applies only when the rule is on AND we lack the weapon.
    proficient = True
    prof_pen = 0
    specialised = False
    if spec.ruleset.weapon_proficiency:
        classes = [data.classes[e.class_id] for e in spec.classes if e.class_id in data.classes]
        base_id = base_weapon_id(weapon)   # magic variants count as their base type
        proficient = is_proficient(base_id, spec)
        if not proficient:
            prof_pen = penalty_for_classes(classes)
        specialised = is_specialised(base_id, spec)
    spec_hit = 1 if specialised else 0
    spec_dmg = 1 if specialised else 0

    use_variable = spec.ruleset.variable_weapon_damage
    base_damage = weapon.damage.variable if use_variable else weapon.damage.default

    rng = None
    if weapon.ranged and weapon.range_short is not None:
        rng = (weapon.range_short, weapon.range_medium or 0, weapon.range_long or 0)

    def hit_thac0(extra: int) -> int:
        return base_thac0 - atk_mod - prof_pen - spec_hit - extra - g_atk

    def hit_asc(extra: int) -> int:
        return base_attack + atk_mod + prof_pen + spec_hit + extra + g_atk

    def dmg(extra: int) -> str:
        return _format_damage(base_damage, dmg_mod + g_dmg + spec_dmg + extra)

    flat = weapon.magic_bonus + ammo_bonus

    conditional = None
    if weapon.conditional_bonus is not None:
        extra = weapon.magic_bonus + weapon.conditional_bonus.bonus + ammo_bonus
        conditional = ConditionalAttack(
            label=f"vs {weapon.conditional_bonus.vs}",
            to_hit_thac0=hit_thac0(extra),
            to_hit_ascending=hit_asc(extra),
            damage=dmg(extra),
        )
    elif ammo_conditional is not None:
        extra = flat + ammo_conditional.bonus
        conditional = ConditionalAttack(
            label=f"vs {ammo_conditional.vs}",
            to_hit_thac0=hit_thac0(extra),
            to_hit_ascending=hit_asc(extra),
            damage=dmg(extra),
        )

    return AttackProfile(
        weapon_id=weapon.id,
        name=weapon.name,
        count=count,
        melee=weapon.melee,
        ranged=weapon.ranged,
        proficient=proficient,
        specialised=specialised,
        to_hit_thac0=hit_thac0(flat),
        to_hit_ascending=hit_asc(flat),
        damage=dmg(flat),
        range_ft=rng,
        conditional=conditional,
        unarmed=False,
        unloaded=unloaded,
        loaded_ammo_name=ammo_name,
        manageable_item_id=manageable_item_id,
    )


def _unarmed_profile(spec: CharacterSpec, eff: dict,
                     base_thac0: int, g_atk: int, g_dmg: int) -> AttackProfile:
    """Synthetic unarmed strike — always prepended, always proficient."""
    str_mod = ability_modifier(eff[Ability.STR])
    base_attack = 19 - base_thac0
    return AttackProfile(
        weapon_id="unarmed",
        name="Unarmed",
        count=1,
        melee=True,
        ranged=False,
        proficient=True,
        to_hit_thac0=base_thac0 - str_mod - g_atk,
        to_hit_ascending=base_attack + str_mod + g_atk,
        damage=_format_damage(UNARMED_DAMAGE, str_mod + g_dmg),
        range_ft=None,
        conditional=None,
        unarmed=True,
    )


def attack_profiles(spec: CharacterSpec, data: GameData) -> list[AttackProfile]:
    """One profile per *unique* equipped weapon, with the ``count`` field
    reflecting how many identical copies are ready.  Profiles are sorted by
    weapon name for stable rendering.

    The **Unarmed** synthetic profile is always prepended as the first element,
    even when no weapons are equipped.  Abilities are read via
    ``effective_abilities`` so ability-boosting magic items flow into STR/DEX.
    """
    eff = effective_abilities(spec, data)
    base_thac0 = thac0(spec, data)
    mods = all_modifiers(spec, data)

    def _ammo_args(weapon):
        if not weapon.accepts_ammo:
            return {}
        a_bonus, a_cond = loaded_bonus(weapon.id, spec, data)
        stack = loaded_stack(weapon.id, spec, data)
        name = resolve_ammo(stack, data)["name"] if stack else None
        return {"ammo_bonus": a_bonus, "ammo_conditional": a_cond,
                "ammo_name": name,
                "unloaded": is_unloaded(weapon.id, weapon, spec, data)}

    counts = Counter(spec.equipped_weapons)
    weapon_profiles: list[AttackProfile] = []
    for weapon_id, count in counts.items():
        item = data.items.get(weapon_id)
        if not isinstance(item, Weapon):
            continue  # equipped_weapons should only contain weapons, defensive
        g_atk, g_dmg = _atk_dmg(mods, melee=item.melee, ranged=item.ranged)
        weapon_profiles.append(
            _profile_for(item, spec, data, count, eff, base_thac0, g_atk, g_dmg,
                         manageable_item_id=item.id, **_ammo_args(item))
        )
    for resolved in equipped_enchanted(spec, data, "weapon"):
        g_atk, g_dmg = _atk_dmg(mods, melee=resolved.melee, ranged=resolved.ranged)
        weapon_profiles.append(
            _profile_for(resolved, spec, data, 1, eff, base_thac0, g_atk, g_dmg,
                         **_ammo_args(resolved))
        )
    weapon_profiles.sort(key=lambda p: p.name)
    u_atk, u_dmg = _atk_dmg(mods, melee=True, ranged=False)
    return [_unarmed_profile(spec, eff, base_thac0, u_atk, u_dmg), *weapon_profiles]
