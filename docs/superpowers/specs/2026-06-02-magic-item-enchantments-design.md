# Magic Item Enchantments — extensible composition model (Phase 1)

**Date:** 2026-06-02
**Status:** Design approved, ready for plan
**Scope:** Phase 1 — all code/architecture, minimal seed data. Bulk data import
is a separate spec (`2026-06-02-magic-item-import-design.md`) executed later.

## Problem

Magic weapons and armour are currently modelled as **fully spelled-out
catalog entries** (`sword_plus_1` is a whole `Weapon` with `magic_bonus`,
`conditional_bonus`, `base_weapon`). The book separates two things the catalog
fuses:

- the **enchantment** (+1; +1, +3 vs Undead; Flaming; Quickness; Armour +2…),
- the **base item type** (short sword / normal sword / two-handed sword;
  leather / chainmail / plate).

A magic "Sword +1" may be *any* sword type — the type is chosen separately. With
the current model, supporting a new base weapon (e.g. a **bastard sword**, or a
**"lightsaber"** that doesn't contain the word "sword") means re-authoring every
magic variant by hand → combinatorial explosion. We want a new base to be
adopted into every relevant magic chart automatically, by tagging alone.

The character builder is **not** fully automated. The only mechanical
requirement: when an equipped/held item passively changes a derived stat
(abilities, AC, THAC0, saves, attack, damage, carry capacity), that change must
flow through. Everything else (activated powers, charm, invisibility, summons)
is **description-only**.

## Decisions (from brainstorming)

1. **Runtime composition**, not loader-expansion or hand-written entries. A
   magic weapon/armour is an instance pairing a *base id* + an *enchantment id*;
   the engine resolves effective stats on the fly. Nothing composed is stored or
   written to YAML.
2. **Auto-applied effects** stay the existing modifier targets, plus extend the
   `ac` target to support **set-base-AC** (Bracers of Armour, Medallion, cursed
   "AC 9 [10]"). No new `max_hp` or spell-slot targets — the data has no clean
   passive cases (HP heals are play-state; spell items are activated). Those stay
   description-only.
3. **Phasing:** Phase 1 = all non-data changes (this spec). Phase 2 = bulk YAML
   import (separate spec). The placeholder `magic_items.yaml` is deleted in
   Phase 1; `weapons.yaml`, `armor.yaml`, `weapon_qualities.yaml` are **kept**
   (real base catalog).
4. **No magic acquisition in the wizard.** Magic items *and* enchanted items are
   sheet-only (GM grants happen in play). The existing magic-item Add UI is
   removed from the wizard equipment step.
5. **No backward compatibility.** App is local single-user, not deployed; no
   migrations for data-shape changes.

## Section 1 — Catalog models

### `Enchantment` (new — `aose/models/enchantment.py`)

A registry record, independent of any base item. Loaded into
`GameData.enchantments: dict[str, Enchantment]` from `data/enchantments.yaml`
(enchantments are **not** `Item`s — own registry, like `spell_lists.yaml`).

```yaml
- id: sword_plus_1_vs_undead
  name_template: "{base} +1, +3 vs Undead"   # {base} -> base item name
  kind: weapon                                # weapon | armor | shield
  applies_to:
    include: [sword]                          # tokens (see matching below)
    exclude: []
  magic_bonus: 1                              # to-hit & damage (weapons); AC (armour/shield)
  conditional_bonus: {vs: undead, bonus: 2}   # weapons only; optional
  modifiers: []                               # extra passive Modifiers (save:all, ac, …)
  charge_dice: null                           # e.g. "1d4+16"; or max_charges: int
  max_charges: null
  cursed: false
  description: "..."                           # book rules text (shown on sheet)
```

Fields:

| Field | Type | Notes |
|---|---|---|
| `id` | str | unique |
| `name_template` | str | `.format(base=base.name)` → display name |
| `kind` | `Literal["weapon","armor","shield"]` | drives resolver + Add UI grouping |
| `applies_to` | `AppliesTo` | include/exclude token lists (below) |
| `magic_bonus` | int = 0 | may be negative (cursed) |
| `conditional_bonus` | `ConditionalBonus \| None` | weapons only; reuse existing model |
| `modifiers` | `list[Modifier]` | passive side-effects (saves, ac, …) |
| `charge_dice` / `max_charges` | `str \| None` / `int \| None` | mirror `MagicItem` |
| `cursed` | bool = False | display flag |
| `description` | `str \| None` | rules text |

`AppliesTo`: `{include: list[str], exclude: list[str] = []}`.

**Matching (tag-based, never by name).** A base item matches a token `T` if:
`T == base.id` **OR** `T in base.groups` **OR** `T` is the kind wildcard
(`any_weapon` for any `Weapon`, `any_armour` for any non-shield `Armor`,
`any_shield` for any shield). A base is compatible with an enchantment when it
matches **at least one** `include` token and **no** `exclude` token (exclude
wins). Compatibility also requires the base's nature to match the enchantment
`kind` (weapon vs armour vs shield).

Worked cases (all approved):

| Case | Base | `applies_to` | Result |
|---|---|---|---|
| Lightsaber gets sword bonuses | `id: lightsaber, groups: [sword]` | `include: [sword]` | matches on tag, name ignored |
| Generic weapon +1, **not** swords | swords carry `groups: [sword]` | `include: [any_weapon], exclude: [sword]` | every weapon except swords; no double +1 on a sword |
| Short-sword-only (Quickness) | `id: short_sword, groups: [sword]` | `include: [short_sword]` | base-id match only |
| Trident-only | `id: trident` | `include: [trident]` | base-id match only |
| Plate-mail-only | `id: plate_mail, groups: [metal_armour]` | `include: [plate_mail]` | base-id match only |
| Any armour (+1) | any `Armor` | `include: [any_armour]` | all armour |

### `Weapon` / `Armor` changes

- `Weapon` gains `groups: list[str] = []` (e.g. `sword`, `axe`, `trident`).
- `Armor` gains `groups: list[str] = []` and **`ac_bonus: int = 0`** (the shield
  refactor — see Section 2). Existing `magic_bonus`, `weight_multiplier`,
  `base_weapon`/`base_armor` stay.
- The hand-written magic `Weapon`/`Armor`/`MagicItem` seed entries in
  `magic_items.yaml` are deleted; magic weapons/armour now exist only as
  (base + enchantment) instances.

### `EnchantedInstance` (new — on `CharacterSpec`, in `character.py`)

Mirrors `MagicItemInstance`, adding the base/enchantment pairing.

```python
class EnchantedInstance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instance_id: str                  # uuid4 hex
    base_id: str                      # references a Weapon or Armor
    enchantment_id: str               # references an Enchantment
    equipped: bool = False
    charges_max: int | None = None
    charges_remaining: int | None = None
    extra_modifiers: list[Modifier] = Field(default_factory=list)  # escape hatch
    note: str = ""
```

`CharacterSpec` gains `enchanted: list[EnchantedInstance] = []`. These items are
**not** in `inventory`/`equipped`/`equipped_weapons`; they carry their own
`equipped` bool. Weight is counted from the resolved instance (Section 2).

## Section 2 — Engine

### New module `aose/engine/enchant.py` (cycle-free core)

Imports only models, loader, dice (like `magic.py`). Derivation modules import
*from* it.

- `matches(base, token) -> bool`, `is_compatible(base, ench) -> bool`,
  `compatible_bases(ench, data) -> list[Weapon|Armor]`.
- `resolve_weapon(base: Weapon, ench: Enchantment) -> Weapon` — synthetic
  `Weapon`: `damage`/`hands`/`qualities`/`melee`/`ranged`/`range_*` from base;
  `magic_bonus`, `conditional_bonus` from ench; `name =
  ench.name_template.format(base=base.name)`; `base_weapon = base.id` (proficiency
  counts as base type); `id = f"ench:{instance_id}"` (caller passes instance id
  so attack profiles are stable/unique).
- `resolve_armor(base: Armor, ench: Enchantment) -> Armor` — synthetic `Armor`:
  `ac_descending`/`ac_bonus`/`is_shield`/`movement_impact`/`groups` from base;
  `magic_bonus` from ench; `base_armor = base.id`; `weight_multiplier = 0.5`
  (half-weight enchanted-armour rule).
- Instance lifecycle (mirror `magic.py`): `new_enchanted_instance(base_id,
  enchantment_id, data, rng=None)` (validates compatibility, rolls
  `charge_dice`/seeds `max_charges`), `add_free_enchanted`, `equip`/`unequip`,
  `use_charge`/`reset_charges`, `remove`, `set_note`. Errors:
  `UnknownEnchantment`, `IncompatibleBase`, `NoCharges` (all enchanted items are
  equippable, so there is no `NotEquippable` case).
- `equipped_enchanted(spec, data, kind)` helper → resolved synthetic items for
  equipped instances of a given kind.

### `magic.py::active_modifiers` extension

Also collect, for every **equipped** `EnchantedInstance`, the
`enchantment.modifiers + instance.extra_modifiers`. This lights up passive
side-effects for free (Luck Blade `save:all +1`, Holy Avenger `save:spells +4`,
Defender `ac`). `magic_bonus`/`conditional_bonus` are **not** modifiers — they
are consumed directly by `attacks.py`/`armor_class.py`. No new cycles
(`magic.py` still imports only models + loader).

### `armor_class.py`

- **Shield refactor:** remove the `SHIELD_AC_BONUS = 1` constant. Shield bonus =
  `item.ac_bonus + item.magic_bonus`, read from data. Mundane `shield` becomes
  `is_shield: true, ac_bonus: 1` in `armor.yaml`.
- Base-AC candidate may come from an equipped enchanted instance of `kind:
  armor` (`resolve_armor(...).ac_descending − magic_bonus`); shield bonus may
  come from an equipped enchanted instance of `kind: shield`. Precedence with the
  mundane `equipped` dict is **best-AC-wins** (take the better base; sum is not
  doubled because only one armour/shield is intended worn — best-wins is a safe,
  order-independent rule). The existing `ac set` (set-base-AC) path stays and now
  documents Bracers/Medallion/cursed-AC use.

### `attacks.py`

After the mundane `equipped_weapons` loop, a second loop over equipped
`EnchantedInstance` of `kind: weapon`: resolve to a synthetic `Weapon`, feed
through the existing `_profile_for` (already handles `magic_bonus`,
`conditional_bonus`, and `base_weapon` proficiency). No new attack math; the
conditional `vs <type>` row appears automatically.

### `encumbrance.py`

Count equipped/carried enchanted-instance weight from the resolved item (armour
0.5 multiplier applied), the same treatment magic-item instances already get
(`banding_weight_cn` etc.).

## Section 3 — Web (sheet-only acquisition)

### Loader

`GameData.load` reads `data/enchantments.yaml` into `enchantments`.

### Routes (shared handlers, sheet-only UI)

Mirror the magic-item set, keyed by `instance_id`:

- `/add-enchanted` — body: `base_id`, `enchantment_id` (validated compatible) →
  `add_free_enchanted`. **Add-only**, no gold.
- `/equip-enchanted`, `/unequip-enchanted`
- `/enchanted/use-charge`, `/enchanted/reset-charges`
- `/remove-enchanted`
- `/enchanted-note`

### Sheet

- Enchanted **weapons** surface in the Attacks table via `attack_profiles`
  (incl. conditional row) — no new template.
- Enchanted **armour/shield** surface in the AC value automatically.
- Each enchanted instance gets a row in the existing **Magic Items section**:
  collapsible `enchantment.description`, `modifier_summary` chips for passive
  extras, charges box when charged, and Equip / Unequip / Remove / Note controls.
- **Add picker** (the only genuinely new screen): choose enchantment (grouped by
  `kind`) → base dropdown filtered to `compatible_bases`.

### Wizard

- Wizard equipment step handles **mundane items only**.
- The existing magic-item Add UI is **removed** from the wizard equipment
  template; no enchanted Add there either.
- Regression test: wizard equipment step exposes no magic/enchanted acquisition.

## Section 4 — Seed data (Phase 1, minimal & representative)

Just enough to prove the model and drive tests — **not** the bulk import:

- Base weapons (add to `weapons.yaml`): a **bastard sword** and a
  **non-"sword"-named sword** (e.g. `lightsaber`) both `groups: [sword]`, plus an
  `axe`/`trident` for the exclude case. Existing `sword`/etc. get `groups`.
- `armor.yaml`: add `groups` + `ac_bonus`; `shield` → `ac_bonus: 1`.
- `data/enchantments.yaml` (new, small): one generic `+1`
  (`include: [any_weapon], exclude: [sword]`), one sword `+1, +3 vs undead`, one
  short-sword-only (Quickness-style), one charged (Trident Fish Command-style),
  one passive-modifier (Luck Blade `save:all +1`), one armour `+1`
  (`any_armour`), one shield `+1` (`any_shield`).
- **Delete** placeholder `magic_items.yaml` (and reconcile `containers.yaml`
  ownership in Phase 2).

## Testing

- `enchant.py`: matching (every Section-1 case incl. lightsaber + exclude),
  resolution (weapon & armour stats/name), compatibility validation, instance
  lifecycle (add/equip/charges/remove), charge rolling.
- `armor_class.py`: shield `ac_bonus` from data (no constant), enchanted armour
  base + enchanted shield bonus, set-base-AC, best-AC precedence.
- `attacks.py`: enchanted weapon profile incl. `magic_bonus`,
  `conditional_bonus` row, proficiency via `base_weapon`.
- `magic.py`: enchantment passive modifiers in `active_modifiers` (save/ac).
- `encumbrance.py`: enchanted-instance weight incl. armour 0.5 multiplier.
- Web: `/add-enchanted` validation, equip/charge/remove round-trips, sheet
  renders enchanted rows; **wizard exposes no magic/enchanted acquisition**.

## Out of scope (Phase 1)

- Bulk YAML import (Phase 2 spec).
- d% random-treasure tables (GM tooling).
- Activated/conditional powers, HP-heal items, spell-granting items — remain
  description-only.
- "Cannot discard cursed item" lock — `cursed` is a display flag only; no
  equip-lock behaviour (non-automated tool).
