# Animals & Vehicles (Companions & Holdings — Phase A) — design

**Date:** 2026-06-16
**Status:** Approved design — ready for an implementation plan.
**Parent:** [`2026-06-16-companions-and-holdings-design.md`](2026-06-16-companions-and-holdings-design.md)
**Slug:** `animals-and-vehicles`

Phase A of Companions & Holdings: let a character **buy animals and vehicles**
(official core-rulebook content, descriptions and all), see their stats, and use
each owned animal/vehicle as a **top-level storage location** that gear can be
loaded onto — independent of the character's own encumbrance. Includes a mundane
**animal-armour slot**. Retainers (Phase B) and **magic** animal items are out of
scope here.

This document is implementation-ready: it specifies the models, the data to
import, the derived-stat engine, the topology changes, the shop wiring, the UI,
and the tests. It reuses the existing `Item` union, the `Container`
instance/`stow`/`take_out` machinery, and `shop_categories` rather than inventing
parallel systems.

---

## Goals / non-goals

**Goals**
- Buy/own animals & vehicles via the existing shop (gold-spend), as per-instance
  roster entries (not flat inventory ids).
- Faithful import of the provided official tables, **with descriptions and trait
  bullets**.
- Each owned animal/vehicle is a storage location with its own max-load capacity;
  its contents do **not** count toward the PC's encumbrance.
- Mundane animal armour (barding, dog armour) that *sets* the animal's AC.
- Combat stats (ascending AC, THAC0/attack bonus, saving throws) **derived** from
  HD via table lookup — not stored.
- Light damage state (animal hp, vehicle hull) with manual +/- controls.

**Non-goals (this phase)**
- Magic animal items / the `mv` modifier target (free-text `magic_note` only).
- Ship weaponry, rams, catapults, vehicle-to-vehicle combat.
- Enforcing required crew / required animals / passenger limits (display only).
- Auto-computing movement penalties from load, hull/hp damage, or crew shortfall
  (the rules are shown as reference text; not calculated).
- Retainers, wages, mercenaries (Phase B / separate).

---

## Data model

### New `Item` variants

Added to the `Item` discriminated union in `aose/models/item.py` (and re-exported
from `aose/models/__init__.py`). Both extend `ItemBase`, so they inherit `id`,
`name`, `category`, `cost_gp`, `weight_cn`, `description`, `source`.

All imported content is **Old School Essentials Classic Fantasy**, so `source`
takes its default (`ose_classic_fantasy`) — the locked-on Classic source. The
content-toggle gate therefore never disables animals/vehicles (Classic is never
added to `disabled_content`); no `source:` line is needed in the YAML entries.

```python
class AnimalAttack(BaseModel):
    name: str            # "bite", "hoof", "kick"
    count: int = 1       # attacks per round of this kind
    damage: str          # "1d4", "1", "2d4"
    note: str | None = None   # e.g. "or" alternatives flagged in the UI

class Animal(ItemBase):
    item_type: Literal["animal"]
    hd: str                       # HD rating, e.g. "2", "1+2", "½"  → THAC0/XP
    save_as_hd: int | str         # parenthesised save-as ("NH" or an int) → saves
    hp: int                       # average hp (the parenthesised value)
    ac: int                       # descending; ascending derived (19 - ac)
    attacks: list[AnimalAttack] = []
    morale: int
    alignment: Literal["law", "neutral", "chaos", "any"] = "neutral"
    xp: int = 0
    movement: str                 # "150' (50')" base (encounter)
    miles_per_day: int | None = None
    # Beast-of-burden load table (None for non-carriers like dogs):
    max_load_unencumbered_cn: int | None = None
    max_load_encumbered_cn: int | None = None
    movement_encumbered: str | None = None     # "75' (25')"
    miles_per_day_encumbered: int | None = None
    armor_fits: list[str] = []    # animal-armour ids this animal may wear
    traits: list[str] = []        # the ▶ ability bullets (verbatim)

class Vehicle(ItemBase):
    item_type: Literal["vehicle"]
    vehicle_category: Literal["land_vehicle", "water_vessel"]
    ac: int                       # descending; ascending derived
    hull_points: str              # dice ("1d4") OR range ("60-90")
    cargo_capacity_cn: int        # base storage capacity
    cargo_capacity_extra_cn: int | None = None   # with the doubled animal team
    # Display-only (not enforced):
    required_animals: str | None = None     # "1 draft horse or 2 mules"
    required_crew: str | None = None        # free text from the movement table
    miles_per_day: str | None = None
    movement: str | None = None
    max_mercenaries: int | None = None
    seaworthy: bool | None = None           # None for land vehicles
    requires_captain: bool | None = None
    passengers: str | None = None
    dimensions: str | None = None           # "60'-80' / 10'-15' / 2'-3'"
    traits: list[str] = []

class AnimalArmor(ItemBase):
    item_type: Literal["animal_armor"]
    sets_ac: int                  # descending; replaces natural AC (asc derived)
    fits: list[str] = []          # animal ids it can be worn by
    # weight_cn (from ItemBase) counts against the animal's load
```

> **Saddle bags** are modelled as a normal **`Container`** (`capacity_cn: 300`),
> reusing all container machinery — so they can sit on a horse (container-in-
> animal) and hold gear. **Saddle and bridle** is plain `AdventuringGear`. Only
> barding and dog-armour are `AnimalArmor`.

`_class_allows` (shop.py) returns `True` for any non-`Weapon`/`Armor` item, so
the new variants are never gated by class weapon/armour allowances. The
`shop_categories` content-gate buckets them as `"equipment"` for source toggles.

### New per-instance roster state on `CharacterSpec`

```python
animals:  list[AnimalInstance]  = []
vehicles: list[VehicleInstance] = []
```

```python
class AnimalInstance(BaseModel):
    instance_id: str               # uuid4 hex
    catalog_id: str                # -> Animal
    name: str = ""                 # optional label ("Bessie")
    hp_damage: int = 0             # current hp = max(0, catalog.hp - hp_damage)
    armor_id: str | None = None    # -> AnimalArmor (must be in catalog.armor_fits)
    contents: list[str] = []       # loose gear loaded onto the animal
    magic_note: str = ""           # free-text placeholder until magic items land

class VehicleInstance(BaseModel):
    instance_id: str
    catalog_id: str                # -> Vehicle
    name: str = ""
    hull_max: int                  # resolved from catalog.hull_points at purchase
    hull_damage: int = 0
    contents: list[str] = []       # loose cargo
    extra_animals: bool = False    # land vehicle hauling the doubled team:
                                   # raises the cargo cap to cargo_capacity_extra_cn
    note: str = ""
```

Both default-empty on `CharacterSpec`, so old saves load unchanged (no
migration). Containers placed aboard a vehicle/animal are handled by the
generalised location concept below — not duplicated into `contents`.

---

## Derived combat stats — `aose/engine/monster_stats.py`

New cycle-free module (imports models/loader only) — the single home for "derive
a monster/NH combat stat from HD." Two data tables transcribed from the provided
NPC combat reference:

**`data/monster_attack_matrix.yaml`** — band → `{thac0, attack_bonus}` (Attack
Roll to Hit AC). Bands: `nh`, `up_to_1`, `1+_to_2`, `2+_to_3`, `3+_to_4`,
`4+_to_5`, `5+_to_6`, `6+_to_7`, `7+_to_9`, `9+_to_11`, `11+_to_13`, `13+_to_15`,
`15+_to_17`, `17+_to_19`, `19+_to_21`, `21+`. (Values per the reference, e.g.
`nh: {thac0: 20, attack_bonus: -1}`, `1+_to_2: {thac0: 18, attack_bonus: 1}`.)

**`data/monster_saves.yaml`** — band → `{death, wands, paralysis, breath, spells}`.
Bands: `nh` (14/15/16/17/18), `1-3` (12/13/14/15/16), `4-6` (10/11/12/13/14),
`7-9` (8/9/10/10/12), `10-12` (6/7/8/8/10), `13-15` (4/5/6/5/8), `16-18`
(2/3/4/3/6), `19-21` (2/2/2/2/4), `22+` (2/2/2/2/2).

**API:**
```python
def ascending_ac(descending: int) -> int:            # 19 - descending
def attack_for_hd(hd: str, data) -> AttackStats:      # {thac0, attack_bonus}
def saves_for_hd(save_as_hd: int | str, data) -> dict[str, int]
def hd_to_attack_band(hd: str) -> str                 # parse helper
```

**HD-string → attack band** (`hd_to_attack_band`):
- `"NH"` → `nh`; `"½"`, `"0"`, `"1"` → `up_to_1`.
- A `"N+x"` form (any plus) → band starting at `N`: `"1+2"` → `1+_to_2`,
  `"2+2"` → `2+_to_3`.
- A plain integer `N ≥ 2` → band whose top is `N`: `"2"` → `1+_to_2`,
  `"3"` → `2+_to_3`.

**save-as → save band:** `"NH"` → `nh`; integer `N` → the band whose inclusive
range contains `N` (`1-3`, `4-6`, …).

**Unit tests (worked examples from the reference):**
- `attack_for_hd("2")` → THAC0 18, +1; `("3")` → 17, +2; `("1+2")` → 18, +1;
  `("2+2")` → 17, +2; `("½")` → 19, 0; `("NH")` → 20, −1.
- `saves_for_hd(1)` → 12/13/14/15/16; `saves_for_hd("NH")` → 14/15/16/17/18;
  `saves_for_hd(2)` → 12/13/14/15/16.
- `ascending_ac(7)` → 12; `ascending_ac(9)` → 10.

The `normal_human` class (Phase B) authors its own NH progression row directly;
it does **not** call this module — uniformity of the class engine is preserved.
This module serves animals (and any future monster NPCs).

---

## Storage-location topology

Today loose gear lives in: **on-person** (`inventory`, weighs), **stashed**
(`stashed`, no weight), or inside a **container** (`ContainerInstance`, carried or
stashed). Animals and vehicles add **new top-level locations** — peers of
on-person/stashed, *not carried by a person*.

### Engine: a generalised "location" for stow/take-out

Extend `aose/engine/shop.py` (or a thin sibling) so the move helpers can target an
animal or vehicle instance, mirroring the container helpers:

```python
load_onto_animal(spec, instance_id, item_id, data)      # inventory -> animal.contents
unload_from_animal(spec, instance_id, item_id, data)    # animal.contents -> inventory
load_onto_vehicle(spec, instance_id, item_id, data)     # inventory -> vehicle.contents
unload_from_vehicle(spec, instance_id, item_id, data)
```

Each performs the same shape of operation as `stow`/`take_out`:
- source is always `inventory` (to load a stashed/equipped item, unstash/unequip
  first — same rule as containers);
- a `Container` catalog item **can** be loaded onto an animal/vehicle (so a
  saddle-bag rides a horse) — unlike container-in-container, which stays banned;
- **capacity check** before adding (see below); raises `AnimalOverloaded` /
  `VehicleOverloaded` (subclasses of a shared `LoadError`).

**Container-on-carrier is in scope** (saddle-bags-on-horse must work). When a
`Container` is loaded onto an animal/vehicle, add to `ContainerInstance`:
`location: Literal["person","animal","vehicle"] = "person"` + `location_id: str | None = None`.
The existing carried/stashed `state` still governs weight while the container is
on the person; once its `location` is an animal/vehicle, the container's effective
weight (own + multiplier × contents) counts toward **that carrier's** load, not
the PC's, and the container drops out of the PC's `carried_weight_cn`. Defaults
keep old saves valid. `take_out` from such a container returns items to the
carrier's `contents`, not the PC's `inventory`.

### Capacity

- **Animal:** `max_load_unencumbered_cn` / `max_load_encumbered_cn`. Worn barding
  weight + loaded contents weight are summed. Over `max_load_encumbered_cn` →
  reject the load (overloaded). Between the two thresholds the card shows an
  **"encumbered"** badge (informational; movement penalty shown as reference text,
  not auto-applied). Dogs (no load table) accept no cargo.
- **Vehicle:** the enforced cap is `cargo_capacity_extra_cn` when the instance's
  `extra_animals` toggle is on (and the vehicle has an extra figure), else
  `cargo_capacity_cn`. Over the active cap → reject. The toggle is a simple
  per-instance bool ("Extra Animals", default off) on land vehicles that define
  `cargo_capacity_extra_cn`; **actual draft animals are not tracked or linked** —
  it only switches which capacity figure applies.

### Encumbrance interaction

`aose/engine/encumbrance.py` needs **no change to the PC total**: animal/vehicle
contents live in their own instance lists, never in `inventory`/`containers`, so
they're already excluded from `carried_weight_cn`. The spec only adds the
*separate* per-carrier load computation used by the cards.

---

## Damage / repair (light)

- Animal current hp = `max(0, catalog.hp - hp_damage)`; mirrors the PC's
  `damage_taken` pattern. Card shows current/max with −/+ controls.
- Vehicle hull = `max(0, hull_max - hull_damage)`; −/+ controls.
- Movement-reduction-per-10%, destruction (0 hull → sinks in 1d10), and repair
  rules are rendered as **reference text** on the card, not computed.

`hull_max` is resolved at purchase: a dice `hull_points` (`"1d4"`, `"2d4"`) is
rolled; a range (`"60-90"`) defaults to its maximum. Editable afterward.

---

## Shop wiring

Animals, vehicles, and tack appear automatically in the shop because
`shop_categories` groups by `category`. New categories: `animals`, `vehicles`,
`tack_and_harness`.

Buying must create an **instance**, not append to `inventory`. Add, mirroring
`buy_container`:

```python
buy_animal(spec, item_id, data)    -> deduct gold, append AnimalInstance
buy_vehicle(spec, item_id, data)   -> deduct gold, resolve hull_max, append VehicleInstance
add_free_animal / add_free_vehicle -> GM grant, no gold
```

Tack items (`AnimalArmor`, the saddle-bag `Container`, saddle & bridle gear) buy
through the **existing** paths (`buy` for gear, `buy_container` for saddle bags);
`AnimalArmor` is bought into `inventory` like gear and then **assigned** to an
animal via its armour control (assignment moves it out of `inventory` onto
`AnimalInstance.armor_id`; unassigning returns it).

**Routes** (FastAPI, URL-mutating like the rest):
- `POST /character/{id}/animal/buy?item_id=` · `/animal/add` · `/animal/remove?instance_id=&mode=`
- `POST /character/{id}/animal/{instance_id}/rename` · `/hp` (damage/heal) · `/armor/assign?armor_id=` · `/armor/clear`
- `POST /character/{id}/animal/{instance_id}/load?item_id=` · `/unload?item_id=`
- `POST /character/{id}/vehicle/buy` · `/add` · `/remove` · `/{instance_id}/rename` · `/hull` · `/load` · `/unload`

Removal modes reuse the `drop`/`sell`/`refund` convention (sell = half cost;
refund only when empty, à la `remove_container`).

---

## Detail cards

`aose/engine/detail.py::item_card(i)` gains rendering for `Animal`, `Vehicle`, and
`AnimalArmor` (stat lines + description + traits), so the shop expander and the
roster cards show book-faithful detail. Ascending-AC display uses
`monster_stats.ascending_ac`; THAC0/attack and saves use the lookups, shown when
relevant (e.g. respect `ruleset.ascending_ac` for which AC/attack figure leads).

---

## UI — "Companions & Holdings" section

A new full-width section on `sheet.html` (same structure as the inventory group:
inked bar, internal scroll), gated to render only when the character owns ≥1
animal/vehicle (Phase B adds retainers to the same section). Per the style guide,
read `docs/STYLE-GUIDE.md` first; reuse zine tokens and the overlay model.

- **Animal card:** name/label, species, derived AC (natural or barding), HD, hp
  current/max (−/+), THAC0 or attack bonus (per `ascending_ac` rule), saves,
  attacks, MV, morale, traits. An **armour control** (assign/clear from owned
  `AnimalArmor` that `fits`). A collapsible **contents** sub-list = the storage
  location, with load/unload controls and a load-vs-capacity meter + encumbered
  badge. `magic_note` free-text field.
- **Vehicle card:** name/label, type, derived AC, hull current/max (−/+), cargo
  used/capacity meter, required animals/crew/passengers/seaworthiness (reference),
  dimensions, traits, and the **contents** sub-list (load/unload).
- Acquisition is via the shop (new categories). The section itself holds
  management only (rename, damage, load/unload, armour, remove) — destructive
  actions in the management drawer, not in per-item modals (matches the existing
  `show_remove` boundary).
- Print sheet (`sheet_print.html`) gets a compact companions block.

The wizard's equipment step stays Carried + Shop only; animals/vehicles are a
play-state concern surfaced on the live sheet (consistent with magic items /
treasure being sheet-only).

---

## Tests

- **Models:** Animal/Vehicle/AnimalArmor parse from YAML; `CharacterSpec` round-
  trips with `animals`/`vehicles`; old save without the fields still loads.
- **monster_stats:** the worked-example table above (attack bands, save bands, AC
  conversion, HD-string parse incl. `"½"`, `"1+2"`, `"2+2"`).
- **Loader:** every seeded animal/vehicle/tack entry loads; `armor_fits`/`fits`
  cross-references resolve; `monster_attack_matrix`/`monster_saves` tables load
  and cover every band a seeded animal needs.
- **Shop:** `buy_animal`/`buy_vehicle` deduct gold and create instances;
  insufficient-gold raises; `hull_max` resolves from dice/range; sell/refund/drop.
- **Topology:** load/unload moves between `inventory` and an animal/vehicle;
  capacity rejects overload; barding weight counts toward animal load; a saddle-
  bag container can ride a horse (if container-on-carrier is in MVP); PC
  `carried_weight_cn` is unchanged by loading cargo onto an animal.
- **Damage:** hp/hull clamp at 0; heal caps at max.
- **Regression:** `/settings` "no pending badge" test still passes (no new
  `RuleSet` flag is introduced — this feature is not rule-gated).

---

## Data to import (authoritative — from the provided core reference)

The provided `advanced-fantasy_vehicles-and-animals.md` is the transcription
source. Import **every** row of its tables; descriptions and ▶ bullets are
carried verbatim. Field mapping is defined above. Spelled out here for the
animals and land vehicles; water vessels follow the same mapping across the
Seaworthy/Unseaworthy + Vessel Combat Stats + Vessel Movement tables.

### Animals (`data/equipment/animals.yaml`, category `animals`)

| id | cost | ac | hd | save_as | hp | attacks | mv | ml | xp | load unenc/enc (cn) | armor_fits |
|---|--|--|--|--|--|--|--|--|--|--|--|
| camel | 100 | 7 | 2 | 1 | 9 | bite 1, hoof 1d4 | 150'(50') | 7 | 20 | 3000/6000 | — |
| draft_horse | 40 | 7 | 3 | 2 | 13 | — | 90'(30') | 6 | 35 | 4500/9000 | horse_barding |
| riding_horse | 75 | 7 | 2 | 1 | 9 | 2×hoof 1d4 | 240'(80') | 7 | 20 | 3000/6000 | horse_barding |
| war_horse | 250 | 7 | 3 | 2 | 13 | 2×hoof 1d6 | 120'(40') | 9 | 35 | 4000/8000 | horse_barding |
| mule | 30 | 7 | 2 | NH | 9 | kick 1d4 / bite 1d3 | 120'(40') | 8 | 20 | 2000/4000 | — |
| hunting_dog | 17 | 7 | 1+2 | 1 | 6 | bite 1d6 | 180'(60') | 10 | 15 | — | — |
| war_dog | 25 | 8 | 2+2 | 1 | 11 | bite 2d4 | 120'(40') | 11 | 25 | — | dog_armour |

Encumbered movement / miles-per-day per the Animals-of-Burden table; descriptions
and traits per each entry (camel: ill-tempered, water, desert travel; draft horse:
non-combatants flee; war horse: charge, melee; mule: tenacious, defensive; hunting
dog: tracking, command; war dog: armour, command).

### Land vehicles (`data/equipment/vehicles.yaml`, category `vehicles`)

| id | cost | ac | hull | cargo / extra (cn) | mv | mi/day | required_animals |
|---|--|--|--|--|--|--|--|
| cart | 100 | 9 | 1d4 | 4000 / 8000 | 60'(20') | 12 | 1 draft horse or 2 mules |
| wagon | 200 | 9 | 2d4 | 15000 / 25000 | 60'(20') | 12 | 2 draft horses or 4 mules |

### Water vessels (`vehicles.yaml`, `vehicle_category: water_vessel`)

Import all from the reference, mapping: `cost_gp`, `cargo_capacity_cn` (Cargo
Capacity), `ac`, `hull_points` (Hull Points range), `max_mercenaries`,
`requires_captain`, `required_crew`/`movement`/`miles_per_day` (Vessel Movement
table — rowing and/or sailing), `seaworthy` (true for the Seaworthy table, false
for Unseaworthy), `dimensions` (length/beam/draft), `passengers`. Entries:
lifeboat, longship, sailing ship (large/small), troop transport (large/small),
warship (large/small), boat (river/sailing), canoe, galley (large/small/war),
raft (makeshift/professional). Ship weaponry, rams, and catapults are **excluded**
(out of scope).

### Tack & harness (`data/equipment/tack.yaml`, category `tack_and_harness`)

| id | type | cost | data |
|---|---|--|--|
| dog_armour | AnimalArmor | 25 | sets_ac 6, fits [war_dog] |
| horse_barding | AnimalArmor | 150 | sets_ac 5, weight 600, fits [draft_horse, riding_horse, war_horse] |
| saddle_and_bridle | AdventuringGear | 25 | — |
| saddle_bags | Container | 5 | capacity_cn 300 |

---

## Resolved decisions

1. **Container-on-carrier is in scope** — saddle-bags-on-horse works via the
   `ContainerInstance.location`/`location_id` extension (see Topology).
2. **Source** = Old School Essentials Classic Fantasy → default
   `ose_classic_fantasy`; no `source:` line in the YAML, never content-gated.
3. **"Extra Animals"** is a per-instance toggle on land vehicles that switches the
   enforced cap from `cargo_capacity_cn` to `cargo_capacity_extra_cn`; draft
   animals themselves are **not** tracked or linked.
