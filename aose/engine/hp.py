from aose.data.loader import GameData
from aose.models import Ability, CharacterSpec

from .ability_mods import ability_modifier


def max_hp(spec: CharacterSpec, data: GameData) -> int:
    if len(spec.classes) > 1:
        raise NotImplementedError(
            "Multiclass HP is not implemented yet (see build-order step 6)."
        )

    con_mod = ability_modifier(spec.abilities[Ability.CON])
    entry = spec.classes[0]
    total = 0
    for roll in entry.hp_rolls:
        total += max(1, roll + con_mod)
    return total
