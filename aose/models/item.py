from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from .modifier import Modifier


class ItemBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    category: str
    cost_gp: float
    weight_cn: int = 0
    description: str | None = None   # long flavour / rules text
    magic: bool = False              # drives Magic Items section + Add-only acquisition


class WeaponDamage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: str = "1d6"
    variable: str = "1d6"
    variable_two_handed: str | None = None


class ConditionalBonus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vs: str          # creature-category label, e.g. "undead"
    bonus: int       # ADDITIONAL bonus on top of magic_bonus when it applies


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
    magic_bonus: int = 0
    conditional_bonus: ConditionalBonus | None = None


class Armor(ItemBase):
    item_type: Literal["armor"]
    ac_descending: int
    movement_impact: Literal["none", "leather", "metal"] = "metal"
    is_shield: bool = False
    magic_bonus: int = 0
    weight_multiplier: float = 1.0   # 0.5 for enchanted armour


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


class MagicItem(ItemBase):
    item_type: Literal["magic"]
    equippable: bool = False
    modifiers: list[Modifier] = Field(default_factory=list)
    max_charges: int | None = None     # fixed charge ceiling, OR…
    charge_dice: str | None = None     # …rolled at acquisition (e.g. "2d6")


Item = Annotated[
    Union[Weapon, Armor, AdventuringGear, Poison, Container, MagicItem],
    Field(discriminator="item_type"),
]
