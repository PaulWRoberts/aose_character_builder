from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


EncumbranceMode = Literal["none", "basic", "detailed"]

CONTENT_CATEGORIES = ("classes", "equipment", "magic_items")


class RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ascending_ac: bool = False
    secondary_skills: bool = False
    weapon_proficiency: bool = False
    multiclassing: bool = False
    reroll_1s_2s_hp_l1: bool = False
    separate_race_class: bool = True
    lift_demihuman_restrictions: bool = False
    variable_weapon_damage: bool = False
    advanced_spell_books: bool = False
    human_racial_abilities: bool = False
    strict_mode: bool = True
    optional_staves: bool = False
    two_weapon_fighting: bool = False
    individual_initiative: bool = False
    combat_talents: bool = False
    cantrips: bool = False
    read_magic_cantrip: bool = False

    encumbrance: EncumbranceMode = "basic"

    # Content the user has switched off, as "{source_id}:{category}" keys. A
    # category is enabled unless its key is listed here. Classic Fantasy
    # categories are never added (its content is locked on).
    disabled_content: list[str] = Field(default_factory=list)
