import random
import re
from typing import Optional

_DICE_RE = re.compile(r"^\s*(\d+)d(\d+)\s*([+-]\s*\d+)?\s*$")
_NDS_RE = re.compile(r"^\s*(\d+)d(\d+)")


def roll(dice: str, rng: Optional[random.Random] = None) -> int:
    """Roll standard NdS or NdS+M notation."""
    m = _DICE_RE.match(dice)
    if not m:
        raise ValueError(f"Invalid dice notation: {dice!r}")
    n, s = int(m.group(1)), int(m.group(2))
    mod = int(m.group(3).replace(" ", "")) if m.group(3) else 0
    r = rng or random.Random()
    return sum(r.randint(1, s) for _ in range(n)) + mod


def roll_3d6_in_order(rng: Optional[random.Random] = None) -> list[int]:
    r = rng or random.Random()
    return [sum(r.randint(1, 6) for _ in range(3)) for _ in range(6)]


def roll_hp(
    hit_die: str,
    rng: Optional[random.Random] = None,
    *,
    min_die: int = 1,
) -> int:
    """Roll first-level HP from a hit die, with an optional re-roll house rule.

    min_die > 1 -> any single-die result below ``min_die`` is re-rolled until it
                   lands at or above it ("re-roll 1s & 2s" uses 3). Silently
                   treated as 1 if the die can't reach ``min_die``.
    """
    m = _NDS_RE.match(hit_die)
    if not m:
        raise ValueError(f"Invalid dice notation: {hit_die!r}")
    n, s = int(m.group(1)), int(m.group(2))

    effective_min = min_die if min_die <= s else 1
    r = rng or random.Random()
    total = 0
    for _ in range(n):
        v = r.randint(1, s)
        while v < effective_min:
            v = r.randint(1, s)
        total += v
    return total
