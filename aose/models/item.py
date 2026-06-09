from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

    # "1d6" is the standard-rule damage for every weapon and the SOLE place 1d6
    # lives — weapon YAML omits both fields unless overriding (a differentiated
    # variable die, or "" for a no-damage weapon like the net/blowgun).
    default: str = "1d6"
    variable: str = "1d6"


class ConditionalBonus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vs: str          # creature-category label, e.g. "undead"
    bonus: int       # ADDITIONAL bonus on top of magic_bonus when it applies


class QualityRef(BaseModel):
    """A weapon's reference to a quality, optionally carrying a parameter.
    Authored in YAML as a bare id (``melee``) or a one-key mapping
    (``{missile: [10, 20, 30]}``, ``{versatile: "1d8+1"}``)."""
    model_config = ConfigDict(extra="forbid")
    id: str
    param: Any = None


class Weapon(ItemBase):
    item_type: Literal["weapon"]
    damage: WeaponDamage = Field(default_factory=WeaponDamage)
    qualities: list[QualityRef] = Field(default_factory=list)
    accepts_ammo: list[str] = Field(default_factory=list)  # ammo groups this launcher fires
    groups: list[str] = Field(default_factory=list)        # enchantment matching tags
    magic_bonus: int = 0
    conditional_bonus: ConditionalBonus | None = None
    base_weapon: str | None = None   # magic/variant: mundane type for proficiency

    @field_validator("qualities", mode="before")
    @classmethod
    def _parse_qualities(cls, v):
        if not v:
            return []
        out: list[dict] = []
        for entry in v:
            if isinstance(entry, str):
                out.append({"id": entry})
            elif isinstance(entry, dict) and set(entry) <= {"id", "param"}:
                out.append(entry)              # already structured (e.g. enchant copy)
            elif isinstance(entry, dict) and len(entry) == 1:
                (key, val), = entry.items()
                out.append({"id": key, "param": val})
            else:
                raise ValueError(f"bad weapon quality entry: {entry!r}")
        return out

    def _q(self, qid: str) -> "QualityRef | None":
        return next((q for q in self.qualities if q.id == qid), None)

    @property
    def quality_ids(self) -> set[str]:
        return {q.id for q in self.qualities}

    @property
    def melee(self) -> bool:
        return "melee" in self.quality_ids

    @property
    def ranged(self) -> bool:
        return "missile" in self.quality_ids

    @property
    def hands(self) -> int:
        return 2 if "two_handed" in self.quality_ids else 1

    @property
    def versatile(self) -> bool:
        return "versatile" in self.quality_ids

    @property
    def _ranges(self) -> "tuple[int, int, int] | None":
        q = self._q("missile")
        return tuple(q.param) if q and q.param else None

    @property
    def range_short(self) -> int | None:
        r = self._ranges
        return r[0] if r else None

    @property
    def range_medium(self) -> int | None:
        r = self._ranges
        return r[1] if r else None

    @property
    def range_long(self) -> int | None:
        r = self._ranges
        return r[2] if r else None

    @property
    def two_handed_damage(self) -> str | None:
        q = self._q("versatile")
        return q.param if q else None

    @property
    def deals_damage(self) -> bool:
        return bool(self.damage.default)


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
