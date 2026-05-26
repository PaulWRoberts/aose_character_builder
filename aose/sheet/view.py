from pydantic import BaseModel

from aose.data.loader import GameData
from aose.engine import ability_mods, armor_class, attack_bonus, hp, saves
from aose.engine.leveling import ClassAdvancement, all_advancement, xp_share
from aose.models import Ability, CharacterSpec, RuleSet

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
    movement_base: int
    movement_encounter: int

    race_features: list[SheetFeature]
    class_features: list[SheetFeature]

    equipped: list[EquippedRow]
    inventory: list[str]

    secondary_skill: str | None
    proficiencies: list["ProficiencyDisplay"]  # rich per-group display; empty when rule off
    weapon_proficiency_active: bool

    enabled_optional_rules: list[str]
    encumbrance_mode: str
    encumbrance_description: str


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


def build_sheet(spec: CharacterSpec, data: GameData) -> CharacterSheet:
    race = data.races[spec.race_id]

    abilities = [
        AbilityRow(
            ability=ab.value,
            score=spec.abilities[ab],
            modifier=ability_mods.ability_modifier(spec.abilities[ab]),
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
        movement_base=race.base_movement,
        movement_encounter=race.base_movement // 3,
        race_features=_race_features(spec, data),
        class_features=_class_features(spec, data),
        equipped=_equipped(spec, data),
        inventory=_inventory(spec, data),
        secondary_skill=spec.secondary_skill,
        proficiencies=_proficiency_display(spec, data),
        weapon_proficiency_active=spec.ruleset.weapon_proficiency,
        enabled_optional_rules=_enabled_optional_rules(spec.ruleset),
        encumbrance_mode=spec.ruleset.encumbrance,
        encumbrance_description=ENCUMBRANCE_DESCRIPTIONS.get(
            spec.ruleset.encumbrance, ""
        ),
    )
