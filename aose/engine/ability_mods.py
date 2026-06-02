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


def apply_racial_modifiers(base: dict[str, int], race, *,
                           include_optional: bool = False) -> dict[str, int]:
    """Return ``base`` with ``race.ability_modifiers`` applied (and, when
    ``include_optional`` is set, ``race.optional_ability_modifiers`` on top),
    each score clamped to ``[3, 18]``.

    The input dict is not mutated. Callers decide whether to apply (Advanced
    only) and whether the optional human_racial_abilities rule is active; this
    helper does not consult the ruleset.
    """
    result = dict(base)
    deltas: dict = {}
    for ability, delta in race.ability_modifiers.items():
        key = ability.value if hasattr(ability, "value") else ability
        deltas[key] = deltas.get(key, 0) + delta
    if include_optional:
        for ability, delta in race.optional_ability_modifiers.items():
            key = ability.value if hasattr(ability, "value") else ability
            deltas[key] = deltas.get(key, 0) + delta
    for key, delta in deltas.items():
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


def _ability_floor(ability: str, classes) -> int:
    """The lowest a lowered ability may reach: ``max(9, highest class
    requirement for that ability)``."""
    reqs = [cls.ability_requirements.get(Ability(ability), 0) for cls in classes]
    return max(9, max(reqs, default=0))


def validate_ability_adjustments(post_racial: dict, classes,
                                 adjustments: dict) -> None:
    """Raise ``AdjustmentError`` unless every rule holds:

    * raised abilities ⊆ raisable; lowered ⊆ lowerable
    * each lowered amount is even (−2 per +1, from a single score)
    * ``lowered_total == 2 * raised_total`` (exact, no waste)
    * each lowered post-value ≥ ``max(9, class requirement)``
    * each raised post-value ≤ 18
    """
    adj = adjustable_abilities(classes)
    raised = {a: d for a, d in adjustments.items() if d > 0}
    lowered = {a: -d for a, d in adjustments.items() if d < 0}  # positive amounts

    bad_raise = set(raised) - adj["raisable"]
    if bad_raise:
        raise AdjustmentError(
            f"Cannot raise non-prime-requisite abilities: {sorted(bad_raise)}"
        )
    bad_lower = set(lowered) - adj["lowerable"]
    if bad_lower:
        raise AdjustmentError(f"Cannot lower abilities: {sorted(bad_lower)}")

    odd_lowers = sorted(a for a, amt in lowered.items() if amt % 2 != 0)
    if odd_lowers:
        raise AdjustmentError(
            "Each lowered ability must drop by an even amount "
            f"(2 points buys 1 raise): {odd_lowers}."
        )

    raised_total = sum(raised.values())
    lowered_total = sum(lowered.values())
    if lowered_total != 2 * raised_total:
        raise AdjustmentError(
            "Must lower exactly 2 points for every 1 raised (no waste): "
            f"lowered {lowered_total}, raised {raised_total}."
        )

    for ability, amount in lowered.items():
        new_value = post_racial[ability] - amount
        floor = _ability_floor(ability, classes)
        if new_value < floor:
            raise AdjustmentError(
                f"{ability} may not drop below {floor} (would be {new_value})."
            )
    for ability, amount in raised.items():
        new_value = post_racial[ability] + amount
        if new_value > 18:
            raise AdjustmentError(
                f"{ability} may not exceed 18 (would be {new_value})."
            )


def apply_ability_adjustments(scores: dict, adjustments: dict) -> dict:
    """Return ``scores`` with ``adjustments`` added per key. No clamping —
    validation has already bounded the result. Input is not mutated."""
    result = dict(scores)
    for ability, delta in adjustments.items():
        result[ability] = result.get(ability, 0) + delta
    return result
