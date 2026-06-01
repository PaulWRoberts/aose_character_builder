from typing import Literal

from pydantic import BaseModel, ConfigDict


EncumbranceMode = Literal["none", "basic", "detailed"]


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

    encumbrance: EncumbranceMode = "basic"
