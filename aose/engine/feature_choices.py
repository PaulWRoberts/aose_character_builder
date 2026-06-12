"""Rolling and validating CC3 feature choices. Cycle-free: imports ``random``
and the choice models only."""
import random as _random

from aose.models import FeatureChoice


class ChoiceError(Exception):
    """Raised when a submitted choice is invalid (wrong count, duplicate, or an
    unknown option id)."""


def _band_lookup(table: dict[int, int], key: int) -> int:
    candidates = [k for k in table if k <= key]
    return table[max(candidates)] if candidates else 0


def effective_pick(group: FeatureChoice, level: int) -> int:
    """Total picks allowed for ``group`` at ``level`` — the banded
    ``pick_by_level`` value if set, else the flat ``pick``."""
    if group.pick_by_level:
        return _band_lookup(group.pick_by_level, level)
    return group.pick


def roll_choice(group: FeatureChoice, rng: _random.Random | None = None,
                pick: int | None = None) -> list[str]:
    """Pick ``pick`` (or ``group.pick``) *distinct* option ids uniformly.
    Caps at the number of options."""
    _rng = rng or _random.Random()
    ids = [o.id for o in group.options]
    k = min(group.pick if pick is None else pick, len(ids))
    return _rng.sample(ids, k)


def validate_choice(group: FeatureChoice, chosen: list[str],
                    pick: int | None = None) -> None:
    """Raise ``ChoiceError`` unless ``chosen`` is exactly ``pick`` (or
    ``group.pick``) distinct, valid option ids."""
    want = group.pick if pick is None else pick
    ids = {o.id for o in group.options}
    if len(chosen) != want:
        raise ChoiceError(
            f"{group.name}: choose exactly {want} (got {len(chosen)})."
        )
    if len(set(chosen)) != len(chosen):
        raise ChoiceError(f"{group.name}: choices must be distinct.")
    bad = [c for c in chosen if c not in ids]
    if bad:
        raise ChoiceError(f"{group.name}: unknown option(s) {bad}.")
