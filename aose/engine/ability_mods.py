from aose.models import Ability

_MOD_TABLE = {
    3: -3,
    4: -2, 5: -2,
    6: -1, 7: -1, 8: -1,
    9: 0, 10: 0, 11: 0, 12: 0,
    13: 1, 14: 1, 15: 1,
    16: 2, 17: 2,
    18: 3,
}


def ability_modifier(score: int) -> int:
    if score < 3:
        return -3
    if score > 18:
        return 3
    return _MOD_TABLE[score]


def prime_requisite_xp_multiplier(score: int) -> float:
    if score <= 5:
        return 0.80
    if score <= 8:
        return 0.90
    if score <= 12:
        return 1.00
    if score <= 15:
        return 1.05
    return 1.10


def apply_racial_modifiers(base: dict[str, int], race) -> dict[str, int]:
    """Return ``base`` with ``race.ability_modifiers`` applied, each score
    clamped to ``[3, 18]``.

    The input dict is not mutated. Callers decide whether to apply (Advanced
    only); this helper does not consult the ruleset.
    """
    result = dict(base)
    for ability, delta in race.ability_modifiers.items():
        key = ability.value if hasattr(ability, "value") else ability
        result[key] = max(3, min(18, result.get(key, 0) + delta))
    return result


def ability_warnings(abilities: dict[str, int]) -> dict:
    """Non-blocking creation warnings derived purely from ability scores.

    * ``subpar``      — True when *all six* scores are 8 or lower (the AOSE
                        "may start over" condition).
    * ``rock_bottom`` — the names of any abilities that rolled exactly 3.

    Both are advisory only; nothing here blocks character creation.
    """
    subpar = all(v <= 8 for v in abilities.values())
    rock_bottom = [name for name, v in abilities.items() if v == 3]
    return {"subpar": subpar, "rock_bottom": rock_bottom}


class AdjustmentError(ValueError):
    """Raised when a proposed ability-score adjustment violates the rules."""


# Only STR/INT/WIS may ever be lowered (the base set); a class may remove
# entries from this set via non_reducible_abilities, never add to it.
_BASE_LOWERABLE = {"STR", "INT", "WIS"}


def adjustable_abilities(classes) -> dict:
    """Return ``{'raisable': set[str], 'lowerable': set[str]}`` for the selected
    classes.

    * raisable  = union of every class's prime requisites.
    * lowerable = {STR,INT,WIS} minus the raisable set minus the union of every
      class's ``non_reducible_abilities``.
    """
    raisable: set[str] = set()
    non_reducible: set[str] = set()
    for cls in classes:
        raisable |= {a.value for a in cls.prime_requisites}
        non_reducible |= {a.value for a in cls.non_reducible_abilities}
    lowerable = _BASE_LOWERABLE - raisable - non_reducible
    return {"raisable": raisable, "lowerable": lowerable}
