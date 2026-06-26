from dataclasses import dataclass

from pydantic import BaseModel

from aose.data.loader import GameData
from aose.models import Ability, Armor, CharacterSpec, Modifier

from .ability_mods import ability_modifier
from .equip import equipped_instance, slot_item
from .features import all_modifiers
from .magic import effective_abilities

UNARMORED_AC_DESCENDING = 9

# Conditions the headline AC computation can evaluate. Every other condition on
# an `ac add` modifier is situational: carried for display, excluded from the
# headline, and surfaced as a conditional breakdown line.
_HEADLINE_AC_CONDITIONS = frozenset({"unarmored"})

_AC_CONDITION_NOTES = {
    "bright_light": "in bright light",
    "large_attacker": "vs attackers larger than human-sized",
}
"""Display note for an `ac add` modifier's condition. Unregistered conditions
fall back to ``condition.replace("_", " ")`` — mirrors ``_VS_DISPLAY`` in saves."""


def _ac_condition_note(condition: str) -> str:
    return _AC_CONDITION_NOTES.get(condition, condition.replace("_", " "))


class ACModLine(BaseModel):
    source: str          # "Plate Mail", "Unarmoured", "Dexterity", "Shield", feature/item name
    effect: str          # "AC 3", "+1", "−1" (unicode minus for penalties)
    conditional: bool    # True for situational modifiers
    note: str            # condition note ("" when unconditional)


class ACBreakdown(BaseModel):
    descending: int
    ascending: int
    unarmored_descending: int
    unarmored_ascending: int
    lines: list[ACModLine]   # unconditional contributions first, then conditional
    has_conditional: bool


@dataclass
class _ACComputation:
    base: int
    base_source: str
    dex_mod: int
    shield_bonus: int
    has_shield: bool
    applied_adds: list[Modifier]      # unconditional / applicable `ac add`
    situational_adds: list[Modifier]  # conditional `ac add`, excluded from headline
    descending: int
    ascending: int


def _has_worn_armor(spec: CharacterSpec, data: GameData) -> bool:
    """True when a body-armour item (not a shield) is equipped — mundane or
    enchanted.  Used to drop ``unarmored``-conditioned AC bonuses."""
    item = slot_item(spec, "armor", data)
    return isinstance(item, Armor) and not item.is_shield


def _compute_ac(spec: CharacterSpec, data: GameData, *,
                use_armor: bool, use_shield: bool) -> _ACComputation:
    """Single source of truth for AC. ``armor_class`` returns the numbers;
    ``armor_class_detail`` also reads the component fields for the breakdown."""
    eff = effective_abilities(spec, data)
    dex_mod = ability_modifier(eff[Ability.DEX])
    mods = all_modifiers(spec, data)

    base = UNARMORED_AC_DESCENDING
    base_source = "Unarmoured"
    if use_armor:
        armor_inst = equipped_instance(spec, "armor")
        if armor_inst is not None:
            item = slot_item(spec, "armor", data)
            if isinstance(item, Armor) and not item.is_shield:
                ac_desc = item.ac_descending
                if (item.tailorable and not armor_inst.tailored
                        and item.untailored_ac_descending is not None):
                    ac_desc = item.untailored_ac_descending
                cand = ac_desc - item.magic_bonus
                if cand < base:
                    base, base_source = cand, item.name

    # `ac set N` from ANY source is a literal descending base candidate; best
    # (lowest) wins. Evaluated OUTSIDE the use_armor gate so class-granted AC
    # (e.g. Kineticist) and bracers-style items show in the unarmoured display
    # and still beat worn armour. (Condition on `set` is intentionally ignored
    # here, preserving prior behaviour — no data uses a conditional `ac set`.)
    for m in mods:
        if m.target == "ac" and m.op == "set" and m.value < base:
            base, base_source = m.value, (m.source or "—")

    shield_bonus = 0
    has_shield = False
    if use_shield:
        off_item = slot_item(spec, "off_hand", data)
        if isinstance(off_item, Armor) and off_item.is_shield:
            shield_bonus = off_item.ac_bonus + off_item.magic_bonus
            has_shield = True

    armor_worn = use_armor and _has_worn_armor(spec, data)

    def ac_add_applies(m: Modifier) -> bool:
        if m.condition is None:
            return True
        if m.condition == "unarmored":
            return not armor_worn
        return False  # unrecognised condition: situational, never in the headline

    ac_mods = [m for m in mods if m.target == "ac" and m.op == "add"]
    applied_adds = [m for m in ac_mods if ac_add_applies(m)]
    situational_adds = [m for m in ac_mods
                        if m.condition is not None
                        and m.condition not in _HEADLINE_AC_CONDITIONS]

    ac_add = sum(m.value for m in applied_adds)
    descending = base - dex_mod - shield_bonus - ac_add
    ascending = 19 - descending
    return _ACComputation(base, base_source, dex_mod, shield_bonus, has_shield,
                          applied_adds, situational_adds, descending, ascending)


def armor_class(spec: CharacterSpec, data: GameData, *,
                use_armor: bool = True, use_shield: bool = True) -> tuple[int, int]:
    """Return (descending_ac, ascending_ac). Sheet renders one based on ruleset.

    use_armor / use_shield = False computes the unarmoured value (DEX + magic/
    feature AC mods only), used for the sheet's armoured-vs-unarmoured display.
    """
    c = _compute_ac(spec, data, use_armor=use_armor, use_shield=use_shield)
    return c.descending, c.ascending


def unarmored_ac(spec: CharacterSpec, data: GameData) -> tuple[int, int]:
    """AC with worn armour & shield ignored (DEX + magic/feature AC mods kept)."""
    return armor_class(spec, data, use_armor=False, use_shield=False)


def _effect_str(value: int) -> str:
    """`+N` for a bonus, unicode-minus `−N` for a penalty (matches view.py)."""
    return f"+{value}" if value >= 0 else f"−{abs(value)}"


def armor_class_detail(spec: CharacterSpec, data: GameData) -> ACBreakdown:
    """Full AC breakdown: headline composition lines (armour, DEX, shield,
    unconditional feature/magic AC mods) plus situational conditional lines.
    Headline numbers are authoritative (same helper as ``armor_class``)."""
    c = _compute_ac(spec, data, use_armor=True, use_shield=True)
    un = _compute_ac(spec, data, use_armor=False, use_shield=False)

    lines: list[ACModLine] = [
        ACModLine(source=c.base_source, effect=f"AC {c.base}", conditional=False, note=""),
    ]
    if c.dex_mod:
        lines.append(ACModLine(source="Dexterity", effect=_effect_str(c.dex_mod),
                               conditional=False, note=""))
    if c.has_shield:
        lines.append(ACModLine(source="Shield", effect=f"+{c.shield_bonus}",
                               conditional=False, note=""))
    for m in c.applied_adds:
        if m.condition == "unarmored":
            # Already folded into the base/headline via the unarmoured display.
            continue
        lines.append(ACModLine(source=m.source or "—", effect=_effect_str(m.value),
                               conditional=False, note=""))
    for m in c.situational_adds:
        # situational_adds is filtered to condition-is-not-None in _compute_ac.
        lines.append(ACModLine(source=m.source or "—", effect=_effect_str(m.value),
                               conditional=True, note=_ac_condition_note(m.condition or "")))

    return ACBreakdown(
        descending=c.descending, ascending=c.ascending,
        unarmored_descending=un.descending, unarmored_ascending=un.ascending,
        lines=lines,
        has_conditional=any(ln.conditional for ln in lines),
    )
