from pydantic import BaseModel, Field

from aose.data.loader import GameData
from aose.engine import ability_mods, armor_class, attack_bonus, hp, saves, spells as spell_engine
from aose.engine import currency as currency_engine
from aose.engine import spell_sources as spell_source_engine
from aose.engine import valuables as valuables_engine
from aose.engine.attacks import AttackProfile, attack_modifiers_detail, attack_profiles
from aose.engine.encumbrance import (
    MAX_LOAD,
    EncumbranceTable,
    armor_movement_class,
    band_label,
    banding_weight_cn,
    carried_weight_cn,
    effective_movement,
    encumbrance_table,
    treasure_weight_cn,
    weight_band,
)
from aose.engine.languages import (
    broken_speech, display_name, granted_languages, known_languages, literacy,
)
from aose.engine.leveling import ClassAdvancement, all_advancement
from aose.engine.detail import DetailCard, item_card, spell_card
from aose.engine.shop import CoinRow, ContainerView, TopLevelGroup, _build_row, inventory_view
from aose.sheet.companions_view import CompanionsBlock, companions_block
from aose.engine.features import is_race_as_class, open_doors_category_bonus, selected_options
from aose.engine.initiative import initiative_detail
from aose.engine.innate import innate_abilities as _innate_abilities
from aose.engine.magic import active_modifiers, apply_modifiers, effective_abilities
from aose.models import Ability, CharacterSpec, MagicItem, MagicItemInstance, RuleSet

ABILITY_ORDER = [Ability.STR, Ability.INT, Ability.WIS, Ability.DEX, Ability.CON, Ability.CHA]

ALIGNMENT_LABELS = {"law": "Lawful", "neutral": "Neutral", "chaos": "Chaotic"}

SAVE_ORDER = ["death", "wands", "paralysis", "breath", "spells"]
SAVE_LABELS = {
    "death": "Death / Poison",
    "wands": "Magic Wands",
    "paralysis": "Paralysis / Petrify",
    "breath": "Breath Attacks",
    "spells": "Spells / Rods / Staves",
}

OPTIONAL_RULE_LABELS = {
    "ascending_ac": "Ascending AC",
    "secondary_skills": "Secondary Skills",
    "weapon_proficiency": "Weapon Proficiency",
    "multiclassing": "Multiclassing",
    "reroll_1s_2s_hp_l1": "Reroll 1s & 2s for HP at L1",
    "lift_demihuman_restrictions": "Lift Demihuman Class & Level Restrictions",
    "variable_weapon_damage": "Variable Weapon Damage",
    "individual_initiative": "Individual Initiative",
    "cantrips": "Cantrips",
    "read_magic_cantrip": "Read Magic Cantrip",
}

ENCUMBRANCE_DESCRIPTIONS = {
    "none": "Encumbrance is ignored entirely.",
    "basic": ("Movement is set by armour worn and whether you carry significant "
              "treasure. Only treasure weight is tracked, against the 1,600 cn cap."),
    "detailed": ("Movement is set by total weight: armour and weapons by listed "
                 "weight, miscellaneous gear as a flat 80 cn, plus all treasure."),
}


class AbilityModLine(BaseModel):
    source: str           # item/feature name, or "Temporary"
    effect: str           # "+2", "−1", "set to 18" …
    conditional: bool     # True when the modifier carries a condition
    note: str             # condition label ("" when unconditional)


class AbilityTableCell(BaseModel):
    label: str            # column name (e.g. "Open Doors")
    value: str            # banded value for the computed score
    note: str = ""        # explanatory note (e.g. gargantua category bump)


class AbilityRow(BaseModel):
    ability: str
    score: int            # final effective score (clamped) — the headline
    modifier: int
    base_score: int = 0   # real underlying score
    equip_delta: int = 0  # magic-effective minus base (works for add & set ops)
    temp_delta: int = 0   # temporary modifier (signed)
    modified: bool = False
    lines: list[AbilityModLine] = Field(default_factory=list)
    table: list[AbilityTableCell] = Field(default_factory=list)
    has_conditional: bool = False


class SheetSaveLine(BaseModel):
    source: str
    bonus: int
    conditional: bool
    note: str


class SheetSave(BaseModel):
    name: str
    label: str
    base: int
    modified: int
    lines: list[SheetSaveLine]


class SheetSituationalSave(BaseModel):
    bonus: int
    vs: str            # joined display, e.g. "fire & lightning"
    source: str

    @classmethod
    def from_bonus_things(cls, bonus: int, things: list[str], source: str) -> "SheetSituationalSave":
        if len(things) <= 1:
            vs = things[0] if things else ""
        elif len(things) == 2:
            vs = f"{things[0]} & {things[1]}"
        else:
            vs = ", ".join(things[:-1]) + f" & {things[-1]}"
        return cls(bonus=bonus, vs=vs, source=source)


class SheetACLine(BaseModel):
    source: str
    effect: str
    conditional: bool
    note: str


class SheetAttackLine(BaseModel):
    source: str
    bonus: int
    conditional: bool
    note: str


class SheetFeature(BaseModel):
    name: str
    text: str
    source: str
    spell_detail: DetailCard | None = None


class InnateAbilityRow(BaseModel):
    id: str
    name: str
    text: str
    source: str
    max_uses: int
    used: int
    remaining: int
    spell_detail: DetailCard | None = None


class EquippedRow(BaseModel):
    slot: str
    item_name: str
    item_id: str = ""


class ProficientWeaponView(BaseModel):
    id: str
    name: str
    damage: str
    specialised: bool = False


class ProficiencyView(BaseModel):
    category: str
    penalty: int
    slots_total: int
    slots_spent: int
    weapons: list[ProficientWeaponView]


class WeaponQualityRef(BaseModel):
    id: str
    name: str
    description: str


class MagicItemView(BaseModel):
    instance_id: str | None
    catalog_id: str
    name: str
    description: str | None
    equippable: bool
    equipped: bool
    charges_remaining: int | None
    charges_max: int | None
    note: str
    modifier_summary: list[str]


class AmmoRow(BaseModel):
    instance_id: str
    name: str
    count: int
    magic: bool
    detail: DetailCard | None = None


class AmmoOption(BaseModel):
    instance_id: str
    name: str
    count: int


class SpellEntryView(BaseModel):
    id: str
    name: str
    level: int
    description: str
    reversible: bool
    detail: DetailCard | None = None


class SlotView(BaseModel):
    index: int          # index into ClassEntry.slots (for cast/clear/restore)
    spell_id: str
    name: str
    display_name: str   # reverse name when reversed
    level: int
    reversible: bool
    reversed: bool
    spent: bool
    detail: DetailCard | None = None


class SpellLevelGroup(BaseModel):
    level: int
    cap: int                  # memorizable slots at this level
    free: int                 # cap − filled
    slots: list[SlotView]     # filled slots at this level


class SpellClassView(BaseModel):
    class_id: str
    class_name: str
    caster_type: str            # "arcane" | "divine"
    can_learn: bool             # arcane only
    can_forget: bool            # arcane + standard spell book + not strict mode
    known: list[SpellEntryView]
    slot_groups: list[SpellLevelGroup]
    learnable: list[SpellEntryView]


class SpellSourceEntryView(BaseModel):
    spell_id: str
    name: str
    level: int
    copy_failed: bool
    can_cast: bool
    can_copy: bool
    detail: DetailCard | None = None


class SpellSourceView(BaseModel):
    instance_id: str
    kind: str                 # "spellbook" | "scroll"
    caster_type: str
    name: str                 # display label (falls back to a default)
    arcane_class_id: str | None  # the class whose book a Copy targets, if any
    entries: list[SpellSourceEntryView]


class SpellSourceOptionGroup(BaseModel):
    list_id: str | None       # set for arcane spellbook lists; None for scroll type buckets
    label: str
    caster_type: str
    spells: list[SpellEntryView]


class SpellSourceAddOptions(BaseModel):
    arcane_lists: list[SpellSourceOptionGroup]   # spellbook: one group per arcane list
    arcane_spells: list[SpellEntryView]          # scroll arcane: all arcane spells
    divine_spells: list[SpellEntryView]          # scroll divine: all divine spells


class GemRow(BaseModel):
    instance_id: str
    value: int
    count: int
    label: str
    stack_value: int


class JewelleryRow(BaseModel):
    instance_id: str
    value: int           # full value
    damaged: bool
    label: str
    effective_value: int


class ValuablesView(BaseModel):
    gems: list[GemRow]
    jewellery: list[JewelleryRow]
    total_value: int


class SpellbookRow(BaseModel):
    spell_id: str
    name: str
    display_name: str    # reverse name when reversed, else name
    level: int
    reversible: bool
    reversed: bool = False
    description: str
    known: bool          # in book (arcane) / on accessible list (divine)
    ready: int           # memorised copies with casts remaining
    spent: int           # memorised copies already cast
    ready_slots: list[int] = []   # ClassEntry.slots indices, ready (for cast)
    spent_slots: list[int] = []   # ClassEntry.slots indices, spent (for restore)


class SpellbookLevelGroup(BaseModel):
    level: int
    cap: int             # memorizable slots at this level
    used: int            # filled slots at this level
    rows: list[SpellbookRow]


class SpellbookBlock(BaseModel):
    class_id: str
    class_name: str
    caster_type: str         # arcane | divine
    levels: list[SpellbookLevelGroup]


class MentalPowerRow(BaseModel):
    power_id: str
    name: str
    detail: DetailCard | None = None


class MentalPowersBlock(BaseModel):
    class_id: str
    class_name: str
    cap: int                       # powers known at this level
    known: list[MentalPowerRow]
    addable: list[MentalPowerRow]  # on-list powers not yet known
    can_add: bool                  # len(known) < cap
    uses_total: int                # 2 x level
    uses_used: int
    uses_remaining: int


class LevelUpModal(BaseModel):
    class_id: str
    class_name: str
    current_level: int
    next_level: int
    hit_die: str
    con_mod: int
    at_name_level: bool
    flat_hp: int
    pending: int | None
    strict_mode: bool
    can_level: bool


class CharacterSheet(BaseModel):
    name: str
    race_name: str
    race_as_class: bool  # true → omit race from subtitle (avoids "Dwarf · Dwarf 1")
    class_summary: str
    alignment: str
    xp: int                                  # total XP across all classes
    next_level: int | None
    xp_to_next: int | None
    advancement: list[ClassAdvancement]      # one entry per class (own XP/level)
    level_up_modals: list[LevelUpModal] = Field(default_factory=list)

    abilities: list[AbilityRow]

    max_hp: int
    current_hp: int
    is_dead: bool
    ac_descending: int
    ac_ascending: int
    unarmored_ac_descending: int
    unarmored_ac_ascending: int
    use_ascending: bool
    ac_lines: list[SheetACLine]
    ac_has_conditional: bool
    thac0: int
    attack_bonus: int
    attack_lines: list[SheetAttackLine]
    attack_has_conditional: bool
    individual_initiative: bool
    initiative_modifier: int
    initiative_lines: list[SheetAttackLine]
    initiative_has_conditional: bool

    saves: list[SheetSave]
    situational_saves: list[SheetSituationalSave]

    languages: list[str]
    literacy: str                    # "illiterate" / "basic" / "literate"
    broken_speech: bool              # INT 3 — speaks only in broken sentences
    movement_base: int               # effective exploration move (after encumbrance)
    movement_encounter: int          # = movement_base // 3
    movement_overland: int           # miles/day = exploration // 5
    movement_unencumbered: int       # race base, for "before encumbrance" reference
    carried_weight_cn: int | None    # None when encumbrance is "none"
    armor_movement_class: str        # "none" / "leather" / "metal"
    current_weight_band: str | None  # human-readable band label, None in basic/none modes
    encumbrance_table: EncumbranceTable | None  # full threshold table for the sheet

    race_features: list[SheetFeature]
    class_features: list[SheetFeature]

    equipped: list[EquippedRow]
    inventory: list[str]
    attacks: list[AttackProfile]

    secondary_skills: list[str]
    proficiencies: ProficiencyView | None
    weapon_proficiency_active: bool
    weapon_qualities_reference: list[WeaponQualityRef]

    magic_items: list[MagicItemView]
    spells: list[SpellClassView]
    spellbook: list[SpellbookBlock] = Field(default_factory=list)
    mental_powers: list[MentalPowersBlock] = Field(default_factory=list)
    innate_abilities: list[InnateAbilityRow] = Field(default_factory=list)
    spell_sources: list[SpellSourceView] = Field(default_factory=list)
    valuables: ValuablesView = Field(default_factory=lambda: ValuablesView(
        gems=[], jewellery=[], total_value=0))
    ammo: list[AmmoRow] = Field(default_factory=list)
    ammo_load_options: dict[str, list[AmmoOption]] = Field(default_factory=dict)
    companions: CompanionsBlock | None = None
    race_id: str = ""
    retainer_class_options: list[dict] = Field(default_factory=list)
    other_possessions: list[str] = Field(default_factory=list)
    notes: str = ""

    coins: dict[str, int] = Field(default_factory=dict)   # {"pp":..,"gp":..,...}
    treasure_value_gp: int = 0
    treasure_weight_cn: int = 0
    carrying_treasure: bool = False
    max_load: int = MAX_LOAD

    inventory_groups: list[TopLevelGroup] = Field(default_factory=list)
    total_wealth_gp: int = 0

    armor_tailorable: bool = False   # equipped body armour can be tailored (full plate)
    armor_tailored: bool = True      # and is currently fitted to this wearer

    pending_rest_heal: int | None = None
    strict_mode: bool = False

    enabled_optional_rules: list[str]
    encumbrance_mode: str
    encumbrance_description: str

    # Unspent level-up selections (proficiency slots, talent picks).
    level_choices: list = Field(default_factory=list)
    # Weapon options for the inline proficiency picker (base types only).
    proficiency_weapon_options: list = Field(default_factory=list)
    # Available talent options per group id, keyed by group_id.
    talent_options: dict = Field(default_factory=dict)


def _coins_dict(spec) -> dict[str, int]:
    """Aggregate all coin stacks into a {denom: total_count} dict (all locations)."""
    totals: dict[str, int] = {"pp": 0, "gp": 0, "ep": 0, "sp": 0, "cp": 0}
    for s in spec.coins:
        totals[s.denom] = totals.get(s.denom, 0) + s.count
    return totals


def _summarize_modifier(m) -> str:
    """Return a human-readable one-line description of a Modifier."""
    t = m.target
    if t.startswith("ability:"):
        ab = t.split(":", 1)[1]
        return (
            f"{ab} → {m.value}"
            if m.op in ("set", "set_min", "set_max")
            else f"{ab} {'+' if m.value >= 0 else ''}{m.value}"
        )
    if t == "ac":
        return f"+{m.value} AC" if m.op == "add" else f"AC {m.value}"
    if t == "save:all":
        return f"+{m.value} all saves" if m.op == "add" else f"saves {m.value}"
    if t.startswith("save:"):
        cat = t.split(":", 1)[1]
        return f"+{m.value} {cat} save" if m.op == "add" else f"{cat} save {m.value}"
    if t == "attack":
        return f"+{m.value} to hit"
    if t == "damage":
        return f"+{m.value} damage"
    if t == "carry_capacity":
        return f"+{m.value} cn capacity"
    if t == "thac0":
        return f"THAC0 {m.value}" if m.op != "add" else f"+{m.value} THAC0"
    return f"{t} {m.op} {m.value}"


def _magic_bonus_summary(item) -> list[str]:
    """Return mechanical bullet-points for a plain-inventory magic weapon or armour."""
    from aose.models import Armor, Weapon
    out: list[str] = []
    if isinstance(item, Weapon) and item.magic_bonus:
        out.append(f"+{item.magic_bonus} to hit & damage")
        if item.conditional_bonus:
            out.append(
                f"+{item.magic_bonus + item.conditional_bonus.bonus}"
                f" vs {item.conditional_bonus.vs}"
            )
    if isinstance(item, Armor) and item.magic_bonus:
        out.append(f"+{item.magic_bonus} AC")
    return out


def magic_items_view(
    magic_items: list[MagicItemInstance],
    inventory: list[str],
    data: GameData,
) -> list[MagicItemView]:
    """Build the Magic Items view rows from raw instance + inventory lists.

    (a) Every ``MagicItemInstance`` → a row with instance_id set; summary
        combines catalog.modifiers + inst.extra_modifiers via
        ``_summarize_modifier``.
    (b) Plain-inventory items whose catalog ``.magic`` is True → a row with
        instance_id None; deduped by catalog_id; summary via
        ``_magic_bonus_summary``.

    This is the canonical implementation.  ``_magic_items`` is a thin wrapper
    so ``build_sheet`` stays unchanged; the wizard can call this helper directly
    with raw draft lists.
    """
    views: list[MagicItemView] = []

    # Instance-tracked magic items (equippable / charged)
    for inst in magic_items:
        catalog = data.items.get(inst.catalog_id)
        is_magic = isinstance(catalog, MagicItem)
        summary = (
            [_summarize_modifier(m) for m in catalog.modifiers] if is_magic else []
        ) + [_summarize_modifier(m) for m in inst.extra_modifiers]
        views.append(MagicItemView(
            instance_id=inst.instance_id,
            catalog_id=inst.catalog_id,
            name=catalog.name if catalog else inst.catalog_id,
            description=catalog.description if catalog else None,
            equippable=bool(is_magic and catalog.equippable),
            equipped=inst.equipped,
            charges_remaining=inst.charges_remaining,
            charges_max=inst.charges_max,
            note=inst.note,
            modifier_summary=summary,
        ))

    # Plain-inventory magic items (deduped by catalog_id; V1 has no count field)
    seen: set[str] = set()
    for item_id in inventory:
        if item_id in seen:
            continue
        item = data.items.get(item_id)
        if item is None or not getattr(item, "magic", False):
            continue
        seen.add(item_id)
        views.append(MagicItemView(
            instance_id=None,
            catalog_id=item_id,
            name=item.name,
            description=item.description,
            equippable=False,
            equipped=False,
            charges_remaining=None,
            charges_max=None,
            note="",
            modifier_summary=_magic_bonus_summary(item),
        ))

    return views


def _magic_items(spec: CharacterSpec, data: GameData) -> list[MagicItemView]:
    """Thin wrapper — delegates to the public ``magic_items_view`` helper."""
    return magic_items_view(spec.magic_items, spec.inventory, data)


def enchanted_items_view(enchanted, data: GameData) -> list[MagicItemView]:
    """Build Magic-Items rows for EnchantedInstance items.  Each resolves to a
    synthetic weapon/armour for its display name; the summary combines the
    enchantment's magic_bonus, passive modifiers, and per-instance
    extra_modifiers.  All enchanted items are equippable."""
    from aose.engine.enchant import resolve_instance
    views: list[MagicItemView] = []
    for inst in enchanted:
        ench = data.enchantments.get(inst.enchantment_id)
        resolved = resolve_instance(inst, data)
        name = resolved.name if resolved is not None else inst.enchantment_id
        summary: list[str] = []
        if ench is not None and ench.magic_bonus:
            if ench.kind == "weapon":
                summary.append(f"+{ench.magic_bonus} to hit & damage")
                if ench.conditional_bonus:
                    summary.append(
                        f"+{ench.magic_bonus + ench.conditional_bonus.bonus}"
                        f" vs {ench.conditional_bonus.vs}")
            else:
                summary.append(f"+{ench.magic_bonus} AC")
        if ench is not None:
            summary += [_summarize_modifier(m) for m in ench.modifiers]
        summary += [_summarize_modifier(m) for m in inst.extra_modifiers]
        views.append(MagicItemView(
            instance_id=inst.instance_id,
            catalog_id=inst.base_id,
            name=name,
            description=ench.description if ench is not None else None,
            equippable=True,
            equipped=inst.equipped,
            charges_remaining=inst.charges_remaining,
            charges_max=inst.charges_max,
            note=inst.note,
            modifier_summary=summary,
        ))
    return views


def _class_summary(spec: CharacterSpec, data: GameData) -> str:
    parts = []
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        parts.append(f"{cls.name} {entry.level}")
    return " / ".join(parts)


def _xp_to_next(spec: CharacterSpec, data: GameData) -> tuple[int | None, int | None]:
    """Legacy single-class shim kept for the existing CharacterSheet fields.

    Multi-class characters return (None, None) here — read ``sheet.advancement``
    instead for the per-class story.  All cap/limit logic now lives in
    :mod:`aose.engine.leveling`.
    """
    if len(spec.classes) != 1:
        return None, None
    from aose.engine.leveling import class_advancement
    adv = class_advancement(spec, data, spec.classes[0])
    if adv.at_max:
        return None, None
    return adv.next_level, adv.next_threshold


def _feature_row(feat, source: str, data: GameData) -> SheetFeature:
    spell_id = getattr(feat, "spell_id", None)
    detail = spell_card(data.spells[spell_id]) if spell_id in (data.spells or {}) else None
    return SheetFeature(name=feat.name, text=feat.text, source=source, spell_detail=detail)


def _feature_visible(feat, ruleset: RuleSet) -> bool:
    """A feature whose ``mechanical.requires_rule`` names a RuleSet flag is
    hidden when that flag is off; otherwise always visible."""
    rule = (getattr(feat, "mechanical", None) or {}).get("requires_rule")
    if rule is None:
        return True
    return bool(getattr(ruleset, rule, False))


def _race_features(spec: CharacterSpec, data: GameData) -> list[SheetFeature]:
    if _is_race_as_class(spec, data):
        return []
    race = data.races[spec.race_id]
    rs = spec.ruleset
    rows = [_feature_row(f, f"Race: {race.name}", data)
            for f in race.features if _feature_visible(f, rs)]
    rows += [_feature_row(o, f"Race: {race.name}", data)
             for o in selected_options(race, spec.feature_choices)
             if _feature_visible(o, rs)]
    return rows


def _class_features(spec: CharacterSpec, data: GameData) -> list[SheetFeature]:
    out: list[SheetFeature] = []
    rs = spec.ruleset
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        for f in cls.features:
            if f.gained_at_level <= entry.level and _feature_visible(f, rs):
                out.append(_feature_row(f, f"Class: {cls.name}", data))
        for o in selected_options(cls, spec.feature_choices):
            if _feature_visible(o, rs):
                out.append(_feature_row(o, f"Class: {cls.name}", data))
    return out


def _equipped(spec: CharacterSpec, data: GameData) -> list[EquippedRow]:
    rows: list[EquippedRow] = []
    for slot, item_id in spec.equipped.items():
        name = data.items[item_id].name if item_id in data.items else item_id
        rows.append(EquippedRow(slot=slot, item_name=name, item_id=item_id))
    return rows


def _inventory(spec: CharacterSpec, data: GameData) -> list[str]:
    return [data.items[i].name if i in data.items else i for i in spec.inventory]


def _enabled_optional_rules(rs: RuleSet) -> list[str]:
    return [label for field, label in OPTIONAL_RULE_LABELS.items() if getattr(rs, field)]


def _proficiency_view(spec: CharacterSpec, data: GameData) -> "ProficiencyView | None":
    """Per-weapon proficiency view for the sheet.  None when the rule is off."""
    from aose.engine.proficiency import (
        category_for_classes,
        penalty_for_classes,
        slots_spent,
        total_proficiency_slots,
    )
    from aose.models import Weapon

    if not spec.ruleset.weapon_proficiency:
        return None

    classes = [data.classes[e.class_id] for e in spec.classes if e.class_id in data.classes]
    pairs = [(data.classes[e.class_id], e.level) for e in spec.classes
             if e.class_id in data.classes]
    use_variable = spec.ruleset.variable_weapon_damage
    weapons: list[ProficientWeaponView] = []
    for wid in spec.weapon_proficiencies:
        item = data.items.get(wid)
        if not isinstance(item, Weapon):
            continue
        weapons.append(ProficientWeaponView(
            id=item.id,
            name=item.name,
            damage=(item.damage.variable if use_variable else item.damage.default),
            specialised=wid in spec.weapon_specialisations,
        ))
    weapons.sort(key=lambda w: w.name)
    return ProficiencyView(
        category=category_for_classes(classes) if classes else "non_martial",
        penalty=penalty_for_classes(classes) if classes else -5,
        slots_total=total_proficiency_slots(pairs),
        slots_spent=slots_spent(spec),
        weapons=weapons,
    )


def _weapon_qualities_reference(spec: CharacterSpec, data: GameData) -> list[WeaponQualityRef]:
    """Quality definitions for qualities present on the character's equipped or
    owned weapons — for the in-game reference block."""
    from aose.models import Weapon

    present: set[str] = set()
    for wid in set(spec.inventory) | set(spec.equipped.values()):
        item = data.items.get(wid)
        if isinstance(item, Weapon):
            present.update(item.quality_ids)
    refs = [
        WeaponQualityRef(id=q.id, name=q.name, description=q.description)
        for qid in sorted(present)
        if (q := data.qualities.get(qid)) is not None
    ]
    return refs


def _is_race_as_class(spec: CharacterSpec, data: GameData) -> bool:
    """True when the character's (single) class is race-locked to their race.

    Multi-class characters never trigger this — the subtitle would still need
    to surface the race separately from each class. Thin alias over the engine
    predicate so the sheet and the modifier pipeline agree on what counts.
    """
    return is_race_as_class(spec, data)


def _spell_entry(spell) -> SpellEntryView:
    return SpellEntryView(
        id=spell.id, name=spell.name, level=spell.level,
        description=spell.description, reversible=spell.reversible,
        detail=spell_card(spell),
    )


def _slot_display_name(spell, reversed: bool) -> str:
    if reversed:
        return spell.reverse_name or f"{spell.name} (reversed)"
    return spell.name


def spells_view(spec: CharacterSpec, data: GameData) -> list[SpellClassView]:
    """One block per casting class entry; shared by the live sheet and the
    wizard review.  Arcane blocks expose learnable spells; divine know their
    whole accessible list.  Memorized spells are grouped into per-level slot
    rows (filled slots + free count)."""
    out: list[SpellClassView] = []
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        ctype = spell_engine.caster_type_of(cls, data)
        if ctype is None or ctype == "mental":
            continue
        known = spell_engine.known_spells(entry, cls, data, spec.ruleset)
        caps = spell_engine.memorizable_slots(entry, cls, data, spec.ruleset)
        groups: list[SpellLevelGroup] = []
        for level in sorted(caps):
            filled = [
                SlotView(
                    index=i,
                    spell_id=slot.spell_id,
                    name=data.spells[slot.spell_id].name,
                    display_name=_slot_display_name(data.spells[slot.spell_id], slot.reversed),
                    level=slot.level,
                    reversible=data.spells[slot.spell_id].reversible,
                    reversed=slot.reversed,
                    spent=slot.spent,
                    detail=spell_card(data.spells[slot.spell_id], reversed=slot.reversed),
                )
                for i, slot in enumerate(entry.slots)
                if slot.spell_id is not None
                and slot.level == level
                and slot.spell_id in data.spells
            ]
            groups.append(SpellLevelGroup(
                level=level, cap=caps[level],
                free=caps[level] - len(filled), slots=filled,
            ))
        is_arcane = ctype == "arcane"
        out.append(SpellClassView(
            class_id=entry.class_id,
            class_name=cls.name,
            caster_type=ctype,
            can_learn=is_arcane,
            can_forget=(
                is_arcane
                and not spec.ruleset.advanced_spell_books
                and not spec.ruleset.strict_mode
            ),
            known=[_spell_entry(s) for s in known],
            slot_groups=groups,
            learnable=(
                [] if spec.ruleset.advanced_spell_books
                else [_spell_entry(s) for s in spell_engine.learnable_spells(entry, cls, data, spec.ruleset)]
            ),
        ))
    return out


def spellbook_view(spec: CharacterSpec, data: GameData) -> list[SpellbookBlock]:
    """One block per casting class: arcane shows the spellbook by level with
    cast-pip counts; divine shows only memorised spells (ready/spent).

    Each row carries ready/spent counts derived from ClassEntry.slots."""
    out: list[SpellbookBlock] = []
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        ctype = spell_engine.caster_type_of(cls, data)
        if ctype is None or ctype == "mental":
            continue
        caps = spell_engine.memorizable_slots(entry, cls, data, spec.ruleset)  # {level: cap}
        known = spell_engine.known_spells(entry, cls, data, spec.ruleset)      # book (arcane) / list (divine)
        known_ids = {s.id for s in known}
        # tally memorised copies per (level, spell_id, reversed), tracking slot indices
        ready: dict[tuple[int, str, bool], int] = {}
        spent: dict[tuple[int, str, bool], int] = {}
        ready_idx: dict[tuple[int, str, bool], list[int]] = {}
        spent_idx: dict[tuple[int, str, bool], list[int]] = {}
        used_by_level: dict[int, int] = {}
        for i, slot in enumerate(entry.slots):
            if slot.spell_id is None:
                continue
            key = (slot.level, slot.spell_id, slot.reversed)
            if slot.spent:
                spent[key] = spent.get(key, 0) + 1
                spent_idx.setdefault(key, []).append(i)
            else:
                ready[key] = ready.get(key, 0) + 1
                ready_idx.setdefault(key, []).append(i)
            used_by_level[slot.level] = used_by_level.get(slot.level, 0) + 1

        def _row(spell, level: int, rev: bool) -> SpellbookRow:
            key = (level, spell.id, rev)
            return SpellbookRow(
                spell_id=spell.id, name=spell.name,
                display_name=_slot_display_name(spell, rev),
                level=spell.level, reversible=spell.reversible, reversed=rev,
                description=spell.description, known=spell.id in known_ids,
                ready=ready.get(key, 0), spent=spent.get(key, 0),
                ready_slots=ready_idx.get(key, []), spent_slots=spent_idx.get(key, []),
            )

        levels: list[SpellbookLevelGroup] = []
        for level in sorted(caps):
            rows: list[SpellbookRow] = []
            # (spell_id, reversed) combos that have at least one memorised copy here
            memo_keys = {
                (sid, rev)
                for (lv, sid, rev) in list(ready.keys()) + list(spent.keys())
                if lv == level
            }
            if ctype == "arcane":
                level_known = [s for s in known if s.level == level]
                known_ids_at_level = {s.id for s in level_known}
                # 1) every known book spell (normal orientation)
                for s in level_known:
                    rows.append(_row(s, level, False))
                # 2) reversed memorisations + any memorised spell not in the book
                for (sid, rev) in sorted(memo_keys):
                    if not rev and sid in known_ids_at_level:
                        continue  # already emitted as a known row above
                    s = data.spells.get(sid)
                    if s is not None:
                        rows.append(_row(s, level, rev))
            else:
                # Divine: only show memorised spells (ready or spent)
                for (sid, rev) in sorted(memo_keys):
                    s = data.spells.get(sid)
                    if s is not None:
                        rows.append(_row(s, level, rev))
            levels.append(SpellbookLevelGroup(
                level=level, cap=caps[level],
                used=used_by_level.get(level, 0), rows=rows,
            ))
        out.append(SpellbookBlock(
            class_id=entry.class_id, class_name=cls.name,
            caster_type=ctype, levels=levels,
        ))
    return out


def mental_powers_view(spec: CharacterSpec, data: GameData) -> list[MentalPowersBlock]:
    """One block per mental caster class: known powers, addable powers, and the
    daily-use pool (2 x level activations)."""
    out: list[MentalPowersBlock] = []
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        if spell_engine.caster_type_of(cls, data) != "mental":
            continue
        cap = spell_engine.powers_known_cap(entry, cls)
        known = [
            MentalPowerRow(power_id=s.id, name=s.name, detail=spell_card(s))
            for s in spell_engine.known_spells(entry, cls, data)
        ]
        addable = [
            MentalPowerRow(power_id=s.id, name=s.name, detail=spell_card(s))
            for s in spell_engine.learnable_spells(entry, cls, data)
        ]
        total = spell_engine.power_pool(entry)
        out.append(MentalPowersBlock(
            class_id=entry.class_id, class_name=cls.name, cap=cap,
            known=known, addable=addable, can_add=len(known) < cap,
            uses_total=total, uses_used=entry.powers_used,
            uses_remaining=max(0, total - entry.powers_used),
        ))
    return out


def innate_view(spec: CharacterSpec, data: GameData) -> list[InnateAbilityRow]:
    rows: list[InnateAbilityRow] = []
    for ab in _innate_abilities(spec, data):
        detail = spell_card(data.spells[ab.spell_id]) if ab.spell_id in data.spells else None
        rows.append(InnateAbilityRow(
            id=ab.id, name=ab.name, text=ab.text, source=ab.source,
            max_uses=ab.max_uses, used=ab.used, remaining=ab.remaining,
            spell_detail=detail,
        ))
    return rows


def _first_arcane_class_id(spec: CharacterSpec, data: GameData) -> str | None:
    for entry in spec.classes:
        cls = data.classes.get(entry.class_id)
        if cls is not None and spell_engine.caster_type_of(cls, data) == "arcane":
            return entry.class_id
    return None


def _default_source_name(source) -> str:
    if source.name:
        return source.name
    kind = "Spell Book" if source.kind == "spellbook" else "Scroll"
    n = len(source.entries)
    return f"{kind} ({n} spell{'s' if n != 1 else ''})"


def spell_sources_view(spec: CharacterSpec, data: GameData) -> list[SpellSourceView]:
    """One row per owned spell book / scroll, with per-spell cast/copy flags.

    ``can_cast`` (scrolls): the character has a class matching the scroll's caster
    type.  ``can_copy`` (advanced rule only): arcane caster, arcane source, spell
    castable-level + on-list + not known + not failed on this source."""
    arcane_cid = _first_arcane_class_id(spec, data)
    arcane_entry = None
    arcane_cls = None
    if arcane_cid is not None:
        arcane_entry = next(e for e in spec.classes if e.class_id == arcane_cid)
        arcane_cls = data.classes[arcane_cid]

    advanced = spec.ruleset.advanced_spell_books
    out: list[SpellSourceView] = []
    for source in spec.spell_sources:
        castable = spell_source_engine.can_cast_scroll(source, spec, data)
        copyable: set[str] = set()
        if advanced and arcane_entry is not None:
            copyable = spell_source_engine.copyable_spell_ids(
                source, arcane_entry, arcane_cls, data)
        entries: list[SpellSourceEntryView] = []
        for e in source.entries:
            spell = data.spells.get(e.spell_id)
            entries.append(SpellSourceEntryView(
                spell_id=e.spell_id,
                name=spell.name if spell else e.spell_id,
                level=spell.level if spell else 0,
                copy_failed=e.copy_failed,
                can_cast=castable,
                can_copy=e.spell_id in copyable,
                detail=spell_card(spell) if spell else None,
            ))
        out.append(SpellSourceView(
            instance_id=source.instance_id,
            kind=source.kind,
            caster_type=source.caster_type,
            name=_default_source_name(source),
            arcane_class_id=arcane_cid,
            entries=entries,
        ))
    return out


def spell_source_add_options(data: GameData) -> SpellSourceAddOptions:
    """Selectable spells for the Add-document form, grouped for the UI."""
    arcane_list_ids = {lid for lid, sl in data.spell_lists.items() if sl.caster_type == "arcane"}
    divine_list_ids = {lid for lid, sl in data.spell_lists.items() if sl.caster_type == "divine"}

    arcane_lists: list[SpellSourceOptionGroup] = []
    for lid in sorted(arcane_list_ids):
        sl = data.spell_lists[lid]
        spells = sorted(
            (s for s in data.spells.values() if lid in s.spell_lists),
            key=lambda s: (s.level, s.name),
        )
        arcane_lists.append(SpellSourceOptionGroup(
            list_id=lid, label=sl.name, caster_type="arcane",
            spells=[_spell_entry(s) for s in spells],
        ))

    def bucket(list_ids) -> list[SpellEntryView]:
        spells = sorted(
            (s for s in data.spells.values() if set(s.spell_lists) & list_ids),
            key=lambda s: (s.level, s.name),
        )
        return [_spell_entry(s) for s in spells]

    return SpellSourceAddOptions(
        arcane_lists=arcane_lists,
        arcane_spells=bucket(arcane_list_ids),
        divine_spells=bucket(divine_list_ids),
    )


def valuables_view(spec: CharacterSpec) -> ValuablesView:
    """Gem stacks + jewellery pieces with computed values, plus the section
    total.  Weightless — never touches encumbrance."""
    gems = [
        GemRow(
            instance_id=g.instance_id, value=g.value, count=g.count,
            label=g.label, stack_value=valuables_engine.gem_stack_value(g),
        )
        for g in spec.gems
    ]
    jewellery = [
        JewelleryRow(
            instance_id=j.instance_id, value=j.value, damaged=j.damaged,
            label=j.label, effective_value=valuables_engine.jewellery_value(j),
        )
        for j in spec.jewellery
    ]
    gems.sort(key=lambda r: (-r.value, r.label))
    jewellery.sort(key=lambda r: (-r.value, r.label))
    return ValuablesView(
        gems=gems, jewellery=jewellery,
        total_value=valuables_engine.total_value(spec),
    )


def ammo_view(spec, data: GameData) -> tuple[list[AmmoRow], dict[str, list[AmmoOption]]]:
    """Build ammo rows and per-launcher load options.  ``spec`` may be a
    ``CharacterSpec`` or a draft-like object that has ``.ammo``,
    ``.loaded_ammo``, and ``.equipped``."""
    from aose.engine.ammo import accepts, resolve_ammo
    from aose.models import Ammunition, Weapon

    ammo_rows = []
    for s in spec.ammo:
        view = resolve_ammo(s, data)
        base = data.items.get(s.base_id)
        ammo_rows.append(AmmoRow(
            instance_id=s.instance_id, name=view["name"],
            count=s.count, magic=s.enchantment_id is not None,
            detail=item_card(base) if base is not None else None))

    # Build per-launcher load options from attack profiles
    attacks = attack_profiles(spec, data)
    load_options: dict[str, list[AmmoOption]] = {}
    for prof in attacks:
        weapon = data.items.get(prof.weapon_id)
        if weapon is None or not isinstance(weapon, Weapon) or not weapon.accepts_ammo:
            continue
        opts = []
        for s in spec.ammo:
            base = data.items.get(s.base_id)
            if isinstance(base, Ammunition) and accepts(weapon, base):
                v = resolve_ammo(s, data)
                opts.append(AmmoOption(instance_id=s.instance_id, name=v["name"],
                                       count=s.count))
        if opts:
            load_options[prof.weapon_id] = opts

    return ammo_rows, load_options


def _effect_str(m) -> str:
    """Human-readable effect for an ability modifier line."""
    if m.op == "add":
        return f"+{m.value}" if m.value >= 0 else f"−{abs(m.value)}"
    if m.op == "set":
        return f"set to {m.value}"
    if m.op == "set_min":
        return f"at least {m.value}"
    if m.op == "set_max":
        return f"at most {m.value}"
    return str(m.value)


def _labeled_ability_mods(spec: CharacterSpec, data: GameData) -> list[tuple]:
    """``(modifier, source_label)`` for every equipped item's ``ability:*``
    modifier. The label is the modifier's own ``source`` if set, else the
    catalog/enchantment display name."""
    out: list[tuple] = []
    for inst in spec.magic_items:
        if not inst.equipped:
            continue
        catalog = data.items.get(inst.catalog_id)
        name = getattr(catalog, "name", inst.catalog_id)
        item_mods = list(catalog.modifiers) if isinstance(catalog, MagicItem) else []
        item_mods += list(inst.extra_modifiers)
        out += [(m, m.source or name) for m in item_mods if m.target.startswith("ability:")]
    for inst in spec.enchanted:
        if not inst.equipped:
            continue
        ench = data.enchantments.get(inst.enchantment_id)
        name = getattr(ench, "name", inst.enchantment_id)
        ench_mods = list(ench.modifiers) if ench is not None else []
        ench_mods += list(inst.extra_modifiers)
        out += [(m, m.source or name) for m in ench_mods if m.target.startswith("ability:")]
    return out


def _level_choice_extras(spec: CharacterSpec, data: GameData) -> dict:
    """Compute level_choices, proficiency_weapon_options, and talent_options
    for the CharacterSheet."""
    from aose.engine.level_choices import all_capacities
    from aose.models import Weapon as _W
    from aose.engine.proficiency import base_weapon_id as _bwid, allowed_weapon_ids as _awi

    caps = all_capacities(spec, data)

    # Weapon options for the proficiency picker.
    prof_weapon_opts: list = []
    if any(c.kind == "proficiency" for c in caps):
        classes = [data.classes[e.class_id] for e in spec.classes if e.class_id in data.classes]
        allowed = _awi(classes, data, spec.ruleset)
        for w in sorted(
            (i for i in data.items.values() if isinstance(i, _W) and _bwid(i) == i.id),
            key=lambda w: w.name,
        ):
            if allowed == "all" or w.id in allowed:
                prof_weapon_opts.append({"id": w.id, "name": w.name})

    # Available options per talent group.
    talent_opts: dict = {}
    for c in caps:
        if c.kind != "talent":
            continue
        grp = next(
            (g for e in spec.classes if (cl := data.classes.get(e.class_id))
             for g in cl.feature_choices if g.id == c.group_id),
            None,
        )
        if grp is None:
            continue
        already = set(spec.feature_choices.get(c.group_id, []))
        talent_opts[c.group_id] = [
            {"id": o.id, "name": o.name,
             "param": (o.param.model_dump() if o.param else None)}
            for o in grp.options
            if o.id not in already
            and not (o.excluded_when_rule and getattr(spec.ruleset, o.excluded_when_rule, False))
        ]

    return {
        "level_choices": caps,
        "proficiency_weapon_options": prof_weapon_opts,
        "talent_options": talent_opts,
    }


def _retainer_class_options(spec: CharacterSpec, data: GameData) -> list[dict]:
    from aose.engine.retainers import allowed_retainer_classes
    allowed = allowed_retainer_classes(spec, data)
    return [
        {"id": c.id, "name": c.name}
        for c in data.classes.values()
        if c.id == "normal_human" or allowed == "any" or (isinstance(allowed, set) and c.id in allowed)
    ]


def _retainer_cards(spec: CharacterSpec, data: GameData) -> list:
    from collections import Counter
    from aose.sheet.companions_view import RetainerCard
    from aose.engine.shop import _build_row
    cards = []
    for r in spec.retainers:
        rs = build_sheet(r.spec, data)   # recursive; bounded (retainer.spec.retainers is empty)
        entry = r.spec.classes[0]
        cls = data.classes.get(entry.class_id)
        is_nh = entry.class_id == "normal_human"
        race_name = data.races[r.spec.race_id].name if r.spec.race_id in data.races else ""
        descriptor = ("0-level Normal Human" if is_nh
                      else f"{race_name} {cls.name} {entry.level}".strip() if cls else "")
        equipped_names = {slot: data.items[i].name
                         for slot, i in r.spec.equipped.items() if i in data.items}
        inv_rows = [_build_row(i, n, data) for i, n in Counter(r.spec.inventory).items()]
        inv_rows.sort(key=lambda x: x.name)
        cards.append(RetainerCard(
            id=r.id, name=r.spec.name, descriptor=descriptor, is_normal_human=is_nh,
            ac_descending=rs.ac_descending, ac_ascending=rs.ac_ascending,
            hp_current=rs.current_hp, hp_max=rs.max_hp, thac0=rs.thac0,
            saves={s.name: s.modified for s in rs.saves},
            equipped=equipped_names,
            loyalty=r.loyalty, role=r.role, inventory=inv_rows, xp=entry.xp))
    return cards


def _with_retainers(block, spec: CharacterSpec, data: GameData, class_options=None):
    from aose.sheet.companions_view import CompanionsBlock
    from aose.engine.ability_mods import max_retainers
    cards = _retainer_cards(spec, data)
    if block is None and not cards and not class_options:
        return None
    block = block or CompanionsBlock()
    block.retainers = cards
    cha = int(spec.abilities.get(Ability.CHA, 9))
    block.max_retainers = max_retainers(cha)
    return block


def build_inventory_groups(spec: CharacterSpec, data: GameData) -> list[TopLevelGroup]:
    """Build the top-level inventory groups for the sheet (Carried, Stashed, each
    carrier/retainer).  Each group contains equipped rows, loose rows, coin rows,
    treasure rows (gems/jewellery), and container views for its location."""
    from collections import Counter
    from aose.models import Container as _Container
    from aose.models.storage import StorageLocation

    def _coin_rows(loc: StorageLocation) -> list[CoinRow]:
        return [CoinRow(denom=s.denom, count=s.count)
                for s in spec.coins if s.location == loc and s.count > 0]

    def _gem_rows(loc: StorageLocation) -> list:
        return [
            GemRow(instance_id=g.instance_id, value=g.value, count=g.count,
                   label=g.label, stack_value=valuables_engine.gem_stack_value(g))
            for g in spec.gems if g.location == loc
        ]

    def _jewellery_rows(loc: StorageLocation) -> list:
        return [
            JewelleryRow(instance_id=j.instance_id, value=j.value, damaged=j.damaged,
                         label=j.label, effective_value=valuables_engine.jewellery_value(j))
            for j in spec.jewellery if j.location == loc
        ]

    def _carrier_container_views(loc: StorageLocation) -> list[ContainerView]:
        views = []
        for c in spec.containers:
            if c.location != loc:
                continue
            catalog = data.items.get(c.catalog_id)
            if not isinstance(catalog, _Container):
                continue
            rows_by_id: Counter = Counter(c.contents)
            content_rows = sorted(
                [_build_row(i, n, data) for i, n in rows_by_id.items()],
                key=lambda r: r.name,
            )
            raw_used = sum(
                (data.items[x].weight_cn if x in data.items else 0)
                for x in c.contents
            )
            views.append(ContainerView(
                instance_id=c.instance_id, catalog_id=c.catalog_id,
                name=catalog.name, state=loc.kind,
                capacity_cn=catalog.capacity_cn, used_cn=raw_used,
                weight_multiplier=catalog.weight_multiplier,
                own_weight_cn=catalog.weight_cn,
                effective_weight_cn=(
                    catalog.weight_cn + int(catalog.weight_multiplier * raw_used)
                    if loc.kind == "carried" else 0
                ),
                contents=content_rows, detail=item_card(catalog),
            ))
        return views

    # The existing inventory_view gives us equipped/loose split + carried/stashed containers.
    inv_view = inventory_view(spec.inventory, spec.stashed, spec.equipped,
                              spec.containers, data)
    carried_containers = [c for c in inv_view.containers if c.state == "carried"]
    stashed_containers = [c for c in inv_view.containers if c.state == "stashed"]

    groups: list[TopLevelGroup] = []

    # ── Carried ───────────────────────────────────────────────────────────────
    carried_loc = StorageLocation(kind="carried")
    groups.append(TopLevelGroup(
        kind="carried", label="Carried",
        has_equipped=bool(inv_view.equipped),
        equipped=inv_view.equipped,
        loose=inv_view.carried,
        coins=_coin_rows(carried_loc),
        treasure_gems=_gem_rows(carried_loc),
        treasure_jewellery=_jewellery_rows(carried_loc),
        containers=carried_containers,
    ))

    # ── Stashed ───────────────────────────────────────────────────────────────
    stashed_loc = StorageLocation(kind="stashed")
    groups.append(TopLevelGroup(
        kind="stashed", label="Stashed",
        loose=inv_view.stashed,
        coins=_coin_rows(stashed_loc),
        treasure_gems=_gem_rows(stashed_loc),
        treasure_jewellery=_jewellery_rows(stashed_loc),
        containers=stashed_containers,
    ))

    # ── Animals ───────────────────────────────────────────────────────────────
    for animal in spec.animals:
        animal_loc = StorageLocation(kind="animal", id=animal.instance_id)
        catalog = data.items.get(animal.catalog_id)
        label = animal.name or (catalog.name if catalog else animal.catalog_id)
        count: Counter = Counter(animal.contents)
        groups.append(TopLevelGroup(
            kind="animal", id=animal.instance_id, label=label,
            loose=sorted([_build_row(i, n, data) for i, n in count.items()],
                         key=lambda r: r.name),
            coins=_coin_rows(animal_loc),
            treasure_gems=_gem_rows(animal_loc),
            treasure_jewellery=_jewellery_rows(animal_loc),
            containers=_carrier_container_views(animal_loc),
        ))

    # ── Vehicles ──────────────────────────────────────────────────────────────
    for vehicle in spec.vehicles:
        vehicle_loc = StorageLocation(kind="vehicle", id=vehicle.instance_id)
        catalog = data.items.get(vehicle.catalog_id)
        label = vehicle.name or (catalog.name if catalog else vehicle.catalog_id)
        count = Counter(vehicle.contents)
        groups.append(TopLevelGroup(
            kind="vehicle", id=vehicle.instance_id, label=label,
            loose=sorted([_build_row(i, n, data) for i, n in count.items()],
                         key=lambda r: r.name),
            coins=_coin_rows(vehicle_loc),
            treasure_gems=_gem_rows(vehicle_loc),
            treasure_jewellery=_jewellery_rows(vehicle_loc),
            containers=_carrier_container_views(vehicle_loc),
        ))

    # ── Retainers ─────────────────────────────────────────────────────────────
    for retainer in spec.retainers:
        ret_carried = StorageLocation(kind="carried")
        count = Counter(retainer.spec.inventory)
        ret_coins = [CoinRow(denom=s.denom, count=s.count)
                     for s in retainer.spec.coins
                     if s.location == ret_carried and s.count > 0]
        groups.append(TopLevelGroup(
            kind="retainer", id=retainer.id, label=retainer.spec.name,
            loose=sorted([_build_row(i, n, data) for i, n in count.items()],
                         key=lambda r: r.name),
            coins=ret_coins,
        ))

    return groups


def build_sheet(spec: CharacterSpec, data: GameData) -> CharacterSheet:
    race = data.races[spec.race_id]

    eff = effective_abilities(spec, data)
    mods = active_modifiers(spec, data)
    labeled_ability_mods = _labeled_ability_mods(spec, data)
    prime_abilities = {
        a.value
        for entry in spec.classes
        for a in data.classes[entry.class_id].prime_requisites
    }
    od_bonus, od_source = open_doors_category_bonus(spec, data)
    abilities = []
    for ab in ABILITY_ORDER:
        base = spec.abilities[ab]
        target = f"ability:{ab.value}"
        after_equip = (
            apply_modifiers(base, mods, target)
            if any(m.target == target for m in mods)
            else base
        )
        final = eff[ab]

        lines = [
            AbilityModLine(
                source=label,
                effect=_effect_str(m),
                conditional=m.condition is not None,
                note=m.condition or "",
            )
            for (m, label) in labeled_ability_mods if m.target == target
        ]
        temp = spec.temp_ability_modifiers.get(ab, 0)
        if temp:
            lines.append(AbilityModLine(
                source="Temporary",
                effect=f"+{temp}" if temp >= 0 else f"−{abs(temp)}",
                conditional=False, note="",
            ))

        abilities.append(AbilityRow(
            ability=ab.value,
            score=final,
            modifier=ability_mods.ability_modifier(final),
            base_score=base,
            equip_delta=after_equip - base,
            temp_delta=temp,
            modified=(final != base),
            lines=lines,
            has_conditional=any(ln.conditional for ln in lines),
            table=[
                AbilityTableCell(
                    label=lbl, value=val,
                    note=(f"+{od_bonus} category ({od_source})"
                          if ab == Ability.STR and od_bonus and lbl == "Open Doors"
                          else ""),
                )
                for lbl, val in ability_mods.ability_table_row(
                    ab.value, final, is_prime=ab.value in prime_abilities,
                    open_doors_category_bonus=(od_bonus if ab == Ability.STR else 0))
            ],
        ))

    ac_breakdown = armor_class.armor_class_detail(spec, data)
    desc_ac, asc_ac = ac_breakdown.descending, ac_breakdown.ascending
    un_desc, un_asc = ac_breakdown.unarmored_descending, ac_breakdown.unarmored_ascending
    ac_line_rows = [
        SheetACLine(source=ln.source, effect=ln.effect,
                    conditional=ln.conditional, note=ln.note)
        for ln in ac_breakdown.lines
    ]
    save_detail = saves.saving_throws_detail(spec, data)
    save_rows = [
        SheetSave(
            name=name,
            label=SAVE_LABELS[name],
            base=save_detail[name].base,
            modified=save_detail[name].modified,
            lines=[
                SheetSaveLine(source=ln.source, bonus=ln.bonus,
                              conditional=ln.conditional, note=ln.note)
                for ln in save_detail[name].lines
            ],
        )
        for name in SAVE_ORDER
        if name in save_detail
    ]
    situational_save_rows = [
        SheetSituationalSave.from_bonus_things(b.bonus, b.things, b.source)
        for b in saves.situational_save_bonuses(spec, data)
    ]

    next_level, xp_to_next = _xp_to_next(spec, data)
    advancement_rows = all_advancement(spec, data)

    eff_abilities = effective_abilities(spec, data)
    con_mod = ability_mods.ability_modifier(eff_abilities[Ability.CON])
    level_up_modal_list = []
    for entry, adv in zip(spec.classes, advancement_rows):
        cls = data.classes[entry.class_id]
        next_lv = adv.next_level if adv.next_level is not None else entry.level + 1
        level_up_modal_list.append(LevelUpModal(
            class_id=entry.class_id,
            class_name=cls.name,
            current_level=entry.level,
            next_level=next_lv,
            hit_die=cls.hit_die,
            con_mod=con_mod,
            at_name_level=(entry.level >= cls.name_level),
            flat_hp=cls.hp_after_name_level,
            pending=spec.pending_level_up.get(entry.class_id),
            strict_mode=spec.ruleset.strict_mode,
            can_level=adv.can_level,
        ))

    attacks = attack_profiles(spec, data)
    attack_breakdown = attack_modifiers_detail(spec, data)
    attack_line_rows = [
        SheetAttackLine(source=ln.source, bonus=ln.bonus,
                        conditional=ln.conditional, note=ln.note)
        for ln in attack_breakdown.lines
    ]
    init_detail = initiative_detail(spec, data)
    initiative_line_rows = [
        SheetAttackLine(source=ln.source, bonus=ln.bonus,
                        conditional=ln.conditional, note=ln.note)
        for ln in init_detail.lines
    ]
    ammo_rows, ammo_options = ammo_view(spec, data)

    _armor_id = spec.equipped.get("armor")
    _armor_item = data.items.get(_armor_id) if _armor_id else None
    _armor_tailorable = bool(getattr(_armor_item, "tailorable", False))

    return CharacterSheet(
        name=spec.name,
        race_name=race.name,
        race_as_class=_is_race_as_class(spec, data),
        class_summary=_class_summary(spec, data),
        alignment=ALIGNMENT_LABELS[spec.alignment],
        xp=sum(e.xp for e in spec.classes),
        next_level=next_level,
        xp_to_next=xp_to_next,
        advancement=advancement_rows,
        level_up_modals=level_up_modal_list,
        abilities=abilities,
        max_hp=hp.max_hp(spec, data),
        current_hp=hp.current_hp(spec, data),
        is_dead=hp.is_dead(spec, data),
        ac_descending=desc_ac,
        ac_ascending=asc_ac,
        unarmored_ac_descending=un_desc,
        unarmored_ac_ascending=un_asc,
        use_ascending=spec.ruleset.ascending_ac,
        ac_lines=ac_line_rows,
        ac_has_conditional=ac_breakdown.has_conditional,
        thac0=attack_bonus.thac0(spec, data),
        attack_bonus=attack_bonus.attack_bonus(spec, data),
        attack_lines=attack_line_rows,
        attack_has_conditional=attack_breakdown.has_conditional,
        individual_initiative=spec.ruleset.individual_initiative,
        initiative_modifier=init_detail.total,
        initiative_lines=initiative_line_rows,
        initiative_has_conditional=init_detail.has_conditional,
        saves=save_rows,
        situational_saves=situational_save_rows,
        languages=[
            display_name(lang, data.languages)
            for lang in known_languages(
                spec.languages, race, spec.alignment, data.languages,
                granted=granted_languages(spec, data),
            )
        ],
        literacy=literacy(spec, data),
        broken_speech=broken_speech(spec.abilities[Ability.INT]),
        movement_base=effective_movement(spec, data),
        movement_encounter=effective_movement(spec, data) // 3,
        movement_overland=effective_movement(spec, data) // 5,
        movement_unencumbered=race.base_movement,
        carried_weight_cn=(
            carried_weight_cn(spec, data) if spec.ruleset.encumbrance != "none" else None
        ),
        armor_movement_class=armor_movement_class(spec, data),
        current_weight_band=(
            band_label(weight_band(banding_weight_cn(spec, data)))
            if spec.ruleset.encumbrance == "detailed"
            else None
        ),
        encumbrance_table=encumbrance_table(spec, data),
        race_features=_race_features(spec, data),
        class_features=_class_features(spec, data),
        equipped=_equipped(spec, data),
        inventory=_inventory(spec, data),
        attacks=attacks,
        secondary_skills=list(spec.secondary_skills),
        proficiencies=_proficiency_view(spec, data),
        weapon_proficiency_active=spec.ruleset.weapon_proficiency,
        weapon_qualities_reference=_weapon_qualities_reference(spec, data),
        magic_items=_magic_items(spec, data) + enchanted_items_view(spec.enchanted, data),
        spells=spells_view(spec, data),
        spellbook=spellbook_view(spec, data),
        mental_powers=mental_powers_view(spec, data),
        innate_abilities=innate_view(spec, data),
        spell_sources=spell_sources_view(spec, data),
        valuables=valuables_view(spec),
        ammo=ammo_rows,
        ammo_load_options=ammo_options,
        companions=_with_retainers(companions_block(spec, data), spec, data, class_options=_retainer_class_options(spec, data)),
        race_id=spec.race_id,
        retainer_class_options=_retainer_class_options(spec, data),
        other_possessions=list(spec.other_possessions),
        notes=spec.notes,
        coins=_coins_dict(spec),
        treasure_value_gp=currency_engine.total_value_gp(spec),
        treasure_weight_cn=treasure_weight_cn(spec, data),
        carrying_treasure=spec.carrying_treasure,
        max_load=MAX_LOAD,
        inventory_groups=build_inventory_groups(spec, data),
        total_wealth_gp=valuables_engine.total_wealth_gp(spec),
        enabled_optional_rules=_enabled_optional_rules(spec.ruleset),
        encumbrance_mode=spec.ruleset.encumbrance,
        encumbrance_description=ENCUMBRANCE_DESCRIPTIONS.get(
            spec.ruleset.encumbrance, ""
        ),
        armor_tailorable=_armor_tailorable,
        armor_tailored=spec.armor_tailored,
        pending_rest_heal=spec.pending_rest_heal,
        strict_mode=spec.ruleset.strict_mode,
        **_level_choice_extras(spec, data),
    )
