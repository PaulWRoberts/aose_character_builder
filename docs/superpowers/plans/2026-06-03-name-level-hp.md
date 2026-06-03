# Fixed HP at Name Level Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop rolling Hit Dice and adding the Constitution modifier once a class reaches its name level; instead grant a fixed HP step per level (divided by N classes, fractions tracked) faithful to AOSE.

**Architecture:** Two typed fields on `CharClass` (`name_level`, `hp_after_name_level`) become the single source of truth, replacing the unused `ClassLevelData.hit_dice` string. The HP engine adds a CON-free, floor-free fixed term to its existing exact-`Fraction` total and defensively caps rolled events at name level; `level_up` stops rolling past name level; `energy_drain` stops popping rolls for levels that never had one.

**Tech Stack:** Python 3, Pydantic v2, pytest. Run tests with `.venv\Scripts\python.exe -m pytest`.

Spec: `docs/superpowers/specs/2026-06-03-name-level-hp-design.md`

---

## File Structure

- `aose/models/character_class.py` — add `name_level` + `hp_after_name_level` to `CharClass`; remove `hit_dice` from `ClassLevelData`.
- `data/classes/*.yaml` (22 files) — strip `hit_dice` from every progression row; add the two new class-level fields.
- `aose/engine/hp.py` — `_hp_events` caps rolls at name level; `_hp_total` adds the fixed term.
- `aose/engine/leveling.py` — `level_up` skips rolling at/after name level.
- `aose/engine/energy_drain.py` — only pop a roll when the removed level is at/below name level.
- `tests/test_data_loading.py`, `tests/test_leveling.py`, `tests/test_energy_drain.py` — new tests.
- `tests/test_demihuman_rules.py` — fix one `ClassLevelData(...)` construction.
- `import/cribs/class.md` — update the data-authoring crib.

---

## Task 1: Data model + data migration (atomic)

Adding/removing model fields and editing YAML must land together — `ClassLevelData` and `CharClass` use `extra="forbid"`, so a mismatch between model and YAML breaks `GameData.load` and every test. The new `CharClass` fields get defaults so the model is valid even before YAML is populated, but we populate the YAML in the same task.

**Files:**
- Modify: `aose/models/character_class.py`
- Modify: `data/classes/*.yaml` (all 22, via script)
- Modify: `tests/test_demihuman_rules.py:118`
- Modify: `import/cribs/class.md`
- Test: `tests/test_data_loading.py`

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/test_data_loading.py`:

```python
def test_classes_have_name_level_fields(data):
    fighter = data.classes["fighter"]
    assert fighter.name_level == 9
    assert fighter.hp_after_name_level == 2
    assert data.classes["magic_user"].hp_after_name_level == 1
    assert data.classes["cleric"].hp_after_name_level == 1
    assert data.classes["barbarian"].hp_after_name_level == 3
    assert data.classes["thief"].hp_after_name_level == 2
    # Capped race-as-class options: dice stop at 8, fixed step never fires.
    assert data.classes["gnome"].name_level == 8
    assert data.classes["halfling"].name_level == 8


def test_hit_dice_removed_from_class_level_data():
    from pydantic import ValidationError
    from aose.models.character_class import ClassLevelData

    # The retired `hit_dice` field must now be rejected (extra="forbid").
    with pytest.raises(ValidationError):
        ClassLevelData(
            xp_required=0, thac0=19, hit_dice="1d8",
            saves={"death": 12, "wands": 13, "paralysis": 14,
                   "breath": 15, "spells": 16},
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py::test_classes_have_name_level_fields tests/test_data_loading.py::test_hit_dice_removed_from_class_level_data -q`
Expected: FAIL — `AttributeError: 'CharClass' object has no attribute 'name_level'` and the `ClassLevelData` construction does NOT raise (hit_dice still accepted).

- [ ] **Step 3: Update the models**

In `aose/models/character_class.py`, remove `hit_dice` from `ClassLevelData`:

```python
class ClassLevelData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    xp_required: int
    thac0: int
    saves: dict[str, int]
    # spell_level -> slot count; only set on spellcasting classes
    spell_slots: dict[int, int] | None = None
```

In the same file, add two fields to `CharClass` (place them right after `hit_die`):

```python
    hit_die: str
    # Name level: the last level at which this class rolls a Hit Die. Beyond it
    # the class gains a flat `hp_after_name_level` HP per level with NO CON
    # modifier (AOSE). 9 for almost every class; 8 for capped race-as-class
    # options whose max_level is also 8 (so the step never fires for them).
    name_level: int = 9
    hp_after_name_level: int = 0
```

- [ ] **Step 4: Migrate the YAML data**

Run this one-shot migration script (it strips every `hit_dice:` progression line and inserts the two class-level fields after the `hit_die:` line):

```python
.venv\Scripts\python.exe -c "
import glob, os, re

STEP = {
    'acrobat': (9, 2), 'assassin': (9, 2), 'barbarian': (9, 3), 'bard': (9, 2),
    'cleric': (9, 1), 'drow': (9, 2), 'druid': (9, 1), 'duergar': (9, 3),
    'dwarf': (9, 3), 'elf': (9, 2), 'fighter': (9, 2), 'gnome': (8, 1),
    'half_elf': (9, 2), 'half_orc': (8, 1), 'halfling': (8, 1),
    'illusionist': (9, 1), 'knight': (9, 2), 'magic_user': (9, 1),
    'paladin': (9, 2), 'ranger': (9, 2), 'svirfneblin': (8, 1), 'thief': (9, 2),
}

for path in sorted(glob.glob('data/classes/*.yaml')):
    cid = os.path.splitext(os.path.basename(path))[0]
    name_level, step = STEP[cid]
    out = []
    for line in open(path, encoding='utf-8').read().splitlines():
        if line.strip().startswith('hit_dice:'):
            continue  # drop the retired per-row field
        out.append(line)
        if re.match(r'^hit_die:', line):  # top-level singular die -> inject fields
            out.append(f'name_level: {name_level}')
            out.append(f'hp_after_name_level: {step}')
    open(path, 'w', encoding='utf-8', newline='\n').write('\n'.join(out) + '\n')
    print(f'{cid}: name_level={name_level} hp_after_name_level={step}')
"
```

Expected: prints one line per class (22 lines), e.g. `fighter: name_level=9 hp_after_name_level=2`.

- [ ] **Step 5: Fix the one test that constructs `ClassLevelData(hit_dice=...)`**

In `tests/test_demihuman_rules.py`, change the construction at line ~117-119 to drop `hit_dice="1d4",`:

```python
        progression={
            1: ClassLevelData(
                xp_required=0, thac0=19,
                saves={"death": 13, "wands": 14, "paralysis": 13, "breath": 16, "spells": 15},
            ),
        },
```

- [ ] **Step 6: Update the authoring crib**

In `import/cribs/class.md`:

1. In the Fields table, add a row after the `hit_die` row:

```markdown
| name_level | int | no | default 9; last level that rolls a Hit Die (8 for capped race-as-class) |
| hp_after_name_level | int | no | default 0; flat HP/level gained beyond name level, no CON modifier |
```

2. Change the `ClassLevelData` description line (remove `hit_dice:str,`):

```markdown
`ClassLevelData`: `{xp_required:int, thac0:int,
saves:{death,wands,paralysis,breath,spells (ints)}, spell_slots: map int->int | null}`
```

3. In the two example `progression` blocks, delete the `hit_dice: 1d8` / `hit_dice: 1d4` / `hit_dice: 3d4` lines, and add `name_level: 9` + `hp_after_name_level: 2` under `hit_die: 1d8` in the non-caster example.

- [ ] **Step 7: Run the new tests and the full suite to verify green**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py tests/test_demihuman_rules.py -q`
Expected: PASS.

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all tests pass (the engine does not consume the new fields yet — `hp_after_name_level` defaults effectively change nothing because every existing test character is level 1). Ignore the trailing `pytest-current` PermissionError.

- [ ] **Step 8: Commit**

```bash
git add aose/models/character_class.py data/classes/ tests/test_demihuman_rules.py tests/test_data_loading.py import/cribs/class.md
git commit -m "Add name_level/hp_after_name_level fields; retire ClassLevelData.hit_dice

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: HP engine — fixed post-name-level term + defensive roll cap

**Files:**
- Modify: `aose/engine/hp.py:10-47`
- Test: `tests/test_leveling.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_leveling.py` (it already imports `CharacterSpec`, `ClassEntry`, `RuleSet` and has a module-scoped `data` fixture):

```python
from aose.engine.hp import max_hp, hp_remainder


def _fighter_spec(level, hp_rolls, con=14, ruleset=None):
    return CharacterSpec(
        name="Vala",
        abilities={"STR": 12, "INT": 12, "WIS": 12, "DEX": 12, "CON": con, "CHA": 10},
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=level, xp=0, hp_rolls=hp_rolls)],
        alignment="law",
        ruleset=ruleset or RuleSet(),
    )


def test_max_hp_at_name_level_unchanged(data):
    # L9 fighter, CON 14 (+1): 9 rolled events of 8 each + 1 CON each = 9*9 = 81.
    spec = _fighter_spec(9, [8] * 9)
    assert max_hp(spec, data) == 81


def test_max_hp_one_level_past_name_adds_fixed_step_no_con(data):
    # L10 fighter: still 9 rolls (none added past name level) + fixed (10-9)*2 = 2.
    spec = _fighter_spec(10, [8] * 9)
    assert max_hp(spec, data) == 83  # 81 + 2


def test_fixed_step_ignores_con(data):
    # Same as above but CON 18 (+3). Rolled part = 9*(8+3)=99; fixed still +2.
    spec = _fighter_spec(10, [8] * 9, con=18)
    assert max_hp(spec, data) == 101  # 99 + 2 (no CON on the fixed step)


def test_max_hp_at_class_max_full_fixed_run(data):
    # L14 fighter: 9 rolls + (14-9)*2 = 10 fixed. CON +1 → 9*9 + 10 = 91.
    spec = _fighter_spec(14, [8] * 9)
    assert max_hp(spec, data) == 91


def test_defensive_cap_ignores_overlong_hp_rolls(data):
    # A stale character with 14 rolls at L14 must still count only 9 rolls.
    spec = _fighter_spec(14, [8] * 14)
    assert max_hp(spec, data) == 91  # identical to the 9-roll case


def test_multiclass_fixed_step_divides_and_tracks_fraction(data):
    # Fighter L10 (step 2) + magic_user L10 (step 1), each 9 rolls of value 2.
    # Rolled: creation event sum=4 -> 4/2+1=3; then 8 fighter + 8 MU single
    #   events of 2 each -> (2/2 + 1)=2 apiece, 16 events -> 32; rolled total 35.
    # Fixed: ((10-9)*2 + (10-9)*1) / 2 = 3/2 = 1.5.
    # Total 36.5 -> max_hp 36, remainder 1/2.
    from fractions import Fraction
    spec = CharacterSpec(
        name="Twin",
        abilities={"STR": 12, "INT": 12, "WIS": 12, "DEX": 12, "CON": 14, "CHA": 10},
        race_id="elf",
        classes=[
            ClassEntry(class_id="fighter", level=10, xp=0, hp_rolls=[2] * 9),
            ClassEntry(class_id="magic_user", level=10, xp=0, hp_rolls=[2] * 9),
        ],
        alignment="neutral",
        ruleset=RuleSet(multiclassing=True),
    )
    assert max_hp(spec, data) == 36
    assert hp_remainder(spec, data) == Fraction(1, 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py -k "name_level or fixed_step or defensive_cap or multiclass_fixed or name_adds" -q`
Expected: FAIL — `test_max_hp_one_level_past_name_adds_fixed_step_no_con` returns 81 (no fixed term), `test_defensive_cap_ignores_overlong_hp_rolls` returns more than 91, etc.

- [ ] **Step 3: Implement the engine changes**

Replace `_hp_events` and `_hp_total` in `aose/engine/hp.py` with:

```python
def _hp_events(spec: CharacterSpec, data: GameData) -> list[int]:
    """The sequence of HP-gain *events*, each an integer roll-sum.

    At character creation every class rolls its hit die simultaneously — that is
    a single event whose value is the sum of those rolls.  Each subsequent
    per-class level-up is its own single-die event.  Rolls live per class on
    ``ClassEntry.hp_rolls`` (index 0 = the creation roll).

    Each class contributes only its first ``name_level`` rolls: Hit Dice stop at
    name level, so any rolls stored beyond that (e.g. on a character leveled
    under an older engine) are ignored defensively.
    """
    rolls = [e.hp_rolls[: data.classes[e.class_id].name_level] for e in spec.classes]
    if not any(rolls):
        return []
    events: list[int] = [sum(r[0] for r in rolls if r)]
    max_len = max(len(r) for r in rolls)
    for k in range(1, max_len):
        for r in rolls:
            if k < len(r):
                events.append(r[k])
    return events


def _hp_total(spec: CharacterSpec, data: GameData) -> Fraction:
    """Exact (fractional) maximum HP before flooring.

    Two contributions, both divided by the number of classes N (AOSE Advanced
    Multiple Classes rule) and summed as exact ``Fraction``s, floored once:

    * Rolled Hit Dice (up to name level): each event gets the *effective* CON
      modifier added, with a floor of 1 HP per event (min 1 per Hit Die).
    * Fixed post-name-level HP: ``hp_after_name_level`` per level beyond name
      level, per class.  This is a flat bonus — NO CON modifier and NO per-event
      floor — so partial hit points accumulate and may form whole HP later.

    Single-class (N=1) below name level reduces to ``sum(max(1, roll + CON))``.
    CON is read from ``effective_abilities`` — never baked into stored rolls.
    """
    n = len(spec.classes)
    con_mod = ability_modifier(effective_abilities(spec, data)[Ability.CON])
    total = Fraction(0)
    for event in _hp_events(spec, data):
        total += max(Fraction(1), Fraction(event, n) + con_mod)
    fixed = sum(
        max(0, e.level - data.classes[e.class_id].name_level)
        * data.classes[e.class_id].hp_after_name_level
        for e in spec.classes
    )
    total += Fraction(fixed, n)
    return total
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py tests/test_multiclassing.py -q`
Expected: PASS (existing level-1 max_hp tests unaffected; new tests green).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/hp.py tests/test_leveling.py
git commit -m "HP engine: fixed CON-free step past name level, cap rolls at name level

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `level_up` stops rolling at name level

**Files:**
- Modify: `aose/engine/leveling.py:121-150`
- Test: `tests/test_leveling.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_leveling.py`:

```python
def test_level_up_past_name_level_rolls_nothing(data):
    # Fighter at name level (9) with 9 rolls; XP for L10 is 360000.
    spec = _fighter_spec(9, [8] * 9)
    spec.classes[0].xp = 360000
    result = level_up(spec, data, "fighter")
    assert spec.classes[0].level == 10
    assert spec.classes[0].hp_rolls == [8] * 9   # no new roll appended
    assert result == 0                            # no die rolled


def test_level_up_at_name_level_minus_one_still_rolls(data):
    # Leveling 8 -> 9 is the last rolling level; a die is still added.
    spec = _fighter_spec(8, [8] * 8)
    spec.classes[0].xp = 240000
    result = level_up(spec, data, "fighter")
    assert spec.classes[0].level == 9
    assert len(spec.classes[0].hp_rolls) == 9
    assert 1 <= result <= 8
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py::test_level_up_past_name_level_rolls_nothing -q`
Expected: FAIL — a 10th roll is appended (`hp_rolls` length 10) and `result` is a die value, not 0.

- [ ] **Step 3: Implement the no-roll branch**

In `aose/engine/leveling.py`, replace the tail of `level_up` (from the `cls = data.classes[class_id]` line through `return new_hp`) with:

```python
    cls = data.classes[class_id]
    # At or beyond name level the class no longer rolls Hit Dice; it gains a
    # flat `hp_after_name_level` per level instead (applied in hp.py, no CON).
    if entry.level >= cls.name_level:
        entry.level += 1
        return 0

    new_hp = roll_hp(cls.hit_die, rng=rng)
    entry.level += 1
    entry.hp_rolls.append(new_hp)
    return new_hp
```

Also update the `level_up` docstring's "HP rules" note to read:

```python
    HP rules: standard ``roll_hp(hit_die)`` until name level.  At or beyond
    ``cls.name_level`` no die is rolled and ``hp_rolls`` is left unchanged
    (returns 0); the flat post-name-level HP is applied by ``hp.py``.
    Max-HP-at-L1 and Re-roll 1s/2s apply only at character creation.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/leveling.py tests/test_leveling.py
git commit -m "level_up: no Hit Die roll at or beyond name level

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `energy_drain` does not pop rolls for post-name-level levels

**Files:**
- Modify: `aose/engine/energy_drain.py:118-127`
- Test: `tests/test_energy_drain.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_energy_drain.py` (mirror its existing `_spec` helper and `data` fixture; check the top of the file for their exact names — the single-class helper builds a fighter):

```python
def test_drain_past_name_level_keeps_all_hit_dice(data):
    # L11 fighter has only 9 rolls (none past name level). Draining 11 -> 10 -> 9
    # must NOT pop a real Hit Die — those levels never had one.
    spec = _spec(level=11, xp=480000, hp_rolls=[8] * 9)
    energy_drain(spec, data, 2, "new_min")
    e = spec.classes[0]
    assert e.level == 9
    assert e.hp_rolls == [8] * 9        # all 9 dice intact


def test_drain_across_name_level_boundary_pops_only_real_dice(data):
    # L10 fighter (9 rolls). Drain 2 levels: 10 -> 9 (no pop), 9 -> 8 (pop one).
    spec = _spec(level=10, xp=360000, hp_rolls=[8] * 9)
    energy_drain(spec, data, 2, "new_min")
    e = spec.classes[0]
    assert e.level == 8
    assert e.hp_rolls == [8] * 8        # exactly one real die removed
```

Confirm `energy_drain` and `_spec` are imported/defined at the top of `tests/test_energy_drain.py`; add the import if missing (`from aose.engine.energy_drain import energy_drain`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_energy_drain.py -k "name_level or boundary" -q`
Expected: FAIL — the current code pops a roll on every level, so `hp_rolls` ends shorter than asserted.

- [ ] **Step 3: Implement the name-level-aware pop**

In `aose/engine/energy_drain.py`, replace the per-level loop body (the `for _ in range(levels):` block) so the `hp_rolls.pop()` only happens for levels at/below name level:

```python
    former: dict[str, int] = {}  # class_id -> level before this drain
    for _ in range(levels):
        target = _most_recently_leveled(spec, data)
        if target is None:
            _kill(spec, data)
            return
        former.setdefault(target.class_id, target.level)
        removed_level = target.level  # the level being stripped
        target.level -= 1
        # Levels above name level never rolled a Hit Die, so there is nothing to
        # pop; only remove a stored roll when the removed level had one.
        if removed_level <= data.classes[target.class_id].name_level and target.hp_rolls:
            target.hp_rolls.pop()
        _trim_to_accessible(target, data, spec.ruleset)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_energy_drain.py -q`
Expected: PASS (existing low-level drain tests unaffected — their removed levels are ≤ 9).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/energy_drain.py tests/test_energy_drain.py
git commit -m "energy_drain: do not pop Hit Dice for post-name-level levels

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Round-trip integration test + full-suite verification

**Files:**
- Test: `tests/test_leveling.py`

- [ ] **Step 1: Write the round-trip test**

Add to `tests/test_leveling.py`:

```python
def test_level_up_then_drain_round_trips_max_hp(data):
    # Start at name level (9 rolls), record max HP, level to 10 (+2 fixed),
    # then drain back to 9. Max HP must return to the original value and the
    # roll list must be intact.
    spec = _fighter_spec(9, [8] * 9)
    spec.classes[0].xp = 360000
    before = max_hp(spec, data)          # 81

    level_up(spec, data, "fighter")      # -> L10, +2 fixed, no roll
    assert max_hp(spec, data) == before + 2

    from aose.engine.energy_drain import energy_drain
    energy_drain(spec, data, 1, "new_min")   # -> L9
    assert spec.classes[0].level == 9
    assert spec.classes[0].hp_rolls == [8] * 9
    assert max_hp(spec, data) == before
```

- [ ] **Step 2: Run it to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py::test_level_up_then_drain_round_trips_max_hp -q`
Expected: PASS (all behavior is already implemented; this guards the interaction).

- [ ] **Step 3: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all tests pass. Ignore the trailing `pytest-current` PermissionError (known Windows quirk).

- [ ] **Step 4: Commit**

```bash
git add tests/test_leveling.py
git commit -m "Test: level-up/energy-drain round-trip across name level

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-review notes

- **Spec coverage:** §1 data model → Task 1. §2 HP fixed term + defensive cap → Task 2. §3 `level_up` → Task 3. §4 `energy_drain` → Task 4. Testing section → Tasks 2–5. `import/cribs/class.md` + `test_demihuman_rules` updates → Task 1. All covered.
- **Type consistency:** `name_level` / `hp_after_name_level` field names are used identically in the model (Task 1), `hp.py` (Task 2), `leveling.py` (Task 3), and `energy_drain.py` (Task 4). `_hp_events(spec, data)` new signature is only called by `_hp_total` (same file, updated together).
- **No behavior change for existing characters:** every pre-existing test character is level 1, so `fixed = 0` and the defensive cap is a no-op — the full suite stays green after every task.
