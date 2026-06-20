from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from .ability import Ability
from .modifier import GrantedModifier
from .choice import DailyUses, FeatureChoice


class ClassLevelData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    xp_required: int
    thac0: int
    saves: dict[str, int]
    # spell_level -> slot count; only set on spellcasting classes
    spell_slots: dict[int, int] | None = None
    # Number of "mental powers" known at this level (the mental caster type's
    # analogue of the magic-user's spell-book size). None for non-mental classes.
    powers_known: int | None = None


class XpBonusTier(BaseModel):
    """One prime-requisite experience-bonus tier.

    AOSE states a *per-class* rule for the +5%/+10% XP bonus, and multi-prime
    classes vary widely (one ≥13 vs both ≥13 vs a specific ability ≥16, …), so
    each class encodes its rule as data rather than deriving it from a single
    score.

    A tier is satisfied when *any* requirement set in ``any_of`` is fully met —
    i.e. every ability in that set is at or above its listed minimum. The
    character receives the highest ``bonus_pct`` among satisfied tiers; if none
    match there is no adjustment. The ``any_of`` list expresses OR across sets,
    AND within a set, which covers every stated pattern:

    - "one prime ≥13" → ``any_of: [{A: 13}, {B: 13}]``
    - "both ≥13"      → ``any_of: [{A: 13, B: 13}]``
    - "A ≥16 and B ≥13" (specific) → ``any_of: [{A: 16, B: 13}]``
    - "one ≥16, the other ≥13" (symmetric) →
      ``any_of: [{A: 16, B: 13}, {A: 13, B: 16}]``
    """

    model_config = ConfigDict(extra="forbid")

    bonus_pct: int
    any_of: list[dict[Ability, int]]


class ClassFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    text: str
    gained_at_level: int = 1
    mechanical: dict[str, Any] | None = None
    granted_modifiers: list[GrantedModifier] = Field(default_factory=list)
    daily_uses: DailyUses | None = None
    spell_id: str | None = None


AllowedList = Union[list[str], Literal["all"]]


class RetainerHiringRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_level: int                                     # hiring PC level this tier applies at
    allows: list[str] | Literal["any", "none"]         # class ids, or "any"/"none"


class CharClass(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    source: str = "ose_classic_fantasy"
    prime_requisites: list[Ability]
    # Per-class prime-requisite XP-bonus rule (the +5%/+10% experience bonus).
    # Empty → fall back to the standard single-ability XP table on the lowest
    # prime score (correct for single-prime classes, and the only path that
    # carries the low-score XP penalty). Multi-prime classes MUST set this — the
    # single-ability table can't express "both ≥13". See aose/engine/leveling.py
    # and XpBonusTier above.
    xp_bonus_tiers: list[XpBonusTier] = Field(default_factory=list)
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
    # Weapon qualities that grant usage of every weapon bearing them.
    # Cleric/acolyte use [blunt] — "May be used by clerics".
    weapon_qualities_allowed: list[str] = Field(default_factory=list)
    armor_allowed: AllowedList
    shields_allowed: bool
    progression: dict[int, ClassLevelData] = Field(default_factory=dict)
    features: list[ClassFeature] = Field(default_factory=list)
    # "Pick/roll N at creation" groups (CC3). Chosen options live on
    # CharacterSpec.feature_choices and flow through aose/engine/features.py.
    feature_choices: list[FeatureChoice] = Field(default_factory=list)
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
    retainer_hiring: list[RetainerHiringRule] = Field(default_factory=list)
