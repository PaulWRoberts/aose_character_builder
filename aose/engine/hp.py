from fractions import Fraction

from aose.data.loader import GameData
from aose.models import Ability, CharacterSpec

from .ability_mods import ability_modifier
from .magic import effective_abilities


def _hp_events(spec: CharacterSpec, data: GameData) -> list[int]:
    """The sequence of HP-gain *events*, each an integer roll-sum.

    At character creation every class rolls its hit die simultaneously — that is
    a single event whose value is the sum of those rolls.  Each subsequent
    per-class level-up is its own single-die event.  Rolls live per class on
    ``ClassEntry.hp_rolls`` (index 0 = the creation roll).

    Each class contributes only its first ``name_level`` rolls: Hit Dice stop at
    name level, so any rolls stored beyond that (e.g. on a character leveled
    under an older engine) are ignored defensively.
    """
    rolls = [e.hp_rolls[: data.classes[e.class_id].name_level] for e in spec.classes]
    if not any(rolls):
        return []
    events: list[int] = [sum(r[0] for r in rolls if r)]
    max_len = max(len(r) for r in rolls)
    for k in range(1, max_len):
        for r in rolls:
            if k < len(r):
                events.append(r[k])
    return events


def _hp_total(spec: CharacterSpec, data: GameData) -> Fraction:
    """Exact (fractional) maximum HP before flooring.

    Two contributions, both divided by the number of classes N (AOSE Advanced
    Multiple Classes rule) and summed as exact ``Fraction``s, floored once:

    * Rolled Hit Dice (up to name level): each event gets the *effective* CON
      modifier added, with a floor of 1 HP per event (min 1 per Hit Die).
    * Fixed post-name-level HP: ``hp_after_name_level`` per level beyond name
      level, per class.  This is a flat bonus — NO CON modifier and NO per-event
      floor — so partial hit points accumulate and may form whole HP later.

    Single-class (N=1) below name level reduces to ``sum(max(1, roll + CON))``.
    CON is read from ``effective_abilities`` — never baked into stored rolls.
    """
    n = len(spec.classes)
    con_mod = ability_modifier(effective_abilities(spec, data)[Ability.CON])
    total = Fraction(0)
    for event in _hp_events(spec, data):
        total += max(Fraction(1), Fraction(event, n) + con_mod)
    fixed = sum(
        max(0, e.level - data.classes[e.class_id].name_level)
        * data.classes[e.class_id].hp_after_name_level
        for e in spec.classes
    )
    total += Fraction(fixed, n)
    return total


def max_hp(spec: CharacterSpec, data: GameData) -> int:
    """Maximum hit points (floored). See :func:`_hp_total`."""
    return int(_hp_total(spec, data))  # total is non-negative → int() == floor


def hp_remainder(spec: CharacterSpec, data: GameData) -> Fraction:
    """The accumulated fractional hit point not yet counted toward ``max_hp``
    (``Σ events − floor``).  Zero for single-class characters.  Derived from the
    rolls + effective CON; nothing is stored."""
    total = _hp_total(spec, data)
    return total - int(total)


# ── Play-state: current HP, damage, healing ────────────────────────────────

def current_hp(spec: CharacterSpec, data: GameData) -> int:
    """Current hit points: ``max(0, max_hp − damage_taken)``."""
    return max(0, max_hp(spec, data) - spec.damage_taken)


def is_dead(spec: CharacterSpec, data: GameData) -> bool:
    """A character is dead when current HP is 0 (derived, not stored)."""
    return current_hp(spec, data) == 0


def apply_damage(spec: CharacterSpec, data: GameData, amount: int) -> int:
    """Return the new ``damage_taken`` after taking ``amount`` (>=0) damage,
    capped so current HP never drops below 0."""
    if amount < 0:
        raise ValueError("damage amount must be non-negative")
    return min(max_hp(spec, data), spec.damage_taken + amount)


def apply_healing(spec: CharacterSpec, data: GameData, amount: int) -> int:
    """Return the new ``damage_taken`` after healing ``amount`` (>=0), floored
    at 0 (current HP never exceeds max)."""
    if amount < 0:
        raise ValueError("healing amount must be non-negative")
    return max(0, spec.damage_taken - amount)


def set_current_hp(spec: CharacterSpec, data: GameData, value: int) -> int:
    """Return the ``damage_taken`` that sets current HP to ``value``, clamped to
    ``[0, max_hp]``."""
    m = max_hp(spec, data)
    clamped = max(0, min(m, value))
    return m - clamped
