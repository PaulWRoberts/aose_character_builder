"""Rolling and validating CC3 feature choices. Cycle-free: imports ``random``
and the choice models only."""
import random as _random

from aose.models import FeatureChoice


class ChoiceError(Exception):
    """Raised when a submitted choice is invalid (wrong count, duplicate, or an
    unknown option id)."""


def roll_choice(group: FeatureChoice, rng: _random.Random | None = None) -> list[str]:
    """Pick ``group.pick`` *distinct* option ids uniformly (re-roll duplicates is
    inherent — ``sample`` never repeats). Caps at the number of options."""
    _rng = rng or _random.Random()
    ids = [o.id for o in group.options]
    k = min(group.pick, len(ids))
    return _rng.sample(ids, k)


def validate_choice(group: FeatureChoice, chosen: list[str]) -> None:
    """Raise ``ChoiceError`` unless ``chosen`` is exactly ``pick`` distinct,
    valid option ids."""
    ids = {o.id for o in group.options}
    if len(chosen) != group.pick:
        raise ChoiceError(
            f"{group.name}: choose exactly {group.pick} (got {len(chosen)})."
        )
    if len(set(chosen)) != len(chosen):
        raise ChoiceError(f"{group.name}: choices must be distinct.")
    bad = [c for c in chosen if c not in ids]
    if bad:
        raise ChoiceError(f"{group.name}: unknown option(s) {bad}.")
