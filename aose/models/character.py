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
    inventory: list[str] = Field(default_factory=list)
    # slot -> item_id (e.g., {"armor": "chain_mail", "shield": "shield"})
    equipped: dict[str, str] = Field(default_factory=dict)
    secondary_skill: str | None = None
    chosen_proficiencies: list[str] = Field(default_factory=list)
    ruleset: RuleSet = Field(default_factory=RuleSet)
