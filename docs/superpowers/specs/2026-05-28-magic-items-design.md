# Magic Items — Design

**Date:** 2026-05-28
**Status:** Approved
**Implements:** Magic-item support for the AOSE Character Builder.

## Goal

Let a character own magic items. Most are pure flavour text. Some modify the
character mechanically — and those modifications must show on the sheet:

- adjust an ability score (set or modify),
- set or modify Armour Class,
- modify all or some saving throws,
- grant attack/damage bonuses to a specific weapon,
- grant a half-weight, AC-boosting enchantment to armour/shields,
- track limited-use charges.

The design is deliberately **data-driven**: a small, bounded modifier
vocabulary applied at the natural derivation sites covers the regular items
with **zero per-item engine code**. Four genuinely awkward mechanics
(attack-as-monster, damage-die override, conditional-vs-creature beyond a flat
bonus, spell reflection) are handled by an **escape hatch** (a free-text note
plus per-instance ad-hoc modifiers) rather than bespoke code.

## Decisions

| Question | Decision |
|---|---|
| Automation line | Data-driven core (ability / AC / saves / weapon `+N` / armour `+N` / carry capacity / charges) + a manual escape hatch for oddities. No bespoke per-item code. |
| Worn-item identity | Per-instance, mirroring `ContainerInstance`. Worn/charged magic items get a `uuid4` `instance_id`. Activation is an `equipped` bool on the instance. |
| Activation gesture | The existing **Equip / Unequip** UX. Catalog `equippable` flag decides what can be worn (a ring is inherently wearable; a potion is not). No slot limits — GM trust. |
| Magic weapons / armour | Stay native `Weapon` / `Armor` types (they need the weapon/armour slot + attack/AC/movement machinery). A `magic_bonus` field carries the enchantment; **not** the `magic` item_type. |
| "Magic" grouping & acquisition | A cross-cutting `magic: bool` flag on `ItemBase`. Drives the dedicated Magic Items section (sheet + shop), **Add-only** acquisition (no Buy / gold), and collapsible descriptions — for any item type. This is the "GM-grant only" flag the container spec deferred. |
| Instance vs plain inventory | A magic item needs an instance **iff** it carries mutable per-instance state: `equippable` (→ `equipped` bool) **or** charges. Stateless magic items (potions, magic weapons, magic armour) stay plain inventory ids; their `magic` flag only affects display/acquisition. |
| Stacking | Additive. No non-stacking rules engine. |
| Sign convention | `op: add` always means **better for the character** (relative improvement). `op: set` / `set_min` / `set_max` use **literal game-system numbers** (descending AC, save target, THAC0, ability score). |
| Unarmed attack | Always shown, first in the attack list. Base damage `1d2`, run through the melee/STR path so item STR buffs flow in. Always treated as proficient. |
| Conditional weapon bonus | Supported as a single `{vs, bonus}` rendered as a second parenthesised attack line. Multiple conditionals / non-weapon conditionals are out of scope. |
| Escape-hatch UI | V1 edits the free-text `note` only. `extra_modifiers` exist in the model (settable via homebrew catalog data) but get no edit form in V1. |
| Magic-item drag-and-drop | Out of scope for V1 — Equip/charges/remove are button/form only. Magic *weapons/armour* still DnD via the existing inventory machinery (they're plain inventory ids). |

## Data Model

### `ItemBase` gains two cross-cutting fields (`aose/models/item.py`)

```python
class ItemBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    category: str
    cost_gp: float
    weight_cn: int = 0
    description: str | None = None   # NEW — long flavour/rules text
    magic: bool = False              # NEW — drives Magic Items section + Add-only
```

### `Modifier` value type (new `aose/models/modifier.py`)

Shared by catalog `MagicItem.modifiers` and per-instance `extra_modifiers`,
so it lives in its own module to avoid item.py ↔ character.py coupling.

```python
class Modifier(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str                                  # see grammar below
    op: Literal["add", "set", "set_min", "set_max"]
    value: int
```

**Target grammar** (engine-parsed; unknown targets ignored, forward-compatible):

| Target | Applied in | `add` meaning | `set`/bounds meaning |
|---|---|---|---|
| `ability:STR…CHA` | `effective_abilities` | +value to score | literal score |
| `ac` | `armor_class` | +value defence (descending −value) | literal descending base candidate |
| `save:all` | `saving_throws` | +value to every save (target −value) | literal save target |
| `save:death\|wands\|paralysis\|breath\|spells` | `saving_throws` | +value to that save | literal save target |
| `attack` | `attacks` (all weapons + unarmed) | +value to-hit | literal (rare) |
| `damage` | `attacks` (all weapons + unarmed) | +value damage | literal (rare) |
| `carry_capacity` | `encumbrance` | +value cn capacity | literal (rare) |
| `thac0` | `attack_bonus.thac0` | +value (thac0 −value) | literal thac0 |

**Op semantics** (applied per target in this order): all `set` (last wins) →
all `add` (summed) → `set_min` (result = `max(result, value)`) → `set_max`
(result = `min(result, value)`). Example — Girdle "attacks as 8 HD, if already
better keep it": `thac0 set_max 14` → `min(current_thac0, 14)`.

### New `MagicItem` catalog variant (`aose/models/item.py`)

```python
class MagicItem(ItemBase):
    item_type: Literal["magic"]
    equippable: bool = False
    modifiers: list[Modifier] = Field(default_factory=list)
    max_charges: int | None = None     # fixed charge ceiling, OR…
    charge_dice: str | None = None     # …rolled at acquisition (e.g. "2d6")
```

Added to the `Item` discriminated union and re-exported from
`aose/models/__init__.py`. `Modifier`, `MagicItem`, and `MagicItemInstance`
(below) are all exported.

### `Weapon` and `Armor` gain enchantment fields

```python
class ConditionalBonus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vs: str          # creature category label, e.g. "undead"
    bonus: int       # ADDITIONAL bonus on top of magic_bonus when it applies

class Weapon(ItemBase):
    ...
    magic_bonus: int = 0
    conditional_bonus: ConditionalBonus | None = None

class Armor(ItemBase):
    ...
    magic_bonus: int = 0
    weight_multiplier: float = 1.0   # 0.5 for enchanted armour
```

### New `MagicItemInstance` runtime model (`aose/models/character.py`)

```python
class MagicItemInstance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instance_id: str                         # uuid4 hex
    catalog_id: str                          # references a MagicItem
    equipped: bool = False                   # ← the "equip state"; modifiers apply when True
    charges_max: int | None = None           # this instance's ceiling (rolled or fixed)
    charges_remaining: int | None = None     # None = no charges
    extra_modifiers: list[Modifier] = Field(default_factory=list)  # escape hatch
    note: str = ""                                                 # escape hatch
```

### `CharacterSpec` gains one field

```python
magic_items: list[MagicItemInstance] = Field(default_factory=list)
```

### Invariants (enforced by helpers, not Pydantic validators)

1. A `MagicItem` that is `equippable` **or** has charges is tracked **only** in
   `spec.magic_items` — its catalog id never appears in `inventory`/`stashed`/
   container contents.
2. A stateless magic item (`magic: true` on gear/weapon/armour, or a
   non-equippable non-charged `MagicItem`) lives in `inventory` like any other
   item; the `magic` flag is display/acquisition only.
3. Only `instance.equipped == True` items contribute modifiers. A charged but
   un-worn item (e.g. a wand) contributes no passive modifiers.
4. Magic weapon/armour bonuses come from `magic_bonus` fields, **never** from
   `Modifier`s. The `attack`/`damage` modifier targets exist only for worn
   items that buff *all* attacks (escape-hatch territory).

### Migration

`default_factory=list` / field defaults populate old saves on load. New
`ItemBase` fields default safely. No migration script.

## Engine API

### New module `aose/engine/magic.py`

```python
def active_modifiers(spec: CharacterSpec, data: GameData) -> list[Modifier]:
    """Catalog modifiers + extra_modifiers from every EQUIPPED magic item."""

def apply_modifiers(base: int, mods: list[Modifier], target: str) -> int:
    """Filter by target, apply set → add → set_min → set_max (see semantics)."""

def effective_abilities(spec: CharacterSpec, data: GameData) -> dict[Ability, int]:
    """spec.abilities with every `ability:*` modifier applied."""

def carry_capacity_bonus(spec: CharacterSpec, data: GameData) -> int:
    """Sum of `carry_capacity add` (and literal set) from active modifiers."""
```

`active_modifiers` reads `spec.magic_items`; for each `equipped` instance it
yields `catalog.modifiers + instance.extra_modifiers`. No import of the
derivation modules → no cycles.

### `aose/engine/ability_mods.py`

Unchanged (pure score → mod). **Consumers switch from `spec.abilities[…]` to
`effective_abilities(spec, data)[…]`.**

### `aose/engine/armor_class.py`

```python
def armor_class(spec, data) -> tuple[int, int]:
    dex_mod = ability_modifier(effective_abilities(spec, data)[Ability.DEX])
    base = UNARMORED_AC_DESCENDING                      # 9
    if body armor equipped:
        base = armor.ac_descending - armor.magic_bonus  # chainmail+1: 5-1=4
    mods = active_modifiers(spec, data)
    for m in mods if target=="ac" and op=="set":        # bracers-style base candidate
        base = min(base, m.value)
    shield_bonus = (SHIELD_AC_BONUS + shield.magic_bonus) if shield equipped else 0
    ac_add = sum(m.value for m in mods if target=="ac" and op=="add")  # improvement pts
    descending = base - dex_mod - shield_bonus - ac_add
    return descending, 19 - descending
```

### `aose/engine/saves.py`

After computing the best per-category target, apply `save:all` and
`save:<cat>` modifiers. `add` improves (`target -= value`); `set`/bounds use
literal save numbers. Targets clamp at a sane floor (≥ 2).

### `aose/engine/attack_bonus.py`

```python
def thac0(spec, data) -> int:
    best = min class thac0 (existing)
    return apply_modifiers(best, active_modifiers(spec, data), "thac0")
```
`add` improves (thac0 − value); `set_max` gives the Girdle's best-of override.
`attack_bonus = 19 - thac0` (unchanged, now picks up the override).

### `aose/engine/attacks.py`

- Abilities via `effective_abilities`. Base THAC0 via `thac0()` (already
  includes thac0 modifiers).
- Add `weapon.magic_bonus` to to-hit **and** damage.
- Apply global `attack`/`damage` modifiers (from `active_modifiers`).
- **Conditional bonus:** when `weapon.conditional_bonus` is set, compute a
  second profile variant (extra `magic_bonus + conditional_bonus.bonus`) and
  attach it as a nested `ConditionalAttack`.
- **Unarmed:** `attack_profiles` prepends a synthetic profile — `name="Unarmed"`,
  `melee=True`, base damage `1d2`, STR mod + global modifiers applied,
  `proficient=True`, `count=1`, no magic/conditional bonus.

`AttackProfile` gains an optional nested field:

```python
class ConditionalAttack(BaseModel):
    label: str                 # e.g. "vs undead"
    to_hit_thac0: int
    to_hit_ascending: int
    damage: str

class AttackProfile(BaseModel):
    ...                        # existing fields
    conditional: ConditionalAttack | None = None
    unarmed: bool = False      # for template styling / ordering
```

### `aose/engine/encumbrance.py`

`carried_weight_cn` changes:
- Inventory `Armor` items contribute `int(weight_cn * weight_multiplier)`;
  every other inventory item contributes `weight_cn` as before.
- Each `MagicItemInstance` contributes its catalog `weight_cn` (on-person
  whether worn or merely carried; no stash distinction in V1).
- Containers unchanged.

Banding accounts for carry capacity — `effective_movement` and
`encumbrance_table` band on `max(0, carried_weight_cn(spec,data) -
carry_capacity_bonus(spec,data))`. The **displayed** carried weight stays raw
(you really are hauling 1400 cn); only the band/movement improves. Only
matters in detailed mode (basic mode is always band 0).

### `aose/engine/magic.py` — charge helpers

```python
def new_magic_instance(catalog_id, data) -> MagicItemInstance
    # validates catalog is a MagicItem; rolls charge_dice (via engine.dice) or
    # uses max_charges to seed charges_max == charges_remaining; uuid4 id.
def use_charge(magic_items, instance_id) -> list[MagicItemInstance]
    # charges_remaining = max(0, charges_remaining - 1); raises if no charges.
def reset_charges(magic_items, instance_id) -> list[MagicItemInstance]
    # charges_remaining = charges_max.
def add_free_magic_item(magic_items, catalog_id, data) -> list[MagicItemInstance]
def equip_magic(magic_items, instance_id, data) -> list[MagicItemInstance]
    # requires catalog.equippable; sets equipped=True.
def unequip_magic(magic_items, instance_id) -> list[MagicItemInstance]
def remove_magic(magic_items, gold, instance_id, mode, data) -> tuple[list, int]
    # mode="drop" removes; "sell"/"refund" only if cost_gp > 0.
def set_magic_note(magic_items, instance_id, note) -> list[MagicItemInstance]
```

### New exceptions (`aose/engine/magic.py`)

```python
class UnknownMagicItem(ValueError): ...
class NotEquippable(ValueError): ...
class NoCharges(ValueError): ...
```

### Acquisition routing

Adding a `magic: true` item:
- `item_type == "magic"` and (`equippable` or has charges) → `add_free_magic_item`
  (creates an instance).
- otherwise (magic weapon/armour, pure-text magic gear) → append to `inventory`
  via the existing add path.

### Sheet view model (`aose/sheet/view.py`)

- `AbilityRow` gains `modified: bool`; `score`/`modifier` use **effective**
  scores. Template shows `18*` + a footnote when `modified`.
- New `MagicItemView` and a `magic_items: list[MagicItemView]` on
  `CharacterSheet`, listing every owned magic item (instances + inventory
  `magic` items) with name, description, equipped state, charges, note.

```python
class MagicItemView(BaseModel):
    instance_id: str | None        # None for plain-inventory magic items
    catalog_id: str
    name: str
    description: str | None
    equippable: bool
    equipped: bool
    charges_remaining: int | None
    charges_max: int | None
    note: str
    modifier_summary: list[str]    # human-readable, e.g. ["STR → 18", "+1 AC"]
```

## HTTP Routes

Mirrored on sheet (`/character/{id}/equipment/…`) and wizard
(`/wizard/{id}/equipment/…`).

| Method | Path suffix | Body | Engine call |
|---|---|---|---|
| POST | `/add` | `item_id` | Augmented: magic-instance items → `add_free_magic_item`; else existing add |
| POST | `/equip-magic` | `instance_id` | `equip_magic()` — 400 if not equippable |
| POST | `/unequip-magic` | `instance_id` | `unequip_magic()` |
| POST | `/use-charge` | `instance_id` | `use_charge()` — 400 on `NoCharges` |
| POST | `/reset-charges` | `instance_id` | `reset_charges()` |
| POST | `/remove-magic` | `instance_id`, `mode` | `remove_magic()` |
| POST | `/magic-note` | `instance_id`, `note` | `set_magic_note()` |

`/buy` is **not** extended for magic items (Add-only). Magic weapons/armour use
the existing `/equip`, `/unequip`, `/remove` (they're plain inventory ids).
404 for missing character, 400 for user errors — consistent with existing routes.

The wizard's `_draft_to_spec` **must** include
`magic_items=[MagicItemInstance.model_validate(m) for m in draft.get("magic_items", [])]`
(the container feature shipped a bug where this was forgotten — guard with a
finalize round-trip test).

## UI Rendering

### Shared editor — `_equipment_ui.html`

- **Magic Items shop section:** groups all `magic: true` catalog items, **Add
  only** (no Buy button, cost shown as "—"), collapsed by default, included in
  the existing shop search filter.
- **Owned magic items panel:** one row per `MagicItemInstance` —
  Equip/Unequip toggle, charges `n / max` with Use (−1) and Reset, an editable
  `note` field, and Remove (drop). Plain-inventory magic items render in the
  normal inventory table as today (their description surfaces in the sheet
  section below).

### Sheet display — `sheet.html`

- **Magic Items section** (`magic_items` view) with **collapsible
  descriptions** (collapsed by default — fixes the disproportionate-space
  pain), `modifier_summary` chips, and charge/worn state.
- **Abilities table** renders the effective score with a `*` marker + footnote
  when `modified`.
- **Attacks** renders the always-present Unarmed row first and a parenthesised
  conditional line under any weapon with a `conditional` profile.
- AC and saves need no template change — the numbers already reflect modifiers.
- **Print block:** add an owned-magic-items summary (name + one-line
  modifier_summary; descriptions omitted to save print space).

### CSS additions (`aose/web/static/sheet.css`)

- `.magic-item-row`, `.magic-desc` (collapsible), `.modifier-chip`
- `.charges` counter styling
- `.ability-modified` marker
- `.attack-conditional` muted sub-line
- `.unarmed-row` subtle styling

## Seed Data — `data/equipment/magic_items.yaml`

```yaml
# ── Worn misc magic items (instances) ──
- id: gauntlets_of_ogre_power
  name: Gauntlets of Ogre Power
  category: miscellaneous_magic_items
  item_type: magic
  magic: true
  cost_gp: 0
  weight_cn: 0
  equippable: true
  description: >-
    The wearer has a Strength score of 18 (all usual bonuses apply). With
    detailed encumbrance, carrying capacity rises by 1,000 cn (1,400 cn before
    becoming encumbered).
  modifiers:
    - {target: "ability:STR", op: set, value: 18}
    - {target: carry_capacity, op: add, value: 1000}

- id: ring_of_protection
  name: Ring of Protection
  category: magic_rings
  item_type: magic
  magic: true
  cost_gp: 0
  weight_cn: 0
  equippable: true
  description: "+1 bonus to Armour Class and to all saving throws."
  modifiers:
    - {target: ac, op: add, value: 1}
    - {target: "save:all", op: add, value: 1}

- id: ring_of_spell_turning
  name: Ring of Spell Turning
  category: magic_rings
  item_type: magic
  magic: true
  cost_gp: 0
  weight_cn: 0
  equippable: true
  charge_dice: "2d6"
  description: >-
    Spells cast on the wearer are reflected onto the caster. After the charges
    are exhausted the ring loses its power.

- id: girdle_of_giant_strength
  name: Girdle of Giant Strength
  category: miscellaneous_magic_items
  item_type: magic
  magic: true
  cost_gp: 0
  weight_cn: 0
  equippable: true
  description: >-
    The wearer attacks as an 8 HD monster (kept only if better) and inflicts
    2d8 damage in combat (or twice normal damage under variable weapon damage).
    NOTE: the 2d8 damage override is not auto-applied — apply by hand.
  modifiers:
    # 8 HD monster THAC0 — confirm value against the AOSE monster attack matrix.
    - {target: thac0, op: set_max, value: 14}

# ── Magic weapons (native Weapon type) ──
- id: sword_plus_1
  name: Sword +1
  category: magic_swords
  item_type: weapon
  magic: true
  cost_gp: 0
  weight_cn: 60
  damage: {default: "1d6", variable: "1d8"}
  melee: true
  proficiency_group: sword
  magic_bonus: 1

- id: sword_plus_2
  name: Sword +2
  category: magic_swords
  item_type: weapon
  magic: true
  cost_gp: 0
  weight_cn: 60
  damage: {default: "1d6", variable: "1d8"}
  melee: true
  proficiency_group: sword
  magic_bonus: 2

- id: sword_plus_3
  name: Sword +3
  category: magic_swords
  item_type: weapon
  magic: true
  cost_gp: 0
  weight_cn: 60
  damage: {default: "1d6", variable: "1d8"}
  melee: true
  proficiency_group: sword
  magic_bonus: 3

- id: sword_plus_1_vs_undead
  name: Sword +1, +3 vs Undead
  category: magic_swords
  item_type: weapon
  magic: true
  cost_gp: 0
  weight_cn: 60
  damage: {default: "1d6", variable: "1d8"}
  melee: true
  proficiency_group: sword
  magic_bonus: 1
  conditional_bonus: {vs: "undead", bonus: 2}

# ── Magic armour (native Armor type) ──
- id: chain_mail_plus_1
  name: Chain Mail +1
  category: magic_armour
  item_type: armor
  magic: true
  cost_gp: 0
  weight_cn: 400
  ac_descending: 5          # base chain mail; magic_bonus improves it to 4
  movement_impact: metal
  magic_bonus: 1
  weight_multiplier: 0.5

- id: shield_plus_1
  name: Shield +1
  category: magic_armour
  item_type: armor
  magic: true
  cost_gp: 0
  weight_cn: 100
  ac_descending: 9          # match the existing mundane shield's value (unused for shields)
  is_shield: true
  magic_bonus: 1
  weight_multiplier: 0.5

# ── Pure-text magic item (plain inventory, no instance) ──
- id: potion_of_healing
  name: Potion of Healing
  category: magic_potions
  item_type: gear
  magic: true
  cost_gp: 0
  weight_cn: 10
  description: "Quaffing restores lost hit points (per the referee's table)."
```

`_category_label` title-cases category ids automatically
(`miscellaneous_magic_items` → "Miscellaneous Magic Items", `magic_swords` →
"Magic Swords", etc.).

**Loader wiring:** `aose/data/loader.py` loads from an explicit `ITEM_FILES`
list, **not** a glob. Add `"magic_items.yaml"` to that list or the new file is
silently ignored.

## Tests — new `tests/test_magic_items.py`

### Catalog / model
- `MagicItem`, magic `Weapon`, magic `Armor` parse from YAML and are reachable
  via `data.items[…]`.
- `description` / `magic` defaults are safe on existing mundane items.

### Modifier engine (pure)
- `apply_modifiers` order: set → add → set_min → set_max.
- `effective_abilities` applies `ability:STR set 18`; unchanged for the rest.
- `effective_abilities` returns base scores when no magic items are equipped.
- An **un-equipped** worn item contributes nothing (`active_modifiers` empty).

### Abilities cascade (Gauntlets of Ogre Power)
- STR shows 18 when worn; melee to-hit/damage pick up +3.
- Unarmed attack shows `1d2+3`.
- carry_capacity +1000 → 1400 cn still in band 0 (detailed mode); displayed
  carried weight remains raw.

### Armour Class
- Ring of Protection equipped → descending −1 / ascending +1.
- Chain Mail +1 → base AC 4 [15].
- Shield +1 → 2 points of shield bonus.
- Chain Mail +1 **and** Ring of Protection stack additively.
- Removing/unequipping the ring reverts AC.
- `ac set N` (bracers-style, ad-hoc) takes the better base.

### Saves
- `save:all add 1` improves every category by 1.
- `save:death add 2` improves only Death.
- Save targets clamp at the floor.

### Weapons & unarmed
- `magic_bonus` adds to to-hit and damage (THAC0 and ascending).
- `conditional_bonus` produces a `conditional` profile with the right numbers
  and label.
- Unarmed profile is always present and first, even with no weapons.
- Variable-weapon-damage interaction (Sword +1 → 1d8+str+1).

### THAC0 override (Girdle)
- `thac0 set_max 14` lowers a worse THAC0 to 14.
- A better natural THAC0 is left untouched.

### Charges
- `new_magic_instance` rolls `charge_dice` into `charges_max == charges_remaining`.
- `use_charge` decrements; raises `NoCharges` at 0.
- `reset_charges` restores to `charges_max`.

### Encumbrance / weight
- Magic armour contributes half weight (`weight_multiplier 0.5`).
- A worn magic-item instance contributes its catalog weight.

### Acquisition / instance rule
- Adding Ring of Protection creates an instance (not an inventory entry).
- Adding Potion of Healing appends to inventory (no instance).
- Adding Sword +1 appends to inventory and is then equippable as a weapon.

### HTTP (sheet + wizard)
- `/add` of a worn item creates an instance and persists.
- `/equip-magic` / `/unequip-magic` round-trip; modifiers reflected on the sheet.
- `/equip-magic` on a non-equippable item → 400.
- `/use-charge` and `/reset-charges` round-trip; `/use-charge` at 0 → 400.
- `/magic-note` persists free text.
- `/remove-magic` drop removes the instance.
- Wizard finalize round-trips `magic_items` into the saved spec (regression
  guard for the `_draft_to_spec` omission bug).
- Sheet HTML renders the Magic Items section, the `*` ability marker, the
  Unarmed attack row, and a conditional attack line.
- Shop HTML renders a "Magic Swords" / "Magic Rings" etc. Add-only section.

## Out of Scope (deferred)

- **Damage-die overrides** (Girdle's 2d8 / "twice normal") — note only; not
  numerically expressible as a `Modifier`.
- **Spell-turning reflection** automation — text + a charge counter only.
- **Multiple / non-weapon conditional bonuses** — one flat `{vs, bonus}` only.
- **Slot limits / attunement** — no enforcement; GM trust.
- **Editing `extra_modifiers` via UI** — note-only in V1; the field is settable
  via homebrew catalog data.
- **Stashing magic-item instances** — always on-person in V1.
- **Non-stacking rules** for like bonuses — additive only.
- **Magic-item drag-and-drop** — buttons/forms only (magic weapons/armour still
  DnD via the existing inventory path).
- **Custom item creation UI** — homebrew goes in YAML / `extra_modifiers`.
