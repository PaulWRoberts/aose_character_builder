# Mental Powers caster type + Kineticist class — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generic third spellcasting type — "mental powers" — and the Kineticist class (Carcass Crawler Issue 1) that uses it, plus a generic level-based-AC class column, end-to-end through engine, sheet, routes, and wizard.

**Architecture:** Two reusable engine features, keyed on data/`caster_type`, never on the class id `"kineticist"`. (1) A `ClassLevelData.armor_class` column read by the AC engine (best across classes). (2) `caster_type == "mental"` handled by `engine/spells.py`: known = a chosen subset (reusing `ClassEntry.spellbook`), no spell levels, with a daily-use pool of `2 × level` activations tracked by `ClassEntry.powers_used`. The Kineticist is data that exercises both.

**Tech Stack:** Python 3, FastAPI, Pydantic v2, Jinja2, YAML game data, pytest. Run via `.venv\Scripts\python.exe`.

**Spec:** `docs/superpowers/specs/2026-06-06-mental-powers-and-kineticist-design.md`

**Conventions:**
- Run tests: `.venv\Scripts\python.exe -m pytest <path> -q` (the trailing `pytest-current` PermissionError on Windows is a known harmless quirk — ignore it).
- Power source markdown (verify text against this): `C:\Users\paulw\Downloads\carcass-crawler-1_kineticist.md`.
- Commit after every task.

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `data/sources.yaml` | Register the non-core Carcass Crawler source | Modify |
| `aose/models/spell_list.py` | Add `"mental"` to `caster_type` literal | Modify |
| `aose/models/character_class.py` | `ClassLevelData.armor_class`, `.powers_known` | Modify |
| `aose/models/character.py` | `ClassEntry.powers_used`; spellbook docstring | Modify |
| `aose/engine/armor_class.py` | Fold class-granted AC into base | Modify |
| `aose/engine/spells.py` | Mental caster type + power-pool helpers | Modify |
| `data/spell_lists.yaml` | The `kineticist` mental spell list | Modify |
| `data/spells/carcass_crawler_kineticist_powers.yaml` | The 9 mental powers | Create |
| `data/classes/kineticist.yaml` | The class (AC + powers_known columns) | Create |
| `aose/sheet/view.py` | Skip mental in spell views; `mental_powers_view` | Modify |
| `aose/web/routes.py` | `/powers/*` routes; rest resets pool | Modify |
| `aose/web/wizard.py` | Casting predicate + spells step handle mental | Modify |
| `aose/web/templates/sheet.html` | Mental Powers section + drawer | Modify |
| `tests/test_mental_powers.py` | Engine + view + route + wizard coverage | Create |

---

## Task 1: Register the Carcass Crawler source

**Files:**
- Modify: `data/sources.yaml`
- Test: `tests/test_mental_powers.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_mental_powers.py`:

```python
"""Mental Powers caster type + Kineticist class + level-based AC column."""
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def _data():
    from aose.data.loader import GameData
    return GameData.load(DATA_DIR)


def test_carcass_crawler_source_loaded_and_non_core():
    data = _data()
    src = data.sources["carcass_crawler_1"]
    assert src.name == "Carcass Crawler Issue 1"
    assert src.publisher == "Necrotic Gnome"
    assert src.core is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py::test_carcass_crawler_source_loaded_and_non_core -q`
Expected: FAIL with `KeyError: 'carcass_crawler_1'`.

- [ ] **Step 3: Add the source**

Append to `data/sources.yaml`:

```yaml
- id: carcass_crawler_1
  name: Carcass Crawler Issue 1
  publisher: Necrotic Gnome
  core: false
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data/sources.yaml tests/test_mental_powers.py
git commit -m "feat(sources): add non-core Carcass Crawler Issue 1 source"
```

---

## Task 2: Model fields — `mental` caster type, AC & powers_known columns, powers_used

**Files:**
- Modify: `aose/models/spell_list.py:16`
- Modify: `aose/models/character_class.py:8-15` (`ClassLevelData`)
- Modify: `aose/models/character.py:120-137` (`ClassEntry`)
- Test: `tests/test_mental_powers.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mental_powers.py`:

```python
def test_spell_list_accepts_mental_caster_type():
    from aose.models import SpellList
    sl = SpellList(id="x", name="X", caster_type="mental")
    assert sl.caster_type == "mental"


def test_class_level_data_new_columns_default_none():
    from aose.models.character_class import ClassLevelData
    ld = ClassLevelData(xp_required=0, thac0=19, saves={"death": 13})
    assert ld.armor_class is None
    assert ld.powers_known is None
    ld2 = ClassLevelData(xp_required=0, thac0=19, saves={"death": 13},
                         armor_class=5, powers_known=4)
    assert ld2.armor_class == 5
    assert ld2.powers_known == 4


def test_class_entry_powers_used_defaults_zero():
    from aose.models import ClassEntry
    e = ClassEntry(class_id="x", level=1)
    assert e.powers_used == 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -q`
Expected: FAIL (validation error on `caster_type="mental"`; unexpected keyword `armor_class`/`powers_known`/`powers_used`).

- [ ] **Step 3: Add the fields**

In `aose/models/spell_list.py`, change the `caster_type` line:

```python
    caster_type: Literal["arcane", "divine", "mental"]
```

In `aose/models/character_class.py`, `ClassLevelData` — add two optional columns after `spell_slots`:

```python
class ClassLevelData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    xp_required: int
    thac0: int
    saves: dict[str, int]
    # spell_level -> slot count; only set on spellcasting classes
    spell_slots: dict[int, int] | None = None
    # Descending Armour Class granted by the class at this level (e.g. a class
    # whose honed reactions improve AC as it advances). Read generically by the
    # AC engine (best/lowest across classes); None for classes without it.
    armor_class: int | None = None
    # Number of "mental powers" known at this level (the mental caster type's
    # analogue of the magic-user's spell-book size). None for non-mental classes.
    powers_known: int | None = None
```

In `aose/models/character.py`, `ClassEntry` — update the `spellbook` docstring and add `powers_used` after `slots`:

```python
    # Known spells/powers chosen by the character: the arcane spell book, or a
    # mental caster's known mental powers. Empty for divine casters, who know
    # their whole list automatically; see aose/engine/spells.py.
    spellbook: list[str] = Field(default_factory=list)
```

```python
    slots: list[SpellSlot] = Field(default_factory=list)
    # Mental-powers daily-use pool counter: activations spent today. The pool
    # size is 2 x level (computed in spells.py); 0 for non-mental classes.
    powers_used: int = 0
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/models/spell_list.py aose/models/character_class.py aose/models/character.py tests/test_mental_powers.py
git commit -m "feat(models): mental caster type, class AC/powers_known columns, powers_used"
```

---

## Task 3: Kineticist data — spell list, powers, class YAML

**Files:**
- Modify: `data/spell_lists.yaml`
- Create: `data/spells/carcass_crawler_kineticist_powers.yaml`
- Create: `data/classes/kineticist.yaml`
- Test: `tests/test_mental_powers.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mental_powers.py`:

```python
def test_kineticist_spell_list_loaded():
    data = _data()
    sl = data.spell_lists["kineticist"]
    assert sl.caster_type == "mental"
    assert sl.source == "carcass_crawler_1"


def test_kineticist_powers_loaded():
    data = _data()
    powers = [s for s in data.spells.values()
              if "kineticist" in s.spell_lists]
    assert len(powers) == 9
    assert all(p.source == "carcass_crawler_1" for p in powers)
    assert "accelerated_motion" in data.spells
    assert "throw_weapon" in data.spells


def test_kineticist_class_loaded():
    data = _data()
    cls = data.classes["kineticist"]
    assert cls.source == "carcass_crawler_1"
    assert cls.spell_lists == ["kineticist"]
    assert cls.hit_die == "1d6"
    assert cls.armor_allowed == []
    assert cls.shields_allowed is False
    assert [a.value for a in cls.prime_requisites] == ["DEX", "WIS"]
    # AC + powers columns present per level
    assert cls.progression[1].armor_class == 9
    assert cls.progression[14].armor_class == -3
    assert cls.progression[1].powers_known == 3
    assert cls.progression[14].powers_known == 9
    # no leveled spell slots — mental does not use them
    assert cls.progression[1].spell_slots is None
```

(`Ability` is an enum; `a.value` yields the string. If `prime_requisites` compares oddly, use `cls.prime_requisites == [Ability.DEX, Ability.WIS]` importing `from aose.models import Ability`.)

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -q`
Expected: FAIL with `KeyError: 'kineticist'`.

- [ ] **Step 3a: Add the spell list**

Append to `data/spell_lists.yaml`:

```yaml
- id: kineticist
  name: Mental Powers
  caster_type: mental
  source: carcass_crawler_1
  description: Mental powers fuelled by the manipulation of internal kinetic force.
```

- [ ] **Step 3b: Create the powers data**

Create `data/spells/carcass_crawler_kineticist_powers.yaml` (transcribe faithfully from the source markdown; `level: 1` is a uniform placeholder — mental powers have no level):

```yaml
- id: accelerated_motion
  name: Accelerated Motion
  level: 1
  spell_lists: [kineticist]
  source: carcass_crawler_1
  range: The kineticist
  duration: 1 round
  description: |-
    The kineticist makes a rapid burst of movement, driven by an internal surge of kinetic force.

    **Movement:** The kineticist's movement rate is doubled.

    **Melee attacks:** The kineticist may make multiple melee attacks per round. The number depends on level:

    | Level | Attacks per Round |
    |---|---|
    | 1–4 | 2 |
    | 5–8 | 3 |
    | 9–12 | 4 |
    | 13+ | 5 |
- id: control_density
  name: Control Density
  level: 1
  spell_lists: [kineticist]
  source: carcass_crawler_1
  range: The kineticist
  duration: 1 round per level
  description: |-
    The kineticist focuses kinetic force to alter the effective density of their own body, becoming lighter or heavier.

    **Lighter:** The kineticist becomes so light that they barely touch the ground. They leave no tracks in soft surfaces and can walk across the surface of water.

    **Heavier:** The kineticist is rooted to the spot, immune to attacks or effects that would cause them to fall or be pushed.
- id: crush_life
  name: Crush Life
  level: 1
  spell_lists: [kineticist]
  source: carcass_crawler_1
  range: 30'
  duration: Concentration, up to 1 round per level
  description: |-
    The kineticist focuses precise kinetic pressure onto the vital organs of a living target within range, crushing the life out of them by constricting breathing, blood flow, etc.

    **Damage:** The target suffers 1d3 points of damage per round.

    **Stun:** The target is unable to move or act unless they make a saving throw versus paralysis. A save is required each round.

    **Restrictions:** Non-living creatures (e.g. undead, constructs) are unaffected.

    **Concentration:** Being distracted (e.g. attacked) or performing any other action (except moving) causes the power to end.
- id: kinetic_fist
  name: Kinetic Fist
  level: 1
  spell_lists: [kineticist]
  source: carcass_crawler_1
  range: The kineticist
  duration: 1 round per level
  description: |-
    The kineticist's unarmed attacks are charged with focused kinetic energy, making their bare hands deadly weapons.

    **Damage:** The kineticist's unarmed attacks inflict increased damage, by level:

    | Level | Unarmed Damage |
    |---|---|
    | 1–4 | 2d4 |
    | 5–8 | 2d6 |
    | 9–12 | 2d8 |
    | 13+ | 2d12 |

    **Invulnerable monsters:** Kinetically charged attacks can harm monsters immune to mundane damage (e.g. only harmed by magic or silver weapons).
- id: kinetic_leap
  name: Kinetic Leap
  level: 1
  spell_lists: [kineticist]
  source: carcass_crawler_1
  range: 10' + 10' per level
  duration: Instant
  description: |-
    The kineticist propels their own body with a surge of kinetic force, allowing them to make a superhuman leap.

    **Leap:** The kineticist can leap to any location within range, including vertically.
- id: kinetic_shield
  name: Kinetic Shield
  level: 1
  spell_lists: [kineticist]
  source: carcass_crawler_1
  range: The kineticist
  duration: Concentration, up to 1 round per level
  description: |-
    A shield of kinetic energy whirls around the kineticist's body, deflecting attacks.

    **Missiles:** The kineticist is completely immune to small, non-magical missiles. No protection against hurled boulders or enchanted arrows.

    **Melee attacks:** Opponents suffer a −2 penalty to melee attack rolls against the kineticist.

    **Energy attacks:** The kineticist gains a +2 bonus to saving throws versus magic wands, rods, and staves, breath weapons, and energy attacks.

    **Concentration:** Performing any other action (except moving) causes the power to end.
- id: kinetic_wave
  name: Kinetic Wave
  level: 1
  spell_lists: [kineticist]
  source: carcass_crawler_1
  range: 30'
  duration: Instant
  description: |-
    A wave of kinetic force surges from the kineticist's hand at a single target in range.

    **Push:** The target must save vs paralysis or be thrown back by the kinetic force.

    **If the save fails:** The target suffers 1d6 damage and is thrown away from the kineticist to a distance of 10' per level of the kineticist.
- id: telekinetic_attack
  name: Telekinetic Attack
  level: 1
  spell_lists: [kineticist]
  source: carcass_crawler_1
  range: 10' per level
  duration: Instant
  description: |-
    The kineticist telekinetically lifts an object within range and hurls it at a nearby opponent.

    **Weight:** Up to 200 coins of weight per level of the kineticist may be lifted.

    **Range:** The targeted creature must be within 60' of the object.

    **Saving throw:** The target must save versus wands or be hit by the hurled object, suffering damage.

    **Damage:** Depends on the weight of the object hurled:

    | Object's Weight (Coins) | Damage |
    |---|---|
    | Up to 200 | 2d4 |
    | 201–400 | 2d6 |
    | 401–800 | 3d6 |
    | 801–1,500 | 4d6 |
    | 1,501 or more | 5d6 |
- id: throw_weapon
  name: Throw Weapon
  level: 1
  spell_lists: [kineticist]
  source: carcass_crawler_1
  range: 10' per level
  duration: Instant
  description: |-
    The kineticist throws a melee weapon they are holding in a precise, arcing flight. The weapon attacks a target within range and then returns to the kineticist's hand.

    **Attack:** The thrown weapon is handled as a missile attack roll with a +4 bonus.

    **Damage:** If the attack hits, any damage dealt is doubled.
```

- [ ] **Step 3c: Create the class data**

Create `data/classes/kineticist.yaml`:

```yaml
id: kineticist
name: Kineticist
source: carcass_crawler_1
prime_requisites:
- DEX
- WIS
max_level: 14
hit_die: 1d6
name_level: 9
hp_after_name_level: 2
weapons_allowed: all
armor_allowed: []
shields_allowed: false
spell_lists:
- kineticist
progression:
  1:
    xp_required: 0
    thac0: 19
    armor_class: 9
    powers_known: 3
    saves: {death: 13, wands: 14, paralysis: 13, breath: 16, spells: 15}
  2:
    xp_required: 2000
    thac0: 19
    armor_class: 8
    powers_known: 3
    saves: {death: 13, wands: 14, paralysis: 13, breath: 16, spells: 15}
  3:
    xp_required: 4000
    thac0: 19
    armor_class: 7
    powers_known: 4
    saves: {death: 13, wands: 14, paralysis: 13, breath: 16, spells: 15}
  4:
    xp_required: 8000
    thac0: 19
    armor_class: 6
    powers_known: 4
    saves: {death: 13, wands: 14, paralysis: 13, breath: 16, spells: 15}
  5:
    xp_required: 16000
    thac0: 17
    armor_class: 5
    powers_known: 5
    saves: {death: 12, wands: 13, paralysis: 11, breath: 14, spells: 13}
  6:
    xp_required: 32000
    thac0: 17
    armor_class: 4
    powers_known: 5
    saves: {death: 12, wands: 13, paralysis: 11, breath: 14, spells: 13}
  7:
    xp_required: 64000
    thac0: 17
    armor_class: 3
    powers_known: 6
    saves: {death: 12, wands: 13, paralysis: 11, breath: 14, spells: 13}
  8:
    xp_required: 120000
    thac0: 17
    armor_class: 2
    powers_known: 6
    saves: {death: 12, wands: 13, paralysis: 11, breath: 14, spells: 13}
  9:
    xp_required: 240000
    thac0: 14
    armor_class: 1
    powers_known: 7
    saves: {death: 10, wands: 11, paralysis: 9, breath: 12, spells: 10}
  10:
    xp_required: 360000
    thac0: 14
    armor_class: 0
    powers_known: 7
    saves: {death: 10, wands: 11, paralysis: 9, breath: 12, spells: 10}
  11:
    xp_required: 480000
    thac0: 14
    armor_class: -1
    powers_known: 8
    saves: {death: 10, wands: 11, paralysis: 9, breath: 12, spells: 10}
  12:
    xp_required: 600000
    thac0: 14
    armor_class: -2
    powers_known: 8
    saves: {death: 10, wands: 11, paralysis: 9, breath: 12, spells: 10}
  13:
    xp_required: 720000
    thac0: 12
    armor_class: -3
    powers_known: 9
    saves: {death: 8, wands: 9, paralysis: 7, breath: 10, spells: 8}
  14:
    xp_required: 840000
    thac0: 12
    armor_class: -3
    powers_known: 9
    saves: {death: 8, wands: 9, paralysis: 7, breath: 10, spells: 8}
features:
- id: combat
  name: Combat
  text: |-
    Kineticists can use all weapons, but cannot use armour or shields, instead relying on their honed reactions and mental powers for defence in battle.
  gained_at_level: 1
- id: armour_class
  name: Armour Class
  text: |-
    As a kineticist advances in level, their honed reactions and ability to deflect attacks grant them an improved Armour Class, as shown on the class table.
  gained_at_level: 1
- id: mental_defence
  name: Mental Defence
  text: |-
    Kineticists gain a +2 bonus to all saving throws against mental powers, including the powers of other kineticists.
  gained_at_level: 1
- id: mental_powers
  name: Mental Powers
  text: |-
    Kineticists know a number of mental powers depending on their level, as shown on the class table. Mental powers are chosen by the referee, who may allow the player to choose.

    **Frequency of use:** Twice per day per level, a kineticist may activate one of the mental powers they know. (A 2nd level kineticist may activate four powers per day.)

    **Activating:** Mental powers take effect instantly at the beginning of the character's initiative. A kineticist may activate a power and perform other actions (e.g. moving, attacking) in the same round. Mental powers take effect at the beginning of the combat sequence, before movement. A kineticist cannot activate more than one power in a single round.
  gained_at_level: 1
- id: after_reaching_9th_level
  name: After Reaching 9th Level
  text: |-
    A kineticist may establish an academy where they teach their skills to students. The kineticist will attract 1d6 apprentices, who are of level 1d4.
  gained_at_level: 9
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -q`
Expected: PASS. Also run the data-loading suite: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py tests/test_spells.py -q` — expected PASS (no regressions).

- [ ] **Step 5: Commit**

```bash
git add data/spell_lists.yaml data/spells/carcass_crawler_kineticist_powers.yaml data/classes/kineticist.yaml tests/test_mental_powers.py
git commit -m "feat(data): Kineticist class, mental spell list, and 9 mental powers"
```

---

## Task 4: AC engine — generic class-granted AC column

**Files:**
- Modify: `aose/engine/armor_class.py:11-52`
- Test: `tests/test_mental_powers.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mental_powers.py`:

```python
def _kin_spec(level=1, dex=10, **kw):
    from aose.models import CharacterSpec, ClassEntry
    base = dict(
        name="K",
        abilities={"STR": 10, "INT": 10, "WIS": 13, "DEX": dex, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="kineticist", level=level, hp_rolls=[6])],
        alignment="neutral",
    )
    base.update(kw)
    return CharacterSpec(**base)


def test_class_granted_ac_drives_unarmored_ac():
    from aose.engine.armor_class import unarmored_ac
    data = _data()
    # L5 kineticist: class AC column = 5 descending; DEX 10 -> +0.
    desc, asc = unarmored_ac(_kin_spec(level=5), data)
    assert desc == 5
    assert asc == 14


def test_class_granted_ac_still_applies_dex():
    from aose.engine.armor_class import unarmored_ac
    data = _data()
    # L5 class AC 5, DEX 13 -> +1 -> descending 4.
    desc, _ = unarmored_ac(_kin_spec(level=5, dex=13), data)
    assert desc == 4


def test_class_granted_ac_applies_in_armored_call_too():
    from aose.engine.armor_class import armor_class
    data = _data()
    # Kineticist cannot wear armour; armored call still reflects the class AC.
    desc, _ = armor_class(_kin_spec(level=10), data)
    assert desc == 0  # L10 column


def test_class_with_no_ac_column_unaffected():
    from aose.engine.armor_class import unarmored_ac
    from aose.models import CharacterSpec, ClassEntry
    data = _data()
    spec = CharacterSpec(
        name="F", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=5, hp_rolls=[8])],
        alignment="neutral")
    assert unarmored_ac(spec, data) == (9, 10)  # unchanged baseline
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -k ac -q`
Expected: FAIL (e.g. L5 returns 9, not 5 — column ignored).

- [ ] **Step 3: Fold class-granted AC into base**

In `aose/engine/armor_class.py`, inside `armor_class()`, after the `if use_armor:` block (i.e. after the enchanted-armour / `ac set` loops) and **before** the `shield_bonus` block, insert:

```python
    # Class-granted base AC (e.g. a class whose reactions improve AC by level).
    # Best (lowest descending) across classes; applies whether or not armour is
    # worn — it is not worn armour, so the unarmoured display reflects it too.
    class_acs = [
        cls.progression[entry.level].armor_class
        for entry in spec.classes
        if (cls := data.classes.get(entry.class_id)) is not None
        and entry.level in cls.progression
        and cls.progression[entry.level].armor_class is not None
    ]
    if class_acs:
        base = min(base, min(class_acs))
```

(The walrus `:=` inside the comprehension binds `cls` per iteration; this is valid Python 3.8+. If the project style avoids walrus in comprehensions, replace with an explicit loop building `class_acs`.)

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -k ac -q`
Expected: PASS. Then full AC regression: `.venv\Scripts\python.exe -m pytest tests/test_unarmored_ac.py tests/test_derivation.py -q` — PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/armor_class.py tests/test_mental_powers.py
git commit -m "feat(engine): generic class-granted AC column in armor_class"
```

---

## Task 5: Spells engine — mental caster type (known / learnable / learn / counts)

**Files:**
- Modify: `aose/engine/spells.py` (`CasterType:15`, `known_spells:68`, `learnable_spells:87`, `learn:144`, `beginning_spell_count:123`; add `powers_known_cap`)
- Test: `tests/test_mental_powers.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mental_powers.py`:

```python
def _kin_entry(level=1, spellbook=None):
    from aose.models import ClassEntry
    return ClassEntry(class_id="kineticist", level=level, hp_rolls=[6],
                      spellbook=list(spellbook or []))


def test_mental_caster_type_detected():
    from aose.engine import spells
    data = _data()
    cls = data.classes["kineticist"]
    assert spells.caster_type_of(cls, data) == "mental"


def test_powers_known_cap_reads_column():
    from aose.engine import spells
    data = _data()
    cls = data.classes["kineticist"]
    assert spells.powers_known_cap(_kin_entry(level=1), cls) == 3
    assert spells.powers_known_cap(_kin_entry(level=3), cls) == 4


def test_mental_known_and_learnable():
    from aose.engine import spells
    data = _data()
    cls = data.classes["kineticist"]
    entry = _kin_entry(level=1, spellbook=["kinetic_fist"])
    assert [s.id for s in spells.known_spells(entry, cls, data)] == ["kinetic_fist"]
    learnable_ids = {s.id for s in spells.learnable_spells(entry, cls, data)}
    assert "kinetic_fist" not in learnable_ids          # already known
    assert "accelerated_motion" in learnable_ids        # available


def test_mental_learn_enforces_cap():
    from aose.engine import spells
    data = _data()
    cls = data.classes["kineticist"]
    ruleset = __import__("aose.models", fromlist=["RuleSet"]).RuleSet()
    entry = _kin_entry(level=1, spellbook=["kinetic_fist", "kinetic_leap", "kinetic_wave"])
    # cap is 3 at level 1 — a 4th must be refused
    with pytest.raises(spells.SpellError):
        spells.learn(entry, cls, data, ruleset, "crush_life")


def test_mental_learn_then_forget():
    from aose.engine import spells
    data = _data()
    cls = data.classes["kineticist"]
    ruleset = __import__("aose.models", fromlist=["RuleSet"]).RuleSet()
    entry = spells.learn(_kin_entry(level=1), cls, data, ruleset, "kinetic_fist")
    assert entry.spellbook == ["kinetic_fist"]
    entry = spells.forget(entry, "kinetic_fist")
    assert entry.spellbook == []


def test_mental_beginning_spell_count_is_cap():
    from aose.engine import spells
    from aose.models import RuleSet
    data = _data()
    cls = data.classes["kineticist"]
    assert spells.beginning_spell_count(_kin_entry(level=1), cls, 10, RuleSet()) == 3
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -k "mental or powers_known or caster_type" -q`
Expected: FAIL (`powers_known_cap` missing; `learn` raises "not an arcane caster"; etc.).

- [ ] **Step 3: Implement the mental branches**

In `aose/engine/spells.py`:

(a) Widen `CasterType`:

```python
CasterType = Literal["arcane", "divine", "mental"]
```

(b) `known_spells` — fold mental into the arcane (chosen-subset) branch:

```python
    if ctype in ("arcane", "mental"):
        return [data.spells[s] for s in entry.spellbook if s in data.spells]
```

(c) Add `powers_known_cap` near `memorizable_slots`:

```python
def powers_known_cap(entry: ClassEntry, cls: CharClass) -> int:
    """Mental caster: number of powers known at the entry's level (table column)."""
    row = _level_row(entry, cls)
    return (row.powers_known or 0) if row is not None else 0
```

(d) `learnable_spells` — add a mental branch at the top (before the `!= "arcane"` guard):

```python
def learnable_spells(entry: ClassEntry, cls: CharClass, data: GameData) -> list[Spell]:
    """Arcane: accessible-level spells on the class's lists not yet known.
    Mental: every on-list power not yet known (no level filter)."""
    ctype = caster_type_of(cls, data)
    known = set(entry.spellbook)
    if ctype == "mental":
        return sorted(
            (s for s in data.spells.values()
             if _on_class_lists(s, cls) and s.id not in known),
            key=lambda s: (s.level, s.name),
        )
    if ctype != "arcane":
        return []
    levels = accessible_levels(entry, cls)
    return sorted(
        (s for s in data.spells.values()
         if _on_class_lists(s, cls) and s.level in levels and s.id not in known),
        key=lambda s: (s.level, s.name),
    )
```

(e) `beginning_spell_count` — mental returns the cap. Note this function has **no `data` parameter**, so it cannot call `caster_type_of` (which needs `data`). Detect mental instead via the `powers_known` column, which only mental classes populate:

```python
def beginning_spell_count(entry: ClassEntry, cls: CharClass, int_score: int,
                          ruleset: RuleSet) -> int:
    """How many spells/powers a caster begins with.

    mental: powers-known cap at the entry's level. advanced arcane rule:
    INT-table lookup. standard arcane: total memorizable at the entry's level.
    """
    row = _level_row(entry, cls)
    if row is not None and row.powers_known is not None:
        return powers_known_cap(entry, cls)
    if ruleset.advanced_spell_books:
        return beginning_spells_for_int(int_score)
    return sum(memorizable_slots(entry, cls).values())
```

(The `row.powers_known is not None` check identifies a mental class without needing `data`; only mental classes populate that column.)

(f) `learn` — add a mental branch at the very top of the function body (after the docstring):

```python
def learn(entry: ClassEntry, cls: CharClass, data: GameData, ruleset: RuleSet,
          spell_id: str) -> ClassEntry:
    """Add a spell/power to a caster's known set.

    mental: power on the class list, not already known, under the powers-known
    cap. arcane: see below (list/level/cap or advanced copy-only restriction)."""
    ctype = caster_type_of(cls, data)
    if ctype == "mental":
        spell = _require_spell(data, spell_id)
        if not _on_class_lists(spell, cls):
            raise SpellError(f"{spell_id!r} is not a {cls.id!r} mental power")
        if spell_id in entry.spellbook:
            raise SpellError(f"{spell_id!r} is already known")
        cap = powers_known_cap(entry, cls)
        if len(entry.spellbook) >= cap:
            raise SpellError(
                f"Only {cap} mental power(s) may be known at this level"
            )
        return entry.model_copy(update={"spellbook": [*entry.spellbook, spell_id]})
    if ctype != "arcane":
        raise SpellError(f"{cls.id!r} is not an arcane caster; nothing to learn")
    # ... existing arcane body unchanged ...
```

(Remove the now-duplicated `if caster_type_of(...) != "arcane": raise` line that previously opened the function — the `ctype != "arcane"` guard above replaces it.)

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -q`
Expected: PASS. Regression: `.venv\Scripts\python.exe -m pytest tests/test_spells.py tests/test_spell_slots.py tests/test_spell_routes.py -q` — PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/spells.py tests/test_mental_powers.py
git commit -m "feat(engine): mental caster type in spells (known/learn/cap/counts)"
```

---

## Task 6: Spells engine — daily-use power pool helpers

**Files:**
- Modify: `aose/engine/spells.py` (add helpers near the slot mutators)
- Test: `tests/test_mental_powers.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mental_powers.py`:

```python
def test_power_pool_is_two_per_level():
    from aose.engine import spells
    assert spells.power_pool(_kin_entry(level=1)) == 2
    assert spells.power_pool(_kin_entry(level=3)) == 6


def test_spend_restore_reset_powers():
    from aose.engine import spells
    e = _kin_entry(level=2)              # pool = 4
    e = spells.spend_power(e)
    e = spells.spend_power(e)
    assert e.powers_used == 2
    e = spells.restore_power(e)
    assert e.powers_used == 1
    e = spells.reset_powers(e)
    assert e.powers_used == 0


def test_spend_beyond_pool_raises():
    from aose.engine import spells
    e = _kin_entry(level=1)              # pool = 2
    e = spells.spend_power(e)
    e = spells.spend_power(e)
    with pytest.raises(spells.SpellError):
        spells.spend_power(e)


def test_restore_below_zero_raises():
    from aose.engine import spells
    with pytest.raises(spells.SpellError):
        spells.restore_power(_kin_entry(level=1))
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -k "power_pool or powers" -q`
Expected: FAIL (`power_pool`/`spend_power`/... missing).

- [ ] **Step 3: Add the pool helpers**

In `aose/engine/spells.py`, after `clear_all_slots` (end of file), add:

```python
# ── Mental-powers daily-use pool (play state) ──────────────────────────────

def power_pool(entry: ClassEntry) -> int:
    """Total mental-power activations available per day: 2 x level."""
    return 2 * entry.level


def spend_power(entry: ClassEntry) -> ClassEntry:
    """Spend one daily activation.  Raises if none remain."""
    if entry.powers_used >= power_pool(entry):
        raise SpellError("No mental-power uses remaining today")
    return entry.model_copy(update={"powers_used": entry.powers_used + 1})


def restore_power(entry: ClassEntry) -> ClassEntry:
    """Un-spend one activation (undo / referee override).  Raises at zero."""
    if entry.powers_used <= 0:
        raise SpellError("No spent mental-power uses to restore")
    return entry.model_copy(update={"powers_used": entry.powers_used - 1})


def reset_powers(entry: ClassEntry) -> ClassEntry:
    """Refresh the whole daily pool (e.g. on rest).  No-op for non-mental
    entries, whose ``powers_used`` is always 0."""
    return entry.model_copy(update={"powers_used": 0})
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/spells.py tests/test_mental_powers.py
git commit -m "feat(engine): mental-powers daily-use pool helpers"
```

---

## Task 7: Sheet view — skip mental in spell views; add `mental_powers_view`

**Files:**
- Modify: `aose/sheet/view.py` (`spells_view:649`, `spellbook_view:706`; add models + `mental_powers_view`; `CharacterSheet:322`; `build_sheet:~1038`)
- Test: `tests/test_mental_powers.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mental_powers.py`:

```python
def _kin_full_spec(level=1, spellbook=None, powers_used=0):
    from aose.models import CharacterSpec, ClassEntry
    return CharacterSpec(
        name="K",
        abilities={"STR": 10, "INT": 10, "WIS": 13, "DEX": 13, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="kineticist", level=level, hp_rolls=[6],
                            spellbook=list(spellbook or []), powers_used=powers_used)],
        alignment="neutral",
    )


def test_spell_views_skip_mental():
    from aose.sheet.view import spells_view, spellbook_view
    data = _data()
    spec = _kin_full_spec(spellbook=["kinetic_fist"])
    assert spells_view(spec, data) == []
    assert spellbook_view(spec, data) == []


def test_mental_powers_view_shape():
    from aose.sheet.view import mental_powers_view
    data = _data()
    spec = _kin_full_spec(level=2, spellbook=["kinetic_fist"], powers_used=1)
    blocks = mental_powers_view(spec, data)
    assert len(blocks) == 1
    b = blocks[0]
    assert b.class_id == "kineticist"
    assert b.cap == 3
    assert [r.power_id for r in b.known] == ["kinetic_fist"]
    assert "kinetic_fist" not in {r.power_id for r in b.addable}
    assert b.can_add is True
    assert b.uses_total == 4
    assert b.uses_used == 1
    assert b.uses_remaining == 3


def test_build_sheet_exposes_mental_powers():
    from aose.sheet.view import build_sheet
    data = _data()
    sheet = build_sheet(_kin_full_spec(spellbook=["kinetic_fist"]), data)
    assert len(sheet.mental_powers) == 1
    assert sheet.spells == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -k "mental_powers_view or spell_views_skip or build_sheet_exposes" -q`
Expected: FAIL (`mental_powers_view` missing; `spells_view` returns a block for the kineticist).

- [ ] **Step 3a: Skip mental in the two spell views**

In `aose/sheet/view.py`, in **both** `spells_view` and `spellbook_view`, change the early `if ctype is None:` guard to also skip mental:

```python
        ctype = spell_engine.caster_type_of(cls, data)
        if ctype is None or ctype == "mental":
            continue
```

- [ ] **Step 3b: Add the view models and `mental_powers_view`**

In `aose/sheet/view.py`, after the `SpellbookBlock` model (around line 255), add:

```python
class MentalPowerRow(BaseModel):
    power_id: str
    name: str
    detail: DetailCard | None = None


class MentalPowersBlock(BaseModel):
    class_id: str
    class_name: str
    cap: int                       # powers known at this level
    known: list[MentalPowerRow]
    addable: list[MentalPowerRow]  # on-list powers not yet known
    can_add: bool                  # len(known) < cap
    uses_total: int                # 2 x level
    uses_used: int
    uses_remaining: int
```

Then add the view function near `spellbook_view` (after it, around line 778):

```python
def mental_powers_view(spec: CharacterSpec, data: GameData) -> list[MentalPowersBlock]:
    """One block per mental caster class: known powers, addable powers, and the
    daily-use pool (2 x level activations)."""
    out: list[MentalPowersBlock] = []
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        if spell_engine.caster_type_of(cls, data) != "mental":
            continue
        cap = spell_engine.powers_known_cap(entry, cls)
        known = [
            MentalPowerRow(power_id=s.id, name=s.name, detail=spell_card(s))
            for s in spell_engine.known_spells(entry, cls, data)
        ]
        addable = [
            MentalPowerRow(power_id=s.id, name=s.name, detail=spell_card(s))
            for s in spell_engine.learnable_spells(entry, cls, data)
        ]
        total = spell_engine.power_pool(entry)
        out.append(MentalPowersBlock(
            class_id=entry.class_id, class_name=cls.name, cap=cap,
            known=known, addable=addable, can_add=len(known) < cap,
            uses_total=total, uses_used=entry.powers_used,
            uses_remaining=max(0, total - entry.powers_used),
        ))
    return out
```

(`spell_card` is already defined/imported in this module — it builds the `DetailCard`; mental powers have no reversed form, so call it with the spell only.)

- [ ] **Step 3c: Wire into `CharacterSheet` and `build_sheet`**

In the `CharacterSheet` model, after `spellbook: list[SpellbookBlock] = ...` (line 323), add:

```python
    mental_powers: list[MentalPowersBlock] = Field(default_factory=list)
```

In `build_sheet`, where `spells=spells_view(spec, data)` / `spellbook=spellbook_view(spec, data)` are passed (around line 1038-1039), add:

```python
        mental_powers=mental_powers_view(spec, data),
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -q`
Expected: PASS. Regression: `.venv\Scripts\python.exe -m pytest tests/test_sheet.py tests/test_spellbook_view.py tests/test_detail_views.py -q` — PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/sheet/view.py tests/test_mental_powers.py
git commit -m "feat(sheet): mental_powers_view; spell views skip mental"
```

---

## Task 8: Routes — `/powers/*` and rest pool reset

**Files:**
- Modify: `aose/web/routes.py` (add power routes near the spell routes ~912; edit `_apply_rest_mode:998`)
- Test: `tests/test_mental_powers.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mental_powers.py` (mirrors `tests/test_spell_routes.py` / `test_rest_routes.py` style — uses the FastAPI app + a saved character). First inspect `tests/test_spell_routes.py` for the exact `client`/save fixtures and reuse them. Concretely:

```python
def _client_and_id(tmp_path):
    """Build a TestClient with a saved kineticist; return (client, character_id)."""
    from starlette.testclient import TestClient
    from aose.web.app import app
    from aose.characters.storage import save_character
    app.state.characters_dir = tmp_path
    spec = _kin_full_spec(level=2, spellbook=["kinetic_fist"])
    save_character("kin1", spec, tmp_path)
    return TestClient(app), "kin1"


def test_power_learn_and_forget_routes(tmp_path):
    from aose.characters.storage import load_character
    client, cid = _client_and_id(tmp_path)
    r = client.post(f"/character/{cid}/powers/learn",
                    data={"class_id": "kineticist", "power_id": "kinetic_leap"},
                    follow_redirects=False)
    assert r.status_code == 303
    spec = load_character(cid, tmp_path)
    assert "kinetic_leap" in spec.classes[0].spellbook
    r = client.post(f"/character/{cid}/powers/forget",
                    data={"class_id": "kineticist", "power_id": "kinetic_fist"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "kinetic_fist" not in load_character(cid, tmp_path).classes[0].spellbook


def test_power_spend_restore_reset_routes(tmp_path):
    from aose.characters.storage import load_character
    client, cid = _client_and_id(tmp_path)
    client.post(f"/character/{cid}/powers/spend", data={"class_id": "kineticist"},
                follow_redirects=False)
    assert load_character(cid, tmp_path).classes[0].powers_used == 1
    client.post(f"/character/{cid}/powers/restore", data={"class_id": "kineticist"},
                follow_redirects=False)
    assert load_character(cid, tmp_path).classes[0].powers_used == 0
    client.post(f"/character/{cid}/powers/spend", data={"class_id": "kineticist"},
                follow_redirects=False)
    client.post(f"/character/{cid}/powers/reset", data={"class_id": "kineticist"},
                follow_redirects=False)
    assert load_character(cid, tmp_path).classes[0].powers_used == 0


def test_rest_night_resets_power_pool(tmp_path):
    from aose.characters.storage import load_character, save_character
    client, cid = _client_and_id(tmp_path)
    spec = load_character(cid, tmp_path)
    spec.classes[0].powers_used = 3
    save_character(cid, spec, tmp_path)
    client.post(f"/character/{cid}/rest/night", data={"mode": "restore"},
                follow_redirects=False)
    assert load_character(cid, tmp_path).classes[0].powers_used == 0
```

(If `tests/test_spell_routes.py` uses a shared `conftest`/fixture for the client and saved character, prefer that fixture over `_client_and_id`; match the existing import names for `load_character`/`save_character`.)

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -k "power_learn or power_spend or rest_night_resets" -q`
Expected: FAIL (404 for `/powers/*`; pool not reset).

- [ ] **Step 3a: Add the power routes**

In `aose/web/routes.py`, after the spell `clear` route (around line 913), add:

```python
# ── Mental powers on the live sheet ────────────────────────────────────────

@router.post("/character/{character_id}/powers/learn")
async def sheet_power_learn(request: Request, character_id: str,
                            class_id: str = Form(...), power_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = spell_engine.learn(
            spec.classes[idx], data.classes[class_id], data, spec.ruleset, power_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/powers/forget")
async def sheet_power_forget(request: Request, character_id: str,
                             class_id: str = Form(...), power_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = spell_engine.forget(spec.classes[idx], power_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


def _power_pool_op(request: Request, character_id: str, class_id: str, op):
    spec = _load_spec_or_404(request, character_id)
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = op(spec.classes[idx])
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/powers/spend")
async def sheet_power_spend(request: Request, character_id: str,
                            class_id: str = Form(...)):
    return _power_pool_op(request, character_id, class_id, spell_engine.spend_power)


@router.post("/character/{character_id}/powers/restore")
async def sheet_power_restore(request: Request, character_id: str,
                              class_id: str = Form(...)):
    return _power_pool_op(request, character_id, class_id, spell_engine.restore_power)


@router.post("/character/{character_id}/powers/reset")
async def sheet_power_reset(request: Request, character_id: str,
                            class_id: str = Form(...)):
    return _power_pool_op(request, character_id, class_id, spell_engine.reset_powers)
```

(`SpellError` subclasses `ValueError`, so the `except ValueError` catch maps engine errors to HTTP 400 — same pattern as the spell routes.)

- [ ] **Step 3b: Reset the pool on rest**

In `aose/web/routes.py`, edit `_apply_rest_mode` so a rest always refreshes the daily pool (a no-op for non-mental classes):

```python
def _apply_rest_mode(entry, mode: str):
    """Apply a rest spell-option to one class entry, and refresh the mental-power
    daily pool (a new day).  Non-casters/non-mental: pool reset is a no-op and
    slot modes do nothing."""
    entry = spell_engine.reset_powers(entry)
    if mode == "restore":
        return spell_engine.restore_all_slots(entry)
    if mode == "clear":
        return spell_engine.clear_all_slots(entry)
    if mode == "keep":
        return entry
    raise HTTPException(400, f"Unknown rest mode {mode!r}")
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -q`
Expected: PASS. Regression: `.venv\Scripts\python.exe -m pytest tests/test_spell_routes.py tests/test_rest_routes.py -q` — PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_mental_powers.py
git commit -m "feat(routes): mental-power learn/forget/spend/restore/reset; rest refreshes pool"
```

---

## Task 9: Wizard — mental casting in the spells step

**Files:**
- Modify: `aose/web/wizard.py` (`_casts_at_level_1:180`, `_caster_entries:1276`, `post_spells:1316`)
- Test: `tests/test_mental_powers.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mental_powers.py`. First open `tests/test_wizard_class_setup.py` to reuse its draft-building helpers (the wizard stores drafts via `save_draft`; tests post through the app). Match those helpers; the assertions to add:

```python
def test_kineticist_triggers_spellcasting_step():
    from aose.web.wizard import _casts_at_level_1
    data = _data()
    assert _casts_at_level_1(data.classes["kineticist"]) is True
    assert _casts_at_level_1(data.classes["fighter"]) is False
    assert _casts_at_level_1(data.classes["magic_user"]) is True


def test_caster_entries_mental_required_and_candidates():
    from aose.web.wizard import _caster_entries
    data = _data()
    draft = {
        "abilities": {"STR": 10, "INT": 10, "WIS": 13, "DEX": 13, "CON": 10, "CHA": 10},
        "class_id": "kineticist",
        "ruleset": {},          # default ruleset
        "spellbooks": {},
    }
    rows = _caster_entries(draft, data)
    row = next(r for r in rows if r["class_id"] == "kineticist")
    assert row["caster_type"] == "mental"
    assert row["required"] == 3
    assert len(row["candidates"]) == 9     # all powers offered (no level filter)
```

(If `_ruleset_of(draft)` expects a different `ruleset` shape, mirror how `tests/test_wizard_class_setup.py` builds the draft dict — use the same keys it uses.)

For `post_spells`, add an end-to-end test posting the spells form through the app, mirroring the class-setup test's draft setup, asserting: posting exactly 3 powers succeeds and stores them in `draft["spellbooks"]["kineticist"]`; posting 2 returns HTTP 400. Use the existing wizard-test client + `load_draft` helpers from `tests/test_wizard_class_setup.py`.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -k "kineticist_triggers or caster_entries_mental" -q`
Expected: FAIL (`_casts_at_level_1` returns False for kineticist — it has no `spell_slots`; `_caster_entries` filters candidates to empty via `accessible_levels`).

- [ ] **Step 3a: Recognise mental in the casting predicate**

In `aose/web/wizard.py`, update `_casts_at_level_1`:

```python
def _casts_at_level_1(cls) -> bool:
    """True if the class casts at L1: has a spell list and either L1 spell slots
    (arcane/divine) or L1 mental powers known."""
    row = cls.progression.get(1)
    return bool(cls.spell_lists) and bool(row and (row.spell_slots or row.powers_known))
```

- [ ] **Step 3b: Mental candidates + required in `_caster_entries`**

In `_caster_entries`, change the `candidates` comprehension and the `required` field so mental skips the accessible-level filter and uses the powers cap:

```python
        candidates = sorted(
            (s for s in data.spells.values()
             if set(s.spell_lists) & enabled_lists
             and (ctype == "mental"
                  or s.level in spell_engine.accessible_levels(entry, cls))),
            key=lambda s: (s.level, s.name),
        )
        rows.append({
            "class_id": cid,
            "class_name": cls.name,
            "caster_type": ctype,
            "required": (spell_engine.beginning_spell_count(entry, cls, int_score, ruleset)
                         if ctype in ("arcane", "mental") else 0),
            "advanced": ruleset.advanced_spell_books,
            "candidates": [{"id": s.id, "name": s.name, "level": s.level,
                            "description": s.description,
                            "selected": s.id in books.get(cid, [])}
                           for s in candidates],
        })
```

- [ ] **Step 3c: Mental selection in `post_spells`**

In `post_spells`, replace the `if ctype != "arcane":` divine short-circuit so mental is handled alongside arcane, skipping the accessible-level validation:

```python
        entry = ClassEntry(class_id=cid, level=1)
        ctype = spell_engine.caster_type_of(cls, data)
        if ctype == "divine":
            # Divine casters know their whole list; nothing is chosen here.
            books[cid] = []
            continue
        chosen = form.getlist(f"spell_{cid}")
        chosen = list(dict.fromkeys(chosen))
        required = spell_engine.beginning_spell_count(entry, cls, int_score, ruleset)
        if len(chosen) != required:
            raise HTTPException(
                400, f"{cls.name} must choose exactly {required} "
                     f"{'power' if ctype == 'mental' else 'starting spell'}(s); "
                     f"got {len(chosen)}."
            )
        accessible = spell_engine.accessible_levels(entry, cls)
        for sid in chosen:
            spell = data.spells.get(sid)
            on_list = spell is not None and bool(set(spell.spell_lists) & set(cls.spell_lists))
            if not on_list or (ctype == "arcane" and spell.level not in accessible):
                raise HTTPException(400, f"{sid!r} is not a valid {cls.name} choice.")
        books[cid] = chosen
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -q`
Expected: PASS. Regression: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py tests/test_wizard.py -q` — PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/wizard.py tests/test_mental_powers.py
git commit -m "feat(wizard): mental casting in the spells step (Kineticist starting powers)"
```

---

## Task 10: Sheet template — Mental Powers section + management drawer

**Files:**
- Modify: `aose/web/templates/sheet.html`
- Test: manual + `tests/test_mental_powers.py` (render smoke test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_mental_powers.py` (a render smoke test; reuse `_client_and_id`):

```python
def test_sheet_renders_mental_powers_section(tmp_path):
    client, cid = _client_and_id(tmp_path)
    html = client.get(f"/character/{cid}").text
    assert "Mental Powers" in html
    assert "/powers/spend" in html
    assert "Kinetic Fist" in html        # the known power
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -k renders_mental -q`
Expected: FAIL ("Mental Powers" not in HTML).

- [ ] **Step 3a: Add the section to column 3**

In `aose/web/templates/sheet.html`, inside `COLUMN 3`, immediately after the spellbook `{% endif %}` (line 260) and before the closing `</div>` of the column block, add a mental-powers section. If column 3 is only emitted `{% if sheet.spellbook %}`, the kineticist (no spellbook) would skip the whole column — so wrap the column open/close to also fire for mental. Change line 213 from `{% if sheet.spellbook %}` to:

```jinja
    {% if sheet.spellbook or sheet.mental_powers %}
    <div class="col col-spells">
      {% for block in sheet.spellbook %}
      ... (existing spellbook section, unchanged) ...
      {% endfor %}

      {% for block in sheet.mental_powers %}
      <section class="group">
        <div class="bar">Mental Powers — {{ block.class_name }}
          <span class="tools">
            <span class="meta">{{ block.uses_remaining }}/{{ block.uses_total }} uses</span>
            <button class="btn tool" data-drawer="drawer-powers">Manage</button>
          </span>
        </div>
        <div class="gbody scroll" style="max-height:360px">
          <div class="pips" style="margin:2px 0 6px">
            {% for _ in range(block.uses_remaining) %}<i class="pip"></i>{% endfor %}
            {% for _ in range(block.uses_used) %}<i class="pip spent"></i>{% endfor %}
          </div>
          <div class="pool-actions" style="display:flex;gap:4px;margin-bottom:8px">
            <form method="post" action="/character/{{ character_id }}/powers/spend">
              <input type="hidden" name="class_id" value="{{ block.class_id }}">
              <button class="btn" {% if block.uses_remaining == 0 %}disabled{% endif %}>Use −</button>
            </form>
            <form method="post" action="/character/{{ character_id }}/powers/restore">
              <input type="hidden" name="class_id" value="{{ block.class_id }}">
              <button class="btn" {% if block.uses_used == 0 %}disabled{% endif %}>Restore +</button>
            </form>
            <form method="post" action="/character/{{ character_id }}/powers/reset">
              <input type="hidden" name="class_id" value="{{ block.class_id }}">
              <button class="btn">Reset</button>
            </form>
          </div>
          {% for p in block.known %}
          <div class="spell"><span class="snm">{{ p.name }}</span></div>
          {% else %}
          <p class="hint" style="margin:4px 0">No powers known yet — use Manage.</p>
          {% endfor %}
          <p class="hint" style="margin-top:6px">2/day per level. One power per round; takes effect at the start of the combat sequence.</p>
        </div>
      </section>
      {% endfor %}
    </div>
    {% endif %}
```

(Replace the existing `{% if sheet.spellbook %} ... {% endif %}` column block with this combined version — keep the existing spellbook `{% for block in sheet.spellbook %}...{% endfor %}` body verbatim; only the guard and the appended mental `{% for %}` are new.)

- [ ] **Step 3b: Add the management drawer**

In `aose/web/templates/sheet.html`, after the spells drawer (`<aside ... id="drawer-spells">...</aside>`, ends ~line 562) add a powers drawer:

```jinja
{# DRAWER: mental powers management #}
{% if sheet.mental_powers %}
<aside class="overlay drawer" id="drawer-powers" role="dialog" aria-label="Manage mental powers">
  <div class="ov-head"><h3>Mental Powers</h3><button class="x" data-close>×</button></div>
  <div class="ov-body">
  {% for block in sheet.mental_powers %}
    <h4>{{ block.class_name }} — known {{ block.known|length }}/{{ block.cap }}</h4>
    {% for p in block.known %}
    <div class="spell-detail" style="margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <strong>{{ p.name }}</strong>
        <form method="post" action="/character/{{ character_id }}/powers/forget">
          <input type="hidden" name="class_id" value="{{ block.class_id }}">
          <input type="hidden" name="power_id" value="{{ p.power_id }}">
          <button class="btn" style="font-size:10px;padding:3px 7px;">Forget</button>
        </form>
      </div>
      {{ detail_card(p.detail) }}
    </div>
    {% endfor %}
    {% if block.can_add and block.addable %}
    <form method="post" action="/character/{{ character_id }}/powers/learn" style="margin-top:6px">
      <input type="hidden" name="class_id" value="{{ block.class_id }}">
      <select name="power_id">
        {% for p in block.addable %}<option value="{{ p.power_id }}">{{ p.name }}</option>{% endfor %}
      </select>
      <button class="btn">Learn power</button>
    </form>
    {% elif not block.can_add %}
    <p class="hint">All {{ block.cap }} powers known at this level.</p>
    {% endif %}
  {% endfor %}
  </div>
</aside>
{% endif %}
```

(`detail_card` is already imported at the top of `sheet.html` (line 5). Match the surrounding markup's CSS classes if `spell-detail`/`btn` differ — inspect the spells drawer for the exact classes and reuse them. The overlay controller `sheet_overlays.js` wires any `data-drawer="drawer-powers"` button to the `id="drawer-powers"` aside automatically — no JS change needed.)

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -k renders_mental -q`
Expected: PASS. Regression: `.venv\Scripts\python.exe -m pytest tests/test_web.py tests/test_sheet.py -q` — PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/templates/sheet.html tests/test_mental_powers.py
git commit -m "feat(sheet): Mental Powers section + management drawer"
```

---

## Task 11: Source gating — disabling Carcass Crawler hides the Kineticist

**Files:**
- Test: `tests/test_mental_powers.py` (verifies existing generic gating covers the new content)

- [ ] **Step 1: Write the test**

The wizard race/class steps and `_caster_entries` already gate by `source_enabled`. Add a test confirming the new content is hidden when the source is disabled. Inspect `tests/test_sources_engine.py` / `tests/test_wizard_class_setup.py` for how a disabled-source ruleset is expressed in a draft, then:

```python
def test_caster_entries_hide_powers_when_source_disabled():
    from aose.web.wizard import _caster_entries
    data = _data()
    draft = {
        "abilities": {"STR": 10, "INT": 10, "WIS": 13, "DEX": 13, "CON": 10, "CHA": 10},
        "class_id": "kineticist",
        "ruleset": {"disabled_sources": ["carcass_crawler_1"]},
        "spellbooks": {},
    }
    rows = _caster_entries(draft, data)
    row = next(r for r in rows if r["class_id"] == "kineticist")
    assert row["candidates"] == []     # powers hidden — their source is off
```

(Match the `ruleset` draft shape to whatever `_ruleset_of` expects — see `tests/test_wizard_rules_step.py`. Also confirm the wizard **class list** step excludes the kineticist when the source is disabled, mirroring an existing race/class source-gating test if one exists.)

- [ ] **Step 2: Run to verify it passes (gating already implemented)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mental_powers.py -k source_disabled -q`
Expected: PASS immediately (the generic `source_enabled` filter in `_caster_entries` already covers this). If it FAILS, the spell-list/power `source` tags from Task 3 are missing — fix the data, not the engine.

- [ ] **Step 3: Commit**

```bash
git add tests/test_mental_powers.py
git commit -m "test(sources): Kineticist content hidden when Carcass Crawler disabled"
```

---

## Task 12: Full suite + manual verification

**Files:** none (verification only)

- [ ] **Step 1: Run the whole test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all pass except the two pre-existing breadcrumb-label failures noted in CLAUDE.md (`test_wizard_class_setup` / `test_wizard_identity`) and the harmless Windows `pytest-current` PermissionError. Confirm no **new** failures.

- [ ] **Step 2: Manual smoke — create a Kineticist**

Start the app: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`. Walk the wizard: pick Kineticist, confirm the spells step appears and requires choosing exactly 3 powers, finish creation. On the sheet, confirm:
- AC reflects the level-1 column (9 − DEX mod), not a flat 9 if DEX ≠ 10.
- The **Mental Powers** section shows the daily-use pool (`2/2 uses` at L1) and the 3 chosen powers.
- Use −, Restore +, Reset, Manage (learn/forget) all work; a night's rest refreshes the pool.

- [ ] **Step 3: Manual smoke — source toggle**

In `/settings` (or the wizard `/rules` step), disable "Carcass Crawler Issue 1"; confirm the Kineticist disappears from the class list and its powers vanish from candidates. Re-enable; confirm it returns.

- [ ] **Step 4: Update CLAUDE.md**

Add a "Current state (2026-06-06, mental powers + Kineticist)" note to `CLAUDE.md` summarising: the generic `mental` caster type (known subset reusing `spellbook`; `2×level` daily pool via `ClassEntry.powers_used`; `spells.py` helpers), the generic `ClassLevelData.armor_class` column (AC engine, best across classes — Dwarf can use it later), the Carcass Crawler source, and the Kineticist data. Mention the spec/plan paths. Commit:

```bash
git add CLAUDE.md
git commit -m "docs: note mental-powers caster type + Kineticist in CLAUDE.md"
```

---

## Self-review notes

- **Spec coverage:** source (T1), models incl. mental/AC/powers_known/powers_used (T2), data: list+powers+class (T3), AC engine generic (T4), mental engine known/learn/cap/counts (T5), pool helpers (T6), views skip-mental + mental_powers_view + build_sheet (T7), routes incl. rest reset (T8), wizard predicate+caster_entries+post_spells (T9), template section+drawer (T10), source gating (T11), suite+manual+docs (T12). All spec sections map to a task.
- **Nothing keys on `"kineticist"`:** AC engine reads the `armor_class` column; all spell logic branches on `caster_type`/`powers_known`. The string `"kineticist"` appears only in data files and as a class-id argument in tests — never in an engine/view/route/wizard conditional.
- **Type consistency:** `MentalPowerRow`/`MentalPowersBlock` field names match between view (T7) and template (T10); `power_pool`/`spend_power`/`restore_power`/`reset_powers`/`powers_known_cap` names are identical across T5/T6/T7/T8; route form field names (`class_id`, `power_id`) match template forms.
- **Known caveats flagged for the implementer:** reuse existing wizard/route test fixtures where they exist (T8/T9/T11 call this out); confirm template CSS class names against neighbours (T10); the `beginning_spell_count` mental detection uses `row.powers_known is not None` because that function has no `data` param.
