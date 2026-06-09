# Gargantua Feature Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate the gargantua's Rock Throwing (an always-available synthetic thrown weapon) and Open Doors (a +1 STR-category bump on the chance shown in the STR ability modal), driven entirely by generic `mechanical` data so no engine module names the gargantua.

**Architecture:** A new `_reached_features` generator in `features.py` centralises "which features apply" (class features by level; race features unless race-as-class). Two thin collectors read generic `mechanical` keys off it: `feature_weapons` (→ synthetic `AttackProfile`s in `attacks.py`, like Unarmed) and `open_doors_category_bonus` (→ a band bump + note in the STR ability table). The gargantua YAML carries the data.

**Tech Stack:** Python 3, Pydantic v2 models, pytest. Run tests with the venv interpreter:
`.venv\Scripts\python.exe -m pytest tests/ -q` (bare `pytest`/`uvicorn` won't work — the venv isn't auto-activated). The trailing `PermissionError` on `pytest-current` is a known Windows quirk — ignore it.

---

## File Structure

- `data/races/gargantua.yaml`, `data/classes/gargantua.yaml` — restructure the `rock_throwing` feature's `mechanical` block into a generic `weapon` descriptor. `open_doors` already carries `str_category_bonus: 1`.
- `aose/engine/features.py` — add `_reached_features`, `feature_weapons`, `open_doors_category_bonus`.
- `aose/engine/attacks.py` — add `_feature_weapon_profile`; have `attack_profiles` emit feature weapons.
- `aose/engine/ability_mods.py` — add `_band_bumped`; extend `ability_table_row` with `open_doors_category_bonus`.
- `aose/sheet/view.py` — add `AbilityTableCell.note`; thread the bonus + note in `build_sheet`.
- `aose/web/templates/sheet.html` — render the cell note in the ability modal.
- Tests: `tests/test_feature_modifiers.py` (feature collectors + rock profiles), `tests/test_ability_tables.py` (open-doors bump), `tests/test_sheet_view.py` (end-to-end note) — create if absent.
- Docs: `docs/CHANGELOG.md`, `docs/ARCHITECTURE.md`.

---

## Task 1: Data restructure + feature collectors

Restructure the rock data into a generic weapon descriptor and add the
reached-feature generator plus the `feature_weapons` collector.

**Files:**
- Modify: `data/races/gargantua.yaml` (the `rock_throwing` feature's `mechanical`)
- Modify: `data/classes/gargantua.yaml` (the `rock_throwing` feature's `mechanical`)
- Modify: `aose/engine/features.py`
- Test: `tests/test_feature_modifiers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_feature_modifiers.py`:

```python
# ── Gargantua: feature weapons (Rock Throwing) ───────────────────────────────

def _spec(race_id, class_id, *, level=1, hp=8, **kw):
    from aose.models import CharacterSpec, ClassEntry
    base = dict(
        name="G",
        abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10, "CON": 12, "CHA": 10},
        race_id=race_id, alignment="neutral",
        classes=[ClassEntry(class_id=class_id, level=level, hp_rolls=[hp])],
    )
    base.update(kw)
    return CharacterSpec(**base)


def test_feature_weapons_gargantua_race():
    from aose.engine.features import feature_weapons
    weapons = dict(feature_weapons(_spec("gargantua", "fighter"), DATA))
    assert "rock_throwing" in weapons
    w = weapons["rock_throwing"]
    assert w["damage"] == "1d6"
    assert w["ranged"] is True and w["melee"] is False
    assert w["range"] == [50, 100, 150]


def test_feature_weapons_gargantua_as_class_once():
    from aose.engine.features import feature_weapons
    # race_id == class_id == "gargantua" → race-as-class: only the class path
    # contributes, so the rock appears exactly once.
    weapons = feature_weapons(_spec("gargantua", "gargantua", hp=10), DATA)
    ids = [wid for wid, _ in weapons]
    assert ids.count("rock_throwing") == 1


def test_feature_weapons_none_for_human():
    from aose.engine.features import feature_weapons
    assert feature_weapons(_spec("human", "fighter"), DATA) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -q -k feature_weapons`
Expected: FAIL with `ImportError: cannot import name 'feature_weapons'`.

- [ ] **Step 3: Restructure the rock data (race)**

In `data/races/gargantua.yaml`, replace the `rock_throwing` feature's `mechanical` block:

```yaml
  mechanical:
    damage: 1d6
    range: [50, 100, 150]
```

with:

```yaml
  mechanical:
    weapon:
      name: Rock
      damage: 1d6
      melee: false
      ranged: true
      range: [50, 100, 150]
      qualities: [blunt]
```

- [ ] **Step 4: Restructure the rock data (class)**

In `data/classes/gargantua.yaml`, replace the `rock_throwing` feature's `mechanical` block (same 2-space indent as the race file):

```yaml
  mechanical:
    damage: 1d6
    range: [50, 100, 150]
```

with:

```yaml
  mechanical:
    weapon:
      name: Rock
      damage: 1d6
      melee: false
      ranged: true
      range: [50, 100, 150]
      qualities: [blunt]
```

- [ ] **Step 5: Add `_reached_features` and `feature_weapons`**

In `aose/engine/features.py`, add these functions (after `is_race_as_class`, before `feature_modifiers`):

```python
def _reached_features(spec: CharacterSpec, data: GameData):
    """Yield ``(feature, source_label)`` for every reached class feature and,
    unless the character is race-as-class, every race feature. Mirrors the
    iteration in ``feature_modifiers`` so all feature-derived data agrees on
    what applies."""
    for entry in spec.classes:
        cls = data.classes.get(entry.class_id)
        if cls is None:
            continue
        for feat in cls.features:
            if feat.gained_at_level <= entry.level:
                yield feat, cls.name
    race = None if is_race_as_class(spec, data) else data.races.get(spec.race_id)
    if race is not None:
        for feat in race.features:
            yield feat, race.name


def feature_weapons(spec: CharacterSpec, data: GameData) -> list[tuple[str, dict]]:
    """Synthetic always-available weapons declared by reached features via
    ``mechanical['weapon']`` (e.g. the gargantua's thrown rock). Returns
    ``(feature_id, descriptor)`` pairs. The race-as-class guard in
    ``_reached_features`` keeps the gargantua rock from being contributed by both
    the linked race and the class."""
    out: list[tuple[str, dict]] = []
    for feat, _src in _reached_features(spec, data):
        if feat.mechanical:
            descriptor = feat.mechanical.get("weapon")
            if descriptor:
                out.append((feat.id, descriptor))
    return out
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -q -k feature_weapons`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
git add data/races/gargantua.yaml data/classes/gargantua.yaml aose/engine/features.py tests/test_feature_modifiers.py
git commit -m "feat(features): generic feature-weapon descriptor + reached-feature collector"
```

---

## Task 2: `open_doors_category_bonus` collector

**Files:**
- Modify: `aose/engine/features.py`
- Test: `tests/test_feature_modifiers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_feature_modifiers.py`:

```python
# ── Gargantua: Open Doors STR-category bonus ─────────────────────────────────

def test_open_doors_category_bonus_gargantua_race():
    from aose.engine.features import open_doors_category_bonus
    bonus, source = open_doors_category_bonus(_spec("gargantua", "fighter"), DATA)
    assert bonus == 1
    assert source == "Gargantua"


def test_open_doors_category_bonus_gargantua_as_class():
    from aose.engine.features import open_doors_category_bonus
    bonus, source = open_doors_category_bonus(_spec("gargantua", "gargantua", hp=10), DATA)
    assert bonus == 1            # class path only — not doubled
    assert source == "Gargantua"


def test_open_doors_category_bonus_zero_for_human():
    from aose.engine.features import open_doors_category_bonus
    assert open_doors_category_bonus(_spec("human", "fighter"), DATA) == (0, "")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -q -k open_doors_category_bonus`
Expected: FAIL with `ImportError: cannot import name 'open_doors_category_bonus'`.

- [ ] **Step 3: Add the collector**

In `aose/engine/features.py`, add after `feature_weapons`:

```python
def open_doors_category_bonus(spec: CharacterSpec, data: GameData) -> tuple[int, str]:
    """Total STR-category bump for Open Doors from reached features'
    ``mechanical['str_category_bonus']``, paired with the granting race/class
    name for display. Returns ``(0, "")`` when no feature grants one."""
    total = 0
    source = ""
    for feat, src in _reached_features(spec, data):
        if feat.mechanical:
            bonus = feat.mechanical.get("str_category_bonus")
            if bonus:
                total += bonus
                if not source:
                    source = src
    return total, source
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -q -k open_doors_category_bonus`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/features.py tests/test_feature_modifiers.py
git commit -m "feat(features): open_doors_category_bonus collector"
```

---

## Task 3: Open Doors category bump in the ability table

**Files:**
- Modify: `aose/engine/ability_mods.py`
- Test: `tests/test_ability_tables.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ability_tables.py`:

```python
# ── STR Open Doors category bonus (gargantua) ─────────────────────────────
def test_open_doors_bump_one_category():
    c = _cells("STR", 12)
    assert c["Open Doors"] == "2-in-6"                      # raw band
    bumped = dict(ability_table_row("STR", 12, open_doors_category_bonus=1))
    assert bumped["Open Doors"] == "3-in-6"                 # next category up


def test_open_doors_bump_clamps_at_top():
    bumped = dict(ability_table_row("STR", 18, open_doors_category_bonus=1))
    assert bumped["Open Doors"] == "5-in-6"                 # already top band


def test_open_doors_bump_leaves_melee_untouched():
    bumped = dict(ability_table_row("STR", 12, open_doors_category_bonus=1))
    assert bumped["Melee"] == "None"                       # only Open Doors bumps
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ability_tables.py -q -k open_doors`
Expected: FAIL with `TypeError: ability_table_row() got an unexpected keyword argument 'open_doors_category_bonus'`.

- [ ] **Step 3: Add `_band_bumped`**

In `aose/engine/ability_mods.py`, add after the `_band` function:

```python
def _band_bumped(table: dict[int, str], score: int, bump: int) -> str:
    """Like ``_band`` but advances ``bump`` whole categories up the table,
    clamped to the top band. Used for the gargantua Open Doors bonus ("treated
    as the next highest STR category")."""
    thresholds = sorted(table)
    idx = 0
    for i, threshold in enumerate(thresholds):
        if score >= threshold:
            idx = i
    idx = min(idx + bump, len(thresholds) - 1)
    return table[thresholds[idx]]
```

- [ ] **Step 4: Extend `ability_table_row`**

In `aose/engine/ability_mods.py`, replace the `ability_table_row` function body:

```python
def ability_table_row(ability: str, score: int, *,
                      is_prime: bool = False,
                      open_doors_category_bonus: int = 0) -> list[tuple[str, str]]:
    """Return the relevant reference-table row for ``ability`` at the COMPUTED
    ``score`` as ordered ``(label, value)`` cells. When ``is_prime`` is set the
    prime-requisite XP-modifier cell is appended. ``open_doors_category_bonus``
    (STR only) advances the Open Doors cell that many categories up the table —
    the gargantua's "next highest STR category" rule."""
    cells = [
        (label,
         _band_bumped(table, score, open_doors_category_bonus)
         if label == "Open Doors" and open_doors_category_bonus
         else _band(table, score))
        for label, table in _ABILITY_COLUMNS[ability]
    ]
    if is_prime:
        cells.append(("XP Modifier", _band(_PRIME_XP, score)))
    return cells
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ability_tables.py -q`
Expected: PASS (all, including the 3 new ones — existing `dict(ability_table_row(...))` calls still get 2-tuples).

- [ ] **Step 6: Commit**

```bash
git add aose/engine/ability_mods.py tests/test_ability_tables.py
git commit -m "feat(ability): Open Doors STR-category bump for ability_table_row"
```

---

## Task 4: Synthetic feature-weapon attack profile

**Files:**
- Modify: `aose/engine/attacks.py`
- Test: `tests/test_feature_modifiers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_feature_modifiers.py` (reuses the module-level `_profiles` and `_spec` helpers):

```python
# ── Gargantua: rock attack profile ───────────────────────────────────────────

def test_gargantua_rock_profile_stats():
    profs = _profiles(_spec("gargantua", "fighter"))
    rock = profs["rock_throwing"]
    assert rock.name == "Rock"
    assert rock.ranged is True and rock.melee is False
    assert rock.damage == "1d6"
    assert rock.range_ft == (50, 100, 150)
    assert rock.proficient is True
    assert rock.manageable_item_id is None


def test_gargantua_rock_uses_dex_to_hit():
    # ranged → DEX to hit, no ability damage bonus. DEX 14 = +1; STR 16 = +2.
    spec = _spec("gargantua", "fighter",
                 abilities={"STR": 16, "INT": 10, "WIS": 10, "DEX": 14, "CON": 12, "CHA": 10})
    rock = _profiles(spec)["rock_throwing"]
    assert rock.to_hit_ascending == 1     # DEX +1, not STR +2
    assert rock.damage == "1d6"           # flat (no STR damage)


def test_gargantua_rock_proficient_under_weapon_proficiency():
    from aose.models import RuleSet
    spec = _spec("gargantua", "fighter", ruleset=RuleSet(weapon_proficiency=True))
    assert _profiles(spec)["rock_throwing"].proficient is True


def test_non_gargantua_has_no_rock():
    assert "rock_throwing" not in _profiles(_spec("human", "fighter"))


def test_gargantua_as_class_rock_not_duplicated():
    from aose.engine.attacks import attack_profiles
    ids = [p.weapon_id for p in attack_profiles(_spec("gargantua", "gargantua", hp=10), DATA)]
    assert ids.count("rock_throwing") == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -q -k "rock"`
Expected: FAIL with `KeyError: 'rock_throwing'` (the profile isn't produced yet).

- [ ] **Step 3: Import the collector**

In `aose/engine/attacks.py`, change the features import:

```python
from aose.engine.features import all_modifiers
```

to:

```python
from aose.engine.features import all_modifiers, feature_weapons
```

- [ ] **Step 4: Add `_feature_weapon_profile`**

In `aose/engine/attacks.py`, add after `_unarmed_profile`:

```python
def _feature_weapon_profile(descriptor: dict, weapon_id: str, eff: dict,
                            base_thac0: int, g_atk: int, g_dmg: int) -> AttackProfile:
    """Synthetic always-available weapon from a feature's ``mechanical['weapon']``
    descriptor (e.g. the gargantua's thrown rock). Always proficient — no
    weapon-proficiency penalty, like Unarmed. Ranged ⇒ DEX to hit, flat damage;
    melee ⇒ STR to hit and damage. Not a catalog item, so no manage link."""
    melee = bool(descriptor.get("melee", False))
    ranged = bool(descriptor.get("ranged", not melee))
    str_mod = ability_modifier(eff[Ability.STR])
    dex_mod = ability_modifier(eff[Ability.DEX])
    atk_mod = str_mod if melee else dex_mod
    dmg_mod = str_mod if melee else 0
    base_attack = 19 - base_thac0
    rng = None
    r = descriptor.get("range")
    if ranged and r:
        rng = (r[0], r[1], r[2])
    return AttackProfile(
        weapon_id=weapon_id,
        name=descriptor.get("name", "Weapon"),
        count=1,
        melee=melee,
        ranged=ranged,
        proficient=True,
        to_hit_thac0=base_thac0 - atk_mod - g_atk,
        to_hit_ascending=base_attack + atk_mod + g_atk,
        damage=_format_damage(descriptor["damage"], dmg_mod + g_dmg),
        range_ft=rng,
        conditional=None,
        unarmed=False,
        manageable_item_id=None,
    )
```

- [ ] **Step 5: Emit feature weapons in `attack_profiles`**

In `aose/engine/attacks.py`, inside `attack_profiles`, locate the `weapon_profiles.sort(...)` line near the end:

```python
    weapon_profiles.sort(key=lambda p: p.name)
    u_atk, u_dmg = _atk_dmg(mods, melee=True, ranged=False)
```

Insert the feature-weapon loop immediately **before** that sort line:

```python
    for weapon_id, descriptor in feature_weapons(spec, data):
        melee = bool(descriptor.get("melee", False))
        ranged = bool(descriptor.get("ranged", not melee))
        g_atk, g_dmg = _atk_dmg(mods, melee=melee, ranged=ranged)
        weapon_profiles.append(
            _feature_weapon_profile(descriptor, weapon_id, eff, base_thac0, g_atk, g_dmg)
        )
    weapon_profiles.sort(key=lambda p: p.name)
    u_atk, u_dmg = _atk_dmg(mods, melee=True, ranged=False)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -q -k "rock"`
Expected: PASS (5 passed).

- [ ] **Step 7: Commit**

```bash
git add aose/engine/attacks.py tests/test_feature_modifiers.py
git commit -m "feat(attacks): synthetic always-on feature weapon (gargantua rock)"
```

---

## Task 5: Sheet wiring + template note

**Files:**
- Modify: `aose/sheet/view.py`
- Modify: `aose/web/templates/sheet.html`
- Test: `tests/test_sheet_view.py` (create if absent)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_sheet_view.py` (create the file with this header if it doesn't exist):

```python
"""Sheet assembly (build_sheet) end-to-end checks."""
from pathlib import Path

from aose.data.loader import GameData
from aose.models import CharacterSpec, ClassEntry

DATA = GameData.load(Path(__file__).parent.parent / "data")


def _sheet(race_id, class_id, *, str_score=12, hp=8):
    from aose.sheet.view import build_sheet
    spec = CharacterSpec(
        name="G",
        abilities={"STR": str_score, "INT": 10, "WIS": 10, "DEX": 10, "CON": 12, "CHA": 10},
        race_id=race_id, alignment="neutral",
        classes=[ClassEntry(class_id=class_id, level=1, hp_rolls=[hp])],
    )
    return build_sheet(spec, DATA)


def _open_doors_cell(sheet):
    str_row = next(r for r in sheet.abilities if r.ability == "STR")
    return next(c for c in str_row.table if c.label == "Open Doors")


def test_gargantua_open_doors_cell_bumped_with_note():
    cell = _open_doors_cell(_sheet("gargantua", "fighter", str_score=12))
    assert cell.value == "3-in-6"
    assert cell.note == "+1 category (Gargantua)"


def test_non_gargantua_open_doors_cell_plain():
    cell = _open_doors_cell(_sheet("human", "fighter", str_score=12))
    assert cell.value == "2-in-6"
    assert cell.note == ""
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_view.py -q -k open_doors`
Expected: FAIL — `AbilityTableCell` has no `note` field (validation error) / or AttributeError.

- [ ] **Step 3: Add the `note` field to `AbilityTableCell`**

In `aose/sheet/view.py`, update the model:

```python
class AbilityTableCell(BaseModel):
    label: str            # column name (e.g. "Open Doors")
    value: str            # banded value for the computed score
    note: str = ""        # explanatory note (e.g. gargantua category bump)
```

- [ ] **Step 4: Import the collector**

In `aose/sheet/view.py`, update the features import:

```python
from aose.engine.features import is_race_as_class
```

to:

```python
from aose.engine.features import is_race_as_class, open_doors_category_bonus
```

- [ ] **Step 5: Compute the bonus and thread the note**

In `aose/sheet/view.py`, inside `build_sheet`, just before the `abilities = []` line, add:

```python
    od_bonus, od_source = open_doors_category_bonus(spec, data)
```

Then replace the `table=[...]` block in the `AbilityRow(...)` construction:

```python
            table=[
                AbilityTableCell(label=lbl, value=val)
                for lbl, val in ability_mods.ability_table_row(
                    ab.value, final, is_prime=ab.value in prime_abilities)
            ],
```

with:

```python
            table=[
                AbilityTableCell(
                    label=lbl, value=val,
                    note=(f"+{od_bonus} category ({od_source})"
                          if ab == Ability.STR and od_bonus and lbl == "Open Doors"
                          else ""),
                )
                for lbl, val in ability_mods.ability_table_row(
                    ab.value, final, is_prime=ab.value in prime_abilities,
                    open_doors_category_bonus=(od_bonus if ab == Ability.STR else 0))
            ],
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_view.py -q -k open_doors`
Expected: PASS (2 passed).

- [ ] **Step 7: Render the note in the template**

In `aose/web/templates/sheet.html`, find the ability-modal table row (around line 712):

```html
      <tr><td>{{ c.label }}</td><td class="num">{{ c.value }}</td></tr>
```

Replace it with:

```html
      <tr><td>{{ c.label }}{% if c.note %} <span class="muted">{{ c.note }}</span>{% endif %}</td><td class="num">{{ c.value }}</td></tr>
```

- [ ] **Step 8: Commit**

```bash
git add aose/sheet/view.py aose/web/templates/sheet.html tests/test_sheet_view.py
git commit -m "feat(sheet): show gargantua Open Doors category bump + note in STR modal"
```

---

## Task 6: Full suite + docs

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/ARCHITECTURE.md`

- [ ] **Step 1: Run the full test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (all tests). Ignore the trailing `PermissionError` on `pytest-current` (known Windows quirk).

- [ ] **Step 2: Add the CHANGELOG row**

In `docs/CHANGELOG.md`, add a row at the **top** of the ledger (match the existing column format):

```
| 2026-06-08 | Gargantua feature automation (Rock Throwing synthetic weapon + Open Doors STR-category bump) | main | gargantua-feature-automation |
```

- [ ] **Step 3: Update ARCHITECTURE.md**

In `docs/ARCHITECTURE.md`, edit the existing **attacks** and **features** topics in place (do not append a dated entry):

- Features: note that `_reached_features` centralises reached-feature iteration, and that `feature_weapons` / `open_doors_category_bonus` read generic `mechanical` keys (`weapon`, `str_category_bonus`) — no engine module names a race/class.
- Attacks: note that `attack_profiles` emits a synthetic always-on `AttackProfile` per feature `weapon` descriptor (proficient, no manage link), alongside the Unarmed profile.

- [ ] **Step 4: Commit**

```bash
git add docs/CHANGELOG.md docs/ARCHITECTURE.md
git commit -m "docs: record gargantua feature automation"
```

---

## Self-Review notes

- **Spec coverage:** Part A (synthetic weapon) → Tasks 1 (data + collector) & 4 (profile). Part B (open doors) → Tasks 2 (collector), 3 (table bump), 5 (sheet + template). Tests listed in the spec are covered across Tasks 1–5. Docs → Task 6.
- **Out of scope (per spec):** `blunt`/missile qualities are stored in data but not surfaced in the weapon-qualities reference block (synthetic weapon is not in catalog inventory). No task wires this — intentional.
- **Type consistency:** `feature_weapons` returns `list[tuple[str, dict]]` (feature_id, descriptor) — consumed in Task 4. `open_doors_category_bonus` returns `tuple[int, str]` (bonus, source) — consumed in Task 5. `ability_table_row(..., open_doors_category_bonus=int)` keyword matches Tasks 3 & 5. `AbilityTableCell.note` added in Task 5 before use.
