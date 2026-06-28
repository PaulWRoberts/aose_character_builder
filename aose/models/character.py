from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ability import Ability
from .modifier import Modifier
from .ruleset import RuleSet
from .storage import CoinStack, StorageLocation
from .valuable import GemStack, JewelleryPiece

EquipSlot = Literal["armor", "main_hand", "off_hand"]


class ItemInstance(BaseModel):
    """One owned catalog item, with identity — plain, enchanted, or stacked."""
    model_config = ConfigDict(extra="forbid")

    instance_id: str                       # uuid4 hex
    catalog_id: str                        # references a Weapon / Armor / gear / Ammunition item
    location: StorageLocation = Field(default_factory=lambda: StorageLocation(kind="carried"))
    enchantment_id: str | None = None      # None = plain; else references an Enchantment
    count: int = 1
    equip: EquipSlot | None = None
    tailored: bool = True
    loaded_ammo_id: str | None = None      # launcher weapons only; an ammo ItemInstance id
    charges_max: int | None = None
    charges_remaining: int | None = None
    extra_modifiers: list[Modifier] = Field(default_factory=list)  # escape hatch
    note: str = ""                                                  # escape hatch


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
    location: StorageLocation = Field(default_factory=lambda: StorageLocation(kind="carried"))
    equipped: bool = False
    charges_max: int | None = None
    charges_remaining: int | None = None
    extra_modifiers: list[Modifier] = Field(default_factory=list)  # escape hatch
    note: str = ""                                                 # escape hatch


class ContainerInstance(BaseModel):
    """A specific container the character owns — per-instance state, separate
    from the catalog ``Container`` item.  Items inside the container carry
    ``location=StorageLocation(kind="container", id=<this instance_id>)`` in
    ``CharacterSpec.items``; moving the container moves them for free.
    """
    model_config = ConfigDict(extra="forbid")

    instance_id: str
    catalog_id: str
    # carried/stashed/animal/vehicle only — never "container" (no nesting).
    location: StorageLocation = Field(default_factory=lambda: StorageLocation(kind="carried"))

    @model_validator(mode="after")
    def _no_nesting(self):
        if self.location.kind == "container":
            raise ValueError("a container cannot live inside another container")
        return self


class AnimalInstance(BaseModel):
    """A specific animal the character owns — per-instance state separate from
    the catalog ``Animal``.  Acts as a top-level storage location: items carried
    on it have ``location=StorageLocation(kind="animal", id=<this instance_id>)``."""
    model_config = ConfigDict(extra="forbid")

    instance_id: str                 # uuid4 hex
    catalog_id: str                  # references an Animal
    name: str = ""                   # optional label
    hp_damage: int = 0               # current hp = max(0, catalog.hp - hp_damage)
    armor_id: str | None = None      # references an AnimalArmor in catalog.armor_fits
    magic_note: str = ""             # free-text placeholder until magic items land


class VehicleInstance(BaseModel):
    """A specific vehicle the character owns.  Acts as a top-level storage
    location; cargo items carry ``location=StorageLocation(kind="vehicle", id=<instance_id>)``."""
    model_config = ConfigDict(extra="forbid")

    instance_id: str
    catalog_id: str                  # references a Vehicle
    name: str = ""
    hull_max: int                    # resolved from catalog.hull_points at purchase
    hull_damage: int = 0
    extra_animals: bool = False      # raises cap to cargo_capacity_extra_cn
    note: str = ""


class SpellSourceEntry(BaseModel):
    """One spell recorded in a SpellSource document.  ``copy_failed`` is set when
    an Advanced-rule copy attempt from THIS source failed — it bars retrying the
    same spell from this source only, never from any other source, and is never
    recorded on the character."""
    model_config = ConfigDict(extra="forbid")

    spell_id: str
    copy_failed: bool = False


class SpellSource(BaseModel):
    """A physical document the character owns — an arcane spell book or a magic
    scroll — with custom contents chosen at acquisition (Add-only, sheet).  Not
    stored in ``inventory``; carries its own existence like ContainerInstance.
    Scroll spells are expended (the entry removed) when cast; spell books are
    never expended.  ``caster_type`` is always ``arcane`` for a spellbook."""
    model_config = ConfigDict(extra="forbid")

    instance_id: str                              # uuid4 hex
    kind: Literal["spellbook", "scroll"]
    caster_type: Literal["arcane", "divine"]
    name: str = ""                                # optional label
    language: str = "Common"
    unlocked: bool = False
    location: StorageLocation = Field(default_factory=lambda: StorageLocation(kind="carried"))
    entries: list[SpellSourceEntry] = Field(default_factory=list)


class SpellSlot(BaseModel):
    """One memorized-spell slot in a caster's daily loadout.

    A slot holds at most one spell of a fixed ``level``.  ``reversed`` is an
    arcane-only choice fixed at memorization (divine slots always store False;
    the normal/reversed choice for divine spells is made at cast time and not
    persisted).  ``spent`` flips True when the slot is cast and resets on rest.
    """
    model_config = ConfigDict(extra="forbid")

    level: int
    spell_id: str | None = None
    reversed: bool = False
    spent: bool = False


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
    # Known spells/powers chosen by the character: the arcane spell book, or a
    # mental caster's known mental powers.  Empty for divine casters, who know
    # their whole list automatically; see aose/engine/spells.py.
    spellbook: list[str] = Field(default_factory=list)
    # Daily memorized loadout as individual slots; duplicates allowed (two slots,
    # same spell_id).  Hard-capped per spell level by spell_slots.  Replaces the
    # old flat ``prepared`` list — each slot also tracks reversed/spent state.
    slots: list[SpellSlot] = Field(default_factory=list)
    # Mental-powers daily-use pool counter: activations spent today. The pool
    # size is 2 x level (computed in spells.py); 0 for non-mental classes.
    powers_used: int = 0


class CharacterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    abilities: dict[Ability, int]
    race_id: str
    classes: list[ClassEntry] = Field(min_length=1)
    alignment: Literal["law", "neutral", "chaos"]
    # Coins are located stackable items: at most one stack per (denom, location).
    # The shop spends only carried (on-person) stacks. See aose/engine/storage.py.
    coins: list[CoinStack] = Field(default_factory=list)
    # Basic-encumbrance referee toggle: carrying a significant amount of
    # treasure (drops the movement rate one step). Detailed mode ignores it.
    carrying_treasure: bool = False
    # Play-state: hit points of damage taken.  Current HP is derived as
    # max(0, max_hp − damage_taken); dead == current HP 0.  Tracks live max_hp
    # shifts (e.g. a CON-altering magic item) without rewriting stored state.
    damage_taken: int = 0
    # Per-class HP rolled but not yet confirmed at level-up.  Maps class_id ->
    # the rolled HP awaiting confirmation.  Cleared when the level-up is
    # confirmed or cancelled.  See aose/engine/leveling.py.
    pending_level_up: dict[str, int] = Field(default_factory=dict)
    # 1d3 HP healing roll for full-day rest, awaiting confirmation.  Cleared on confirm.
    pending_rest_heal: int | None = None
    # Play-state: temporary per-ability score adjustments set on the live sheet.
    # Signed deltas keyed by Ability; only non-zero entries are stored. They
    # stack with magic-item ability modifiers and clamp the final effective
    # score to [3, 18] (see aose/engine/magic.py). The real `abilities` are
    # never altered.
    temp_ability_modifiers: dict[Ability, int] = Field(default_factory=dict)
    # All owned catalog items (plain, enchanted, or stacked ammo) — unified.
    # Location, equip-state, and enchantment are on each instance.
    items: list[ItemInstance] = Field(default_factory=list)
    containers: list[ContainerInstance] = Field(default_factory=list)
    animals: list[AnimalInstance] = Field(default_factory=list)
    vehicles: list[VehicleInstance] = Field(default_factory=list)
    magic_items: list[MagicItemInstance] = Field(default_factory=list)
    # Owned spell books / scrolls (custom contents).  Not in `inventory`.
    spell_sources: list[SpellSource] = Field(default_factory=list)
    # Owned treasure — gems (stacked by value+label) and jewellery (individual).
    # Weightless; free to acquire; never in `inventory`.
    gems: list[GemStack] = Field(default_factory=list)
    jewellery: list[JewelleryPiece] = Field(default_factory=list)
    secondary_skills: list[str] = Field(default_factory=list)
    # Free-text "other possessions" — discrete entries, each an implied item the
    # DM handed out ("a bronze key"). Untracked: no weight, value, or encumbrance.
    other_possessions: list[str] = Field(default_factory=list)
    # Open-ended scratch notes, unrelated to inventory.
    notes: str = ""
    # Chosen *additional* languages only (INT-based picks).  Native (race) and
    # alignment tongues are derived at display time, never stored here.
    languages: list[str] = Field(default_factory=list)
    # Weapon Proficiency optional rule (per-weapon).  Specialised weapons must
    # also appear in weapon_proficiencies; specialisation costs a 2nd slot.
    weapon_proficiencies: list[str] = Field(default_factory=list)
    weapon_specialisations: list[str] = Field(default_factory=list)
    # CC3 feature choices: group id -> chosen option ids (distinct).
    feature_choices: dict[str, list[str]] = Field(default_factory=dict)
    # Free player-chosen params for parameterised choice options: option id ->
    # value. Slayer: enemy-type text. (Weapon specialist's weapon lives in
    # weapon_specialisations.)
    choice_params: dict[str, str] = Field(default_factory=dict)
    # Innate daily-use ability id -> uses spent today (reset on rest).
    innate_uses: dict[str, int] = Field(default_factory=dict)
    ruleset: RuleSet = Field(default_factory=RuleSet)
    retainers: list["Retainer"] = Field(default_factory=list)


class Retainer(BaseModel):
    """A hired NPC the character employs. Wraps a full CharacterSpec so the
    whole engine (sheet, leveling, HP, saves, attacks, equip) works on it
    unchanged. ``loyalty`` is the current (editable) loyalty value; ``role`` is
    a free-text note. A retainer's own ``spec.retainers`` stays empty."""
    model_config = ConfigDict(extra="forbid")

    id: str                       # uuid4 hex
    spec: CharacterSpec
    loyalty: int
    role: str = ""


CharacterSpec.model_rebuild()
