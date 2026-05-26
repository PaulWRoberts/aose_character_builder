from aose.data.loader import GameData
from aose.models import Ability, CharacterSpec

from .ability_mods import ability_modifier


def max_hp(spec: CharacterSpec, data: GameData) -> int:
    """Maximum hit points for a character spec.

    Single-class characters: sum of (roll + CON mod) per level, min 1 per level.

    Multi-class (AOSE Advanced rule): at each level, every class rolls its own
    hit die; HP per level is ``floor(average of those rolls) + CON mod``, with
    the per-level minimum of 1 still applied.  This matches the AOSE Advanced
    Player's Tome wording ("for each level, roll all class hit dice and take
    the average").  ``data`` is accepted for symmetry with the other engine
    functions but is unused — all the inputs already live on the spec.
    """
    con_mod = ability_modifier(spec.abilities[Ability.CON])

    if len(spec.classes) == 1:
        entry = spec.classes[0]
        return sum(max(1, roll + con_mod) for roll in entry.hp_rolls)

    # Multi-class: zip rolls per level across classes, average, add CON once.
    max_level = max(e.level for e in spec.classes)
    total = 0
    for lv in range(max_level):
        per_level_rolls = [
            entry.hp_rolls[lv] for entry in spec.classes
            if lv < len(entry.hp_rolls)
        ]
        if not per_level_rolls:
            continue  # one class hasn't levelled this far yet
        avg_floor = sum(per_level_rolls) // len(per_level_rolls)
        total += max(1, avg_floor + con_mod)
    return total
