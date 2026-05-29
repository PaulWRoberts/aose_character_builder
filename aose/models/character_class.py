from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from .ability import Ability


class ClassLevelData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    xp_required: int
    thac0: int
    hit_dice: str
    saves: dict[str, int]
    # spell_level -> slot count; only set on spellcasting classes
    spell_slots: dict[int, int] | None = None


class ProficiencyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starting_slots: int
    new_slot_every_levels: int


class ClassFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    text: str
    gained_at_level: int = 1
    mechanical: dict[str, Any] | None = None


AllowedList = Union[list[str], Literal["all"]]


class CharClass(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    prime_requisites: list[Ability]
    ability_requirements: dict[Ability, int] = Field(default_factory=dict)
    max_level: int = 14
    hit_die: str
    weapons_allowed: AllowedList
    armor_allowed: AllowedList
    shields_allowed: bool
    proficiency: ProficiencyConfig | None = None
    progression: dict[int, ClassLevelData] = Field(default_factory=dict)
    features: list[ClassFeature] = Field(default_factory=list)
    # Spell-list IDs this class casts from (e.g. ["magic_user"]). Empty = non-caster.
    # How-many-slots lives in progression[].spell_slots; this is which-pool.
    spell_lists: list[str] = Field(default_factory=list)
    # When set, this entry is a race-as-class option (e.g., classic OSE Dwarf).
    race_locked: str | None = None
