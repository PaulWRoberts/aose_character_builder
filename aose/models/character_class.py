from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from .ability import Ability


class ClassLevelData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    xp_required: int
    thac0: int
    saves: dict[str, int]
    # spell_level -> slot count; only set on spellcasting classes
    spell_slots: dict[int, int] | None = None
    # Descending Armour Class granted by the class at this level (e.g. a class
    # whose honed reactions improve AC as it advances). Read generically by the
    # AC engine (best/lowest across classes); None for classes without it.
    armor_class: int | None = None
    # Number of "mental powers" known at this level (the mental caster type's
    # analogue of the magic-user's spell-book size). None for non-mental classes.
    powers_known: int | None = None


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
    source: str = "ose_classic_fantasy"
    prime_requisites: list[Ability]
    ability_requirements: dict[Ability, int] = Field(default_factory=dict)
    max_level: int = 14
    hit_die: str
    # Name level: the last level at which this class rolls a Hit Die. Beyond it
    # the class gains a flat `hp_after_name_level` HP per level with NO CON
    # modifier (AOSE). 9 for almost every class; 8 for capped race-as-class
    # options whose max_level is also 8 (so the step never fires for them).
    name_level: int = 9
    hp_after_name_level: int = 0
    weapons_allowed: AllowedList
    # Weapons a class may use in combat ONLY when an optional rule is on.
    # Today this is the staff, gated by RuleSet.optional_staves (the AOSE
    # "Magic-Users/Illusionists and Staves" optional rules). Resolved through
    # the same path as weapons_allowed and unioned in by allowed_weapon_ids.
    optional_weapons_allowed: list[str] = Field(default_factory=list)
    armor_allowed: AllowedList
    shields_allowed: bool
    progression: dict[int, ClassLevelData] = Field(default_factory=dict)
    features: list[ClassFeature] = Field(default_factory=list)
    # Spell-list IDs this class casts from (e.g. ["magic_user"]). Empty = non-caster.
    # How-many-slots lives in progression[].spell_slots; this is which-pool.
    spell_lists: list[str] = Field(default_factory=list)
    # When set, this entry is a race-as-class option (e.g., classic OSE Dwarf).
    race_locked: str | None = None
    # Abilities this class forbids *lowering* during the ability-adjustment
    # step, layered on top of the {STR,INT,WIS} base set (forbid-only). Empty
    # = no extra restriction. Today: acrobat/assassin/thief forbid STR.
    non_reducible_abilities: list[Ability] = Field(default_factory=list)
    # Creation-time alignment restriction (typed; the descriptive `alignment`
    # feature text stays on `features` for the sheet). Empty = unrestricted
    # (any of the three). E.g. paladin=[law], ranger=[law, neutral].
    allowed_alignments: list[Literal["law", "neutral", "chaos"]] = Field(default_factory=list)
