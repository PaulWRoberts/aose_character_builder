from fractions import Fraction

from aose.data.loader import GameData
from aose.models import Ability, CharacterSpec

from .ability_mods import ability_modifier
from .magic import effective_abilities


def _hp_events(spec: CharacterSpec) -> list[int]:
    """The sequence of HP-gain *events*, each an integer roll-sum.

    At character creation every class rolls its hit die simultaneously — that is
    a single event whose value is the sum of those rolls.  Each subsequent
    per-class level-up is its own single-die event.  Rolls live per class on
    ``ClassEntry.hp_rolls`` (index 0 = the creation roll).
    """
    if not any(e.hp_rolls for e in spec.classes):
        return []
    events: list[int] = [sum(e.hp_rolls[0] for e in spec.classes if e.hp_rolls)]
    max_len = max(len(e.hp_rolls) for e in spec.classes)
    for k in range(1, max_len):
        for e in spec.classes:
            if k < len(e.hp_rolls):
                events.append(e.hp_rolls[k])
    return events


def _hp_total(spec: CharacterSpec, data: GameData) -> Fraction:
    """Exact (fractional) maximum HP before flooring.

    For each event the hit points gained are divided by the number of classes
    (AOSE Advanced Multiple Classes rule) and the *effective* CON modifier is
    added, with a floor of 1 hit point per event (min 1 per Hit Die).  Fractions
    are summed exactly and only the final total is floored, so partial hit
    points accumulate across level-ups.  CON is read from
    ``effective_abilities`` — never baked into the stored rolls — so equipped
    CON-altering magic items and curses change max HP live.

    Single-class (N=1) reduces to ``sum(max(1, roll + CON))`` — unchanged.
    """
    n = len(spec.classes)
    con_mod = ability_modifier(effective_abilities(spec, data)[Ability.CON])
    total = Fraction(0)
    for event in _hp_events(spec):
        total += max(Fraction(1), Fraction(event, n) + con_mod)
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
