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
