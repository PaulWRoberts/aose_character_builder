import random
import re
from typing import Optional

_DICE_RE = re.compile(r"^\s*(\d+)d(\d+)\s*([+-]\s*\d+)?\s*$")


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
