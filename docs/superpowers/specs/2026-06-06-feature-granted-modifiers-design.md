# Feature-granted modifiers (data-driven class/race bonuses) — design

**Date:** 2026-06-06

## Goal

Let **classes and races grant mechanical bonuses through data**, feeding the
*same* `Modifier` aggregation that magic items already feed — no class or race
id ever hardcoded into an engine module. This is the "Conditional
feature-modifier framework" that the mental-powers/Kineticist spec explicitly
deferred.

A manual audit of current and near-future content surfaced three mechanically
distinct shapes that must all flow through one path:

| Source | Feature | Shape |
|---|---|---|
| Barbarian (class) | Agile Fighting | AC bonus, **additive**, scales by **level**, only when **unarmored** |
| Halfling (class) & Halfling (race) | Missile attack bonus | +1 to hit, only with **missile/ranged** weapons |
| Dwarf / Duergar / Gnome / Halfling (race) | Resilience / Magic Resistance | save bonus to specific categories, scales by **CON** |
| Kineticist (class) | Armour Class | literal AC by **level** (migrated off the bespoke column onto this framework) |

More classes and races — and more conditions — will arrive with future data
sources. The framework must be open-ended.

## Guiding principle — nothing keys on a class or race id

Engine code reads typed data and the modifier `target`/`condition` strings.
If any derivation references `"barbarian"`, `"halfling"`, `"kineticist"`, etc.
literally, the design is wrong. This mirrors the magic-item modifier path and
the generic AC-column / mental-caster patterns already established.

## Architecture at a glance

```
data (ClassFeature/RaceFeature .granted_modifiers: list[GrantedModifier])
   │  declares: target, op, condition, value-or-scale
   ▼
engine/features.py
   feature_modifiers(spec, data) -> list[Modifier]   # resolves scale → concrete value, carries condition + source
   all_modifiers(spec, data)    = active_modifiers (magic) + feature_modifiers (class/race)
   ▼
engine/{armor_class, saves, attacks}  consume one merged list, honouring `condition`
```

Import DAG stays acyclic: `models/loader → magic → features → {armor_class,
saves, attacks}`. `features` imports `effective_abilities` from `magic`;
`magic` never imports `features`.

## 1. Data model

### 1.1 `GrantedModifier` (new — `aose/models/modifier.py`)

The *declaration* a feature carries. Same `target`/`op` grammar as `Modifier`,
plus a condition and a value that is either flat or table-scaled.

```python
class Scaling(BaseModel):
    model_config = ConfigDict(extra="forbid")
    by: str                      # "level" | "ability:STR".."ability:CHA"
    table: dict[int, int]        # threshold lookup (see §1.3)

class GrantedModifier(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str                  # ac, save:spells, attack, damage, ability:STR, …
    op: Literal["add", "set", "set_min", "set_max"]
    condition: str | None = None # open-ended; None = unconditional. e.g. "unarmored", "ranged"
    value: int | None = None     # flat …
    scale: Scaling | None = None # … XOR table-scaled (exactly one of value/scale)

    @model_validator(mode="after")
    def _exactly_one_value_source(self): ...  # value XOR scale, else ValueError
```

### 1.2 `Modifier` extended (`aose/models/modifier.py`)

Two new optional fields, both defaulting so existing magic-item data and saved
characters load unchanged (no migration — the app is not deployed):

```python
condition: str | None = None   # None = unconditional (current behaviour)
source: str = ""               # human label for the future hover ("Agile Fighting")
```

`condition` is **open-ended free text**. The engine recognises a small set in
each derivation context (§4); any other condition is *situational* — carried
for display but **never folded into a headline number**.

### 1.3 Threshold-table semantics

`Scaling.table` is a **banded** lookup: the value is the entry for the greatest
key ≤ the input (exactly the fallback `saves._level_data` already uses for
level progression). Example resilience table `{3: 1, 7: 2, 11: 3, 15: 4}` →
CON 9 yields +2. Below the lowest key yields 0 (no bonus). This faithfully
encodes AOSE's banded ability/level tables; a flat bonus uses `value` instead.

- `by: "level"` reads **that class's** `entry.level`. Valid only on **class**
  features (a race has no class level); a `by: "level"` scale on a race feature
  is a data error caught by a loader-time / test assertion.
- `by: "ability:CON"` reads the **effective** (magic-adjusted) score via
  `effective_abilities`. Valid on class or race features. Feature-granted
  ability changes do **not** recursively feed ability-scaled features (we read
  magic-effective, not feature-effective, abilities) — documented, negligible
  edge case.

## 2. Where grants live

`granted_modifiers: list[GrantedModifier] = Field(default_factory=list)` on
both **`ClassFeature`** and **`RaceFeature`**.

Attaching to the *feature* (not the class/race root):
- Class features already gate on `gained_at_level`, so a level-gated bonus is
  free — the resolver simply skips features the character hasn't reached.
- Each resolved `Modifier.source` is the feature's `name`, seating the future
  on-hover "where did this come from" view at no extra cost.

The existing free-form `mechanical: dict` stays for descriptive-only features
(nothing reads it; out of scope to change).

## 3. Engine resolver + merge (`aose/engine/features.py`, new, cycle-free)

```python
def resolve_value(g: GrantedModifier, *, level: int, eff: dict[Ability,int]) -> int
    # flat → g.value; scaled → banded lookup on level or eff[ability]

def feature_modifiers(spec, data) -> list[Modifier]
    # class features: for each ClassEntry, each feature with gained_at_level ≤ entry.level
    #                 → resolve with level=entry.level
    # race features:  every feature (races have no per-level gating) → resolve
    # emits Modifier(target, op, value=resolved, condition=g.condition, source=feature.name)

def all_modifiers(spec, data) -> list[Modifier]
    return active_modifiers(spec, data) + feature_modifiers(spec, data)
```

`feature_modifiers` reads `effective_abilities(spec, data)` once. Consumers
switch from `active_modifiers` to **`all_modifiers`**.

## 4. Condition handling at consumption sites

The rule everywhere: **None (unconditional) always applies; a recognised
condition applies when its context matches; an unrecognised condition is
ignored for the headline number** (safe default — never inflate an
always-displayed value with a situational bonus).

Recognised conditions per context (the only ones wired in V1):

| Derivation | Recognised conditions | Behaviour |
|---|---|---|
| `armor_class.py` | `unarmored` | `ac` mods conditioned `unarmored` are dropped when worn armour is equipped; applied otherwise. Reflected in **both** AC and the unarmoured display. → Barbarian Agile Fighting |
| `attacks.py` | `ranged`, `melee` | `attack`/`damage` mods filter per weapon profile: unconditional always; `ranged` only on ranged weapons; `melee` only on melee. (Global-sum logic moves into the per-profile path.) → Halfling missile +1 |
| `saves.py` | — (none) | ranged/melee/unarmored are irrelevant to saves; all `save:*` mods apply as today. Situational save conditions (future) are ignored for the number. → resilience |

V1 guarantee (your stated priority): **the always-displayed AC and AC-unarmored
values fold in exactly `unarmored` + unconditional `ac` mods and nothing else.**
New conditions are added later by teaching the relevant derivation to recognise
the string; until then they are inert-but-carried, never wrong.

The future on-hover "all conditional mods" view is **out of scope** here, but
its data is fully seated: every resolved `Modifier` carries `condition` (when)
and `source` (what), so the hover is a pure view addition with no resolver
rework.

## 5. Kineticist AC column retirement (the one structural change)

Decided: unify on the modifier path rather than keep a second AC mechanism.

1. **Remove** `ClassLevelData.armor_class` and the bespoke best-AC-across-classes
   block in `armor_class.py` (lines folding the column into `base`).
2. **Re-express** Kineticist AC as a `GrantedModifier` on its Armour Class
   feature: `target: ac, op: set, scale: {by: level, table: {1:9, 3:7, 5:5,
   7:3, 9:1, 11:-1, 13:-3, …}}` (full per-level table transcribed from the
   class table; banded lookup reproduces every level).
3. **Restructure `armor_class.py`** so `ac`/`set` from **any** source (feature
   or magic) is evaluated **outside** the `use_armor` gate, min-wins (best
   descending). This is what makes a class-granted literal AC show in the
   unarmoured display and still win against worn armour.

**Accepted consequence (more-correct, per your call):** Bracers of Armour
(`ac set 8−1d4`, today *inside* the gate) will now also reflect in the
unarmoured display. This is the intended, more-consistent behaviour — flagged
here so it is a deliberate change, not a surprise.

A regression test pins Kineticist AC at every level to the pre-migration values.

## 6. Data deliverables (the audit, encoded)

Each verified against the source PDF before encoding (project convention —
`import/pdfs` via PyMuPDF; banded tables and exact save categories confirmed):

- **Barbarian** Agile Fighting → `ac add, condition: unarmored, scale: by
  level`.
- **Halfling class** & **Halfling race** missile bonus → `attack add 1,
  condition: ranged`.
- **Dwarf / Duergar / Gnome / Halfling** resilience → one or more `save:<cat>
  add, scale: by ability:CON` per the book's affected categories and CON bands.
- **Kineticist** Armour Class → migrated per §5.

All audited files already exist in `data/` (classes: `barbarian`, `halfling`,
`kineticist`; races: `dwarf`, `duergar`, `gnome`, `halfling`), so every
deliverable is concrete. Creating *new* classes/races is not part of this spec.

**Race-as-class wrinkle (verify, don't double-apply):** dwarf, gnome, halfling,
duergar, drow exist as *both* a `Race` and a classic `race_locked` `CharClass`.
A racial bonus (e.g. resilience) must apply **once** for a given character, not
twice. The bonus lives on the **race feature**; the implementer confirms how
classic race-as-class characters carry their race (a `Race` is still assigned
under `race_locked`, so the race feature alone covers both modes) and adds the
grant to the race-locked class feature **only if** such characters would
otherwise miss it. A test asserts no double-application.

## 7. Testing

- **Resolver unit tests** — flat value; level banded lookup (boundary +
  between-band); CON banded lookup; below-lowest-band → 0; `value` XOR `scale`
  validation; `by: level` on a race feature rejected.
- **Condition filtering** — `unarmored` AC present unarmoured / absent when
  armoured / present in unarmoured display while armoured; `ranged` attack bonus
  on a bow but not a sword; an unrecognised condition never touches the AC
  headline.
- **Integration** — each audited entry produces the right AC / to-hit / save on
  a built sheet; resilience stacks additively on top of the class save number
  (AOSE: race save bonus adds to the class throw).
- **Kineticist AC regression** — exact per-level parity with the retired column.
- **Bracers display** — its `ac set` now appears in the unarmoured value
  (locks in the §5 consequence intentionally).

## 8. Out of scope (explicit non-goals)

- **Drow innate spellcasting** (auto-known spells with their own daily-use
  limits) — a separate spec; reuses the spell/mental-powers machinery, not the
  `Modifier` path.
- **On-hover conditional-modifier UI** — data is seated (`condition` + `source`)
  but the view is future work.
- **New condition vocabulary beyond `unarmored` / `ranged` / `melee`** — the
  model accepts any string; only these three are *evaluated* in V1. "vs <type>",
  "shield-only", etc. are added when their data and a consuming derivation
  arrive.
- **Creating class/race data that does not yet exist** (e.g. a Barbarian class
  file, if absent) — the framework and existing-content deliverables stand
  alone.
- **Touching the free-form `mechanical: dict`** on features — left as-is.
