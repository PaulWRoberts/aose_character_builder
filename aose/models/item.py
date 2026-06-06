from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from .modifier import Modifier, RolledModifier


class ItemBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    category: str
    cost_gp: float
    weight_cn: int = 0
    description: str | None = None   # long flavour / rules text
    magic: bool = False              # drives Magic Items section + Add-only acquisition
    source: str = "ose_classic_fantasy"


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
    groups: list[str] = Field(default_factory=list)  # enchantment matching tags
    accepts_ammo: list[str] = Field(default_factory=list)  # ammo groups this launcher fires
    magic_bonus: int = 0
    conditional_bonus: ConditionalBonus | None = None
    base_weapon: str | None = None   # for magic/variant weapons: the mundane
                                     # weapon id they count as for proficiency


class Armor(ItemBase):
    item_type: Literal["armor"]
    ac_descending: int
    movement_impact: Literal["none", "leather", "metal"] = "metal"
    is_shield: bool = False
    groups: list[str] = Field(default_factory=list)  # enchantment matching tags
    ac_bonus: int = 0                # AC improvement while worn (shields: 1)
    magic_bonus: int = 0
    weight_multiplier: float = 1.0   # 0.5 for enchanted armour
    base_armor: str | None = None    # for magic/variant armour: the mundane
                                     # armour id it counts as for class allowances


class AdventuringGear(ItemBase):
    item_type: Literal["gear"]
    bundle_count: int = 1   # individual units granted per purchase


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
    rolled_modifiers: list[RolledModifier] = Field(default_factory=list)
    max_charges: int | None = None     # fixed charge ceiling, OR…
    charge_dice: str | None = None     # …rolled at acquisition (e.g. "2d6")


class Ammunition(ItemBase):
    item_type: Literal["ammunition"]
    groups: list[str] = Field(default_factory=list)   # match tags (e.g. [arrow])
    bundle_count: int = 1                              # units granted per purchase
    # weight_cn defaults to 0 (ItemBase) — ammo never contributes encumbrance.


Item = Annotated[
    Union[Weapon, Armor, AdventuringGear, Poison, Container, MagicItem, Ammunition],
    Field(discriminator="item_type"),
]
