from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class ItemBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    category: str
    cost_gp: float
    weight_cn: int = 0


class WeaponDamage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: str = "1d6"
    variable: str = "1d6"
    variable_two_handed: str | None = None


class Weapon(ItemBase):
    item_type: Literal["weapon"]
    damage: WeaponDamage
    hands: int = 1
    versatile: bool = False
    melee: bool = True
    ranged: bool = False
    range_short: int | None = None
    range_medium: int | None = None
    range_long: int | None = None
    qualities: list[str] = Field(default_factory=list)
    proficiency_group: str | None = None


class Armor(ItemBase):
    item_type: Literal["armor"]
    ac_descending: int
    movement_impact: Literal["none", "leather", "metal"] = "metal"
    is_shield: bool = False


class AdventuringGear(ItemBase):
    item_type: Literal["gear"]


class Poison(ItemBase):
    item_type: Literal["poison"]
    save_modifier: int = 0
    onset: str | None = None
    effect: str | None = None


class Container(ItemBase):
    item_type: Literal["container"]
    capacity_cn: int | None = None
    weight_multiplier: float = 1.0


Item = Annotated[
    Union[Weapon, Armor, AdventuringGear, Poison, Container],
    Field(discriminator="item_type"),
]
