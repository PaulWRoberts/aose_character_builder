from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ability import Ability
from .modifier import Modifier
from .ruleset import RuleSet


class MagicItemInstance(BaseModel):
    """A specific magic item the character owns — per-instance state separate
    from the catalog ``MagicItem``.  Tracked here (not in ``inventory``) only
    when the catalog item is ``equippable`` or has charges; stateless magic
    items (potions, magic weapons/armour) stay plain inventory ids.

    Modifiers apply only while ``equipped`` is True.
    """
    model_config = ConfigDict(extra="forbid")

    instance_id: str                         # uuid4 hex
    catalog_id: str                          # references a MagicItem
    equipped: bool = False
    charges_max: int | None = None
    charges_remaining: int | None = None
    extra_modifiers: list[Modifier] = Field(default_factory=list)  # escape hatch
    note: str = ""                                                 # escape hatch


class ContainerInstance(BaseModel):
    """A specific container the character owns — per-instance state, separate
    from the catalog ``Container`` item.  Items inside ``contents`` are not in
    ``CharacterSpec.inventory`` or ``CharacterSpec.stashed``; they live inside
    the container and follow its state (carried/stashed) for weight purposes.
    """
    model_config = ConfigDict(extra="forbid")

    instance_id: str
    catalog_id: str
    state: Literal["carried", "stashed"]
    contents: list[str] = Field(default_factory=list)


class ClassEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class_id: str
    level: int = 1
    # This class's own experience-point count.  Multi-class characters track XP
    # separately per class (XP earned is split evenly, then each class's
    # prime-requisite adjustment is applied to its share); single-class
    # characters keep the whole award here.  See aose/engine/leveling.py.
    xp: int = 0
    hp_rolls: list[int] = Field(default_factory=list)
    # Known spells (arcane spellbook).  Empty for divine casters, who know
    # their whole list automatically; see aose/engine/spells.py.
    spellbook: list[str] = Field(default_factory=list)
    # Daily prepared / memorised loadout; duplicates allowed (memorise a spell
    # twice with two slots).  Hard-capped per spell level by spell_slots.
    prepared: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_chosen_spells(cls, data):
        """Drop the pre-spell-feature ``chosen_spells`` field if a character was
        saved with it.  It was always unused/empty, so nothing of value is lost;
        this keeps old saved characters loadable under ``extra="forbid"`` rather
        than silently vanishing from the index."""
        if isinstance(data, dict) and "chosen_spells" in data:
            data = {k: v for k, v in data.items() if k != "chosen_spells"}
        return data


class CharacterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    abilities: dict[Ability, int]
    race_id: str
    classes: list[ClassEntry] = Field(min_length=1)
    alignment: Literal["law", "neutral", "chaos"]
    gold: int = 0
    # Items on the character's person — equipped items live here too.  Weight
    # in this list contributes to encumbrance.
    inventory: list[str] = Field(default_factory=list)
    # Items left behind / on a horse / at camp.  Don't contribute to weight.
    stashed: list[str] = Field(default_factory=list)
    # slot -> item_id, for single-slot gear: {"armor": "chain_mail", "shield": "shield"}
    equipped: dict[str, str] = Field(default_factory=dict)
    # Equipped weapons — a list so duplicates and multiple ready weapons are OK.
    equipped_weapons: list[str] = Field(default_factory=list)
    containers: list[ContainerInstance] = Field(default_factory=list)
    magic_items: list[MagicItemInstance] = Field(default_factory=list)
    secondary_skill: str | None = None
    # Chosen *additional* languages only (INT-based picks).  Native (race) and
    # alignment tongues are derived at display time, never stored here.
    languages: list[str] = Field(default_factory=list)
    # Weapon Proficiency optional rule (per-weapon).  Specialised weapons must
    # also appear in weapon_proficiencies; specialisation costs a 2nd slot.
    weapon_proficiencies: list[str] = Field(default_factory=list)
    weapon_specialisations: list[str] = Field(default_factory=list)
    ruleset: RuleSet = Field(default_factory=RuleSet)

    @model_validator(mode="before")
    @classmethod
    def _drop_legacy_chosen_proficiencies(cls, data):
        """Drop the pre-per-weapon ``chosen_proficiencies`` field (group ids,
        meaningless now).  Affected characters re-pick.  Keeps old saves
        loadable under ``extra='forbid'``."""
        if isinstance(data, dict) and "chosen_proficiencies" in data:
            data = {k: v for k, v in data.items() if k != "chosen_proficiencies"}
        return data

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_global_xp(cls, data):
        """Migrate the pre-multiclass global ``xp`` field into per-class
        ``ClassEntry.xp``.  XP used to live as a single total on the spec and was
        split evenly at read time (``xp_share``); it now lives per class.  We
        preserve old totals: single-class gets all of it, multi-class splits it
        evenly (matching the former share).  Dropping the key keeps old saved
        characters loadable under ``extra="forbid"``."""
        if isinstance(data, dict) and "xp" in data:
            legacy = data.get("xp") or 0
            classes = data.get("classes") or []
            n = len(classes)
            if n:
                share = legacy // n
                for c in classes:
                    if isinstance(c, dict) and "xp" not in c:
                        c["xp"] = share
            data = {k: v for k, v in data.items() if k != "xp"}
        return data
