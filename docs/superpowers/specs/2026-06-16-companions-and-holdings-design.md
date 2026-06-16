# Companions & Holdings — design

**Date:** 2026-06-16
**Status:** Approved (brainstorming) — splits into two implementation plans.
**Slug:** `companions-and-holdings`

Adds three kinds of supporting cast/property to a character: **retainers** (hired
classed NPCs), **animals** (mounts, beasts of burden, dogs), and **vehicles**
(carts, wagons, boats, ships). All three surface in one new full-width sheet
section, **"Companions & Holdings."**

This is **two loosely-coupled features** sharing only that section. They are built
in two phases, each with its own implementation plan:

- **Phase A — Animals & Vehicles.** Data catalog + shop purchase + a new
  storage-location topology + an animal-armour slot. No new derivation engine of
  the character kind; mostly model + shop + inventory work. **Built first.**
- **Phase B — Retainers.** An embedded `CharacterSpec` per retainer, reusing the
  existing character engine (generation, HP rolls, XP/leveling, saves, attacks),
  plus loyalty, the CHA retainer cap, and class hiring restrictions. **Built
  second.**

The guiding principle throughout: **reuse the existing engine rather than invent
parallel machinery.** A retainer is a `CharacterSpec`; animal/vehicle gear flows
(eventually) through the same `Modifier` pipeline; animals/vehicles are bought
through the existing shop.

---

## Phase A — Animals & Vehicles

### Catalog data: two new `Item` variants

Animals and vehicles become variants of the existing `Item` discriminated union
so they ride the shop's category grouping and gold-spend flow with no new
acquisition machinery. **This is an authoritative import of official core
rulebook content, not throwaway seed data** — the full descriptions and trait
bullets from the provided reference are part of the data and are carried verbatim
(via `ItemBase.description` + a `traits` list), so the cards read like the book.

**`Animal` (`item_type: animal`)** — `data/equipment/animals.yaml`:
- `cost_gp`
- `hd` (string, e.g. `"2"`, `"1+2"`, `"½"`) — HD **rating**; drives THAC0/attack
  bonus and XP, and is what the encumbrance/HP conventions key off
- `save_as_hd` (`int | "NH"`) — the parenthesised "save-as" value (often ≠ HD
  rating); drives the five saving throws by table lookup
- `hp` (average — the parenthesised value)
- `ac` — descending only (ascending is **derived**, see below)
- `attacks` (list of `{name, count, damage}`)
- `morale`, `alignment`, `xp`
- transport stats: `movement` (`base'/encounter'`), and **load capacity** —
  `max_load_unencumbered_cn`, `max_load_encumbered_cn`, plus the
  unencumbered/encumbered movement rates and miles-per-day for display
- `armor_fits: list[str]` — which animal-armour items this animal can wear
  (empty = none)
- `description` (prose) + `traits: list[str]` (the ▶ bullets — camel
  "ill-tempered"/"water"/"desert travel", war horse "charge"/"melee", etc.)

> **Not stored, derived** (see "Derived combat stats" below): `ac_ascending`,
> `thac0`, `attack_bonus`, and the five saving throws.

Entries: camel, draft horse, riding horse, war horse, mule, hunting dog, war dog
— the full animals-of-burden + dogs lists from the reference, with descriptions.

**`Vehicle` (`item_type: vehicle`)** — `data/equipment/vehicles.yaml`:
- `cost_gp`
- `ac` — descending only (ascending derived)
- `hull_points` — `{min, max}` or a dice expression (cart `1d4`, wagon `2d4`,
  ship ranges like `60–90`). Resolved on the instance to `hull_max` at purchase
  (midpoint by default, editable) + `hull_damage`.
- `cargo_capacity_cn` — the vehicle's max load (a storage capacity)
- `category`: `land_vehicle` | `water_vessel`
- informational fields (displayed, **not enforced**): `required_animals`
  (e.g. "1 draft horse or 2 mules"), `required_crew` (rowing/sailing oarsmen &
  sailors + resulting speeds), `max_mercenaries`, `seaworthy: bool`,
  `requires_captain: bool`, `passengers`, and dimensions (`length`/`beam`/
  `draft`) where the book gives them
- `description` (prose) + `traits: list[str]`

Entries: the land vehicles (cart, wagon) and the water vessels (seaworthy and
unseaworthy) from the reference, with descriptions. **Catapults, rams, and
ship-mounted weaponry are out of scope for MVP** (combat-only; recorded as
free-text notes if wanted).

### Derived combat stats (HD-driven table lookups)

Rather than storing redundant numbers, animals (and the `normal_human` class /
0-level retainers, and any future monster NPCs) derive their combat stats from
two **data tables** imported from the provided NPC combat reference, plus one
formula. New engine module `aose/engine/monster_stats.py` (cycle-free; reads
models/loader only):

- **Ascending AC** — `ac_ascending = 19 − ac_descending` (a shared one-line
  helper; the same conversion the rest of the app implies, e.g. AC 9 → 10, 7 →
  12). Nothing stores both.
- **THAC0 / attack bonus** — band lookup on the **HD rating** against the *Attack
  Roll to Hit AC* matrix (`data/monster_attack_matrix.yaml`): bands `NH`,
  `up_to_1`, `1+_to_2`, `2+_to_3`, … each → `{thac0, attack_bonus}`. (Verified
  against the reference: HD 2 → 18 [+1], HD 3 → 17 [+2], HD 1+2 → 18 [+1].)
- **Saving throws** — band lookup on `save_as_hd` against the *Monster & Normal
  Human Saving Throws* table (`data/monster_saves.yaml`): bands `NH`, `1-3`,
  `4-6`, `7-9`, … each → `{D, W, P, B, S}`. `save_as_hd: "NH"` selects the NH row.

The HD-string → band parse (`"1+2"` → `1+_to_2`, `"½"` → `up_to_1`, `"NH"` → NH)
lives in `monster_stats.py` and is unit-tested against the worked examples above.

> Only saves were explicitly requested, but THAC0/attack-bonus derive from the
> same provided matrix by the same mechanism, so both are folded in to avoid
> storing numbers that are pure functions of HD. If you'd rather keep an explicit
> `thac0` override field for edge-case monsters, say so and we'll make the derived
> value a default that an optional stored value overrides.

**Tack & harness** (saddle and bridle, saddle bags, horse barding, dog armour)
are seeded too. Barding and dog-armour are **animal-armour items** (see below);
the rest are normal `AdventuringGear` that can be loaded onto an animal as cargo.

### Animal-armour slot

Barding (AC 5 [14], 600 cn) and dog-armour (AC 6 [13]) are mundane animal armour.
Model as a small item carrying:
- `sets_ac` — descending only; replaces the animal's natural AC (ascending
  derived via the `19 − ac` helper)
- `weight_cn` — counts against the animal's load like cargo
- `fits: list[str]` — animal ids/groups it can be worn by (gates UI offering)

Per-instance, the animal carries an optional `armor_id`. The displayed AC is the
worn armour's set value when present, else the natural AC.

> **Forward-compatibility for magic (deferred).** Magic animal items (e.g.
> Horseshoes of Speed) are **not** built in Phase A — they are recorded as a
> free-text note on the animal for now. The `AnimalInstance` is shaped so a
> `magic_items: list[MagicItemInstance]` field and a new `mv` modifier target can
> be added later **without reshaping** it: the displayed AC/MV will then be a
> `build_animal(instance, data)` derivation (start from the stat block → apply the
> armour AC-set → add equipped magic-item modifiers via the existing
> `apply_modifiers`), mirroring `armor_class`/`magic.py`. Until then `build_animal`
> just resolves armour AC and passes movement through unchanged.

### Purchase → roster instance

Buying an animal or vehicle deducts gold via the existing shop flow but, instead
of appending an id to `inventory`, creates a **per-instance roster entry**
(mirroring `ContainerInstance` — each owned animal/vehicle has state: damage,
loaded contents, a label). New fields on `CharacterSpec`:

```python
animals:  list[AnimalInstance]   = []
vehicles: list[VehicleInstance]  = []
```

```python
AnimalInstance:
    instance_id: str
    catalog_id: str            # references an Animal
    name: str = ""             # optional label ("Bessie")
    hp_damage: int = 0         # current hp = max(0, catalog.hp - hp_damage)
    armor_id: str | None = None
    contents: list[str] = []   # cargo loaded onto the animal (item ids)
    magic_note: str = ""       # free-text until magic-item support lands
    # (future) magic_items: list[MagicItemInstance]

VehicleInstance:
    instance_id: str
    catalog_id: str            # references a Vehicle
    name: str = ""
    hull_max: int              # resolved from the catalog range at purchase
    hull_damage: int = 0
    contents: list[str] = []   # cargo (item ids; a container placed aboard is
                               # referenced via the generalised location concept
                               # below, not duplicated here)
    note: str = ""
```

### Storage-location topology (the key refinement)

Today gear lives in one of: **on-person** (`inventory`, contributes to
encumbrance), **stashed** (`stashed`, off-person, no weight), or inside a
**container** (`ContainerInstance`, which is itself carried or stashed).

Animals and vehicles add **new top-level locations**, peers of on-person/stashed
— *not* carried by any person, because an animal isn't carried. Gear (and
containers) can be moved into an animal/vehicle. Rules:

- An animal/vehicle's loaded contents are checked against **its own** max-load
  capacity (animal: encumbered/unencumbered thresholds; vehicle: cargo capacity).
- Loaded contents do **not** count toward the PC's personal encumbrance.
- Worn barding counts against the animal's load capacity.
- (Optional, nice-to-have) overloading an animal drops it from unencumbered to
  encumbered movement; over the encumbered max it can't move. Vehicle
  over-capacity is flagged but not auto-penalised.

The inventory engine (`equip.py`/`shop.py`/`encumbrance.py`) gains a generalised
notion of a **location** — a person (on-person/stashed), a container, or an
animal/vehicle — so the existing move/stow/take-out helpers can target any of
them. No nesting beyond container-in-vehicle.

### Damage / repair (light)

Animals track `hp_damage` (current hp derived like the PC's `damage_taken`).
Vehicles track `hull_damage` against `hull_max`. Both get simple +/- controls on
the card; the movement-reduction and repair rules are displayed as reference text,
not auto-computed (proportionate to a builder, not a combat tracker).

### Phase A UI

In the new **Companions & Holdings** section: animal cards and vehicle cards, each
showing the stat block, capacity, current hp/hull, an armour control (animals),
and an expandable **contents sub-list** that *is* the storage location (move
items in/out, same controls as container rows). Acquisition is via the existing
shop (new `animal` / `vehicle` categories appear automatically through
`shop_categories`).

---

## Phase B — Retainers

### Storage: an embedded `CharacterSpec`

A retainer **is** a `CharacterSpec`. The existing engine already does abilities,
HP rolls, XP, leveling, saves, THAC0, attacks for a `CharacterSpec` end-to-end;
a parallel "simple character" model would mean re-implementing all of it. So:

```python
# on CharacterSpec
retainers: list[Retainer] = []

Retainer:
    id: str
    spec: CharacterSpec        # the retainer's own character
    loyalty: int               # current loyalty value (editable)
    role: str = ""             # free-text note ("torchbearer", "bodyguard")
```

Two wrinkles, handled explicitly:

- **Self-reference.** `CharacterSpec` gains a `retainers` field that refers to its
  own type. Pydantic handles the forward reference; usage is bounded (a
  retainer's own `retainers` stays empty — retainers don't hire retainers).
  `build_sheet` on a retainer renders an empty Companions section, which is fine.
- **Normal human (level 0).** `CharacterSpec.classes` requires ≥1 class, but a
  normal human has none. Add a data-driven **`normal_human` class**
  (`data/classes/normal_human.yaml`) with a single authored `progression` row
  carrying the NH values (THAC0 20 [-1], saves D14 W15 P16 B17 S18 — the same NH
  numbers the `monster_stats` NH band holds, authored once here so the class path
  stays uniform with every other class), a ~2 hp hit die, and permissive
  `weapons_allowed`/`armor_allowed`. Stored internally
  as level 1, **UI-labelled "0-level / Normal Human."** When it earns enough XP to
  advance, the player converts it to a real adventuring class (the rule: a normal
  human "must choose a character class" on gaining XP). This keeps every engine
  path uniform instead of special-casing NH throughout. *(Implementation note: the
  class progression/HP path may need a tiny accommodation for the ~2 hp hit die /
  fractional HD; verify during planning.)*

A retainer **inherits the hiring PC's `RuleSet` snapshot** (same campaign rules:
source toggles, `separate_race_class`, etc.). Generation copies it into the
retainer's `spec.ruleset`.

### Generation (baseline-10, meets prerequisites)

1. All six abilities start at **10**.
2. Raise any of the class's `ability_requirements` to its minimum.
3. Apply racial ability modifiers (Advanced) if race+class.
4. Roll HP via the existing HP flow for the chosen level.
5. Set level: `0` (normal human) or `1..PC.level`. **A retainer may never exceed
   the hiring PC's level.**

Race+class is offered only when `separate_race_class` is on; class and race
availability follow the inherited ruleset (disabled-content source toggles,
demihuman restrictions). Generated abilities are **hand-editable** afterward.

### Loyalty

Stored editable integer. Default initialised from the **Charisma → Loyalty**
column of the hiring PC, then adjusted by the hiring PC's class/race loyalty
modifiers:

| CHA  | Max retainers | Loyalty |
|------|---------------|---------|
| 3    | 1             | 4       |
| 4–5  | 2             | 5       |
| 6–8  | 3             | 6       |
| 9–12 | 4             | 7       |
| 13–15| 5             | 8       |
| 16–17| 6             | 9       |
| 18   | 7             | 10      |

Loyalty modifiers of the **hiring PC** (data-driven, see below):
- **Human:** all retainers/mercenaries **+1** loyalty (and morale).
- **Half-orc:** retainers' loyalty **−1**, *except* retainers who are themselves
  half-orcs.

After initialisation the referee can edit loyalty freely (the rules allow
discretionary +/-). Only the **current value** is tracked (no history).

### CHA → max retainers (soft cap)

The Max-retainers column caps how many retainers the PC should have. Enforced as a
**soft warning** when exceeded (referee discretion), not a hard block.

### Hiring restrictions ("type stems from class")

Some classes restrict whom they may hire and from what level (e.g. **Assassin:**
none at 1st–3rd; from 4th may hire lower-level assassins; from 8th, thieves; from
12th, any class). Model as a new optional field on `CharClass`:

```python
retainer_hiring: list[RetainerHiringRule]   # default: unrestricted

RetainerHiringRule:
    min_level: int                  # hiring PC level at which this tier applies
    allows: Literal["none"] | list[str] | "any"   # class ids, "any", or "none"
    same_or_lower_level: bool = True
```

The effective rule is the highest `min_level` tier ≤ the PC's level. Encode the
**Assassin** case as the worked example. **A full class-data pass to encode every
class's retainer rules is a follow-up data task**, not blocking — classes with no
`retainer_hiring` are unrestricted (any class, ≤ PC level).

Loyalty modifiers (human +1, half-orc −1) are likewise data on the class/race —
a `mechanical` key such as `retainer_loyalty_modifier: {value, except_same_race}`
read at retainer-creation time. (No combat-modifier pipeline involvement; loyalty
is not a combat number.)

### XP −50%

Retainers earn XP like PCs but **penalised −50%** (they follow orders rather than
solve problems). When granting XP to a retainer, halve the award before calling
the existing `grant_xp(retainer.spec, data, amount)`.

### Phase B UI

In the Companions & Holdings section: a retainer card per retainer — a **compact
stat-block** rendered from `build_sheet(retainer.spec, data)` (AC, HP, THAC0/
attack, saves, key gear), expandable for detail, with controls for **loyalty**
(edit), **level/XP** (advance via the reused leveling flow), and **role** note.
An **"Add retainer"** generator drives the baseline-10 generation, gated by the
hiring restrictions and warning past the CHA cap.

---

## What is explicitly out of scope (MVP)

- Wages / upkeep tracking (too loose to encode — recorded nowhere, or free-text).
- Mercenaries and specialists (distinct from retainers; not requested).
- Magic animal items / the `mv` modifier target (deferred; free-text note).
- Ship weaponry, rams, catapults, and vehicle combat.
- Auto-computed movement penalties from hull/load damage, crew shortfalls, and
  required-animal enforcement (shown as reference, not enforced).
- Retainers carrying the PC's gear as a storage location (a retainer has its own
  `spec.inventory`; moving gear between PC and retainer is a possible later
  nicety, not MVP).
- A full class-data pass for `retainer_hiring` (Assassin encoded as the example).

## Engine-DAG / invariants to preserve

- Animals/vehicles are **data, not code** — new entries are pure YAML, consistent
  with the existing "no engine module references a class/race id" rule.
- `build_animal` (when it gains modifier support) and any retainer derivations
  stay cycle-free, reading models/loader + the existing `magic.apply_modifiers`.
- `monster_stats.py` (AC-ascending formula + THAC0/save band lookups) is
  cycle-free, depends only on models/loader + the two new lookup tables, and is
  the single home for "derive a monster/NH stat from HD." No combat numbers are
  stored that this module can compute.
- No migrations (app isn't deployed); new `CharacterSpec` fields default empty so
  old saves load unchanged.
- Reuse the modifier pipeline, `MagicItemInstance`, the shop, and `build_sheet`
  rather than duplicating them.
