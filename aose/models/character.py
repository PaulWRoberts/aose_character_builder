from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ability import Ability
from .modifier import Modifier
from .ruleset import RuleSet
from .valuable import GemStack, JewelleryPiece


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


class EnchantedInstance(BaseModel):
    """A specific magic weapon/armour the character owns, modelled as a
    composition of a base catalog item + a reusable ``Enchantment``.  Resolved
    to a synthetic ``Weapon``/``Armor`` at display time by
    ``aose/engine/enchant.py``; nothing composed is persisted.  Not stored in
    ``inventory``/``equipped``/``equipped_weapons`` — carries its own
    ``equipped`` bool.  Passive enchantment modifiers apply only while equipped.
    """
    model_config = ConfigDict(extra="forbid")

    instance_id: str                  # uuid4 hex
    base_id: str                      # references a Weapon or Armor
    enchantment_id: str               # references an Enchantment
    equipped: bool = False
    charges_max: int | None = None
    charges_remaining: int | None = None
    extra_modifiers: list[Modifier] = Field(default_factory=list)  # escape hatch
    note: str = ""


class AmmoStack(BaseModel):
    """A stack of one kind of ammunition the character owns.  Stacks with the
    same (base_id, enchantment_id) combine; counts are adjusted manually (no
    automatic per-shot consumption).  ``enchantment_id`` set => magic ammo,
    resolved like an EnchantedInstance to confer its bonus to a loaded launcher.
    """
    model_config = ConfigDict(extra="forbid")

    instance_id: str                       # uuid4 hex
    base_id: str                           # references an Ammunition item
    enchantment_id: str | None = None      # references an Enchantment (kind ammunition)
    count: int = 0


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
    # Known spells (arcane spellbook).  Empty for divine casters, who know
    # their whole list automatically; see aose/engine/spells.py.
    spellbook: list[str] = Field(default_factory=list)
    # Daily memorized loadout as individual slots; duplicates allowed (two slots,
    # same spell_id).  Hard-capped per spell level by spell_slots.  Replaces the
    # old flat ``prepared`` list — each slot also tracks reversed/spent state.
    slots: list[SpellSlot] = Field(default_factory=list)

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
    gold: int = 0            # gp — the shop-spendable balance
    platinum: int = 0        # pp
    electrum: int = 0        # ep
    silver: int = 0          # sp
    copper: int = 0          # cp
    # Basic-encumbrance referee toggle: carrying a significant amount of
    # treasure (drops the movement rate one step). Detailed mode ignores it.
    carrying_treasure: bool = False
    # Play-state: hit points of damage taken.  Current HP is derived as
    # max(0, max_hp − damage_taken); dead == current HP 0.  Tracks live max_hp
    # shifts (e.g. a CON-altering magic item) without rewriting stored state.
    damage_taken: int = 0
    # Play-state: temporary per-ability score adjustments set on the live sheet.
    # Signed deltas keyed by Ability; only non-zero entries are stored. They
    # stack with magic-item ability modifiers and clamp the final effective
    # score to [3, 18] (see aose/engine/magic.py). The real `abilities` are
    # never altered.
    temp_ability_modifiers: dict[Ability, int] = Field(default_factory=dict)
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
    enchanted: list[EnchantedInstance] = Field(default_factory=list)
    # Ammunition stacks (counts), plus which stack is loaded into each launcher.
    ammo: list[AmmoStack] = Field(default_factory=list)
    loaded_ammo: dict[str, str] = Field(default_factory=dict)  # weapon_key -> AmmoStack.instance_id
    # Owned spell books / scrolls (custom contents).  Not in `inventory`.
    spell_sources: list[SpellSource] = Field(default_factory=list)
    # Owned treasure — gems (stacked by value+label) and jewellery (individual).
    # Weightless; free to acquire; never in `inventory`.
    gems: list[GemStack] = Field(default_factory=list)
    jewellery: list[JewelleryPiece] = Field(default_factory=list)
    secondary_skill: str | None = None
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
