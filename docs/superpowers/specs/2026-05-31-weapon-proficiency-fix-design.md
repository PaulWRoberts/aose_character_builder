# Weapon Proficiency fix + book-accurate weapon data — design

- **Date:** 2026-05-31
- **Status:** Draft (awaiting user review)
- **Scope:** Fix the Weapon Proficiency optional rule, replace invented weapon
  metadata with book-accurate data + quality definitions, and enforce class
  weapon/armour/shield restrictions at equip time.
- **Explicitly out of scope:** Compressing class data (deriving THAC0 / sharing
  save tables). The `combat_progression` category is *derived from the existing
  THAC0 table*, leaving class YAML untouched. A later spec may revisit
  compression.

---

## 1. Motivation — what's broken

A magic-user run through the wizard with Weapon Proficiency enabled exposed
several bugs:

1. **Slot count is wrong.** `starting_proficiency_count` falls back to a hard
   `_DEFAULT_STARTING_SLOTS = 2` for every class without a `proficiency:` block
   (no class file sets one), so a non-martial magic-user got **2** slots instead
   of **1**.
2. **Choices aren't filtered by class.** The picker renders *every*
   `proficiency_group` in the dataset, ignoring `weapons_allowed`, so the
   magic-user could pick weapons it can't wield.
3. **`proficiency_group` is invented.** Groups like `bludgeon`/`axe`/`sword` are
   not an AOSE concept. Proficiency in AOSE is **per individual weapon** (Club,
   Crossbow, …). Weapons are described only by their **name** and **qualities**.
4. **Penalty is a flat −2.** AOSE applies **−2 / −3 / −5** by martial category.
5. **Weapon/armour data has errors and gaps** vs the book (wrong weights, a
   `light_crossbow` that should be `Crossbow`, missing Javelin/Lance/Staff/
   Silver dagger), and no machine-readable quality definitions.
6. **No equip-time enforcement.** `equip()` takes no class context, so a
   character can equip weapons/armour their class forbids.

Additionally, class `weapons_allowed` / `armor_allowed` lists are stored as
**human-readable prose** (`war hammer`, `leather`, `any appropriate to size`),
not item ids — correct for a human reader but unusable by the engine as-is.

---

## 2. The AOSE rule (authoritative)

**Categories** (by the rate THAC0 & saves improve):

| Category | Improves every | First THAC0 drop at | 1st-level proficiencies | Non-proficient penalty |
|---|---|---|---|---|
| Martial | 3 levels | L4 | 4 | −2 |
| Semi-martial | 4 levels | L5 | 3 | −3 |
| Non-martial | 5 levels | L6 | 1 | −5 |

- **Chosen from** the weapons usable by the character's class (and race, where
  modelled — see §7).
- **Gained over time:** one additional proficiency every time THAC0 & saves
  improve (i.e. at each category step).
- **Specialisation (martial only):** when picking proficiencies, a martial
  character may spend **two** slots on a single weapon to **specialise**,
  gaining **+1 to attack and +1 to damage** with it.

---

## 3. Part 1 — Book-accurate weapon & armour data + qualities

### 3.1 Weapon model change
- **Remove** `Weapon.proficiency_group`.
- **Keep** the existing `qualities: list[str]` field and **populate** it.
- Quality strings use snake_case ids that key into the new qualities catalog:
  `blunt, brace, charge, melee, missile, reload, slow, splash_weapon, two_handed`.

### 3.2 `data/equipment/weapons.yaml` rewrite
Rewrite to match the book. `damage.default` stays `1d6` (standard rule);
`damage.variable` is the book's per-weapon die. `melee`/`ranged`/`hands`/ranges
follow the qualities. Id renames: `long_sword`→`sword`, `light_crossbow`→
`crossbow`. New ids: `javelin`, `lance`, `staff`, `silver_dagger`.

| id | name | gp | cn | variable dmg | hands | melee | ranged (S/M/L) | qualities |
|---|---|---:|---:|---|---:|:--:|---|---|
| battle_axe | Battle Axe | 7 | 50 | 1d8 | 2 | ✓ | — | melee, slow, two_handed |
| club | Club | 3 | 50 | 1d4 | 1 | ✓ | — | blunt, melee |
| crossbow | Crossbow | 30 | 50 | 1d6 | 2 | — | 80/160/240 | missile, reload, slow, two_handed |
| dagger | Dagger | 3 | 10 | 1d4 | 1 | ✓ | 10/20/30 | melee, missile |
| hand_axe | Hand Axe | 4 | 30 | 1d6 | 1 | ✓ | 10/20/30 | melee, missile |
| javelin | Javelin | 1 | 20 | 1d4 | 1 | — | 30/60/90 | missile |
| lance | Lance | 5 | 120 | 1d6 | 1 | ✓ | — | charge, melee |
| long_bow | Long Bow | 40 | 30 | 1d6 | 2 | — | 70/140/210 | missile, two_handed |
| mace | Mace | 5 | 30 | 1d6 | 1 | ✓ | — | blunt, melee |
| polearm | Pole-arm | 7 | 150 | 1d10 | 2 | ✓ | — | brace, melee, slow, two_handed |
| short_bow | Short Bow | 25 | 30 | 1d6 | 2 | — | 50/100/150 | missile, two_handed |
| short_sword | Short Sword | 7 | 30 | 1d6 | 1 | ✓ | — | melee |
| silver_dagger | Silver Dagger | 30 | 10 | 1d4 | 1 | ✓ | 10/20/30 | melee, missile |
| sling | Sling | 2 | 20 | 1d4 | 1 | — | 40/80/160 | blunt, missile |
| spear | Spear | 4 | 30 | 1d6 | 1 | ✓ | 20/40/60 | brace, melee, missile |
| staff | Staff | 2 | 40 | 1d4 | 2 | ✓ | — | blunt, melee, slow, two_handed |
| sword | Sword | 10 | 60 | 1d8 | 1 | ✓ | — | melee |
| two_handed_sword | Two-Handed Sword | 15 | 150 | 1d10 | 2 | ✓ | — | melee, slow, two_handed |
| war_hammer | War Hammer | 5 | 30 | 1d6 | 1 | ✓ | — | blunt, melee |

> Note: id renames may invalidate `sword`/`crossbow` references in *saved*
> characters' inventories. Acceptable for a local single-user dev app; called out
> in §7.

### 3.3 New `data/equipment/weapon_qualities.yaml`
A new catalog: list of `{id, name, description}` for the nine qualities, loaded by
`GameData` into a `qualities: dict[str, WeaponQuality]` map. Definitions verbatim
from the book (Blunt → "May be used by clerics."; Brace, Charge, Melee, Missile,
Reload, Slow, Splash weapon, Two-handed). A small `WeaponQuality` pydantic model
(`aose/models/weapon_quality.py`, `id`/`name`/`description`). Loader globs it like
other equipment files but into its own dict (it is not an `Item`).

### 3.4 Armour
Armour values already match the book (Leather 7/20/200, Chain 5/40/400, Plate
3/60/500, Shield 10/100). Sanity pass only; no change expected.

### 3.5 Sheet rendering
Weapon rows show their quality chips; a small **Weapon Qualities** reference
(collapsible) lists the definitions for qualities present on the character's
weapons. (Reuses the existing collapsible pattern from magic items.)

---

## 4. Part 2 — Weapon Proficiency rule engine

### 4.1 Category derivation (single source of truth)
New in `aose/engine/proficiency.py`:

```python
def combat_category(cls: CharClass) -> Literal["martial","semi_martial","non_martial"]:
    # period = (first level whose thac0 < level-1 thac0) - 1  → 3/4/5
    # 3→martial, 4→semi_martial, 5→non_martial
```

Derived from the existing per-class THAC0 progression (verified: every class's
THAC0 is the identical `19→17→14→12→10` sequence, differing only in rate).
Fallback: if no THAC0 drop exists in the table, default to `non_martial` (safest:
fewest slots, but never crashes).

Helpers:
- `base_slot_count(category) -> int` → 4 / 3 / 1.
- `improvements_through_level(cls, level) -> int` → count of THAC0 drops at
  levels ≤ `level`.
- `proficiency_slots(cls, level) -> int` → `base + improvements_through_level`.
- `nonproficiency_penalty(category) -> int` → −2 / −3 / −5.

### 4.2 Slot totals (full leveling)
Total slots at the character's current level = base + improvements so far. At
**creation** the wizard requires the full L1 count to be spent (standard AOSE:
note your proficiencies at character creation). **Slots unlocked by later
levels** may be left unspent and filled on the sheet whenever the player likes
(`spent ≤ total`), not force-filled.

**Multi-class ruling** (book is silent): penalty uses the **most martial**
category among the character's classes (smallest penalty); total slots =
`max` over classes of `proficiency_slots(cls, that class's level)`.
Specialisation offered if **any** class is martial.

### 4.3 Proficiency & specialisation accounting
Per-weapon proficiency. Specialisation is an option taken **while choosing**, not
a separate rule.

- `is_proficient(weapon_id, spec) -> bool` → `weapon_id in spec.weapon_proficiencies`.
- `is_specialised(weapon_id, spec) -> bool` → `weapon_id in spec.weapon_specialisations`.
- Slot cost: each proficiency = 1 slot; each specialisation = 1 **additional**
  slot on top of the proficiency (so a specialised weapon costs 2 total).
  `spent = len(weapon_proficiencies) + len(weapon_specialisations)`.
- Invariant: every id in `weapon_specialisations` is also in
  `weapon_proficiencies`; specialisation only legal when category is martial.

### 4.4 Attack calculator (`aose/engine/attacks.py`)
Replace the `is_proficient_with(group)` call:
- `proficient = is_proficient(weapon.id, spec)` when the rule is on (else True).
- `prof_pen = nonproficiency_penalty(category)` when not proficient (was −2).
  For multi-class, the most-martial category's penalty.
- If `is_specialised(weapon.id, spec)`: add **+1** to-hit and **+1** damage.
  Specialisation and the non-proficiency penalty are mutually exclusive (a
  specialised weapon is by definition proficient).
- `AttackProfile` gains a `specialised: bool` flag for rendering.

---

## 5. Part 3 — Equip-time class enforcement

### 5.1 Allowance resolver
New in `aose/engine/proficiency.py` (or a small `allowances.py`):

```python
def allowed_weapon_ids(spec, data) -> set[str] | "all"
def allowed_armor_ids(spec, data) -> set[str] | "all"
def shields_allowed(spec, data) -> bool
```

Rules:
- `"all"` on any of the character's classes → that category is unrestricted.
- A **list** entry is resolved to an item id by normalising (lowercase, strip,
  spaces→`_`) and matching against item **ids and names** (e.g. `war hammer`→
  `war_hammer`, `leather`→`leather_armor`).
- An entry that resolves to **nothing** (freeform, e.g. `any appropriate to
  size`) makes that class **unrestricted** for that category (fail-open) — we
  never wrongly block a legal item. Logged for visibility.
- Multi-class: **union** of allowances (unrestricted wins).

The proficiency picker (§6) and `equip()` both consume this.

### 5.2 `equip()` change
`equip(...)` gains the character's allowances (passed in, keeping the function
pure). On attempting to equip:
- Weapon not in `allowed_weapon_ids` → `ValueError("<Class> cannot use <weapon>")`.
- Armour not in `allowed_armor_ids` → ValueError.
- Shield while `shields_allowed` is False → ValueError.

**Buying/owning is unaffected** — only equipping is gated. Callers (sheet +
wizard equip routes) surface the error as they already do for other equip
failures.

---

## 6. Wizard + sheet UI

### 6.1 Proficiency model & persistence
On `CharacterSpec`:
- **Remove** `chosen_proficiencies: list[str]` (was group ids).
- **Add** `weapon_proficiencies: list[str]` and `weapon_specialisations:
  list[str]`.
- `@model_validator(mode="before")` drops a legacy `chosen_proficiencies` key
  (same pattern as `chosen_spells` / global-`xp` migrations) so old saves load.

Draft storage: the `proficiencies` draft key becomes
`{"weapons": [...], "specialisations": [...]}`. The clear/migration hooks in
`wizard.py` that reference `"proficiencies"` keep working (key name unchanged).

### 6.2 Picker (`wizard/proficiencies.html` + routes)
- Compute `required = proficiency_slots(...)` and `category`.
- List **individual weapons** filtered to `allowed_weapon_ids(spec)` (`"all"`→
  every weapon; magic-user → dagger + staff, per its data-driven list).
- Martial classes: each weapon row offers a **Specialise** toggle (costs 2).
- Live counter shows slots spent / total; server validates
  `spent == required` at L1 (and `spent ≤ total` thereafter), specialisation
  only for martial, and every id ∈ `allowed_weapon_ids`.

### 6.3 Sheet (`aose/sheet/view.py`)
Replace the group-based `_proficiency_display` with a per-weapon
`proficiencies_view`:
- Category + current non-proficiency penalty.
- Proficient weapons (specialised ones flagged with their +1/+1).
- Attack rows already exist; non-proficient rows show the category penalty,
  specialised rows show +1/+1 and the `specialised` flag.
- The Weapon Qualities reference (§3.5).
`ProficiencyDisplay`/`WeaponDisplay`/`weapon_proficiency_active` are reworked
accordingly; `sheet.html`, `sheet_print.html`, `wizard/review.html` updated.

---

## 7. Edge cases, rulings & non-goals

- **Race-based weapon limits:** `Race` has no weapon-restriction field and class
  data is authoritative, so the book's "take race into account" clause has no
  data to act on. **Non-goal**; resolver hook left for a future race field.
- **Freeform allowances** (`any appropriate to size`, halfling-as-class): treated
  as unrestricted (fail-open). Halfling-as-class only appears in classic mode
  (`separate_race_class` off).
- **Magic-user + staff:** picker shows exactly `weapons_allowed` (dagger +
  staff). The "staff optional rule" stays an informational comment; no new
  RuleSet flag.
- **Id renames** (`long_sword`→`sword`, `light_crossbow`→`crossbow`) can orphan
  ids in *saved* inventories. Acceptable for a local dev app; not migrated.
- **Legacy `chosen_proficiencies`** is dropped on load (group ids are
  meaningless under per-weapon proficiency); affected characters re-pick.
- **`ProficiencyConfig`** model + `CharClass.proficiency` field +
  `_DEFAULT_STARTING_SLOTS` are removed (no class file uses them).

---

## 8. Testing

Engine:
- `combat_category` → martial/semi/non for fighter/cleric/magic-user; boundary
  (first-drop L4/L5/L6).
- `proficiency_slots`: martial L1=4, L7=6 (two steps), L13=8; semi L1=3;
  non-martial L1=1, L6=2.
- `nonproficiency_penalty` → −2/−3/−5; applied in `attack_profiles`.
- Specialisation: +1/+1 applied, martial-only, 2-slot cost; mutually exclusive
  with the penalty.
- Multi-class: most-martial penalty + max slots.
- Resolver: `war hammer`→`war_hammer`, `leather`→`leather_armor`, freeform→
  unrestricted, `"all"`→unrestricted, multi-class union.
- `equip()` rejects disallowed weapon/armour/shield; allows legal ones; buying
  still unrestricted.

Data:
- `weapon_qualities.yaml` loads; every weapon's `qualities` reference a known id.
- Weapons match the §3.2 table (costs/weights/damage/qualities); new ids present.

Web/migration:
- Legacy-save migration drops `chosen_proficiencies` and loads.
- Picker filtered to `weapons_allowed`; exact-count validation; specialisation
  gating.

Full suite (`.venv\Scripts\python.exe -m pytest tests/ -q`) green; existing
proficiency/attack/sheet tests updated to the new model.

---

## 9. File touch-list (summary)

- `aose/models/item.py` — drop `Weapon.proficiency_group`.
- `aose/models/weapon_quality.py` — **new** `WeaponQuality`.
- `aose/models/character.py` — swap `chosen_proficiencies` →
  `weapon_proficiencies` + `weapon_specialisations` + migration.
- `aose/models/character_class.py` — remove `ProficiencyConfig` + `proficiency`.
- `aose/data/loader.py` — load `weapon_qualities.yaml` into `qualities`.
- `aose/engine/proficiency.py` — rewrite (category, slots, penalty, accounting,
  allowance resolver).
- `aose/engine/attacks.py` — per-weapon proficiency, category penalty,
  specialisation, `specialised` flag.
- `aose/engine/equip.py` — allowance enforcement.
- `aose/web/wizard.py` + `templates/wizard/proficiencies.html` — per-weapon
  picker, slot maths, specialisation.
- `aose/sheet/view.py` + `templates/sheet.html` / `sheet_print.html` /
  `wizard/review.html` — per-weapon proficiency view + qualities reference.
- `data/equipment/weapons.yaml` — rewrite.
- `data/equipment/weapon_qualities.yaml` — **new**.
- `tests/` — update + add per §8.
