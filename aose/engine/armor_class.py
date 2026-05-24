from aose.data.loader import GameData
from aose.models import Ability, Armor, CharacterSpec

from .ability_mods import ability_modifier

UNARMORED_AC_DESCENDING = 9
SHIELD_AC_BONUS = 1


def armor_class(spec: CharacterSpec, data: GameData) -> tuple[int, int]:
    """Return (descending_ac, ascending_ac). Sheet renders one based on ruleset."""
    dex_mod = ability_modifier(spec.abilities[Ability.DEX])
    base = UNARMORED_AC_DESCENDING

    armor_id = spec.equipped.get("armor")
    if armor_id and armor_id in data.items:
        item = data.items[armor_id]
        if isinstance(item, Armor) and not item.is_shield:
            base = item.ac_descending

    shield_bonus = 0
    shield_id = spec.equipped.get("shield")
    if shield_id and shield_id in data.items:
        item = data.items[shield_id]
        if isinstance(item, Armor) and item.is_shield:
            shield_bonus = SHIELD_AC_BONUS

    descending = base - dex_mod - shield_bonus
    ascending = 19 - descending
    return descending, ascending
