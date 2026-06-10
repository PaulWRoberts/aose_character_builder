from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .modifier import GrantedModifier


class DailyUses(BaseModel):
    """A per-day usage limit on an innate ability (feature or chosen option).

    ``per_day`` is the flat number of uses; when ``scales_with_level`` is True the
    maximum equals the granting class's level instead (Mycelian fungal spores:
    once/day per level). Collected and tracked by ``aose/engine/innate.py``.
    """
    model_config = ConfigDict(extra="forbid")

    per_day: int = 1
    scales_with_level: bool = False


class ChoiceOption(BaseModel):
    """One selectable option in a ``FeatureChoice`` group. Deliberately
    feature-shaped (``mechanical`` + ``granted_modifiers`` + ``daily_uses``) so a
    chosen option reuses every existing feature-automation path. ``spell_id``
    references a real ``Spell`` for the sheet's feature-modal spell expander.
    """
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    text: str = ""
    mechanical: dict[str, Any] | None = None
    granted_modifiers: list[GrantedModifier] = Field(default_factory=list)
    daily_uses: DailyUses | None = None
    spell_id: str | None = None


class FeatureChoice(BaseModel):
    """A "pick (or roll) N from this table" group on a Race/CharClass. Selection
    is always *distinct* (no option appears twice) — there is no duplicates flag
    because no CC3 table allows them.
    """
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    text: str = ""
    pick: int = 1
    roll_dice: str | None = None     # e.g. "d8" / "d10" for the Roll button
    cosmetic: bool = False           # purely flavor (Fiendish Appearance)
    options: list[ChoiceOption]
