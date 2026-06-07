from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class Modifier(BaseModel):
    """A single mechanical effect from a magic item OR a class/race feature.

    Shared by catalog ``MagicItem.modifiers``, per-instance
    ``MagicItemInstance.extra_modifiers``, and the resolved output of
    ``aose/engine/features.py``.  Lives in its own module so ``item.py``,
    ``character.py``, ``race.py``, and ``character_class.py`` can all import it
    without coupling.

    ``op`` semantics (applied per target): all ``set`` (last wins) → all ``add``
    (summed) → ``set_min`` (``max(result, value)``) → ``set_max``
    (``min(result, value)``).  ``add`` always means *better for the character*
    (the lower-is-better targets negate it at their call site); ``set`` and the
    bounds use literal game-system numbers.

    ``target`` grammar (unknown targets are ignored — forward-compatible):
    ``ability:STR``…``ability:CHA``, ``ac``, ``save:all``,
    ``save:death|wands|paralysis|breath|spells``,
    ``save:vs:<thing>`` (cross-cutting situational bonus — e.g. ``save:vs:fire``;
    never folded into a headline, surfaced by ``situational_save_bonuses``),
    ``attack``, ``damage``, ``carry_capacity``, ``thac0``.

    ``condition`` is open-ended free text (``None`` = unconditional).  Each
    derivation recognises only the conditions it can evaluate in context
    (``unarmored`` for AC; ``ranged``/``melee`` for attack/damage); any other
    condition is *situational* — carried for display but never folded into a
    headline number.  ``source`` is a human label (e.g. a feature name) for the
    future on-hover conditional-modifier view.
    """
    model_config = ConfigDict(extra="forbid")

    target: str
    op: Literal["add", "set", "set_min", "set_max"]
    value: int
    condition: str | None = None
    source: str = ""


class RolledModifier(BaseModel):
    """A modifier whose value is rolled when the item *instance* is created
    (e.g. Bracers of Armour: AC 8 − 1d4).  At acquisition,
    ``new_magic_instance`` rolls ``dice`` and appends a concrete
    ``Modifier{target, op, value}`` to the instance's ``extra_modifiers``.
    """
    model_config = ConfigDict(extra="forbid")

    target: str
    op: Literal["add", "set", "set_min", "set_max"]
    dice: str


class Scaling(BaseModel):
    """Table-driven value for a ``GrantedModifier``.

    ``by`` selects the input: ``"level"`` (the granting class's level; invalid
    on a race feature) or ``"ability:STR"``…``"ability:CHA"`` (the effective,
    magic-adjusted score).  ``table`` is a *banded* lookup: the value is the
    entry for the greatest key ≤ the input; below the lowest key yields 0.
    """
    model_config = ConfigDict(extra="forbid")

    by: str
    table: dict[int, int]


class GrantedModifier(BaseModel):
    """A modifier a class/race *feature* grants, declared in YAML and resolved
    to a concrete :class:`Modifier` by ``aose/engine/features.py``.  Exactly one
    of ``value`` (flat) or ``scale`` (table-driven) must be set.
    """
    model_config = ConfigDict(extra="forbid")

    target: str
    op: Literal["add", "set", "set_min", "set_max"]
    condition: str | None = None
    value: int | None = None
    scale: Scaling | None = None

    @model_validator(mode="after")
    def _exactly_one_value_source(self):
        if (self.value is None) == (self.scale is None):
            raise ValueError("GrantedModifier requires exactly one of value or scale")
        return self
