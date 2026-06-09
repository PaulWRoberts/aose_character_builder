# Carcass Crawler 3 expanded equipment — design

**Date:** 2026-06-09
**Status:** Approved (design)
**Source:** `import/pdfs/carcass-crawler-3` (Expanded Equipment, Gavin Norman /
Necrotic Gnome) — supplied as Markdown excerpt; rules verified against it.

## Problem

Add the *Carcass Crawler Issue 3* "Expanded Equipment" content: a large
adventuring-gear list (with several containers), seven new weapons, five new
armour types, and a set of new weapon qualities. CC3 is a non-core source.

Encoding the new weapons exposes existing brittleness in the weapon model:
"versatile" today needs three properties to agree (a `versatile` boolean, a
`variable_two_handed` damage string, and — in the book — a quality tag), and the
same redundancy exists for `missile` (a quality **and** `ranged`/`range_*`
fields) and `two_handed` (a quality **and** `hands`). Inspection of all 20
existing weapons shows these are **fully redundant**: the quality's presence
already matches the stored field in every case (e.g. the bogus `versatile: true`
on the spear is the lone inconsistency, and it is simply wrong). So the work is
split into a behaviour-preserving refactor followed by the new content.

This is **one spec, two phases**, implemented in order: Phase 1 lands green
before any new content is added.

## Decisions (confirmed)

- **Single source of truth = the qualities list.** `melee`, `ranged`,
  `range_short/medium/long`, `hands`, `versatile`, and `variable_two_handed`
  become **computed properties** derived from parametric qualities. The read API
  (`weapon.melee`, `weapon.ranged`, `weapon.range_short`, `weapon.hands`,
  `weapon.versatile`, `weapon.two_handed_damage`) is preserved, so call sites
  change minimally.
- **Bastard sword damage under the standard 1d6 rule is plain `1d6`** (RAW — the
  +1 only applies under variable weapon damage: `1d6+1` 1H / `1d8+1` 2H).
- **`1d6` is the engine default, never restated in data.** Standard-rule weapon
  damage is universally `1d6`, so `WeaponDamage.default` (and `variable`) default
  to `"1d6"` in the model and are **omitted from weapon YAML** unless overriding
  — the whole `damage:` block is omitted for a plain 1d6/1d6 weapon, only the
  differentiated `variable` die is specified, and no-damage weapons explicitly
  override with `""`.
- **Versatile renders two attack profiles only under the variable-damage rule**
  (under the standard rule both hands deal `1d6`, so one profile).
- **Full plate "tailored":** default tailored (AC 2 [17]); a checkbox in the
  **equipment management drawer** marks it untailored (AC 3 [16], "another
  person's plate").
- **`blunt` grants cleric usage automatically** via a new class field
  `weapon_qualities_allowed`. Cleric and Acolyte become
  `weapon_qualities_allowed: [blunt]` (their explicit lists — which were exactly
  the five core blunt weapons — are dropped). Side effect: blackjack, bolas, and
  net (all `blunt` in CC3) become cleric-usable, matching the quality's intent
  ("May be used by clerics").
- **Thieves-and-studded-leather optional rule is out of scope** — thief skills
  are an un-mechanised table, so there is nothing to penalise.

---

## Phase 1 — Parametric weapon qualities (behaviour-preserving refactor)

### Quality registry: a param schema

`WeaponQuality` (`aose/models/weapon_quality.py`, `data/equipment/
weapon_qualities.yaml`) gains:

```python
param: Literal["none", "ranges", "damage"] = "none"
```

- `missile` → `param: ranges` (expects `[short, medium, long]`)
- `versatile` → `param: damage` (expects a 2H damage string)
- everything else (`melee`, `two_handed`, `blunt`, `reload`, `slow`, `brace`,
  `charge`, `splash_weapon`, plus the new CC3 ones) → `param: none`.

### Weapons reference qualities, optionally parameterised

Each entry in a weapon's `qualities` list is either a **bare id** or a
**one-key mapping** `{id: value}`:

```yaml
- id: dagger
  item_type: weapon
  name: Dagger
  category: weapons
  cost_gp: 3
  weight_cn: 10
  damage: { variable: "1d4" }   # default omitted → 1d6
  qualities:
    - melee
    - missile: [10, 20, 30]

- id: crossbow
  # no damage: block at all → 1d6 / 1d6
  qualities: [reload, slow, two_handed, {missile: [80, 160, 240]}]
  accepts_ammo: [crossbow_bolt]
```

The following stored `Weapon` fields are **removed** from data and the model:
`hands`, `versatile`, `melee`, `ranged`, `range_short`, `range_medium`,
`range_long`; and `variable_two_handed` is removed from `WeaponDamage`.
`accepts_ammo`, `groups`, `magic_bonus`, `conditional_bonus`, `base_weapon`
remain independent fields (ammo acceptance and enchantment tags are not
qualities).

### Model shape

```python
class QualityRef(BaseModel):
    id: str
    ranges: tuple[int, int, int] | None = None   # missile param
    damage: str | None = None                    # versatile param (2H damage)

class WeaponDamage(BaseModel):
    default: str = "1d6"    # standard-rule damage; "1d6" is the sole place 1d6
    variable: str = "1d6"   # lives — YAML omits both unless overriding
    # variable_two_handed removed (2H damage now the `versatile` quality param)

class Weapon(ItemBase):
    item_type: Literal["weapon"]
    damage: WeaponDamage
    qualities: list[QualityRef] = Field(default_factory=list)
    accepts_ammo: list[str] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)
    magic_bonus: int = 0
    conditional_bonus: ConditionalBonus | None = None
    base_weapon: str | None = None
```

A field validator parses each YAML `qualities` entry (string → `QualityRef(id=…)`;
mapping → `QualityRef(id=key, ranges=…|damage=…)`).

**Computed properties** preserve the read API:

```python
@property
def quality_ids(self) -> set[str]: ...
@property
def melee(self) -> bool:           return "melee" in self.quality_ids
@property
def ranged(self) -> bool:          return "missile" in self.quality_ids
@property
def hands(self) -> int:            return 2 if "two_handed" in self.quality_ids else 1
@property
def versatile(self) -> bool:       return "versatile" in self.quality_ids
@property
def range_short / _medium / _long: # from the missile QualityRef.ranges, else None
@property
def two_handed_damage(self) -> str | None:  # versatile QualityRef.damage, else None
@property
def deals_damage(self) -> bool:    return bool(self.damage.default)
```

### Loader validation (loud-drift guard)

At load, for each weapon quality ref:

- quality id must exist in the registry;
- a `ranges` quality (`missile`) must carry exactly three ints; a non-`ranges`
  quality must not carry ranges;
- a `damage` quality (`versatile`) must carry a damage string; a non-`damage`
  quality must not carry one.

### Call-site updates

- **`enchant.py` `resolve_weapon`** simplifies: drop the explicit `versatile=`,
  `melee=`, `ranged=`, `range_*=`, `hands=` copies; forward `qualities` (deep
  copy) + `damage`. Derived properties flow through automatically.
- **`detail.py` `item_card`** renders structured qualities (e.g. "Missile
  (80/160/240 ft)", "Versatile (1d8+1)") and shows `—` for `not deals_damage`.
  The `Damage (2H)` line now reads `two_handed_damage`.
- **`attacks.py`** continues to read `weapon.melee/.ranged/.range_*` and is
  otherwise unchanged in Phase 1. The new versatile-split and no-damage
  behaviours are added in Phase 2 (they are behaviour changes, not part of the
  parity-preserving refactor), reading `two_handed_damage` / `deals_damage`.

### Phase-1 acceptance

A **parity test** rewrites every existing weapon into the parametric form and
asserts the derived properties **and** effective damage equal the pre-refactor
stored values (`melee/ranged/hands/range_*/versatile/two_handed_damage` plus
`damage.default`/`damage.variable`, confirming omitted `1d6`s resolve correctly).
The spear's
`versatile` becomes `False` (correcting the bug). All existing tests stay green.

---

## Phase 2 — CC3 content

### Source

`data/sources.yaml` gains:

```yaml
- id: carcass_crawler_3
  name: Carcass Crawler Issue 3
  publisher: Necrotic Gnome
  core: false
```

Every new item below carries `source: carcass_crawler_3`. Gating flows through
the existing `source_enabled` / `shop_categories` path — no engine change.

### Adventuring gear (`adventuring_gear.yaml`)

~35 new `item_type: gear` rows (cost only; weights omitted — the engine folds
gear to a flat 80 cn): barrel, bedroll, bell (miniature), block and tackle,
bucket, caltrops (bag of 20), candles (10), chain (10'), chalk (10 sticks),
chisel, cooking pots, firewood (bundle), fishing rod and tackle, holy symbol
(gold), holy symbol (wooden), ink (vial), ladder (wooden, 10'), lantern bullseye,
lock, magnifying glass, manacles, marbles (bag of 20), mining pick, musical
instrument (string), musical instrument (wind), paper/parchment (2 sheets),
quill, saw, scroll case, sledgehammer, spade or shovel, tent, twine (100' ball),
vial (glass), whistle.

- `bundle_count` where the book sells discrete sets: candles `10`, chalk `10`,
  paper/parchment `2`. Caltrops/marbles are "bag of 20" → the bag is one unit
  (`bundle_count: 1`).
- Holy symbols: the existing silver `holy_symbol` (25 gp) stays; gold (+1
  turning) and wooden (−1 turning) are flavour described in text only (turning is
  not mechanised). The existing hooded `lantern` stays; `lantern_bullseye` is
  distinct.

**5 containers** (`item_type: container`, no own weight, capacity from the coin
limit, grouped under Adventuring Gear like `backpack`/`sack_*`):

| id | capacity_cn |
|---|---|
| belt_pouch | 50 |
| box_iron_small | 250 |
| box_iron_large | 800 |
| chest_wooden_small | 300 |
| chest_wooden_large | 1000 |

Barrel, bucket, vial hold *liquid* (not coin capacity) → plain gear, not
containers.

### Weapon qualities

Add four `param: none` definitions to `weapon_qualities.yaml`: `knock_out`,
`entangle`, `stealth`, `strangle` (descriptive text from CC3). `versatile` and
`missile`'s param schema are added in Phase 1. `blunt`, `melee`, `two_handed`
already exist (reused). These are descriptive only (like `slow`/`brace`); their
save-vs-paralysis / auto-damage prose is **not** mechanised.

### Weapons (`weapons.yaml`, parametric form)

Standard-rule damage is the engine default `1d6` (never written); only the
`variable` die and any 2H die (the `versatile` param) appear in data. The
`damage` column below shows the *effective* default / variable / 2H values.

| id | cost / wt | damage (default / variable / 2H) | `damage:` block in YAML | qualities |
|---|---|---|---|---|
| bastard_sword | 15 / 80 | 1d6 / 1d6+1 / **1d8+1** | `{ variable: "1d6+1" }` | `[melee, {versatile: "1d8+1"}]`, `groups: [sword]` |
| blackjack | 1 / 10 | 1d6 / 1d2 | `{ variable: "1d2" }` | `[blunt, knock_out, melee, stealth]` |
| blowgun | 3 / 5 | **none** | `{ default: "", variable: "" }` | `[{missile: [10, 20, 30]}]`, `accepts_ammo: [blowgun_dart]` |
| bolas | 5 / 40 | 1d6 / 1d2 | `{ variable: "1d2" }` | `[blunt, entangle, {missile: [20, 40, 60]}]` |
| garotte | 1 / 5 | 1d6 / 1d4 | `{ variable: "1d4" }` | `[melee, stealth, strangle, two_handed]` |
| net | 5 / 100 | **none** | `{ default: "", variable: "" }` | `[blunt, entangle, {missile: [10, 20, 30]}]` |
| whip | 10 / 50 | 1d6 / 1d2 | `{ variable: "1d2" }` | `[entangle, melee]` |

- **No-damage weapons** (blowgun, net): `damage: { default: "", variable: "" }`.
  In `attacks.py`, when `not weapon.deals_damage` the profile still computes
  to-hit but its `damage` is `"—"` and no STR/DEX damage modifier is added.
  `detail.py` shows `—`.
- **Versatile split** (`attacks.py`): when `weapon.versatile`,
  `weapon.two_handed_damage` is set, **and** `ruleset.variable_weapon_damage` is
  on, emit two profiles — a 1H row (uses `damage.variable`) and a
  "<name> (Two-handed)" row (uses `two_handed_damage`, note "no shield"). Under
  the standard rule, one profile. The 2H row carries `manageable_item_id=None`
  (managed via the 1H row).

### Ammunition (`ammunition.yaml`)

```yaml
- id: blowgun_dart
  item_type: ammunition
  name: Blowgun Darts (pouch of 5)
  category: ammunition
  cost_gp: 1
  weight_cn: 0
  bundle_count: 5
  groups: [blowgun_dart]
  source: carcass_crawler_3
```

### Armour (`armor.yaml`) + wearable categories

Five new body armours. `base_armor` (already "counts-as for class allowances")
maps each onto an existing type, so **no allowance-engine change** — leather
users get padded/furs, chain users get studded leather, plate users get banded
mail + full plate, automatically via `base_armor_id`.

| id | ac_descending | cost / wt | movement_impact | base_armor | groups |
|---|---|---|---|---|---|
| padded_armor | 8 | 5 / 100 | leather | leather_armor | [leather_armour] |
| furs | 7 | 10 / 250 | leather | leather_armor | [leather_armour] |
| studded_leather | 6 | 25 / 300 | leather (light, per CC3) | chain_mail | [leather_armour] |
| banded_mail | 4 | 50 / 450 | metal | plate_mail | [metal_armour] |
| full_plate | 2 | 1000 / 700 | metal | plate_mail | [metal_armour] |

(`movement_impact` is the basic-encumbrance class: `leather` = light, `metal` =
heavy — matching CC3 Option 1.)

### Full plate "tailored"

- **Model:** `Armor` gains `tailorable: bool = False` and
  `untailored_ac_descending: int | None = None`. Full plate sets
  `tailorable: true`, `ac_descending: 2`, `untailored_ac_descending: 3`.
  `CharacterSpec` gains `armor_tailored: bool = True` (one toggle for the equipped
  body armour; inert when the worn armour isn't tailorable; remembered across
  re-equips).
- **AC engine (`armor_class.py`):** in `_compute_ac`, when the equipped body
  armour is `tailorable` and `not spec.armor_tailored` and
  `untailored_ac_descending is not None`, use `untailored_ac_descending` as the
  base candidate. Generic — reads fields, references no item id.
- **UI:** a "Tailored to wearer" checkbox in the equipment management drawer,
  shown only when the equipped armour is `tailorable`, posting to a small route
  that flips `armor_tailored`. Default checked (AC 2); unchecking → AC 3.

### Cleric blunt allowance

- **Model:** `CharClass` gains
  `weapon_qualities_allowed: list[str] = Field(default_factory=list)`.
- **`proficiency.py` `allowed_weapon_ids`:** after resolving the explicit
  per-class list, union in every weapon whose `quality_ids` intersect that
  class's `weapon_qualities_allowed`. (A class with `weapons_allowed: all` is
  already unrestricted.)
- **Data:** `cleric.yaml` and `acolyte.yaml` drop their explicit
  `weapons_allowed` lists in favour of `weapon_qualities_allowed: [blunt]`.

---

## Docs & tests

- **`ARCHITECTURE.md`:** new "Weapon qualities as the source of truth"
  note under Attacks & ammunition (parametric qualities, computed properties,
  no-damage, versatile split); update the inventory/armour section (tailored
  full plate) and the allowances note (`weapon_qualities_allowed`). One row at
  the top of `CHANGELOG.md`. No `CLAUDE.md` change (no new top-level dir/wizard
  step/storage shape beyond a field).
- **Tests:**
  - Phase 1: parity test (derived props == old stored values for every existing
    weapon); quality-parse round-trip; loader-validation failures (missile
    without 3 ranges, versatile without damage, param on a `none` quality).
  - Phase 2: every CC3 item parses with `source: carcass_crawler_3`; versatile
    two-profile (variable on → two rows; off → one); no-damage profile (`—`, no
    mod); cleric/acolyte can equip every blunt weapon incl. blackjack/bolas/net,
    cannot equip a sword; full-plate AC (2 tailored / 3 untailored); armour
    categories (plate user equips full plate + banded; leather user equips
    padded/furs but not studded leather).
