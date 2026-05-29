from typing import Literal

from pydantic import BaseModel, ConfigDict


AbilityRollMethod = Literal["3d6_in_order", "3d6_arrange", "4d6_drop_lowest"]
EncumbranceMode = Literal["none", "basic", "detailed"]


class RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ascending_ac: bool = False
    secondary_skills: bool = False
    weapon_proficiency: bool = False
    multiclassing: bool = False
    reroll_1s_2s_hp_l1: bool = False
    max_hp_at_l1: bool = False
    separate_race_class: bool = True
    demihuman_level_limits: bool = True
    demihuman_class_restrictions: bool = True
    variable_weapon_damage: bool = False
    advanced_spell_books: bool = False

    ability_roll_method: AbilityRollMethod = "3d6_in_order"
    encumbrance: EncumbranceMode = "basic"
