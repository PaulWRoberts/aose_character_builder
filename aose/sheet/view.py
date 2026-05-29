from pydantic import BaseModel

from aose.data.loader import GameData
from aose.engine import ability_mods, armor_class, attack_bonus, hp, saves, spells as spell_engine
from aose.engine.attacks import AttackProfile, attack_profiles
from aose.engine.encumbrance import (
    EncumbranceTable,
    armor_movement_class,
    band_label,
    banding_weight_cn,
    carried_weight_cn,
    effective_movement,
    encumbrance_table,
    weight_band,
)
from aose.engine.leveling import ClassAdvancement, all_advancement, xp_share
from aose.engine.magic import effective_abilities
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
    "max_hp_at_l1": "Max HP at L1",
    "variable_weapon_damage": "Variable Weapon Damage",
}

ENCUMBRANCE_DESCRIPTIONS = {
    "none": "Encumbrance is ignored entirely.",
    "basic": "Tracks armour and significant loads only.",
    "detailed": "Tracks every item's weight in coins.",
}


class AbilityRow(BaseModel):
    ability: str
    score: int
    modifier: int
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


class WeaponDisplay(BaseModel):
    name: str
    damage: str


class ProficiencyDisplay(BaseModel):
    name: str                       # group label, e.g. "Sword"
    weapons: list[WeaponDisplay]    # weapons in that group with their damage


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


class SpellEntryView(BaseModel):
    id: str
    name: str
    level: int
    description: str
    reversible: bool


class SpellLevelGroup(BaseModel):
    level: int
    slots: int
    prepared: list[SpellEntryView]


class SpellClassView(BaseModel):
    class_id: str
    class_name: str
    caster_type: str            # "arcane" | "divine"
    can_learn: bool             # arcane only
    known: list[SpellEntryView]
    prepared_groups: list[SpellLevelGroup]
    learnable: list[SpellEntryView]


class CharacterSheet(BaseModel):
    name: str
    race_name: str
    race_as_class: bool  # true → omit race from subtitle (avoids "Dwarf · Dwarf 1")
    class_summary: str
    alignment: str
    xp: int
    next_level: int | None
    xp_to_next: int | None
    xp_share: int                            # per-class share (== xp for single-class)
    advancement: list[ClassAdvancement]      # one entry per class

    abilities: list[AbilityRow]

    max_hp: int
    ac_descending: int
    ac_ascending: int
    use_ascending: bool
    thac0: int
    attack_bonus: int

    saves: list[SheetSave]

    languages: list[str]
    movement_base: int               # effective exploration move (after encumbrance)
    movement_encounter: int          # = movement_base // 3
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
    proficiencies: list["ProficiencyDisplay"]  # rich per-group display; empty when rule off
    weapon_proficiency_active: bool

    magic_items: list[MagicItemView]
    spells: list[SpellClassView]

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
        rows.append(EquippedRow(slot=slot, item_name=name))
    return rows


def _inventory(spec: CharacterSpec, data: GameData) -> list[str]:
    return [data.items[i].name if i in data.items else i for i in spec.inventory]


def _enabled_optional_rules(rs: RuleSet) -> list[str]:
    return [label for field, label in OPTIONAL_RULE_LABELS.items() if getattr(rs, field)]


def _proficiency_display(spec: CharacterSpec, data: GameData) -> list[ProficiencyDisplay]:
    """Build the rich per-group proficiency display for the character sheet.

    Each entry lists the weapons in that group with the damage value the
    character would deal under the active rules: the variable per-weapon damage
    if Variable Weapon Damage is on, otherwise the default 1d6.  Returns an
    empty list when the Weapon Proficiency rule is off or no groups were picked.
    """
    from aose.engine.proficiency import proficiency_groups
    from aose.models import Weapon

    if not spec.ruleset.weapon_proficiency or not spec.chosen_proficiencies:
        return []

    use_variable = spec.ruleset.variable_weapon_damage
    id_to_group = {g["id"]: g for g in proficiency_groups(data)}

    # Pre-index weapons by their proficiency group id for one pass.
    weapons_by_group: dict[str, list[Weapon]] = {}
    for item in data.items.values():
        if isinstance(item, Weapon) and item.proficiency_group:
            weapons_by_group.setdefault(item.proficiency_group, []).append(item)

    result: list[ProficiencyDisplay] = []
    for gid in spec.chosen_proficiencies:
        group_meta = id_to_group.get(gid)
        group_name = group_meta["name"] if group_meta else gid.replace("_", " ").title()
        weapons = sorted(weapons_by_group.get(gid, []), key=lambda w: w.name)
        result.append(ProficiencyDisplay(
            name=group_name,
            weapons=[
                WeaponDisplay(
                    name=w.name,
                    damage=(w.damage.variable if use_variable else w.damage.default),
                )
                for w in weapons
            ],
        ))
    return result


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


def spells_view(spec: CharacterSpec, data: GameData) -> list[SpellClassView]:
    """One block per casting class entry; shared by the live sheet and the
    wizard review.  Arcane blocks expose learnable spells; divine know their
    whole accessible list."""
    out: list[SpellClassView] = []
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        ctype = spell_engine.caster_type_of(cls, data)
        if ctype is None:
            continue
        known = spell_engine.known_spells(entry, cls, data)
        slots = spell_engine.memorizable_slots(entry, cls)
        groups: list[SpellLevelGroup] = []
        for level in sorted(slots):
            prepared_here = [
                _spell_entry(data.spells[s]) for s in entry.prepared
                if s in data.spells and data.spells[s].level == level
            ]
            groups.append(SpellLevelGroup(level=level, slots=slots[level],
                                          prepared=prepared_here))
        out.append(SpellClassView(
            class_id=entry.class_id,
            class_name=cls.name,
            caster_type=ctype,
            can_learn=(ctype == "arcane"),
            known=[_spell_entry(s) for s in known],
            prepared_groups=groups,
            learnable=[_spell_entry(s) for s in spell_engine.learnable_spells(entry, cls, data)],
        ))
    return out


def build_sheet(spec: CharacterSpec, data: GameData) -> CharacterSheet:
    race = data.races[spec.race_id]

    eff = effective_abilities(spec, data)
    abilities = [
        AbilityRow(
            ability=ab.value,
            score=eff[ab],
            modifier=ability_mods.ability_modifier(eff[ab]),
            modified=(eff[ab] != spec.abilities[ab]),
        )
        for ab in ABILITY_ORDER
    ]

    desc_ac, asc_ac = armor_class.armor_class(spec, data)
    save_dict = saves.saving_throws(spec, data)
    save_rows = [
        SheetSave(name=name, label=SAVE_LABELS[name], target=save_dict[name])
        for name in SAVE_ORDER
        if name in save_dict
    ]

    next_level, xp_to_next = _xp_to_next(spec, data)
    advancement_rows = all_advancement(spec, data)

    return CharacterSheet(
        name=spec.name,
        race_name=race.name,
        race_as_class=_is_race_as_class(spec, data),
        class_summary=_class_summary(spec, data),
        alignment=ALIGNMENT_LABELS[spec.alignment],
        xp=spec.xp,
        next_level=next_level,
        xp_to_next=xp_to_next,
        xp_share=xp_share(spec),
        advancement=advancement_rows,
        abilities=abilities,
        max_hp=hp.max_hp(spec, data),
        ac_descending=desc_ac,
        ac_ascending=asc_ac,
        use_ascending=spec.ruleset.ascending_ac,
        thac0=attack_bonus.thac0(spec, data),
        attack_bonus=attack_bonus.attack_bonus(spec, data),
        saves=save_rows,
        languages=race.languages,
        movement_base=effective_movement(spec, data),
        movement_encounter=effective_movement(spec, data) // 3,
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
        attacks=attack_profiles(spec, data),
        secondary_skill=spec.secondary_skill,
        proficiencies=_proficiency_display(spec, data),
        weapon_proficiency_active=spec.ruleset.weapon_proficiency,
        magic_items=_magic_items(spec, data),
        spells=spells_view(spec, data),
        enabled_optional_rules=_enabled_optional_rules(spec.ruleset),
        encumbrance_mode=spec.ruleset.encumbrance,
        encumbrance_description=ENCUMBRANCE_DESCRIPTIONS.get(
            spec.ruleset.encumbrance, ""
        ),
    )
