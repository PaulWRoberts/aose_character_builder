from aose.data.loader import GameData
from aose.models import Ability, Armor, CharacterSpec

from .ability_mods import ability_modifier
from .magic import active_modifiers, effective_abilities

UNARMORED_AC_DESCENDING = 9
SHIELD_AC_BONUS = 1


def armor_class(spec: CharacterSpec, data: GameData) -> tuple[int, int]:
    """Return (descending_ac, ascending_ac). Sheet renders one based on ruleset."""
    eff = effective_abilities(spec, data)
    dex_mod = ability_modifier(eff[Ability.DEX])
    mods = active_modifiers(spec, data)

    base = UNARMORED_AC_DESCENDING
    armor_id = spec.equipped.get("armor")
    if armor_id and armor_id in data.items:
        item = data.items[armor_id]
        if isinstance(item, Armor) and not item.is_shield:
            base = item.ac_descending - item.magic_bonus

    # `ac set N` = literal descending base candidate (bracers-style); keep the better.
    for m in mods:
        if m.target == "ac" and m.op == "set":
            base = min(base, m.value)

    shield_bonus = 0
    shield_id = spec.equipped.get("shield")
    if shield_id and shield_id in data.items:
        item = data.items[shield_id]
        if isinstance(item, Armor) and item.is_shield:
            shield_bonus = SHIELD_AC_BONUS + item.magic_bonus

    ac_add = sum(m.value for m in mods if m.target == "ac" and m.op == "add")
    descending = base - dex_mod - shield_bonus - ac_add
    ascending = 19 - descending
    return descending, ascending
