# Retainers + Quick Equipment (Companions & Holdings — Phase B) — design

**Date:** 2026-06-17
**Status:** Approved design — ready for implementation plan(s).
**Parent:** [`2026-06-16-companions-and-holdings-design.md`](2026-06-16-companions-and-holdings-design.md)
**Phase A (landed):** [`2026-06-16-animals-and-vehicles-design.md`](2026-06-16-animals-and-vehicles-design.md)
**Slug:** `retainers`

Phase B adds **retainers** — hired classed NPCs (or 0-level normal humans) — to the
"Companions & Holdings" sheet section built in Phase A. A retainer is modelled as
an **embedded `CharacterSpec`**, reusing the existing engine for abilities, HP,
leveling, saves, attacks. It introduces two supporting subsystems the parent
design didn't anticipate, both driven by the user's chosen workflow:

1. **Quick Equipment** — a reusable generator (Carcass Crawler, Gavin Norman) that
   produces a class-appropriate starting kit. Used to equip a new retainer; built
   standalone so the **character wizard can adopt it later** as a fast-equip option.
2. **PC ↔ retainer inventory transfer** — there is **no shop for retainers**.
   You buy on the PC (the one store) and **transfer** items to/from a retainer.

## Decomposition (two implementation plans)

This spec splits into two plans, built in order:

- **Plan B1 — Quick Equipment** (data + engine, standalone & reusable). Produces a
  function that fills a `CharacterSpec`'s inventory/equipped/ammo from a random
  class kit. No wizard wiring yet — just the engine + tests.
- **Plan B2 — Retainers** (consumes B1). The embedded-`CharacterSpec` model,
  generation, loyalty, hiring restrictions, leveling/XP, transfer, and UI.

---

## Plan B1 — Quick Equipment

### Rules (verified against the provided text)

From "Quick Equipment" by Gavin Norman (Carcass Crawler). A character gets:
1. **Basic equipment** (all classes): backpack, tinder box, 1d6 torches,
   waterskin, 1d6 iron rations, 3d6 gp.
2. **Class kit** (Equipment-by-Class table): armour (usually a d6 *Armour* roll),
   weapons (usually two rolls on a weapon table), plus extra items.
3. **Adventuring gear**: roll 1d12 twice on the *Adventuring Gear* table.

### Data — `data/quick_equipment.yaml`

A mapping keyed by **class id** (so no name→id mapping at runtime). Each entry
declares how to roll that class's kit. Shape:

```yaml
fighter:
  armour: armour_d6          # roll the shared d6 Armour table
  weapons: {table: general, rolls: 2}
  extras: []
cleric:
  armour: {fixed_roll: "1d6", table: armour_d6}   # "1d6" armour roll == d6 table
  weapons: {table: cleric, rolls: 2}
  extras: [holy_symbol]
illusionist:
  armour: none
  weapons: {fixed: [dagger]}
  extras: []
knight:
  armour: {table: armour_d6, modifier: 2}   # "1d4+2" → d6 table, +2, clamp 1..6
  weapons: {table: knight, rolls: 2}
  extras: []
```

The *Armour* table is shared (`armour_d6`): 1 leather, 2 leather+shield,
3 chainmail, 4 chainmail+shield, 5 plate mail, 6 plate mail+shield. Some classes
roll a smaller die (1d4) by RAW — modelled as `armour: {table: armour_d6, die: "1d4"}`
(rolls 1-4 of the same table). Mappings to catalog ids:

- Armour: `leather`→`leather_armor`, `chainmail`→`chain_mail`, `plate mail`→`plate_mail`,
  `+shield`→`shield`.
- Weapon tables (entries → catalog ids; "+N ammo" → an `AmmoStack`, see below):
  - **general** (d12): battle_axe, crossbow (+20 crossbow_bolt), hand_axe, mace,
    polearm, short_bow (+20 arrow), short_sword, silver_dagger, sling
    (+20 sling_stone), spear, sword, war_hammer.
  - **acrobat** (d4): polearm, short_bow (+20 arrow), spear, staff.
  - **bard** (d4): crossbow (+20 crossbow_bolt), short_sword, sling (+20 sling_stone), sword.
  - **cleric** (d4): mace, sling (+20 sling_stone), staff, war_hammer.
  - **druid** (d4): club, dagger, sling (+20 sling_stone), staff.
  - **knight** (d4): lance, short_sword, sword, war_hammer.
- Adventuring gear (d12): crowbar; hammer_small +12 iron_spike; holy_water_vial;
  lantern +3 flask_of_oil; mirror_small; pole_10ft; rope_50ft; rope_50ft +
  grappling_hook; sack_large; sack_small; stakes_and_mallet; wolfsbane.
- Extras: `holy_symbol`, `thieves_tools`, and **`sprig_of_mistletoe`** (druid).

**Data gap to fill:** add a `sprig_of_mistletoe` gear item to
`data/equipment/adventuring_gear.yaml` (cost 0, source `ose_classic_fantasy`) —
it is referenced by the druid kit but absent from the catalog. Every other id
above already exists (verified against the catalog).

The explicit `quick_equipment.yaml` map covers the classes the article names
(RAW fidelity for core + Advanced classes — the bespoke cleric/druid/knight/bard/
acrobat sub-tables, the 1d4 / 1d4+2 armour skews, etc.). **Classes not in the map**
(e.g. `normal_human`, CC race-as-classes like mutoid/mycelian/ratling/tiefling,
beast_master, kineticist, acolyte, mage) are handled by a **proficiency heuristic**
— no per-class data needed.

#### Heuristic kit (for classes absent from `quick_equipment.yaml`)

Derive the kit from what the class is *proficient with*, so it stays sensible
without bespoke tables. Basic equipment + 2× adventuring-gear rolls always apply;
then:

- **Armour** — filter the shared `armour_d6` rows to those whose armour id is in
  the class's `armor_allowed` set (`"all"` ⇒ every row), and include the
  `+shield` rows only when `shields_allowed`. Roll uniformly among the surviving
  rows. No armour allowed (e.g. magic-user-like) ⇒ no armour. This generalises the
  d6/d4 distinction (a leather-only class simply has fewer rows).
- **Weapons** — resolve the class's allowed weapon ids via the existing
  `aose/engine/proficiency.py::allowed_weapon_ids(cls, data)` (which already
  expands `weapon_qualities_allowed`, e.g. cleric `blunt`):
  - allowed set covers the general table (or is `"all"`) ⇒ roll the **general d12**
    table twice;
  - a limited set of **>2** ids ⇒ build a **custom uniform table** from those ids
    and roll twice (with replacement);
  - **1–2** allowed ids ⇒ just grant them (no roll — "get this weapon").
  Ammo for any granted launcher (bow/crossbow/sling) is added as an `AmmoStack`
  of 20, same as the explicit tables.
- **Extras** — none (the heuristic can't infer flavour items like a holy symbol;
  those stay table-only).

`normal_human` (no weapon proficiency restriction, no armour by default) thus gets
basic gear + a rolled simple weapon — a reasonable 0-level kit.

### Engine — `aose/engine/quick_equipment.py`

Cycle-free (models/loader/dice only). Public API:

```python
class QuickKit(BaseModel):
    inventory: list[str]              # all items (incl. those to be equipped)
    equipped: dict[str, str]          # armor / main_hand / off_hand
    ammo: list[AmmoStack]             # rolled ammo bundles
    gold: int                         # 3d6 starting gp

def roll_kit(class_id: str, data: GameData,
             rng: random.Random | None = None) -> QuickKit
```

Behaviour:
- Rolls basic gear, the class kit, and 2× adventuring gear; resolves "+N ammo"
  entries into `AmmoStack(instance_id=uuid, base_id=<ammo id>, count=N)` and the
  launcher into `inventory`.
- Builds `equipped`: the rolled armour into `armor`, a shield (if rolled) into
  `off_hand`, and the **first melee weapon** (else first weapon) into `main_hand`,
  honouring the hand-budget (a two-handed weapon leaves `off_hand` empty even if a
  shield was rolled — keep the shield in inventory). Reuse `aose/engine/equip.py`
  helpers so the budget rules match the PC's.
- `gold` = `roll("3d6")` (note: the PC's normal starting gold is 3d6×10; Quick
  Equipment's 3d6 is RAW and intentionally smaller — pocket money, since the kit
  is granted, not bought).
- Quantities: 1d6 torches, 1d6 iron rations as repeated inventory ids; backpack is
  a `Container` catalog id (already so in Phase A data) placed in `inventory`.

The returned `QuickKit` is applied to a target `CharacterSpec` by the caller
(Plan B2 / future wizard), not mutated in place — keeps the function pure and
reusable. A thin `apply_kit(spec, kit)` helper writes the fields.

**Strict-mode / rolling:** `roll_kit` takes an injectable `rng` (deterministic
tests). The retainer generator calls it once at creation; re-rolling is a
non-strict affordance only (see B2). No interactive multi-step rolling.

### B1 tests
- `roll_kit("fighter", data, rng=seeded)` → armour in `equipped["armor"]`, two
  weapons present, a main_hand set, basic gear present, gold in 3..18.
- ammo: a rolled bow/crossbow/sling yields a matching `AmmoStack` of 20.
- two-handed roll (e.g. polearm as main_hand) leaves `off_hand` empty even with a
  rolled shield.
- `roll_kit("magic_user", ...)` → no armour, a dagger in inventory.
- unknown class id → fallback kit (basic + dagger, no armour); no crash.
- every class id present in `quick_equipment.yaml` maps only to real catalog ids
  (data test, mirrors Phase A's cross-reference test).

---

## Plan B2 — Retainers

### Storage: embedded `CharacterSpec`

```python
# new fields on CharacterSpec
retainers: list[Retainer] = []

class Retainer(BaseModel):
    id: str                  # uuid4 hex
    spec: CharacterSpec      # the retainer's own character
    loyalty: int             # current loyalty value (editable)
    role: str = ""           # free-text note ("torchbearer")
```

`CharacterSpec` self-references via `retainers`. Bounded by usage: a retainer's
own `spec.retainers` stays empty (retainers don't hire retainers). `build_sheet`
on a retainer renders an empty Companions section — harmless. Defaults empty → old
saves load (no migration).

### `normal_human` class — `data/classes/normal_human.yaml`

So a 0-level retainer satisfies `classes: min_length=1` and flows through every
engine path uniformly:
- `prime_requisites: []`, `max_level: 1`, `hit_die: "1d4"` (≈2-3 hp, the NH ½-HD
  ~2 hp approximation), permissive `weapons_allowed: all` / `armor_allowed: all`,
  `shields_allowed: true`.
- single `progression` row at level 1: `thac0: 20`, NH saves
  `{death:14, wands:15, paralysis:16, breath:17, spells:18}` (authored directly —
  same NH numbers `monster_stats` holds; keeps the class engine uniform).
- Stored internally as level 1, **UI-labelled "0-level / Normal Human."**
- With `max_level: 1`, `class_advancement` reports `at_max` so it never levels via
  the normal flow; gaining a class is the explicit **promote** action below.
- `source: ose_classic_fantasy`. Excluded from the wizard's selectable class list
  (it is a retainer-only construct) — gate by id in the wizard's class step.

### Generation (baseline-10, meets prerequisites)

`aose/engine/retainers.py::generate_retainer(name, class_ids, level, race_id,
alignment, hiring_spec, data, rng) -> Retainer`:

1. Abilities: all six start at **10**.
2. If split race+class (`hiring_spec.ruleset.separate_race_class` and not a
   race-locked class): apply `apply_racial_modifiers(base, race)` (Advanced).
   Race-as-class: skip racial mods (the class is self-contained — matches PC rules).
3. Raise any class `ability_requirements` to their minimum (after racial mods, so
   the result is always legal). Multi-class: union of requirements.
4. Build `ClassEntry` per class at `level`, with `hp_rolls` = `level` rolls of the
   class hit die (via `roll_hp`), and `xp` = `progression[level].xp_required`
   (so XP is consistent with the level). For `normal_human`, level 1, one 1d4 roll.
5. `spec.ruleset` = a copy of the hiring PC's ruleset snapshot (same campaign).
6. Quick Equipment: `kit = quick_equipment.roll_kit(primary_class_id, data, rng)`
   then `apply_kit(spec, kit)`.
7. Loyalty: `base_loyalty(hiring CHA)` adjusted by the hiring PC's class/race
   loyalty modifiers (below).
8. **Level ceiling:** `level` must be `0..hiring_spec` PC level. `0` ⇒
   `normal_human`; otherwise the retainer's class level ≤ the PC's highest class
   level. Enforced by the caller/route.

Generated abilities/HP/kit are editable afterwards (re-roll in non-strict; manual
tweaks via the existing ability-adjust / HP paths since the retainer is a real
`CharacterSpec`).

### Loyalty

Numeric accessors added to `ability_mods.py` beside the existing display tables
(`_CHA_RETAINERS_MAX`, `_CHA_RETAINERS_LOYALTY` already live there):

```python
def max_retainers(cha: int) -> int        # 3→1 … 18→7  (banded via _band)
def base_loyalty(cha: int) -> int         # 3→4  … 18→10
```

Hiring-PC class/race loyalty modifiers, **data-driven** via a `mechanical` key on
the class/race feature (read at generation time, never the combat pipeline):
`retainer_loyalty_modifier: {value: int, except_same_race: bool}`.
- **Human** (race feature): `{value: +1}` — all retainers +1 loyalty.
- **Half-orc** (race-as-class + race): `{value: -1, except_same_race: true}` —
  retainers −1 unless the retainer is itself a half-orc.

`generate_retainer` sums applicable modifiers onto `base_loyalty`. After creation,
loyalty is a freely editable integer (referee discretion); only the current value
is stored. A new `engine/retainers.py::initial_loyalty(hiring_spec, retainer_race_id, data)`
encapsulates the lookup.

### CHA → max retainers (soft cap)

The Companions section shows `len(retainers) / max_retainers(PC CHA)` and a
**warning** when over; never a hard block (referee discretion).

### Hiring restrictions ("type stems from class")

New optional field on `CharClass`:

```python
class RetainerHiringRule(BaseModel):
    min_level: int                     # PC level at which this tier applies
    allows: list[str] | Literal["any", "none"]   # class ids / "any" / "none"

# on CharClass
retainer_hiring: list[RetainerHiringRule] = []   # empty == unrestricted
```

`engine/retainers.py::allowed_retainer_classes(hiring_spec, data) -> set[str] | "any"`
returns the effective allowance: the highest `min_level` tier ≤ the PC's level
(empty list ⇒ unrestricted = "any"; a `"none"` tier ⇒ no hiring permitted).
Encode the **Assassin** example in `data/classes/assassin.yaml`:

```yaml
retainer_hiring:
  - {min_level: 1, allows: none}
  - {min_level: 4, allows: [assassin]}
  - {min_level: 8, allows: [assassin, thief]}
  - {min_level: 12, allows: any}
```

The add-retainer form filters its class list to the allowance; a **full class-data
pass** to encode every class's rules is a follow-up data task (classes without
`retainer_hiring` are unrestricted).

### XP −50%

`engine/retainers.py::grant_retainer_xp(retainer, data, amount)` halves a positive
award (`amount // 2`) before delegating to `leveling.grant_xp(retainer.spec, data, …)`.
Negative (GM clawback) passes through unhalved. Leveling itself reuses
`roll_pending_hp`/`confirm_level_up` on `retainer.spec` unchanged.

### Promote a normal human

`engine/retainers.py::promote_normal_human(retainer, new_class_id, data, rng)` —
when a 0-level retainer should "choose a class" on gaining XP: replace the
`normal_human` `ClassEntry` with `new_class_id` at level 1 (fresh hit die roll;
keep accrued XP), re-bump abilities to the new class's requirements if needed.

### Inventory transfer (no retainer shop)

`engine/retainers.py`, mirroring Phase A's load/unload but between two
`CharacterSpec` inventories:

```python
transfer_to_retainer(pc_spec, retainer_id, item_id, data)    # pc.inventory → retainer.spec.inventory
transfer_to_pc(pc_spec, retainer_id, item_id, data)          # retainer.spec.inventory → pc.inventory
```

Source is always the holder's loose `inventory` (unequip/unstash first, same rule
as containers/carriers). Equipping **on the retainer** reuses the existing
`equip.py` against `retainer.spec` (a thin route wrapper). The retainer's own
encumbrance/AC/attacks then derive normally via `build_sheet(retainer.spec, data)`.

### UI — retainer cards in "Companions & Holdings"

Extend the Phase A section (do **not** create a new section). `CompanionsBlock`
gains `retainers: list[RetainerCard]`. Each `RetainerCard` carries a compact
stat-block built from `build_sheet(retainer.spec, data)` (name, race/class/level
or "0-level Normal Human", AC, HP current/max, THAC0/attack, saves, key equipped
gear) plus loyalty and role. Controls:
- **Add retainer** form: name, class(es) (filtered by `allowed_retainer_classes`,
  `normal_human` always offered), level (1..PC level, or "0-level"), race (when
  split mode), alignment → calls `generate_retainer`. Warn past the CHA cap.
- Loyalty: editable number (−/+ or set).
- Level/XP: award XP (−50% applied), roll/confirm level-up (reuses leveling
  routes pointed at the retainer), promote-normal-human picker.
- Role: free-text.
- **Transfer**: a control to move a loose PC item to the retainer, and the
  retainer's items back; equip/unequip on the retainer.
- Remove retainer (management drawer, destructive — matches the `show_remove`
  boundary).

The header shows the soft cap `n / max_retainers`.

### Print sheet

`sheet_print.html` companions block (added in Phase A) gains a retainer line each:
name, class/level, AC, HP, THAC0, saves, loyalty, and key gear.

---

## Out of scope (this phase)

- Wages / upkeep (too loose to encode — confirmed).
- Mercenaries & specialists (distinct from retainers).
- Wizard wiring of Quick Equipment (the engine is built reusable; wizard adoption
  is a later, separate piece).
- Full per-retainer shop, magic-item management, spell-source documents (a retainer
  caster's spell prep *does* work via the embedded spec, but no dedicated UI beyond
  what `build_sheet` already renders read-only on the card — revisit if needed).
- Retainer-on-retainer hiring.

## Resolved decisions

1. **Quick Equipment gold:** apply the 3d6 pocket-gold to the retainer (RAW).
2. **Caster retainers' spells:** leave the spellbook empty at generation; the
   player fills it via the card (spell prep already has its own UI on the spec).
3. **Class coverage:** the explicit `quick_equipment.yaml` map holds the RAW kits
   for the classes the article names; every other class is handled by the
   **proficiency heuristic** above (armour from `armor_allowed`/`shields_allowed`;
   weapons from `allowed_weapon_ids` — general d12 if broad, a custom roll if a
   limited set, or granted outright if only 1–2). No bespoke CC kits needed now.

## Engine-DAG / invariants

- `quick_equipment.py` and `retainers.py` stay cycle-free: models/loader/dice +
  existing `equip`, `leveling`, `ability_mods`, `magic` helpers. No engine module
  references a specific class/race id (the Assassin rule and loyalty mods are
  **data**, read generically).
- No migrations; new `CharacterSpec.retainers` and `CharClass.retainer_hiring`
  default empty.
- Reuse `build_sheet`, `grant_xp`, `roll_pending_hp`/`confirm_level_up`,
  `apply_racial_modifiers`, `equip` — do not duplicate them for retainers.
