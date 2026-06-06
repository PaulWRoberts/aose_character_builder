from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .item import ConditionalBonus
from .modifier import Modifier


class AppliesTo(BaseModel):
    """Token lists for matching an enchantment to compatible base items.

    A base item matches a token ``T`` if ``T == base.id``, ``T in base.groups``,
    or ``T`` is the kind wildcard (``any_weapon`` / ``any_armour`` /
    ``any_shield``).  A base is compatible when it matches at least one
    ``include`` token and no ``exclude`` token (exclude wins).
    """
    model_config = ConfigDict(extra="forbid")

    include: list[str]
    exclude: list[str] = Field(default_factory=list)


class Enchantment(BaseModel):
    """A reusable magical enchantment, independent of any base item.  Lives in
    its own registry (``data/enchantments.yaml`` → ``GameData.enchantments``),
    not in the item catalog.  Composed with a base weapon/armour at runtime by
    ``aose/engine/enchant.py`` — nothing composed is persisted.
    """
    model_config = ConfigDict(extra="forbid")

    id: str
    source: str = "ose_classic_fantasy"
    name_template: str                       # .format(base=base.name) → display name
    kind: Literal["weapon", "armor", "shield", "ammunition"]
    applies_to: AppliesTo
    magic_bonus: int = 0                      # to-hit & damage (weapons); AC (armour/shield)
    conditional_bonus: ConditionalBonus | None = None   # weapons only
    modifiers: list[Modifier] = Field(default_factory=list)
    charge_dice: str | None = None
    max_charges: int | None = None
    cursed: bool = False
    description: str | None = None
