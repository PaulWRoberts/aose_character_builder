from aose.data.loader import GameData
from aose.models import Ability, Armor, CharacterSpec

from .ability_mods import ability_modifier
from .enchant import equipped_enchanted
from .magic import active_modifiers, effective_abilities

UNARMORED_AC_DESCENDING = 9


def armor_class(spec: CharacterSpec, data: GameData, *,
                use_armor: bool = True, use_shield: bool = True) -> tuple[int, int]:
    """Return (descending_ac, ascending_ac). Sheet renders one based on ruleset.

    use_armor / use_shield = False computes the unarmoured value (DEX + magic AC mods
    only), used for the sheet's armoured-vs-unarmoured display.
    """
    eff = effective_abilities(spec, data)
    dex_mod = ability_modifier(eff[Ability.DEX])
    mods = active_modifiers(spec, data)

    base = UNARMORED_AC_DESCENDING
    if use_armor:
        armor_id = spec.equipped.get("armor")
        if armor_id and armor_id in data.items:
            item = data.items[armor_id]
            if isinstance(item, Armor) and not item.is_shield:
                base = item.ac_descending - item.magic_bonus

        # Enchanted armour: best-AC-wins (min descending) over mundane equipped.
        for resolved in equipped_enchanted(spec, data, "armor"):
            base = min(base, resolved.ac_descending - resolved.magic_bonus)

        # `ac set N` = literal descending base candidate (bracers-style); keep the better.
        for m in mods:
            if m.target == "ac" and m.op == "set":
                base = min(base, m.value)

    # Class-granted base AC (e.g. a class whose reactions improve AC by level).
    # Best (lowest descending) across classes; applies whether or not armour is
    # worn — it is not worn armour, so the unarmoured display reflects it too.
    class_acs = []
    for entry in spec.classes:
        cls_obj = data.classes.get(entry.class_id)
        if cls_obj is not None and entry.level in cls_obj.progression:
            col = cls_obj.progression[entry.level].armor_class
            if col is not None:
                class_acs.append(col)
    if class_acs:
        base = min(base, min(class_acs))

    shield_bonus = 0
    if use_shield:
        shield_id = spec.equipped.get("shield")
        if shield_id and shield_id in data.items:
            item = data.items[shield_id]
            if isinstance(item, Armor) and item.is_shield:
                shield_bonus = item.ac_bonus + item.magic_bonus
        for resolved in equipped_enchanted(spec, data, "shield"):
            shield_bonus = max(shield_bonus, resolved.ac_bonus + resolved.magic_bonus)

    ac_add = sum(m.value for m in mods if m.target == "ac" and m.op == "add")
    descending = base - dex_mod - shield_bonus - ac_add
    ascending = 19 - descending
    return descending, ascending


def unarmored_ac(spec: CharacterSpec, data: GameData) -> tuple[int, int]:
    """AC with worn armour & shield ignored (DEX + magic AC mods kept)."""
    return armor_class(spec, data, use_armor=False, use_shield=False)
