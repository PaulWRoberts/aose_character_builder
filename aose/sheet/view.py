from pydantic import BaseModel, Field

from aose.data.loader import GameData
from aose.engine import ability_mods, armor_class, attack_bonus, hp, saves, spells as spell_engine
from aose.engine.armor_class import unarmored_ac as _unarmored_ac
from aose.engine import currency as currency_engine
from aose.engine import spell_sources as spell_source_engine
from aose.engine import valuables as valuables_engine
from aose.engine.attacks import AttackProfile, attack_profiles
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
from aose.engine.languages import broken_speech, known_languages
from aose.engine.leveling import ClassAdvancement, all_advancement
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
}

ENCUMBRANCE_DESCRIPTIONS = {
    "none": "Encumbrance is ignored entirely.",
    "basic": ("Movement is set by armour worn and whether you carry significant "
              "treasure. Only treasure weight is tracked, against the 1,600 cn cap."),
    "detailed": ("Movement is set by total weight: armour and weapons by listed "
                 "weight, miscellaneous gear as a flat 80 cn, plus all treasure."),
}


class AbilityRow(BaseModel):
    ability: str
    score: int            # final effective score (clamped)
    modifier: int
    base_score: int = 0   # real underlying score
    equip_delta: int = 0  # magic-effective minus base (works for add & set ops)
    temp_delta: int = 0   # temporary modifier (signed)
    modified: bool = False


class SheetSave(BaseModel):
    name: str
    label: str
    target: int


class SheetFeature(BaseModel):
    name: str
    text: str
    source: str


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


class SlotView(BaseModel):
    index: int          # index into ClassEntry.slots (for cast/clear/restore)
    spell_id: str
    name: str
    display_name: str   # reverse name when reversed
    level: int
    reversible: bool
    reversed: bool
    spent: bool


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
    thac0: int
    attack_bonus: int

    saves: list[SheetSave]

    languages: list[str]
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

    secondary_skill: str | None
    proficiencies: ProficiencyView | None
    weapon_proficiency_active: bool
    weapon_qualities_reference: list[WeaponQualityRef]

    magic_items: list[MagicItemView]
    spells: list[SpellClassView]
    spellbook: list[SpellbookBlock] = Field(default_factory=list)
    spell_sources: list[SpellSourceView] = Field(default_factory=list)
    valuables: ValuablesView = Field(default_factory=lambda: ValuablesView(
        gems=[], jewellery=[], total_value=0))
    ammo: list[AmmoRow] = Field(default_factory=list)
    ammo_load_options: dict[str, list[AmmoOption]] = Field(default_factory=dict)
    other_possessions: list[str] = Field(default_factory=list)
    notes: str = ""

    coins: dict[str, int] = Field(default_factory=dict)   # {"pp":..,"gp":..,...}
    treasure_value_gp: int = 0
    treasure_weight_cn: int = 0
    carrying_treasure: bool = False
    max_load: int = MAX_LOAD

    enabled_optional_rules: list[str]
    encumbrance_mode: str
    encumbrance_description: str


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


def _race_features(spec: CharacterSpec, data: GameData) -> list[SheetFeature]:
    race = data.races[spec.race_id]
    return [
        SheetFeature(name=f.name, text=f.text, source=f"Race: {race.name}")
        for f in race.features
    ]


def _class_features(spec: CharacterSpec, data: GameData) -> list[SheetFeature]:
    out: list[SheetFeature] = []
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        for f in cls.features:
            if f.gained_at_level <= entry.level:
                out.append(
                    SheetFeature(name=f.name, text=f.text, source=f"Class: {cls.name}")
                )
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
    for wid in set(spec.inventory) | set(spec.equipped_weapons):
        item = data.items.get(wid)
        if isinstance(item, Weapon):
            present.update(item.qualities)
    refs = [
        WeaponQualityRef(id=q.id, name=q.name, description=q.description)
        for qid in sorted(present)
        if (q := data.qualities.get(qid)) is not None
    ]
    return refs


def _is_race_as_class(spec: CharacterSpec, data: GameData) -> bool:
    """True when the character's (single) class is race-locked to their race.

    Multi-class characters never trigger this — the subtitle would still need
    to surface the race separately from each class.
    """
    if len(spec.classes) != 1:
        return False
    cls = data.classes[spec.classes[0].class_id]
    return cls.race_locked == spec.race_id


def _spell_entry(spell) -> SpellEntryView:
    return SpellEntryView(
        id=spell.id, name=spell.name, level=spell.level,
        description=spell.description, reversible=spell.reversible,
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
        if ctype is None:
            continue
        known = spell_engine.known_spells(entry, cls, data)
        caps = spell_engine.memorizable_slots(entry, cls)
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
        out.append(SpellClassView(
            class_id=entry.class_id,
            class_name=cls.name,
            caster_type=ctype,
            can_learn=(ctype == "arcane"),
            known=[_spell_entry(s) for s in known],
            slot_groups=groups,
            learnable=(
                [] if spec.ruleset.advanced_spell_books
                else [_spell_entry(s) for s in spell_engine.learnable_spells(entry, cls, data)]
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
        if ctype is None:
            continue
        caps = spell_engine.memorizable_slots(entry, cls)         # {level: cap}
        known = spell_engine.known_spells(entry, cls, data)       # book (arcane) / list (divine)
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
    ``.loaded_ammo``, and ``.equipped_weapons``."""
    from aose.engine.ammo import accepts, resolve_ammo
    from aose.models import Ammunition, Weapon

    ammo_rows = []
    for s in spec.ammo:
        view = resolve_ammo(s, data)
        ammo_rows.append(AmmoRow(instance_id=s.instance_id, name=view["name"],
                                 count=s.count, magic=s.enchantment_id is not None))

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


def build_sheet(spec: CharacterSpec, data: GameData) -> CharacterSheet:
    race = data.races[spec.race_id]

    eff = effective_abilities(spec, data)
    mods = active_modifiers(spec, data)
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
        abilities.append(AbilityRow(
            ability=ab.value,
            score=final,
            modifier=ability_mods.ability_modifier(final),
            base_score=base,
            equip_delta=after_equip - base,
            temp_delta=spec.temp_ability_modifiers.get(ab, 0),
            modified=(final != base),
        ))

    desc_ac, asc_ac = armor_class.armor_class(spec, data)
    un_desc, un_asc = _unarmored_ac(spec, data)
    save_dict = saves.saving_throws(spec, data)
    save_rows = [
        SheetSave(name=name, label=SAVE_LABELS[name], target=save_dict[name])
        for name in SAVE_ORDER
        if name in save_dict
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
    ammo_rows, ammo_options = ammo_view(spec, data)

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
        thac0=attack_bonus.thac0(spec, data),
        attack_bonus=attack_bonus.attack_bonus(spec, data),
        saves=save_rows,
        languages=known_languages(spec.languages, race, spec.alignment, data.languages),
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
        secondary_skill=spec.secondary_skill,
        proficiencies=_proficiency_view(spec, data),
        weapon_proficiency_active=spec.ruleset.weapon_proficiency,
        weapon_qualities_reference=_weapon_qualities_reference(spec, data),
        magic_items=_magic_items(spec, data) + enchanted_items_view(spec.enchanted, data),
        spells=spells_view(spec, data),
        spellbook=spellbook_view(spec, data),
        spell_sources=spell_sources_view(spec, data),
        valuables=valuables_view(spec),
        ammo=ammo_rows,
        ammo_load_options=ammo_options,
        other_possessions=list(spec.other_possessions),
        notes=spec.notes,
        coins={
            "pp": spec.platinum, "gp": spec.gold, "ep": spec.electrum,
            "sp": spec.silver, "cp": spec.copper,
        },
        treasure_value_gp=currency_engine.total_value_gp(spec),
        treasure_weight_cn=treasure_weight_cn(spec, data),
        carrying_treasure=spec.carrying_treasure,
        max_load=MAX_LOAD,
        enabled_optional_rules=_enabled_optional_rules(spec.ruleset),
        encumbrance_mode=spec.ruleset.encumbrance,
        encumbrance_description=ENCUMBRANCE_DESCRIPTIONS.get(
            spec.ruleset.encumbrance, ""
        ),
    )
