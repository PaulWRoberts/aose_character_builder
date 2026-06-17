# Retainers (Phase B2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add hired classed NPCs (and 0-level normal humans) as **embedded `CharacterSpec`s** on a character, generated with baseline abilities + a Quick Equipment kit, with loyalty, CHA caps, class hiring restrictions, −50% XP, and PC↔retainer item transfer — surfaced as cards in the existing Companions & Holdings section.

**Architecture:** A retainer is a `Retainer` wrapper around a real `CharacterSpec`, so the existing engine (`build_sheet`, `grant_xp`, `roll_pending_hp`/`confirm_level_up`, `armor_class`/`saves`/`hp`, `equip`) works on it unchanged. Generation lives in `aose/engine/retainers.py` and consumes Phase B1's `quick_equipment.roll_kit`. Retainer cards are assembled in `view.py` via a recursive `build_sheet(retainer.spec, data)` to avoid an import cycle with `companions_view`.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, pytest. Tests: `.venv\Scripts\python.exe -m pytest`. App: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`. Ignore the trailing `pytest-current` PermissionError.

**Spec:** [`docs/superpowers/specs/2026-06-17-retainers-design.md`](../specs/2026-06-17-retainers-design.md) (Plan B2).
**Depends on:** Phase B1 (`aose/engine/quick_equipment.py` — `roll_kit`/`apply_kit`).

**Key facts (verified in the codebase):**
- `abilities` keys are **UPPERCASE** (`"STR"`,`"INT"`,`"WIS"`,`"DEX"`,`"CON"`,`"CHA"`) — `Ability` is a str-enum with uppercase values.
- `CompanionsBlock` (in `aose/sheet/companions_view.py`) currently has `animals`/`vehicles`; `companions_block(spec, data) -> CompanionsBlock | None` returns None when both empty; `build_sheet` sets `companions=companions_block(spec, data)` at `view.py:1401`.
- Reuse: `leveling.grant_xp`, `leveling.roll_pending_hp`/`confirm_level_up`, `dice.roll_hp`, `ability_mods.apply_racial_modifiers`, `ability_mods._band`, `equip.equip`/`unequip`, `quick_equipment.roll_kit`/`apply_kit`.
- Routes: `_load_spec_or_404(request, character_id)` → spec; mutate; `save_character(character_id, spec, request.state.characters_dir)`; `return RedirectResponse(f"/character/{character_id}", status_code=303)`.

---

## Checkpoint 1 — Model & data foundation

### Task 1: `Retainer` model + `CharacterSpec.retainers` (self-reference)

**Files:**
- Modify: `aose/models/character.py`
- Modify: `aose/models/__init__.py`
- Test: `tests/test_retainer_model.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_retainer_model.py
from aose.models import CharacterSpec, Retainer


def _spec(name="Hero", **kw):
    return CharacterSpec(
        name=name, abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                              "CON": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": "fighter"}],
        alignment="neutral", **kw)


def test_spec_defaults_to_no_retainers():
    assert _spec().retainers == []


def test_retainer_wraps_a_spec_and_round_trips():
    ret = Retainer(id="r1", spec=_spec("Torchbearer"), loyalty=7, role="light")
    pc = _spec(retainers=[ret])
    again = CharacterSpec.model_validate(pc.model_dump())
    assert again.retainers[0].spec.name == "Torchbearer"
    assert again.retainers[0].loyalty == 7
    assert again.retainers[0].spec.retainers == []   # bounded recursion


def test_old_save_without_retainers_loads():
    raw = _spec().model_dump()
    raw.pop("retainers")
    assert CharacterSpec.model_validate(raw).retainers == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_model.py -q`
Expected: FAIL — `cannot import name 'Retainer'`.

- [ ] **Step 3: Add the model**

In `aose/models/character.py`, add a field to `CharacterSpec` (next to `ruleset`), using a forward reference:

```python
    retainers: list["Retainer"] = Field(default_factory=list)
```

After the `CharacterSpec` class definition (end of file), add the wrapper and rebuild:

```python
class Retainer(BaseModel):
    """A hired NPC the character employs. Wraps a full CharacterSpec so the
    whole engine (sheet, leveling, HP, saves, attacks, equip) works on it
    unchanged. ``loyalty`` is the current (editable) loyalty value; ``role`` is
    a free-text note. A retainer's own ``spec.retainers`` stays empty."""
    model_config = ConfigDict(extra="forbid")

    id: str                       # uuid4 hex
    spec: CharacterSpec
    loyalty: int
    role: str = ""


CharacterSpec.model_rebuild()
```

In `aose/models/__init__.py`, add `Retainer` to the `from .character import (...)` block and to `__all__`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_model.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/models/character.py aose/models/__init__.py tests/test_retainer_model.py
git commit -m "feat(models): Retainer wrapper + CharacterSpec.retainers"
```

---

### Task 2: `normal_human` class

**Files:**
- Create: `data/classes/normal_human.yaml`
- Modify: the wizard class list to exclude it (find the class-selection source — grep `selectable` / class listing in `aose/web/wizard.py`)
- Test: `tests/test_normal_human_class.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_normal_human_class.py
from pathlib import Path
from aose.data.loader import GameData
from aose.engine import saves, hp
from aose.models import CharacterSpec

DATA = GameData.load(Path("data"))


def _nh_spec():
    return CharacterSpec(
        name="Linkboy", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                                   "CON": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": "normal_human", "level": 1,
                                    "hp_rolls": [2]}],
        alignment="neutral")


def test_normal_human_loads_with_nh_saves():
    cls = DATA.classes["normal_human"]
    assert cls.max_level == 1
    row = cls.progression[1]
    assert row.thac0 == 20
    assert row.saves == {"death": 14, "wands": 15, "paralysis": 16,
                         "breath": 17, "spells": 18}


def test_normal_human_saving_throws_are_nh_row():
    spec = _nh_spec()
    st = saves.saving_throws(spec, DATA)
    assert st["death"] == 14 and st["spells"] == 18


def test_normal_human_hp_is_small():
    assert hp.max_hp(_nh_spec(), DATA) >= 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_normal_human_class.py -q`
Expected: FAIL — `KeyError: 'normal_human'`.

- [ ] **Step 3: Create `data/classes/normal_human.yaml`**

```yaml
id: normal_human
name: Normal Human
source: ose_classic_fantasy
prime_requisites: []
ability_requirements: {}
max_level: 1
hit_die: "1d4"
name_level: 1
hp_after_name_level: 0
weapons_allowed: all
armor_allowed: all
shields_allowed: true
progression:
  1:
    xp_required: 0
    thac0: 20
    saves: {death: 14, wands: 15, paralysis: 16, breath: 17, spells: 18}
features:
  - id: zero_level
    name: 0-level
    text: >-
      A normal human has no character class. On gaining experience from an
      adventure, they must choose an adventuring class.
```

- [ ] **Step 4: Exclude `normal_human` from the wizard's class list**

Find where the wizard lists selectable classes (grep `aose/web/wizard.py` for the class step / a `data.classes` iteration). Add a guard skipping `class_id == "normal_human"` so it never appears as a player-choosable class. (It is reachable only via retainer creation.)

- [ ] **Step 5: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_normal_human_class.py -q`
Expected: PASS (3 passed). Also run the wizard tests to confirm the exclusion didn't break the class step:
`.venv\Scripts\python.exe -m pytest tests/ -q -k wizard`

- [ ] **Step 6: Commit**

```bash
git add data/classes/normal_human.yaml aose/web/wizard.py tests/test_normal_human_class.py
git commit -m "feat(data): normal_human 0-level class (retainer-only)"
```

---

### Task 3: `retainer_hiring` rules on `CharClass` + Assassin data

**Files:**
- Modify: `aose/models/character_class.py`
- Modify: `aose/models/__init__.py`
- Modify: `data/classes/assassin.yaml`
- Test: `tests/test_retainer_hiring_model.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_retainer_hiring_model.py
from pathlib import Path
from aose.data.loader import GameData
from aose.models import RetainerHiringRule

DATA = GameData.load(Path("data"))


def test_assassin_encodes_tiered_hiring():
    cls = DATA.classes["assassin"]
    tiers = {r.min_level: r.allows for r in cls.retainer_hiring}
    assert tiers[1] == "none"
    assert tiers[4] == ["assassin"]
    assert tiers[8] == ["assassin", "thief"]
    assert tiers[12] == "any"


def test_default_class_has_no_hiring_rules():
    assert DATA.classes["fighter"].retainer_hiring == []


def test_rule_model_accepts_list_or_keyword():
    assert RetainerHiringRule(min_level=4, allows=["assassin"]).allows == ["assassin"]
    assert RetainerHiringRule(min_level=1, allows="none").allows == "none"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_hiring_model.py -q`
Expected: FAIL — `cannot import name 'RetainerHiringRule'`.

- [ ] **Step 3: Add the model**

In `aose/models/character_class.py`, add (before `CharClass`):

```python
class RetainerHiringRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_level: int                              # hiring PC level the tier applies at
    allows: list[str] | Literal["any", "none"]  # class ids, or "any"/"none"
```

Add to `CharClass`:

```python
    retainer_hiring: list[RetainerHiringRule] = Field(default_factory=list)
```

(`Literal` is already imported in this module; confirm `ConfigDict` is too.) Export `RetainerHiringRule` from `aose/models/__init__.py`.

- [ ] **Step 4: Encode the Assassin rule**

In `data/classes/assassin.yaml`, add a top-level key:

```yaml
retainer_hiring:
  - {min_level: 1, allows: none}
  - {min_level: 4, allows: [assassin]}
  - {min_level: 8, allows: [assassin, thief]}
  - {min_level: 12, allows: any}
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_hiring_model.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add aose/models/character_class.py aose/models/__init__.py data/classes/assassin.yaml tests/test_retainer_hiring_model.py
git commit -m "feat(models): CharClass.retainer_hiring + assassin rule"
```

---

### Task 4: CHA accessors + loyalty modifiers (data) + `initial_loyalty`

**Files:**
- Modify: `aose/engine/ability_mods.py`
- Modify: `data/races/human.yaml`, `data/races/half_orc.yaml`, `data/classes/half_orc.yaml`
- Create: `aose/engine/retainers.py`
- Test: `tests/test_retainer_loyalty.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_retainer_loyalty.py
from pathlib import Path
from aose.data.loader import GameData
from aose.engine import ability_mods, retainers
from aose.models import CharacterSpec

DATA = GameData.load(Path("data"))


def _spec(cha, race="human", cls="fighter"):
    return CharacterSpec(
        name="PC", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                              "CON": 10, "CHA": cha},
        race_id=race, classes=[{"class_id": cls}], alignment="neutral")


def test_cha_accessors():
    assert ability_mods.max_retainers(3) == 1
    assert ability_mods.max_retainers(13) == 5
    assert ability_mods.max_retainers(18) == 7
    assert ability_mods.base_loyalty(9) == 7
    assert ability_mods.base_loyalty(18) == 10


def test_human_grants_plus_one_loyalty():
    # human CHA 9 base loyalty 7, +1 from human → 8
    assert retainers.initial_loyalty(_spec(9, race="human"), "elf", DATA) == 8


def test_half_orc_minus_one_except_for_half_orc_retainers():
    pc = _spec(9, race="half_orc", cls="half_orc")
    assert retainers.initial_loyalty(pc, "human", DATA) == 6      # 7 - 1
    assert retainers.initial_loyalty(pc, "half_orc", DATA) == 7   # exception
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_loyalty.py -q`
Expected: FAIL — accessors / module missing.

- [ ] **Step 3: Add numeric CHA accessors**

In `aose/engine/ability_mods.py`, after the `_CHA_RETAINERS_*` tables, add:

```python
def max_retainers(cha: int) -> int:
    """Maximum retainers the hiring PC may employ (AOSE CHA table)."""
    return int(_band(_CHA_RETAINERS_MAX, cha))


def base_loyalty(cha: int) -> int:
    """Starting loyalty rating for the PC's retainers (AOSE CHA table)."""
    return int(_band(_CHA_RETAINERS_LOYALTY, cha))
```

- [ ] **Step 4: Add the loyalty-modifier data**

Add a feature carrying a `retainer_loyalty_modifier` mechanical to the relevant race/class files. Append to the `features:` list of each:

`data/races/human.yaml`:

```yaml
  - id: human_loyalty
    name: Loyalty
    text: "All of a human's retainers and mercenaries gain a +1 bonus to loyalty and morale."
    mechanical: {retainer_loyalty_modifier: {value: 1}}
```

`data/races/half_orc.yaml` **and** `data/classes/half_orc.yaml` (both, since race and race-as-class are separate stat blocks):

```yaml
  - id: half_orc_distrust
    name: Distrust
    text: "Retainers in a half-orc's employ have their loyalty reduced by one (except retainers who are also half-orcs)."
    mechanical: {retainer_loyalty_modifier: {value: -1, except_same_race: true}}
```

- [ ] **Step 5: Write `aose/engine/retainers.py` (loyalty part)**

```python
"""Retainer generation, loyalty, hiring rules, XP, and PC<->retainer transfer.

A retainer is an embedded CharacterSpec, so this module orchestrates existing
engine helpers (quick_equipment, leveling, ability_mods, equip) rather than
re-implementing them. Cycle-free: models/loader + those engine modules.
"""
from __future__ import annotations

import random
import uuid
from typing import Optional

from aose.data.loader import GameData
from aose.engine import ability_mods
from aose.models import CharacterSpec, Race, Retainer


def _features_with(spec: CharacterSpec, data: GameData, key: str):
    """Yield mechanical dicts carrying ``key`` from the hiring PC's race features
    (all) and class features reached at the class's level. Read-only scan."""
    race = data.races.get(spec.race_id)
    if race is not None:
        for f in race.features:
            if f.mechanical and key in f.mechanical:
                yield f.mechanical[key]
    for entry in spec.classes:
        cls = data.classes.get(entry.class_id)
        if not cls:
            continue
        for f in cls.features:
            if f.gained_at_level <= entry.level and f.mechanical and key in f.mechanical:
                yield f.mechanical[key]


def initial_loyalty(hiring_spec: CharacterSpec, retainer_race_id: str,
                    data: GameData) -> int:
    """Base loyalty from the hiring PC's CHA, adjusted by class/race
    retainer_loyalty_modifier features (human +1; half-orc −1 except for
    half-orc retainers)."""
    cha = hiring_spec.abilities.get("CHA", 9)
    total = ability_mods.base_loyalty(int(cha))
    for mod in _features_with(hiring_spec, data, "retainer_loyalty_modifier"):
        if mod.get("except_same_race") and retainer_race_id == hiring_spec.race_id:
            continue
        total += int(mod.get("value", 0))
    return total
```

> Note: `hiring_spec.abilities` is keyed by the `Ability` enum, whose members
> compare equal to their string values; `.get("CHA")` works because `Ability.CHA
> == "CHA"`. If a strict-key lookup misses, use
> `hiring_spec.abilities[Ability.CHA]` (import `Ability`).

- [ ] **Step 6: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_loyalty.py -q`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
git add aose/engine/ability_mods.py aose/engine/retainers.py data/races/human.yaml data/races/half_orc.yaml data/classes/half_orc.yaml tests/test_retainer_loyalty.py
git commit -m "feat(engine): CHA retainer accessors + data-driven loyalty modifiers"
```

**CHECKPOINT 1 complete** — model + data + loyalty. Stop for review.

---

## Checkpoint 2 — generation, XP, transfer

### Task 5: `generate_retainer`

**Files:**
- Modify: `aose/engine/retainers.py`
- Test: `tests/test_retainer_generation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_retainer_generation.py
from pathlib import Path
import random
from aose.data.loader import GameData
from aose.engine import retainers
from aose.models import CharacterSpec

DATA = GameData.load(Path("data"))


def _pc(level=5, cha=13):
    return CharacterSpec(
        name="Boss", abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10,
                                "CON": 10, "CHA": cha},
        race_id="human", classes=[{"class_id": "fighter", "level": level}],
        alignment="neutral")


def test_generate_fighter_retainer():
    pc = _pc(level=3, cha=13)
    ret = retainers.generate_retainer(
        name="Sten", class_ids=["fighter"], level=2, race_id="human",
        alignment="neutral", hiring_spec=pc, data=DATA, rng=random.Random(1))
    assert ret.spec.classes[0].class_id == "fighter"
    assert ret.spec.classes[0].level == 2
    assert len(ret.spec.classes[0].hp_rolls) == 2     # one per level
    assert all(v == 10 for k, v in ret.spec.abilities.items()
               if k not in ("STR",))                  # baseline 10 except bumps
    assert ret.spec.inventory                         # quick-equipment kit applied
    assert ret.loyalty == 8                            # human CHA13 base 8, +1 human... = 9? see note
    assert ret.spec.ruleset == pc.ruleset             # inherited snapshot


def test_generate_meets_class_requirements():
    pc = _pc()
    # a class with an ability requirement raises that score to the minimum
    cls = next(c for c in DATA.classes.values() if c.ability_requirements)
    req_ab, req_val = next(iter(cls.ability_requirements.items()))
    ret = retainers.generate_retainer(
        name="Req", class_ids=[cls.id], level=1, race_id="human",
        alignment="neutral", hiring_spec=pc, data=DATA, rng=random.Random(2))
    assert ret.spec.abilities[req_ab.value] >= req_val


def test_normal_human_retainer_level_one():
    pc = _pc()
    ret = retainers.generate_retainer(
        name="Boy", class_ids=["normal_human"], level=1, race_id="human",
        alignment="neutral", hiring_spec=pc, data=DATA, rng=random.Random(3))
    assert ret.spec.classes[0].class_id == "normal_human"
```

> Adjust the `loyalty` assertion to the correct expected value once `initial_loyalty` is wired (human CHA 13 → base 8, +1 human = 9). Use 9.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_generation.py -q`
Expected: FAIL — `generate_retainer` not defined.

- [ ] **Step 3: Implement `generate_retainer`**

Add to `aose/engine/retainers.py` (imports: `from aose.engine import quick_equipment; from aose.engine.ability_mods import apply_racial_modifiers; from aose.engine.dice import roll_hp; from aose.models import ClassEntry`):

```python
_ABILITIES = ["STR", "INT", "WIS", "DEX", "CON", "CHA"]


def generate_retainer(*, name: str, class_ids: list[str], level: int,
                      race_id: str, alignment: str,
                      hiring_spec: CharacterSpec, data: GameData,
                      rng: Optional[random.Random] = None) -> Retainer:
    rng = rng or random.Random()
    primary = data.classes[class_ids[0]]

    # 1. baseline 10s
    abilities = {a: 10 for a in _ABILITIES}

    # 2. race-as-class vs split: a race-locked class is self-contained (no racial
    #    mods); a split race+class applies Advanced racial modifiers.
    race_locked = primary.race_locked is not None
    if race_locked:
        race_id = primary.race_locked
    elif hiring_spec.ruleset.separate_race_class and race_id in data.races:
        abilities = apply_racial_modifiers(abilities, data.races[race_id])

    # 3. bump each class's ability_requirements to its minimum (post-racial)
    for cid in class_ids:
        for ab, req in data.classes[cid].ability_requirements.items():
            k = ab.value
            if abilities.get(k, 0) < req:
                abilities[k] = req

    # 4. class entries: roll `level` hit dice (capped at name level); xp set to
    #    the level's threshold so XP is consistent with the level.
    entries: list[ClassEntry] = []
    for cid in class_ids:
        cls = data.classes[cid]
        n_rolls = min(level, cls.name_level)
        rolls = [roll_hp(cls.hit_die, rng) for _ in range(max(1, n_rolls))]
        xp = cls.progression[level].xp_required if level in cls.progression else 0
        entries.append(ClassEntry(class_id=cid, level=level, hp_rolls=rolls, xp=xp))

    spec = CharacterSpec(
        name=name, abilities=abilities, race_id=race_id, classes=entries,
        alignment=alignment, ruleset=hiring_spec.ruleset.model_copy(deep=True))

    # 5. quick-equipment kit
    kit = quick_equipment.roll_kit(class_ids[0], data, rng=rng)
    quick_equipment.apply_kit(spec, kit)

    # 6. loyalty
    loyalty = initial_loyalty(hiring_spec, race_id, data)

    return Retainer(id=uuid.uuid4().hex, spec=spec, loyalty=loyalty, role="")
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_generation.py -q`
Expected: PASS (fix the loyalty assertion to 9 if needed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/retainers.py tests/test_retainer_generation.py
git commit -m "feat(engine): generate_retainer (abilities, HP, level, kit, loyalty)"
```

---

### Task 6: `allowed_retainer_classes`

**Files:**
- Modify: `aose/engine/retainers.py`
- Test: `tests/test_retainer_hiring.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_retainer_hiring.py
from pathlib import Path
from aose.data.loader import GameData
from aose.engine import retainers
from aose.models import CharacterSpec

DATA = GameData.load(Path("data"))


def _pc(cls, level):
    return CharacterSpec(
        name="PC", abilities={"STR": 12, "INT": 12, "WIS": 10, "DEX": 12,
                              "CON": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": cls, "level": level}],
        alignment="neutral")


def test_fighter_unrestricted():
    assert retainers.allowed_retainer_classes(_pc("fighter", 1), DATA) == "any"


def test_assassin_tiers():
    assert retainers.allowed_retainer_classes(_pc("assassin", 2), DATA) == set()
    assert retainers.allowed_retainer_classes(_pc("assassin", 5), DATA) == {"assassin"}
    assert retainers.allowed_retainer_classes(_pc("assassin", 9), DATA) == {"assassin", "thief"}
    assert retainers.allowed_retainer_classes(_pc("assassin", 12), DATA) == "any"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_hiring.py -q`
Expected: FAIL — not defined.

- [ ] **Step 3: Implement**

Add to `aose/engine/retainers.py`:

```python
def allowed_retainer_classes(hiring_spec: CharacterSpec, data: GameData):
    """Effective hiring allowance across the PC's classes (most permissive wins):
    returns "any", or a set of class ids (empty set == may not hire). A class
    with no retainer_hiring rules is unrestricted ("any")."""
    per_class = []
    for entry in hiring_spec.classes:
        cls = data.classes.get(entry.class_id)
        if not cls or not cls.retainer_hiring:
            return "any"                      # an unrestricted class permits all
        tier = None
        for rule in sorted(cls.retainer_hiring, key=lambda r: r.min_level):
            if entry.level >= rule.min_level:
                tier = rule
        if tier is None or tier.allows == "any":
            return "any"
        per_class.append(set() if tier.allows == "none" else set(tier.allows))
    union: set = set()
    for s in per_class:
        union |= s
    return union
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_hiring.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/retainers.py tests/test_retainer_hiring.py
git commit -m "feat(engine): allowed_retainer_classes (hiring restrictions)"
```

---

### Task 7: XP −50%, level-up, promote normal human

**Files:**
- Modify: `aose/engine/retainers.py`
- Test: `tests/test_retainer_xp.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_retainer_xp.py
from pathlib import Path
import random
from aose.data.loader import GameData
from aose.engine import retainers
from aose.models import CharacterSpec

DATA = GameData.load(Path("data"))


def _pc():
    return CharacterSpec(
        name="Boss", abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10,
                                "CON": 10, "CHA": 13},
        race_id="human", classes=[{"class_id": "fighter", "level": 5}],
        alignment="neutral")


def test_grant_retainer_xp_halves_awards():
    ret = retainers.generate_retainer(
        name="X", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=_pc(), data=DATA, rng=random.Random(1))
    before = ret.spec.classes[0].xp
    retainers.grant_retainer_xp(ret, DATA, 1000)     # fighter prime-req mult ~1.0
    assert ret.spec.classes[0].xp == before + 500    # -50% penalty


def test_promote_normal_human_swaps_class_keeping_xp():
    ret = retainers.generate_retainer(
        name="Boy", class_ids=["normal_human"], level=1, race_id="human",
        alignment="neutral", hiring_spec=_pc(), data=DATA, rng=random.Random(2))
    ret.spec.classes[0].xp = 300
    retainers.promote_normal_human(ret, "fighter", DATA, rng=random.Random(2))
    assert ret.spec.classes[0].class_id == "fighter"
    assert ret.spec.classes[0].level == 1
    assert ret.spec.classes[0].xp == 300
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_xp.py -q`
Expected: FAIL — not defined.

- [ ] **Step 3: Implement**

Add to `aose/engine/retainers.py` (import `from aose.engine import leveling`):

```python
def grant_retainer_xp(retainer: Retainer, data: GameData, amount: int) -> None:
    """Award XP to a retainer with the AOSE −50% penalty on positive awards
    (retainers follow orders rather than solve problems). Clawbacks pass through."""
    adjusted = amount // 2 if amount > 0 else amount
    leveling.grant_xp(retainer.spec, data, adjusted)


def promote_normal_human(retainer: Retainer, new_class_id: str, data: GameData,
                         rng: Optional[random.Random] = None) -> None:
    """A 0-level normal human 'chooses a class' on gaining XP: replace the
    normal_human entry with a level-1 entry of the new class (fresh HD roll),
    keeping accrued XP, and bump abilities to the new class's requirements."""
    rng = rng or random.Random()
    entry = retainer.spec.classes[0]
    if entry.class_id != "normal_human":
        raise ValueError("Only a normal human can be promoted")
    cls = data.classes[new_class_id]
    kept_xp = entry.xp
    retainer.spec.classes[0] = ClassEntry(
        class_id=new_class_id, level=1,
        hp_rolls=[roll_hp(cls.hit_die, rng)], xp=kept_xp)
    for ab, req in cls.ability_requirements.items():
        if retainer.spec.abilities.get(ab.value, 0) < req:
            retainer.spec.abilities[ab.value] = req
```

> Leveling a retainer up uses the existing `leveling.roll_pending_hp` /
> `confirm_level_up` on `retainer.spec` — no retainer-specific wrapper needed; the
> routes (Task 10) call them directly.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_xp.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/retainers.py tests/test_retainer_xp.py
git commit -m "feat(engine): retainer XP -50%, promote normal human"
```

---

### Task 8: PC ↔ retainer item transfer

**Files:**
- Modify: `aose/engine/retainers.py`
- Test: `tests/test_retainer_transfer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_retainer_transfer.py
from pathlib import Path
import random
from aose.data.loader import GameData
from aose.engine import retainers
from aose.models import CharacterSpec

DATA = GameData.load(Path("data"))


def _pc_with_retainer():
    pc = CharacterSpec(
        name="Boss", abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10,
                                "CON": 10, "CHA": 13},
        race_id="human", classes=[{"class_id": "fighter", "level": 3}],
        alignment="neutral", inventory=["torch"])
    ret = retainers.generate_retainer(
        name="Sten", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=pc, data=DATA, rng=random.Random(1))
    pc.retainers = [ret]
    return pc


def test_transfer_to_retainer_moves_item():
    pc = _pc_with_retainer()
    rid = pc.retainers[0].id
    retainers.transfer_to_retainer(pc, rid, "torch", DATA)
    assert "torch" not in pc.inventory
    assert "torch" in pc.retainers[0].spec.inventory


def test_transfer_to_pc_moves_item_back():
    pc = _pc_with_retainer()
    rid = pc.retainers[0].id
    pc.retainers[0].spec.inventory.append("torch")
    retainers.transfer_to_pc(pc, rid, "torch", DATA)
    assert "torch" in pc.inventory


def test_transfer_missing_item_raises():
    pc = _pc_with_retainer()
    import pytest
    with pytest.raises(ValueError):
        retainers.transfer_to_retainer(pc, pc.retainers[0].id, "nope", DATA)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_transfer.py -q`
Expected: FAIL — not defined.

- [ ] **Step 3: Implement**

Add to `aose/engine/retainers.py`:

```python
def _find_retainer(pc_spec: CharacterSpec, retainer_id: str) -> Retainer:
    for r in pc_spec.retainers:
        if r.id == retainer_id:
            return r
    raise ValueError(f"No retainer with id {retainer_id!r}")


def transfer_to_retainer(pc_spec: CharacterSpec, retainer_id: str,
                         item_id: str, data: GameData) -> None:
    """Move one copy of a loose PC inventory item onto the retainer. Source must
    be the PC's loose inventory (unequip/unstash first, as elsewhere)."""
    ret = _find_retainer(pc_spec, retainer_id)
    if item_id not in pc_spec.inventory:
        raise ValueError(f"{item_id!r} is not in your inventory")
    pc_spec.inventory.remove(item_id)
    ret.spec.inventory.append(item_id)


def transfer_to_pc(pc_spec: CharacterSpec, retainer_id: str,
                   item_id: str, data: GameData) -> None:
    """Move one copy of a loose retainer inventory item back to the PC."""
    ret = _find_retainer(pc_spec, retainer_id)
    if item_id not in ret.spec.inventory:
        raise ValueError(f"{item_id!r} is not in the retainer's inventory")
    if item_id in ret.spec.equipped.values():
        raise ValueError(f"{item_id!r} is equipped by the retainer; unequip first")
    ret.spec.inventory.remove(item_id)
    pc_spec.inventory.append(item_id)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_transfer.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/retainers.py tests/test_retainer_transfer.py
git commit -m "feat(engine): PC<->retainer item transfer"
```

**CHECKPOINT 2 complete** — generation, XP, transfer all tested. Stop for review.

---

## Checkpoint 3 — view & routes

### Task 9: `RetainerCard` + recursive view wiring

**Files:**
- Modify: `aose/sheet/companions_view.py` (add `RetainerCard`, extend `CompanionsBlock`)
- Modify: `aose/sheet/view.py` (build retainer cards via recursive `build_sheet`)
- Test: `tests/test_retainer_card.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_retainer_card.py
from pathlib import Path
import random
from aose.data.loader import GameData
from aose.engine import retainers
from aose.sheet.view import build_sheet
from aose.models import CharacterSpec

DATA = GameData.load(Path("data"))


def _pc():
    return CharacterSpec(
        name="Boss", abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10,
                                "CON": 10, "CHA": 13},
        race_id="human", classes=[{"class_id": "fighter", "level": 3}],
        alignment="neutral")


def test_sheet_has_retainer_card_with_derived_stats():
    pc = _pc()
    ret = retainers.generate_retainer(
        name="Sten", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=pc, data=DATA, rng=random.Random(1))
    pc.retainers = [ret]
    sheet = build_sheet(pc, DATA)
    assert sheet.companions is not None
    card = sheet.companions.retainers[0]
    assert card.name == "Sten"
    assert card.loyalty == ret.loyalty
    assert card.hp_max >= 1
    assert card.ac_descending  # has an AC
    assert "death" in card.saves


def test_max_retainers_shown():
    pc = _pc()       # CHA 13 → 5 max
    sheet = build_sheet(pc, DATA)  # no retainers → companions may be None
    # build with one retainer to populate the block
    ret = retainers.generate_retainer(
        name="A", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=pc, data=DATA, rng=random.Random(1))
    pc.retainers = [ret]
    sheet = build_sheet(pc, DATA)
    assert sheet.companions.max_retainers == 5
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_card.py -q`
Expected: FAIL — `RetainerCard`/`max_retainers` missing.

- [ ] **Step 3: Add `RetainerCard` and extend `CompanionsBlock`**

In `aose/sheet/companions_view.py`:

```python
class RetainerCard(BaseModel):
    id: str
    name: str
    descriptor: str          # "Human Fighter 1" or "0-level Normal Human"
    is_normal_human: bool
    ac_descending: int
    ac_ascending: int
    hp_current: int
    hp_max: int
    thac0: int
    saves: dict[str, int]
    equipped: dict[str, str]     # slot -> item name (display)
    loyalty: int
    role: str
    inventory: list[InventoryRow]
    xp: int
```

Extend `CompanionsBlock`:

```python
class CompanionsBlock(BaseModel):
    animals: list[AnimalCard] = []
    vehicles: list[VehicleCard] = []
    retainers: list[RetainerCard] = []
    max_retainers: int = 0
```

> Do **not** call `build_sheet` from this module (it would create an import cycle
> with `view.py`). The retainer cards are assembled in `view.py` — see Step 4.

- [ ] **Step 4: Wire retainer cards in `view.py`**

In `aose/sheet/view.py`, add a helper near `build_sheet` (it may call `build_sheet` recursively — same module, no cycle):

```python
def _retainer_cards(spec, data):
    from aose.sheet.companions_view import RetainerCard
    from aose.engine.shop import _build_row
    from aose.engine import monster_stats as ms
    cards = []
    for r in spec.retainers:
        rs = build_sheet(r.spec, data)              # recursive; bounded (empty retainers)
        entry = r.spec.classes[0]
        cls = data.classes.get(entry.class_id)
        is_nh = entry.class_id == "normal_human"
        race_name = data.races[r.spec.race_id].name if r.spec.race_id in data.races else ""
        descriptor = ("0-level Normal Human" if is_nh
                      else f"{race_name} {cls.name} {entry.level}".strip())
        equipped_names = {slot: data.items[i].name
                          for slot, i in r.spec.equipped.items() if i in data.items}
        from collections import Counter
        inv_rows = [_build_row(i, n, data) for i, n in Counter(r.spec.inventory).items()]
        inv_rows.sort(key=lambda x: x.name)
        cards.append(RetainerCard(
            id=r.id, name=r.spec.name, descriptor=descriptor, is_normal_human=is_nh,
            ac_descending=rs.ac_descending, ac_ascending=rs.ac_ascending,
            hp_current=rs.current_hp, hp_max=rs.max_hp, thac0=rs.thac0,
            saves=rs.saves_dict, equipped=equipped_names,
            loyalty=r.loyalty, role=r.role, inventory=inv_rows, xp=entry.xp))
    return cards
```

> Adjust the `rs.*` attribute names to the real `CharacterSheet` fields (grep
> `class CharacterSheet` in `view.py`): AC (descending/ascending), current/max HP,
> THAC0, and the saves mapping. Use whatever the sheet already exposes — do not add
> new derivations.

Then, where `build_sheet` currently sets `companions=companions_block(spec, data)`
(`view.py:1401`), replace with:

```python
        companions=_with_retainers(companions_block(spec, data), spec, data),
```

and add the helper:

```python
def _with_retainers(block, spec, data):
    from aose.sheet.companions_view import CompanionsBlock
    from aose.engine.ability_mods import max_retainers
    cards = _retainer_cards(spec, data)
    if block is None and not cards:
        return None
    block = block or CompanionsBlock()
    block.retainers = cards
    cha = int(spec.abilities.get("CHA", 9))
    block.max_retainers = max_retainers(cha)
    return block
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_card.py -q`
Expected: PASS. Then full suite: `.venv\Scripts\python.exe -m pytest tests/ -q`.

- [ ] **Step 6: Commit**

```bash
git add aose/sheet/companions_view.py aose/sheet/view.py tests/test_retainer_card.py
git commit -m "feat(sheet): retainer cards via recursive build_sheet"
```

---

### Task 10: Retainer routes

**Files:**
- Modify: `aose/web/routes.py`
- Test: `tests/test_retainer_routes.py`

- [ ] **Step 1: Write the failing test** (mirror the Phase A route-test pattern in `tests/test_companion_routes.py`)

```python
# tests/test_retainer_routes.py
from pathlib import Path
import io
import pytest
from fastapi.testclient import TestClient
from aose.web.app import create_app
from aose.data.loader import GameData
from aose.models import CharacterSpec


@pytest.fixture
def client():
    app = create_app()
    app.state.game_data = GameData.load(Path("data"))
    return TestClient(app)


def _make_char(client) -> str:
    spec = CharacterSpec(
        name="Boss", abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10,
                                "CON": 10, "CHA": 13},
        race_id="human", classes=[{"class_id": "fighter", "level": 3}],
        alignment="neutral")
    resp = client.post("/import", files={
        "file": ("c.json", io.BytesIO(spec.model_dump_json().encode()),
                 "application/json")}, follow_redirects=False)
    return resp.headers["location"].rsplit("/", 1)[-1]


def test_add_retainer_route(client):
    cid = _make_char(client)
    resp = client.post(f"/character/{cid}/retainer/add", data={
        "name": "Sten", "class_id": "fighter", "level": "1",
        "race_id": "human", "alignment": "neutral"}, follow_redirects=False)
    assert resp.status_code == 303
    assert "Sten" in client.get(f"/character/{cid}").text


def test_add_normal_human_retainer(client):
    cid = _make_char(client)
    client.post(f"/character/{cid}/retainer/add", data={
        "name": "Boy", "class_id": "normal_human", "level": "1",
        "race_id": "human", "alignment": "neutral"})
    assert "Boy" in client.get(f"/character/{cid}").text
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_routes.py -q`
Expected: FAIL — route 404.

- [ ] **Step 3: Add routes to `aose/web/routes.py`**

Add `from aose.engine import retainers as retainers_engine`. Then (all mirror the `hp/damage` pattern — load, mutate, save, 303):

```python
@router.post("/character/{character_id}/retainer/add")
async def retainer_add(request: Request, character_id: str,
                       name: str = Form(...), class_id: str = Form(...),
                       level: int = Form(1), race_id: str = Form("human"),
                       alignment: str = Form("neutral")):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    pc_level = max((e.level for e in spec.classes), default=1)
    if class_id != "normal_human" and level > pc_level:
        raise HTTPException(400, "A retainer may not exceed your level")
    try:
        ret = retainers_engine.generate_retainer(
            name=name, class_ids=[class_id], level=level, race_id=race_id,
            alignment=alignment, hiring_spec=spec, data=data)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))
    spec.retainers.append(ret)
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/retainer/{retainer_id}/remove")
async def retainer_remove(request: Request, character_id: str, retainer_id: str):
    spec = _load_spec_or_404(request, character_id)
    spec.retainers = [r for r in spec.retainers if r.id != retainer_id]
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/retainer/{retainer_id}/loyalty")
async def retainer_loyalty(request: Request, character_id: str, retainer_id: str,
                           value: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    for r in spec.retainers:
        if r.id == retainer_id:
            r.loyalty = value
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/retainer/{retainer_id}/role")
async def retainer_role(request: Request, character_id: str, retainer_id: str,
                        role: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    for r in spec.retainers:
        if r.id == retainer_id:
            r.role = role
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/retainer/{retainer_id}/xp")
async def retainer_xp(request: Request, character_id: str, retainer_id: str,
                      amount: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    for r in spec.retainers:
        if r.id == retainer_id:
            retainers_engine.grant_retainer_xp(r, data, amount)
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/retainer/{retainer_id}/levelup")
async def retainer_levelup(request: Request, character_id: str, retainer_id: str,
                           class_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    from aose.engine import leveling
    for r in spec.retainers:
        if r.id == retainer_id:
            try:
                leveling.level_up(r.spec, data, class_id)
            except ValueError as e:
                raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/retainer/{retainer_id}/promote")
async def retainer_promote(request: Request, character_id: str, retainer_id: str,
                           class_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    for r in spec.retainers:
        if r.id == retainer_id:
            try:
                retainers_engine.promote_normal_human(r, class_id, data)
            except ValueError as e:
                raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/retainer/{retainer_id}/give")
async def retainer_give(request: Request, character_id: str, retainer_id: str,
                        item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        retainers_engine.transfer_to_retainer(spec, retainer_id, item_id, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/retainer/{retainer_id}/take")
async def retainer_take(request: Request, character_id: str, retainer_id: str,
                        item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        retainers_engine.transfer_to_pc(spec, retainer_id, item_id, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_routes.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_retainer_routes.py
git commit -m "feat(routes): retainer add/remove/loyalty/role/xp/levelup/promote/transfer"
```

**CHECKPOINT 3 complete** — derivations + routes. Stop for review.

---

## Checkpoint 4 — UI, print, docs

### Task 11: Retainer cards + add-retainer form in the Companions section

**Files:**
- Read first: `docs/STYLE-GUIDE.md`
- Modify: `aose/web/templates/_companions.html`
- Modify: `aose/web/static/sheet.css` (reuse `.companion-card` styles from Phase A)
- Manual verification via the preview workflow

- [ ] **Step 1: Read the style guide** (overlay model, group/inked-bar pattern, destructive actions in the drawer).

- [ ] **Step 2: Add a retainers block to `_companions.html`**

Render `sheet.companions.retainers` and the cap, plus an Add-retainer form. Append inside the existing `companions-group` body (after the vehicles loop), using the `cid` variable the template already uses:

```html
{% if sheet.companions %}
  <div class="companions-retainers">
    <h3 class="companions-subbar">
      Retainers
      <span class="companion-stat">{{ sheet.companions.retainers|length }} / {{ sheet.companions.max_retainers }}</span>
      {% if sheet.companions.retainers|length > sheet.companions.max_retainers %}
        <span class="warn">over CHA limit</span>
      {% endif %}
    </h3>

    {% for r in sheet.companions.retainers %}
    <article class="companion-card" data-kind="retainer">
      <header class="companion-head">
        <span class="companion-name">{{ r.name }}</span>
        <span class="companion-sub">{{ r.descriptor }}</span>
        <span class="companion-stat">AC {{ r.ac_descending }} [{{ r.ac_ascending }}]</span>
        <span class="companion-stat">HP {{ r.hp_current }}/{{ r.hp_max }}</span>
        <span class="companion-stat">THAC0 {{ r.thac0 }}</span>
        <span class="companion-stat">Loyalty {{ r.loyalty }}</span>
      </header>
      <div class="companion-saves">
        D {{ r.saves.death }} · W {{ r.saves.wands }} · P {{ r.saves.paralysis }}
        · B {{ r.saves.breath }} · S {{ r.saves.spells }}
      </div>
      {% if r.equipped %}
      <div class="companion-gear">
        {% for slot, nm in r.equipped.items() %}{{ slot }}: {{ nm }}{% if not loop.last %} · {% endif %}{% endfor %}
      </div>
      {% endif %}

      <form method="post" action="/character/{{ cid }}/retainer/{{ r.id }}/loyalty" class="inline-form">
        <label>Loyalty <input type="number" name="value" value="{{ r.loyalty }}" style="width:3.5rem"></label>
        <button class="chip">Set</button>
      </form>

      <form method="post" action="/character/{{ cid }}/retainer/{{ r.id }}/role" class="inline-form">
        <input type="text" name="role" value="{{ r.role }}" placeholder="role">
        <button class="chip">Save</button>
      </form>

      {% if r.is_normal_human %}
      <form method="post" action="/character/{{ cid }}/retainer/{{ r.id }}/promote" class="inline-form">
        <label>Promote to
          <select name="class_id">
            {% for c in sheet.retainer_class_options %}<option value="{{ c.id }}">{{ c.name }}</option>{% endfor %}
          </select>
        </label>
        <button class="chip">Promote</button>
      </form>
      {% endif %}

      <details class="companion-load">
        <summary>Inventory ({{ r.inventory|length }})</summary>
        <ul class="contents-list">
          {% for row in r.inventory %}
          <li>{{ row.name }} ×{{ row.count }}
            <form method="post" action="/character/{{ cid }}/retainer/{{ r.id }}/take" class="inline-form">
              <input type="hidden" name="item_id" value="{{ row.id }}">
              <button class="chip">Take</button>
            </form>
          </li>
          {% endfor %}
        </ul>
        <form method="post" action="/character/{{ cid }}/retainer/{{ r.id }}/give" class="inline-form">
          <label>Give
            <select name="item_id">
              {% for row in sheet.inventory.carried %}<option value="{{ row.id }}">{{ row.name }}</option>{% endfor %}
            </select>
          </label>
          <button class="chip">Give</button>
        </form>
      </details>
    </article>
    {% endfor %}

    <form method="post" action="/character/{{ cid }}/retainer/add" class="retainer-add inline-form">
      <input type="text" name="name" placeholder="name" required>
      <select name="class_id">
        {% for c in sheet.retainer_class_options %}<option value="{{ c.id }}">{{ c.name }}</option>{% endfor %}
      </select>
      <input type="number" name="level" value="1" min="0" style="width:3.5rem">
      <input type="hidden" name="race_id" value="{{ sheet.race_id }}">
      <input type="hidden" name="alignment" value="neutral">
      <button class="chip">Add retainer</button>
    </form>
  </div>
{% endif %}
```

This template references two new sheet fields: `sheet.retainer_class_options`
(list of `{id, name}` filtered by `allowed_retainer_classes`, always including
`normal_human`) and the existing `sheet.race_id`/`sheet.inventory.carried`. Add
`retainer_class_options` in `build_sheet`:

```python
# in view.py build_sheet, compute and pass through:
from aose.engine.retainers import allowed_retainer_classes
_allowed = allowed_retainer_classes(spec, data)
retainer_class_options = [
    {"id": c.id, "name": c.name}
    for c in data.classes.values()
    if c.id == "normal_human" or _allowed == "any" or c.id in _allowed
]
```

Add `retainer_class_options: list[dict] = []` to `CharacterSheet` and set it.
(For a `set()` allowance — e.g. assassin L1-3 — only `normal_human` is offered.)

- [ ] **Step 3: Add styles** to `aose/web/static/sheet.css`:

```css
.companions-subbar { margin: .75rem 0 .25rem; font-size: .95rem;
  border-bottom: 1px solid var(--rule); }
.companion-gear { color: var(--ink-2); font-size: .9em; margin-top: .25rem; }
.retainer-add { margin-top: .5rem; flex-wrap: wrap; }
.warn { color: var(--accent, #a33); font-size: .85em; }
```

- [ ] **Step 4: Manual verification**

Run the app (`.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`) and, via the preview workflow: add a fighter retainer (confirm a real AC/HP/saves stat block from its generated kit), add a normal-human retainer and promote it to a class, set loyalty, give it a torch and take it back. Screenshot the section.

- [ ] **Step 5: Run full suite + commit**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`

```bash
git add aose/web/templates/_companions.html aose/web/static/sheet.css aose/sheet/view.py
git commit -m "feat(sheet): retainer cards, add-retainer + transfer UI"
```

---

### Task 12: Print sheet + docs + final verification

**Files:**
- Modify: `aose/web/templates/sheet_print.html`
- Modify: `docs/CHANGELOG.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md`

- [ ] **Step 1: Add a retainer block to `sheet_print.html`** (after the Phase A companions block):

```html
{% if sheet.companions and sheet.companions.retainers %}
<section class="print-retainers">
  <h3>Retainers</h3>
  {% for r in sheet.companions.retainers %}
  <p><strong>{{ r.name }}</strong> ({{ r.descriptor }}) — AC {{ r.ac_descending }}
     [{{ r.ac_ascending }}], HP {{ r.hp_current }}/{{ r.hp_max }}, THAC0 {{ r.thac0 }},
     Loyalty {{ r.loyalty }}.
     Save D{{ r.saves.death }} W{{ r.saves.wands }} P{{ r.saves.paralysis }}
     B{{ r.saves.breath }} S{{ r.saves.spells }}.
     {% if r.equipped %}Wearing/holding: {{ r.equipped.values()|join(', ') }}.{% endif %}</p>
  {% endfor %}
</section>
{% endif %}
```

- [ ] **Step 2: Update docs**

- `docs/CHANGELOG.md`: top row — date `2026-06-17`, "Retainers + Quick Equipment (Companions & Holdings Phase B)", branch `feat/companions-and-holdings`, slugs `retainers` / `quick-equipment`.
- `docs/ARCHITECTURE.md`: extend the Companions & Holdings section — retainers as embedded `CharacterSpec` (`Retainer` wrapper, `CharacterSpec.retainers`, recursion bound), `normal_human` 0-level class, `engine/retainers.py` (generation/loyalty/hiring/XP/transfer), `quick_equipment.py` (data + heuristic), CHA accessors, retainer cards via recursive `build_sheet`.
- `CLAUDE.md`: under Storage shapes, add a `retainers` bullet (embedded CharacterSpec + loyalty/role); under the engine module list add `quick_equipment`, `retainers`, `monster_stats`.

- [ ] **Step 3: Full verification**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q` (ignore the trailing `pytest-current` PermissionError). Then exercise the app end-to-end via the preview workflow (add retainer → equip from kit → XP → level-up → transfer → print) and screenshot.

- [ ] **Step 4: Commit**

```bash
git add aose/web/templates/sheet_print.html docs/CHANGELOG.md docs/ARCHITECTURE.md CLAUDE.md
git commit -m "docs: retainers + quick equipment (phase B) landed"
```

---

## Self-review notes (for the implementer)

- **Spec coverage:** Retainer model + recursion (T1), normal_human (T2), hiring rules (T3, T6), CHA accessors + loyalty mods (T4), generation w/ Quick Equipment (T5), XP −50% + promote (T7), transfer (T8), cards via recursive build_sheet (T9), routes (T10), UI (T11), print + docs (T12). Resolved decisions honoured: 3d6 gold (B1), spellbook left empty (no spell-prep code here), proficiency heuristic (B1).
- **Type consistency:** `retainers.py` API used by routes/view — `generate_retainer(name=, class_ids=, level=, race_id=, alignment=, hiring_spec=, data=, rng=)`, `initial_loyalty`, `allowed_retainer_classes`, `grant_retainer_xp`, `promote_normal_human`, `transfer_to_retainer`/`transfer_to_pc` — match across tasks. `RetainerCard`/`CompanionsBlock.retainers`/`max_retainers` consistent between T9 and T11. Abilities keyed UPPERCASE throughout.
- **Known risks / confirm during build:** (1) the `_retainer_cards` helper uses placeholder `CharacterSheet` attribute names (`ac_descending`, `current_hp`, `max_hp`, `thac0`, `saves_dict`) — grep `class CharacterSheet` in `view.py` and use the real field names; do not add new derivations. (2) `apply_racial_modifiers` is applied only in split (non-race-locked) mode — confirm this matches how the wizard finalises abilities for a normal character (grep the wizard's ability-finalisation). (3) Route tests assume the `/import` round-trip persists into the workspace dir the TestClient uses (same approach as Phase A's `tests/test_companion_routes.py`) — reuse that fixture pattern if it differs. (4) `_load_table` (used implicitly via B1) and the `dice.roll` `1d{n}` idiom are already verified.
```
