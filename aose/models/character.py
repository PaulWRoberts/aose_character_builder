from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .ability import Ability
from .modifier import Modifier
from .ruleset import RuleSet


class MagicItemInstance(BaseModel):
    """A specific magic item the character owns — per-instance state separate
    from the catalog ``MagicItem``.  Tracked here (not in ``inventory``) only
    when the catalog item is ``equippable`` or has charges; stateless magic
    items (potions, magic weapons/armour) stay plain inventory ids.

    Modifiers apply only while ``equipped`` is True.
    """
    model_config = ConfigDict(extra="forbid")

    instance_id: str                         # uuid4 hex
    catalog_id: str                          # references a MagicItem
    equipped: bool = False
    charges_max: int | None = None
    charges_remaining: int | None = None
    extra_modifiers: list[Modifier] = Field(default_factory=list)  # escape hatch
    note: str = ""                                                 # escape hatch


class ContainerInstance(BaseModel):
    """A specific container the character owns — per-instance state, separate
    from the catalog ``Container`` item.  Items inside ``contents`` are not in
    ``CharacterSpec.inventory`` or ``CharacterSpec.stashed``; they live inside
    the container and follow its state (carried/stashed) for weight purposes.
    """
    model_config = ConfigDict(extra="forbid")

    instance_id: str
    catalog_id: str
    state: Literal["carried", "stashed"]
    contents: list[str] = Field(default_factory=list)


class ClassEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class_id: str
    level: int = 1
    hp_rolls: list[int] = Field(default_factory=list)
    chosen_spells: list[str] = Field(default_factory=list)


class CharacterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    abilities: dict[Ability, int]
    race_id: str
    classes: list[ClassEntry] = Field(min_length=1)
    alignment: Literal["law", "neutral", "chaos"]
    xp: int = 0
    gold: int = 0
    # Items on the character's person — equipped items live here too.  Weight
    # in this list contributes to encumbrance.
    inventory: list[str] = Field(default_factory=list)
    # Items left behind / on a horse / at camp.  Don't contribute to weight.
    stashed: list[str] = Field(default_factory=list)
    # slot -> item_id, for single-slot gear: {"armor": "chain_mail", "shield": "shield"}
    equipped: dict[str, str] = Field(default_factory=dict)
    # Equipped weapons — a list so duplicates and multiple ready weapons are OK.
    equipped_weapons: list[str] = Field(default_factory=list)
    containers: list[ContainerInstance] = Field(default_factory=list)
    magic_items: list[MagicItemInstance] = Field(default_factory=list)
    secondary_skill: str | None = None
    chosen_proficiencies: list[str] = Field(default_factory=list)
    ruleset: RuleSet = Field(default_factory=RuleSet)
