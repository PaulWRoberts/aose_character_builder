from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .ability import Ability
from .ruleset import RuleSet


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
    secondary_skill: str | None = None
    chosen_proficiencies: list[str] = Field(default_factory=list)
    ruleset: RuleSet = Field(default_factory=RuleSet)
