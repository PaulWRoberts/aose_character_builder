from typing import Literal

from pydantic import BaseModel, ConfigDict


class Modifier(BaseModel):
    """A single mechanical effect from a magic item.

    Shared by catalog ``MagicItem.modifiers`` and per-instance
    ``MagicItemInstance.extra_modifiers``.  Lives in its own module so
    ``item.py`` and ``character.py`` can both import it without coupling.

    ``op`` semantics (applied per target): all ``set`` (last wins) → all
    ``add`` (summed) → ``set_min`` (``max(result, value)``) → ``set_max``
    (``min(result, value)``).  ``add`` always means *better for the character*
    (the lower-is-better targets negate it at their call site); ``set`` and the
    bounds use literal game-system numbers.

    ``target`` grammar (unknown targets are ignored — forward-compatible):
    ``ability:STR``…``ability:CHA``, ``ac``, ``save:all``,
    ``save:death|wands|paralysis|breath|spells``, ``attack``, ``damage``,
    ``carry_capacity``, ``thac0``.
    """
    model_config = ConfigDict(extra="forbid")

    target: str
    op: Literal["add", "set", "set_min", "set_max"]
    value: int


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
