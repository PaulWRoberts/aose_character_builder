# Advancement UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the live sheet's advancement UI: gate per-class "Level Up" on actual XP, fix the progress bar to measure within the current level, and split level-up HP into an explicit Roll → Confirm flow that mirrors the wizard's Strict-Mode behaviour. Move Add XP / Energy Drain out of the now-removed Advance modal into the header.

**Architecture:** Engine adds `current_threshold` to `ClassAdvancement` and splits `level_up()` into three cycle-free helpers (`roll_pending_hp`, `confirm_level_up`, `cancel_pending_level_up`) backed by a new `CharacterSpec.pending_level_up: dict[str, int]`. Three new routes wrap the helpers. The header section of `sheet.html` is rewritten to surface a Level-Up button only on classes that can level, and `modal-advance` is replaced by per-class `modal-levelup-{class_id}` overlays plus a single `modal-drain` overlay.

**Tech Stack:** Python 3, FastAPI, Pydantic v2, Jinja2. Tests via pytest + `fastapi.testclient.TestClient`.

**Spec:** [docs/superpowers/specs/2026-06-05-advancement-ux-design.md](../specs/2026-06-05-advancement-ux-design.md)

---

## File map

| File | Change |
|---|---|
| `aose/models/character.py` | Add `pending_level_up: dict[str, int] = Field(default_factory=dict)` to `CharacterSpec` |
| `aose/engine/leveling.py` | Add `current_threshold` to `ClassAdvancement`; add `roll_pending_hp`, `confirm_level_up`, `cancel_pending_level_up`; rewrite `level_up()` as a thin wrapper |
| `aose/web/routes.py` | Add `POST /character/{id}/level-up/{class_id}/{roll,confirm,cancel}` |
| `aose/web/templates/sheet.html` | Replace `<div class="xp">` header block; remove `modal-advance`; add `modal-drain` and per-class `modal-levelup-{class_id}` |
| `tests/test_leveling.py` | Add engine + route tests for new helpers and endpoints |

---

### Task 1: `CharacterSpec.pending_level_up` field

**Files:**
- Modify: `aose/models/character.py` (the `CharacterSpec` class)
- Test: `tests/test_leveling.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_leveling.py` (engine section):

```python
def test_pending_level_up_defaults_empty_and_roundtrips(data, tmp_path):
    """The new pending_level_up dict defaults to empty and survives save/load."""
    from aose.characters import save_character, load_character
    spec = _spec()
    assert spec.pending_level_up == {}
    spec.pending_level_up["fighter"] = 5
    cdir = tmp_path / "chars"
    save_character("pendtest", spec, cdir)
    reloaded = load_character("pendtest", cdir)
    assert reloaded.pending_level_up == {"fighter": 5}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py::test_pending_level_up_defaults_empty_and_roundtrips -q`
Expected: FAIL — Pydantic's `extra="forbid"` will reject the unknown attribute assignment, or `AttributeError`.

- [ ] **Step 3: Add the field**

In `aose/models/character.py`, find the `CharacterSpec` class. After the existing `damage_taken: int = 0` field (or any other simple int field on the class), add:

```python
    # Per-class HP rolled but not yet confirmed at level-up.  Maps class_id ->
    # the rolled HP awaiting confirmation.  Cleared when the level-up is
    # confirmed or cancelled.  See aose/engine/leveling.py.
    pending_level_up: dict[str, int] = Field(default_factory=dict)
```

`Field` is already imported.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py::test_pending_level_up_defaults_empty_and_roundtrips -q`
Expected: PASS

- [ ] **Step 5: Run the full suite to verify nothing else broke**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing pytest-current PermissionError on Windows).

- [ ] **Step 6: Commit**

```bash
git add aose/models/character.py tests/test_leveling.py
git commit -m "feat(model): add CharacterSpec.pending_level_up for Roll→Confirm advancement"
```

---

### Task 2: `ClassAdvancement.current_threshold`

**Files:**
- Modify: `aose/engine/leveling.py` (the `ClassAdvancement` model + `class_advancement()` function)
- Test: `tests/test_leveling.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_leveling.py` in the advancement section (near the other `test_advancement_*` tests):

```python
def test_advancement_current_threshold_l1_is_zero(data):
    """L1 characters: current_threshold is 0 (display floor)."""
    spec = _spec(level=1, xp=500)
    adv = class_advancement(spec, data, spec.classes[0])
    assert adv.current_threshold == 0


def test_advancement_current_threshold_matches_progression(data):
    """At L3 the current_threshold equals progression[3].xp_required."""
    spec = _spec(level=3, xp=5000, hp_rolls=[8, 8, 8])
    cls = data.classes["fighter"]
    expected = cls.progression[3].xp_required
    adv = class_advancement(spec, data, spec.classes[0])
    assert adv.current_threshold == expected


def test_advancement_current_threshold_at_max_level(data):
    """At max level, current_threshold still reads the current level's floor."""
    spec = _spec(level=14, xp=999999, hp_rolls=[8] * 14)
    cls = data.classes["fighter"]
    expected = cls.progression[14].xp_required
    adv = class_advancement(spec, data, spec.classes[0])
    assert adv.current_threshold == expected
    assert adv.at_max is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py -k current_threshold -q`
Expected: FAIL — `current_threshold` is not on the model.

- [ ] **Step 3: Add the field and populate it**

In `aose/engine/leveling.py`:

a) Add `current_threshold: int` to the `ClassAdvancement` model after `next_threshold`:

```python
class ClassAdvancement(BaseModel):
    class_id: str
    name: str
    current_level: int
    next_level: int | None
    next_threshold: int | None  # XP the class needs for its next level
    current_threshold: int      # XP floor of the current level (0 for L1)
    current_xp: int             # the class's own XP count
    can_level: bool
    at_max: bool
```

b) In `class_advancement()`, compute the value once near the top of the body and pass it into both `ClassAdvancement(...)` constructions. Replace the existing function body with:

```python
def class_advancement(spec: CharacterSpec, data: GameData,
                      entry: ClassEntry) -> ClassAdvancement:
    cls = data.classes[entry.class_id]
    next_level = entry.level + 1
    eff_max = _effective_max_level(spec, data, entry)
    current = entry.xp
    current_level_data = cls.progression.get(entry.level)
    current_threshold = current_level_data.xp_required if current_level_data else 0

    if next_level > eff_max or next_level not in cls.progression:
        return ClassAdvancement(
            class_id=entry.class_id,
            name=cls.name,
            current_level=entry.level,
            next_level=None,
            next_threshold=None,
            current_threshold=current_threshold,
            current_xp=current,
            can_level=False,
            at_max=True,
        )

    threshold = cls.progression[next_level].xp_required
    return ClassAdvancement(
        class_id=entry.class_id,
        name=cls.name,
        current_level=entry.level,
        next_level=next_level,
        next_threshold=threshold,
        current_threshold=current_threshold,
        current_xp=current,
        can_level=current >= threshold,
        at_max=False,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py -k current_threshold -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full leveling test file**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py -q`
Expected: PASS — all existing advancement assertions stay green because they don't inspect `current_threshold`.

- [ ] **Step 6: Commit**

```bash
git add aose/engine/leveling.py tests/test_leveling.py
git commit -m "feat(leveling): expose ClassAdvancement.current_threshold for in-level progress"
```

---

### Task 3: `cancel_pending_level_up()` helper

**Files:**
- Modify: `aose/engine/leveling.py` (add the helper)
- Test: `tests/test_leveling.py`

The simplest of the three new helpers; landing it first means later helpers can clear pending state by calling it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_leveling.py` in the engine section:

```python
def test_cancel_pending_level_up_clears_one_class(data):
    """Cancelling clears that class's pending entry without touching others."""
    from aose.engine.leveling import cancel_pending_level_up
    spec = _spec(multi=True, xp=8000)  # two classes
    spec.pending_level_up = {"fighter": 6, "magic_user": 3}
    cancel_pending_level_up(spec, "fighter")
    assert spec.pending_level_up == {"magic_user": 3}


def test_cancel_pending_level_up_is_idempotent(data):
    """Cancelling a class with no pending entry is a no-op (no KeyError)."""
    from aose.engine.leveling import cancel_pending_level_up
    spec = _spec()
    assert spec.pending_level_up == {}
    cancel_pending_level_up(spec, "fighter")  # must not raise
    assert spec.pending_level_up == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py -k cancel_pending_level_up -q`
Expected: FAIL — `cancel_pending_level_up` does not exist.

- [ ] **Step 3: Implement the helper**

Append to `aose/engine/leveling.py`, after `class_advancement()` and `all_advancement()`:

```python
def cancel_pending_level_up(spec: CharacterSpec, class_id: str) -> None:
    """Idempotently clear any pending level-up HP roll for ``class_id``."""
    spec.pending_level_up.pop(class_id, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py -k cancel_pending_level_up -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/leveling.py tests/test_leveling.py
git commit -m "feat(leveling): add cancel_pending_level_up engine helper"
```

---

### Task 4: `roll_pending_hp()` helper

**Files:**
- Modify: `aose/engine/leveling.py` (add the helper)
- Test: `tests/test_leveling.py`

`roll_pending_hp` validates the can-level / not-at-max / not-at-name-level / Strict-Mode-lock preconditions, then rolls a fresh hit die and stores the result in `spec.pending_level_up[class_id]`. It does **not** mutate `entry.level` or `entry.hp_rolls`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_leveling.py` engine section:

```python
def test_roll_pending_hp_stores_in_pending(data):
    """A successful roll lands in pending_level_up, leaves level & hp_rolls alone."""
    from aose.engine.leveling import roll_pending_hp
    spec = _spec(level=1, xp=2000)  # enough for L2 fighter (threshold 2000)
    rng = random.Random(7)
    rolled = roll_pending_hp(spec, data, "fighter", rng=rng)
    assert 1 <= rolled <= 8
    assert spec.pending_level_up == {"fighter": rolled}
    assert spec.classes[0].level == 1
    assert spec.classes[0].hp_rolls == [8]


def test_roll_pending_hp_xp_short_raises(data):
    from aose.engine.leveling import roll_pending_hp
    spec = _spec(level=1, xp=500)
    with pytest.raises(ValueError, match="Need 2000"):
        roll_pending_hp(spec, data, "fighter")
    assert spec.pending_level_up == {}


def test_roll_pending_hp_at_max_raises(data):
    from aose.engine.leveling import roll_pending_hp
    spec = _spec(level=14, xp=999999, hp_rolls=[8] * 14)
    with pytest.raises(ValueError, match="maximum level"):
        roll_pending_hp(spec, data, "fighter")


def test_roll_pending_hp_at_name_level_raises(data):
    """At/beyond name level there is no Hit Die to roll — caller should
    skip straight to confirm_level_up instead."""
    from aose.engine.leveling import roll_pending_hp
    cls = data.classes["fighter"]
    nl = cls.name_level
    threshold = cls.progression[nl + 1].xp_required
    spec = _spec(level=nl, xp=threshold, hp_rolls=[8] * nl)
    with pytest.raises(ValueError, match="name level"):
        roll_pending_hp(spec, data, "fighter")


def test_roll_pending_hp_strict_mode_locks_after_one_roll(data):
    """Under Strict Mode, a second roll while a pending value exists raises."""
    from aose.engine.leveling import roll_pending_hp
    spec = _spec(level=1, xp=2000, ruleset=RuleSet(strict_mode=True))
    roll_pending_hp(spec, data, "fighter", rng=random.Random(1))
    with pytest.raises(ValueError, match="locked"):
        roll_pending_hp(spec, data, "fighter", rng=random.Random(2))


def test_roll_pending_hp_non_strict_allows_reroll(data):
    """With Strict off, a second roll overwrites the pending value."""
    from aose.engine.leveling import roll_pending_hp
    spec = _spec(level=1, xp=2000, ruleset=RuleSet(strict_mode=False))
    first = roll_pending_hp(spec, data, "fighter", rng=random.Random(1))
    second = roll_pending_hp(spec, data, "fighter", rng=random.Random(2))
    assert spec.pending_level_up == {"fighter": second}
    # (first and second are independent; we just verify the second one stuck)
    _ = first


def test_roll_pending_hp_unknown_class_raises(data):
    from aose.engine.leveling import roll_pending_hp
    spec = _spec(level=1, xp=2000)
    with pytest.raises(ValueError, match="no class"):
        roll_pending_hp(spec, data, "cleric")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py -k roll_pending_hp -q`
Expected: FAIL — `roll_pending_hp` does not exist.

- [ ] **Step 3: Implement the helper**

Append to `aose/engine/leveling.py`:

```python
def roll_pending_hp(spec: CharacterSpec, data: GameData, class_id: str,
                    rng: Optional[random.Random] = None) -> int:
    """Roll the new level's hit die and store the result in
    ``spec.pending_level_up[class_id]``.

    Does NOT advance the class or touch ``hp_rolls`` — call
    :func:`confirm_level_up` to commit.  Raises ``ValueError`` if the class is
    missing, at max, short on XP, at/beyond name level (no die rolled), or if
    Strict Mode locks an existing pending roll.  Returns the rolled HP.
    """
    entry = next((e for e in spec.classes if e.class_id == class_id), None)
    if entry is None:
        raise ValueError(f"Character has no class {class_id!r}")

    advancement = class_advancement(spec, data, entry)
    if advancement.at_max:
        raise ValueError(f"{advancement.name} is already at maximum level")
    if not advancement.can_level:
        raise ValueError(
            f"Need {advancement.next_threshold} XP for {advancement.name} L"
            f"{advancement.next_level}, have {advancement.current_xp}"
        )

    cls = data.classes[class_id]
    if entry.level >= cls.name_level:
        raise ValueError(
            f"{advancement.name} L{advancement.next_level} is at or beyond name "
            f"level — no Hit Die rolled; confirm directly."
        )

    if spec.ruleset.strict_mode and class_id in spec.pending_level_up:
        raise ValueError("Hit points are already rolled and locked.")

    new_hp = roll_hp(cls.hit_die, rng=rng)
    spec.pending_level_up[class_id] = new_hp
    return new_hp
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py -k roll_pending_hp -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/leveling.py tests/test_leveling.py
git commit -m "feat(leveling): add roll_pending_hp helper for interactive level-up"
```

---

### Task 5: `confirm_level_up()` helper

**Files:**
- Modify: `aose/engine/leveling.py` (add the helper)
- Test: `tests/test_leveling.py`

`confirm_level_up` applies the pending roll (sub-name-level — requires one) and bumps `entry.level`; at/beyond name level it bumps the level without an HP roll.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_leveling.py`:

```python
def test_confirm_level_up_applies_pending_and_clears(data):
    """Sub-name-level confirm appends the pending roll, clears pending, bumps level."""
    from aose.engine.leveling import roll_pending_hp, confirm_level_up
    spec = _spec(level=1, xp=2000)
    rolled = roll_pending_hp(spec, data, "fighter", rng=random.Random(3))
    gained = confirm_level_up(spec, data, "fighter")
    assert gained == rolled
    assert spec.classes[0].level == 2
    assert spec.classes[0].hp_rolls == [8, rolled]
    assert spec.pending_level_up == {}


def test_confirm_level_up_sub_name_level_requires_pending(data):
    """Sub-name-level confirm with no pending roll raises."""
    from aose.engine.leveling import confirm_level_up
    spec = _spec(level=1, xp=2000)
    with pytest.raises(ValueError, match="No pending HP roll"):
        confirm_level_up(spec, data, "fighter")
    assert spec.classes[0].level == 1


def test_confirm_level_up_at_name_level_no_pending_needed(data):
    """At/beyond name level: confirm succeeds without a pending roll;
    level bumps; hp_rolls untouched; gained == 0."""
    from aose.engine.leveling import confirm_level_up
    cls = data.classes["fighter"]
    nl = cls.name_level
    threshold = cls.progression[nl + 1].xp_required
    spec = _spec(level=nl, xp=threshold, hp_rolls=[8] * nl)
    gained = confirm_level_up(spec, data, "fighter")
    assert gained == 0
    assert spec.classes[0].level == nl + 1
    assert spec.classes[0].hp_rolls == [8] * nl


def test_confirm_level_up_xp_short_raises(data):
    from aose.engine.leveling import confirm_level_up
    spec = _spec(level=1, xp=500)
    # Even with a stray pending value, can_level governs.
    spec.pending_level_up["fighter"] = 7
    with pytest.raises(ValueError, match="Need 2000"):
        confirm_level_up(spec, data, "fighter")
    assert spec.classes[0].level == 1


def test_confirm_level_up_at_max_raises(data):
    from aose.engine.leveling import confirm_level_up
    spec = _spec(level=14, xp=999999, hp_rolls=[8] * 14)
    with pytest.raises(ValueError, match="maximum level"):
        confirm_level_up(spec, data, "fighter")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py -k confirm_level_up -q`
Expected: FAIL — `confirm_level_up` does not exist.

- [ ] **Step 3: Implement the helper**

Append to `aose/engine/leveling.py`:

```python
def confirm_level_up(spec: CharacterSpec, data: GameData, class_id: str) -> int:
    """Commit a level-up.

    Sub-name-level: requires a pending HP roll in ``spec.pending_level_up``;
    appends it to ``entry.hp_rolls``, clears the pending entry, bumps
    ``entry.level``.  Returns the HP gained.

    At/beyond name level: no Hit Die is rolled, so a pending roll is neither
    needed nor consumed; bumps ``entry.level`` and returns 0.  (The flat
    ``hp_after_name_level`` is applied by ``hp.py``.)

    Raises ``ValueError`` if the class is missing, at max, short on XP, or if a
    pending roll is required but absent.
    """
    entry = next((e for e in spec.classes if e.class_id == class_id), None)
    if entry is None:
        raise ValueError(f"Character has no class {class_id!r}")

    advancement = class_advancement(spec, data, entry)
    if advancement.at_max:
        raise ValueError(f"{advancement.name} is already at maximum level")
    if not advancement.can_level:
        raise ValueError(
            f"Need {advancement.next_threshold} XP for {advancement.name} L"
            f"{advancement.next_level}, have {advancement.current_xp}"
        )

    cls = data.classes[class_id]
    if entry.level >= cls.name_level:
        entry.level += 1
        # Don't consume a stray pending entry — name-level confirms shouldn't
        # silently swallow data; the UI never sets one here.
        return 0

    if class_id not in spec.pending_level_up:
        raise ValueError(
            f"No pending HP roll for {advancement.name} — roll before confirming."
        )
    gained = spec.pending_level_up.pop(class_id)
    entry.hp_rolls.append(gained)
    entry.level += 1
    return gained
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py -k confirm_level_up -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/leveling.py tests/test_leveling.py
git commit -m "feat(leveling): add confirm_level_up helper for interactive level-up"
```

---

### Task 6: Refactor `level_up()` as a wrapper

**Files:**
- Modify: `aose/engine/leveling.py` (rewrite `level_up()`)
- Test: existing `tests/test_leveling.py` tests cover this — no new tests.

The original `level_up()` is now a thin convenience that calls the two new helpers. Strict Mode's "pending lock" doesn't apply to this single-shot path (nothing was pending beforehand). At/beyond name level it skips the roll entirely.

- [ ] **Step 1: Rewrite `level_up()`**

In `aose/engine/leveling.py`, replace the existing `level_up()` body with:

```python
def level_up(spec: CharacterSpec, data: GameData, class_id: str,
             rng: Optional[random.Random] = None) -> int:
    """Advance the named class by one level in one shot.

    Convenience wrapper around :func:`roll_pending_hp` and
    :func:`confirm_level_up` for callers that don't need the interactive
    Roll → Confirm split (tests, scripts, legacy route).  Sub-name-level:
    rolls a fresh hit die, applies it, returns the new roll.  At/beyond name
    level: bumps the level only, returns 0.
    """
    entry = next((e for e in spec.classes if e.class_id == class_id), None)
    if entry is None:
        raise ValueError(f"Character has no class {class_id!r}")
    cls = data.classes[class_id]
    if entry.level >= cls.name_level:
        return confirm_level_up(spec, data, class_id)
    rolled = roll_pending_hp(spec, data, class_id, rng=rng)
    confirm_level_up(spec, data, class_id)
    return rolled
```

(The original behaviour is preserved: same return value, same mutation, same `ValueError`s on the same conditions. The Strict-Mode lock inside `roll_pending_hp` doesn't fire because there's no prior pending entry for this `class_id`.)

- [ ] **Step 2: Run the entire leveling test file**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py -q`
Expected: PASS — every existing `test_level_up_*` test still goes green via the wrapper.

- [ ] **Step 3: Run the full suite to verify nothing depended on the old internals**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add aose/engine/leveling.py
git commit -m "refactor(leveling): make level_up a wrapper around roll_pending_hp + confirm"
```

---

### Task 7: New routes — `/roll`, `/confirm`, `/cancel`

**Files:**
- Modify: `aose/web/routes.py` (add three handlers + import)
- Test: `tests/test_leveling.py`

- [ ] **Step 1: Write the failing route tests**

Append to `tests/test_leveling.py` in the HTTP endpoint section:

```python
def test_level_up_roll_route_stores_pending_and_303s(client):
    _seed(client, level=1, xp=2000)
    r = client.post("/character/test/level-up/fighter/roll")
    assert r.status_code == 303
    assert r.headers["location"] == "/character/test"
    spec = load_character("test", client._characters_dir)
    assert "fighter" in spec.pending_level_up
    assert 1 <= spec.pending_level_up["fighter"] <= 8
    # Did NOT advance.
    assert spec.classes[0].level == 1
    assert len(spec.classes[0].hp_rolls) == 1


def test_level_up_roll_route_strict_lock_400s(client):
    """A second Roll under Strict Mode while a pending exists returns 400."""
    _seed(client, level=1, xp=2000, ruleset=RuleSet(strict_mode=True))
    client.post("/character/test/level-up/fighter/roll")
    r = client.post("/character/test/level-up/fighter/roll")
    assert r.status_code == 400
    assert "locked" in r.json()["detail"].lower()


def test_level_up_roll_route_xp_short_400s(client):
    _seed(client, level=1, xp=500)
    r = client.post("/character/test/level-up/fighter/roll")
    assert r.status_code == 400


def test_level_up_confirm_route_advances_and_clears_pending(client):
    _seed(client, level=1, xp=2000)
    client.post("/character/test/level-up/fighter/roll")
    spec_before = load_character("test", client._characters_dir)
    pending = spec_before.pending_level_up["fighter"]

    r = client.post("/character/test/level-up/fighter/confirm")
    assert r.status_code == 303
    spec_after = load_character("test", client._characters_dir)
    assert spec_after.classes[0].level == 2
    assert spec_after.classes[0].hp_rolls == [8, pending]
    assert spec_after.pending_level_up == {}


def test_level_up_confirm_without_roll_400s(client):
    """Sub-name-level confirm with no pending roll returns 400."""
    _seed(client, level=1, xp=2000)
    r = client.post("/character/test/level-up/fighter/confirm")
    assert r.status_code == 400


def test_level_up_cancel_route_clears_pending(client):
    _seed(client, level=1, xp=2000)
    client.post("/character/test/level-up/fighter/roll")
    r = client.post("/character/test/level-up/fighter/cancel")
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.pending_level_up == {}
    assert spec.classes[0].level == 1


def test_level_up_cancel_is_idempotent(client):
    _seed(client, level=1, xp=2000)
    r = client.post("/character/test/level-up/fighter/cancel")
    assert r.status_code == 303
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py -k "level_up_roll_route or level_up_confirm or level_up_cancel" -q`
Expected: FAIL — routes are 404.

- [ ] **Step 3: Add the route imports**

In `aose/web/routes.py`, replace the existing leveling import line:

```python
from aose.engine.leveling import grant_xp as _grant_xp, level_up as _level_up
```

with:

```python
from aose.engine.leveling import (
    grant_xp as _grant_xp,
    level_up as _level_up,
    roll_pending_hp as _roll_pending_hp,
    confirm_level_up as _confirm_level_up,
    cancel_pending_level_up as _cancel_pending_level_up,
)
```

- [ ] **Step 4: Add the three route handlers**

In `aose/web/routes.py`, immediately after the existing `level_up_class` handler (the `@router.post("/character/{character_id}/level-up/{class_id}")` block), add:

```python
@router.post("/character/{character_id}/level-up/{class_id}/roll")
async def level_up_roll(request: Request, character_id: str, class_id: str):
    """Roll the new level's hit die into ``spec.pending_level_up[class_id]``
    without advancing the class.  400 if the roll is rejected (XP short, at
    max, at/beyond name level, or Strict-Mode lock)."""
    spec = _load_spec_or_404(request, character_id)
    try:
        _roll_pending_hp(spec, request.app.state.game_data, class_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/level-up/{class_id}/confirm")
async def level_up_confirm(request: Request, character_id: str, class_id: str):
    """Commit a pending level-up: apply the pending HP roll (sub-name-level)
    or just bump the level (at/beyond name level)."""
    spec = _load_spec_or_404(request, character_id)
    try:
        _confirm_level_up(spec, request.app.state.game_data, class_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/level-up/{class_id}/cancel")
async def level_up_cancel(request: Request, character_id: str, class_id: str):
    """Idempotently clear any pending HP roll for this class."""
    spec = _load_spec_or_404(request, character_id)
    _cancel_pending_level_up(spec, class_id)
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py -k "level_up_roll_route or level_up_confirm or level_up_cancel" -q`
Expected: PASS (7 tests).

- [ ] **Step 6: Run the full leveling test file**

Run: `.venv\Scripts\python.exe -m pytest tests/test_leveling.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add aose/web/routes.py tests/test_leveling.py
git commit -m "feat(routes): /level-up/{class_id}/{roll,confirm,cancel} endpoints"
```

---

### Task 8: Sheet header rewrite — XP form, Energy Drain trigger, per-class progress

**Files:**
- Modify: `aose/web/templates/sheet.html` (the `<div class="xp">` block in the page header)

This rewrites the header section that loops over `sheet.advancement`. The single "Advance" button is removed. An inline "Add XP" form and an "Energy Drain" button sit above the per-class rows. Each per-class row shows a Level-Up button only when `adv.can_level`.

- [ ] **Step 1: Replace the header `<div class="xp">` block**

In `aose/web/templates/sheet.html`, find this block (around lines 33–48):

```html
    <div class="xp">
      {% for adv in sheet.advancement %}
      <div class="xp-track">
        <div class="cls">{{ adv.name }} L{{ adv.current_level }}</div>
        <div class="bar2">
          {% if not adv.at_max %}
          <i style="width:{{ (adv.current_xp / adv.next_threshold * 100)|round }}%"></i>
          {% else %}
          <i style="width:100%"></i>
          {% endif %}
        </div>
        <div class="num">{{ adv.current_xp }} / {{ adv.next_threshold or '—' }}</div>
      </div>
      {% endfor %}
      <button class="btn tool" data-modal="modal-advance">Advance</button>
    </div>
```

Replace it with:

```html
    <div class="xp">
      <div class="xp-controls">
        <form method="post" action="/character/{{ character_id }}/xp" class="inline-form">
          <label class="muted small">Add XP</label>
          <input type="number" name="amount" value="100" step="50" style="width:90px">
          <button class="btn solid" type="submit">Grant</button>
        </form>
        <button class="btn tool" data-modal="modal-drain">Energy Drain</button>
      </div>
      {% for adv in sheet.advancement %}
      <div class="xp-track">
        <div class="cls">{{ adv.name }} L{{ adv.current_level }}</div>
        <div class="bar2">
          {% if adv.at_max %}
          <i style="width:100%"></i>
          {% else %}
          {%- set span = adv.next_threshold - adv.current_threshold -%}
          {%- set into = adv.current_xp - adv.current_threshold -%}
          {%- set pct = 0 if span <= 0 else ((into / span) * 100)|round -%}
          {%- if pct < 0 -%}{%- set pct = 0 -%}{%- endif -%}
          {%- if pct > 100 -%}{%- set pct = 100 -%}{%- endif -%}
          <i style="width:{{ pct }}%"></i>
          {% endif %}
        </div>
        <div class="num">{{ adv.current_xp }} / {{ adv.next_threshold or '—' }}</div>
        {% if adv.at_max %}
        <span class="pill">Max</span>
        {% elif adv.can_level %}
        <button class="btn solid" data-modal="modal-levelup-{{ adv.class_id }}">Level Up → {{ adv.next_level }}</button>
        {% endif %}
      </div>
      {% endfor %}
    </div>
```

- [ ] **Step 2: Start the dev server**

Run: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
Expected: server up on http://127.0.0.1:8000.

- [ ] **Step 3: Smoke-test in the browser**

Open an existing character's sheet. Verify:
- Header shows the "Add XP" inline form and the "Energy Drain" button above the class rows.
- Class rows render with the new progress bar — for a character mid-level the bar is short, not nearly-full.
- No "Level Up" button appears when XP is short.
- The old "Advance" button is gone.

(The Energy Drain button currently does nothing useful — its modal is added in Task 9. The Level-Up button is wired in Task 10. This is expected.)

- [ ] **Step 4: Run the suite (template-render tests may need updating)**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: any test that asserted on the "Advance" button text or `modal-advance` overlay will fail. Update such assertions to look for the new strings (`Add XP`, `Energy Drain`) or remove them. If none fail, the suite stays green.

- [ ] **Step 5: Commit**

```bash
git add aose/web/templates/sheet.html
git commit -m "feat(sheet): header XP controls + per-class progress within current level"
```

---

### Task 9: `modal-drain` overlay

**Files:**
- Modify: `aose/web/templates/sheet.html` (move the Energy Drain form out of `modal-advance` into a new standalone modal)

- [ ] **Step 1: Add the drain overlay**

In `aose/web/templates/sheet.html`, find the existing `modal-advance` block (starts with `<div class="overlay modal" id="modal-advance"`). Just *before* that block, insert:

```html
{# MODAL: energy drain #}
<div class="overlay modal" id="modal-drain" role="dialog" aria-label="Energy Drain">
  <div class="ov-head"><h3>Energy Drain</h3><button class="x" data-close>×</button></div>
  <div class="ov-body">
    <p class="muted small">
      Permanently drains experience levels LIFO from the most recently advanced
      class.  Removes the matching Hit Dice and now-inaccessible spells.
      This is a GM action and cannot be undone.
    </p>
    <form method="post" action="/character/{{ character_id }}/energy-drain"
          onsubmit="return confirm('Energy drain ' + this.levels.value + ' level(s)? This is permanent.');">
      <div class="inline-form">
        <input type="number" name="levels" value="1" min="1">
        <label><input type="radio" name="xp_mode" value="midpoint"> Midpoint</label>
        <label><input type="radio" name="xp_mode" value="new_min" checked> New min</label>
        <button class="btn danger" type="submit">Drain</button>
      </div>
    </form>
  </div>
</div>
```

- [ ] **Step 2: Smoke-test in the browser**

Reload the sheet. Click "Energy Drain" in the header. The new modal opens with the same form as before. Pressing Drain still hits `/energy-drain` and behaves identically.

- [ ] **Step 3: Commit**

```bash
git add aose/web/templates/sheet.html
git commit -m "feat(sheet): standalone Energy Drain modal triggered from header"
```

---

### Task 10: Per-class `modal-levelup-{class_id}` overlays + remove `modal-advance`

**Files:**
- Modify: `aose/web/templates/sheet.html` (replace `modal-advance` block with a loop emitting one level-up modal per class)

This is the user-visible heart of the change. One modal per class entry, rendered next to the drain modal. The modal contents branch on three conditions:
1. `adv.at_max` — render nothing (button isn't shown either, but render-safe to skip).
2. `entry.level >= cls.name_level` (need access to both) — flat-HP confirm-only flow.
3. Sub-name-level — Roll → Confirm with Strict-Mode-aware re-roll.

We need the class's `name_level` and `hp_after_name_level` in the template, plus the per-class CON modifier, the pending roll, and the Strict-Mode flag. The cleanest minimal addition is to pre-compute a `level_up_modals` list in `build_sheet()` rather than reaching for raw `data` inside the template.

#### Step A: Extend the sheet view

- [ ] **Step 1: Find `build_sheet` in `aose/sheet/view.py` and locate the advancement block**

Run: `.venv\Scripts\python.exe -c "from aose.sheet.view import build_sheet; import inspect; print(inspect.getsourcefile(build_sheet))"`

Open that file. Find where `advancement` is assigned (it should already call `all_advancement(spec, data)`).

- [ ] **Step 2: Add a `LevelUpModal` model + build the list**

Near the top of `aose/sheet/view.py`, after the existing imports, add a small Pydantic model (next to any existing sheet-view models — match the file's style; if it uses `dataclass`es instead, use a `dataclass` here):

```python
class LevelUpModal(BaseModel):
    class_id: str
    class_name: str
    current_level: int
    next_level: int
    hit_die: str
    con_mod: int               # per-class effective CON modifier
    at_name_level: bool        # if true, next level is at/past name_level → flat HP, no roll
    flat_hp: int               # hp_after_name_level (only meaningful when at_name_level)
    pending: int | None        # currently rolled-but-not-confirmed HP, if any
    strict_mode: bool
    can_level: bool            # mirrors ClassAdvancement.can_level
```

If the file already uses `BaseModel` for its sheet view models, reuse `BaseModel`; otherwise mirror the existing pattern (likely `BaseModel` since `view.py` defines `SpellbookBlock` etc.).

Then, in `build_sheet()`, after `advancement = all_advancement(spec, data)` (the existing line), add:

```python
    # Build per-class level-up modal context.  One entry per class regardless
    # of XP — the template hides modals for classes that can't level — so the
    # data is stable across page renders.
    from aose.engine.ability_mods import ability_modifier
    from aose.engine.magic import effective_abilities
    eff_abilities = effective_abilities(spec, data)
    con_mod = ability_modifier(eff_abilities["CON"])
    level_up_modals = []
    for entry, adv in zip(spec.classes, advancement):
        cls = data.classes[entry.class_id]
        next_level = adv.next_level if adv.next_level is not None else entry.level + 1
        level_up_modals.append(LevelUpModal(
            class_id=entry.class_id,
            class_name=cls.name,
            current_level=entry.level,
            next_level=next_level,
            hit_die=cls.hit_die,
            con_mod=con_mod,
            at_name_level=(entry.level >= cls.name_level),
            flat_hp=cls.hp_after_name_level,
            pending=spec.pending_level_up.get(entry.class_id),
            strict_mode=spec.ruleset.strict_mode,
            can_level=adv.can_level,
        ))
```

Then add `level_up_modals=level_up_modals` to the `CharacterSheet(...)` constructor call. Also add the field to the `CharacterSheet` model (find its class definition higher in the file and append):

```python
    level_up_modals: list[LevelUpModal] = Field(default_factory=list)
```

(If `LevelUpModal` ends up forward-referenced, define it before `CharacterSheet`.)

- [ ] **Step 3: Run the suite to verify the view-extension is benign**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS — no existing test asserts the absence of `level_up_modals`.

#### Step B: Replace `modal-advance` in the template

- [ ] **Step 4: Delete the existing `modal-advance` block**

In `aose/web/templates/sheet.html`, find the entire `{# MODAL: advancement #}` block — from the leading comment through the closing `</div>` of the modal — and delete it.

- [ ] **Step 5: Insert per-class level-up modals**

Where `modal-advance` used to live, insert:

```html
{# MODAL: level-up — one per class entry (only triggerable when adv.can_level) #}
{% for m in sheet.level_up_modals %}
<div class="overlay modal" id="modal-levelup-{{ m.class_id }}" role="dialog" aria-label="Level Up: {{ m.class_name }}">
  <div class="ov-head">
    <h3>{{ m.class_name }} — Level {{ m.next_level }}</h3>
    <button class="x" data-close>×</button>
  </div>
  <div class="ov-body">
    {% if m.at_name_level %}
    <p class="muted small">
      Past name level — gains a flat <strong>+{{ m.flat_hp }}</strong> HP. No Hit Die is rolled.
    </p>
    <form method="post" action="/character/{{ character_id }}/level-up/{{ m.class_id }}/confirm" class="inline-form">
      <button class="btn solid" type="submit">Confirm Level Up</button>
    </form>
    <form method="post" action="/character/{{ character_id }}/level-up/{{ m.class_id }}/cancel" class="inline-form" style="margin-top:6px">
      <button class="btn" type="submit">Cancel</button>
    </form>
    {% else %}
    <p class="muted small">
      Rolls <strong>1{{ m.hit_die }}</strong> for the new level. CON modifier:
      <strong>{{ "%+d"|format(m.con_mod) }}</strong> (applied as part of total HP).
    </p>
    {% if m.pending is none %}
    <form method="post" action="/character/{{ character_id }}/level-up/{{ m.class_id }}/roll" class="inline-form">
      <button class="btn solid" type="submit">Roll HP</button>
    </form>
    {% else %}
    <p>Rolled: <span class="stat-big">{{ m.pending }}</span></p>
    <div class="inline-form" style="gap:6px">
      {% if not m.strict_mode %}
      <form method="post" action="/character/{{ character_id }}/level-up/{{ m.class_id }}/roll" class="inline-form">
        <button class="btn" type="submit">Re-roll</button>
      </form>
      {% endif %}
      <form method="post" action="/character/{{ character_id }}/level-up/{{ m.class_id }}/confirm" class="inline-form">
        <button class="btn solid" type="submit">Confirm Level Up</button>
      </form>
    </div>
    {% endif %}
    <form method="post" action="/character/{{ character_id }}/level-up/{{ m.class_id }}/cancel" class="inline-form" style="margin-top:6px">
      <button class="btn" type="submit">Cancel</button>
    </form>
    {% endif %}
  </div>
</div>
{% endfor %}
```

- [ ] **Step 6: Smoke-test in the browser**

Reload the sheet for a character that has enough XP to level up one class (use the Add XP form to top them up if needed):

1. The "Level Up → N" button is visible next to the qualifying class's progress row.
2. Click it. The class's level-up modal opens.
3. Press "Roll HP". The modal closes (redirect), the sheet reloads, you click "Level Up → N" again, and now the modal shows the rolled HP and a "Confirm Level Up" button. Under Strict Mode there is no Re-roll button; with Strict off (toggle the rule on `/settings` for the test), a Re-roll button appears.
4. Press "Confirm Level Up". The class's `current_level` in the header is now N, `hp_rolls` has grown by one (visible by inspecting the HP total), and `pending_level_up` is cleared (re-opening the modal shows "Roll HP" again — but only if the class qualifies for *another* level immediately).
5. Test Cancel: with a pending roll set, press Cancel — the next page reload shows "Roll HP" instead of the pending result.

For at-name-level: harder to smoke-test without a high-level character, but the engine tests cover it.

- [ ] **Step 7: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS. Any test that referenced the old `modal-advance` markup needs updating to the new `modal-levelup-*` / `modal-drain` IDs.

- [ ] **Step 8: Commit**

```bash
git add aose/sheet/view.py aose/web/templates/sheet.html
git commit -m "feat(sheet): interactive per-class level-up modals (Roll → Confirm)"
```

---

### Task 11: Final verification + STYLE-GUIDE update

**Files:**
- Modify: `docs/STYLE-GUIDE.md` (add a one-line note about the advancement pattern, if the guide documents UI patterns)

The STYLE-GUIDE is the cross-cutting reference for sheet UI; CLAUDE.md says any sheet/UI work should read it first. A quick note about Roll → Confirm advancement helps future agents.

- [ ] **Step 1: Inspect the style guide for an appropriate section**

Run: `.venv\Scripts\python.exe -c "print('see docs/STYLE-GUIDE.md')"` then open the file. Look for an existing section on overlay patterns or on multi-step interactions.

- [ ] **Step 2: Append a brief note**

If there's an "Interaction patterns" or "Overlays" section, add a bullet like:

```
- **Roll → Confirm at level-up.** Sub-name-level advancement uses a two-step
  flow: a `roll` POST stores HP in `CharacterSpec.pending_level_up`, then a
  `confirm` POST commits it.  Strict Mode locks the pending roll;
  Strict off allows re-roll until confirm.  Mirrors the wizard's L1 HP step.
```

If no such section exists, skip this step — the in-code docstrings on the engine helpers are documentation enough.

- [ ] **Step 3: Final full suite + manual smoke**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS.

Manual smoke checklist:
- Sheet header shows Add XP form + Energy Drain button + per-class rows.
- Per-class progress bars are accurate within the current level (L1 character: 0% at 0 XP; halfway through L2 threshold-to-L3-threshold: 50%).
- Level Up button appears exactly when `can_level`, disappears when XP is short, and shows "Max" pill at max level.
- Modal Roll → Confirm flow works end to end; Strict Mode lock works; Re-roll appears with Strict off.
- Energy Drain modal opens, still drains correctly.
- Add XP grants XP via the existing route.

- [ ] **Step 4: Commit (only if STYLE-GUIDE changed)**

```bash
git add docs/STYLE-GUIDE.md
git commit -m "docs(style-guide): note Roll → Confirm advancement flow"
```

---

## Self-review against the spec

**Spec coverage**

- ✅ "Show Level Up only when can_level" — Task 8 (template gating).
- ✅ "Progress through current level" — Tasks 2 (`current_threshold`) + 8 (Jinja math).
- ✅ "Roll → Confirm interactive HP" — Tasks 1 (state), 4–5 (engine), 7 (routes), 10 (UI).
- ✅ "Honour Strict Mode like the wizard" — Tasks 4 (engine lock) + 10 (UI hides Re-roll).
- ✅ "Move Add XP into header" — Task 8.
- ✅ "Move Energy Drain into its own overlay" — Task 9.
- ✅ At/beyond name level: confirm-only flow — Tasks 4 (refuses roll), 5 (no pending needed), 10 (UI branch).
- ✅ Backward-compat with existing `level_up()` callers — Task 6 (wrapper).
- ✅ "Weapon proficiencies at level-up" is a stated non-goal, noted as follow-up in the spec.

**Placeholder scan:** None. All code blocks are complete; all run commands are exact; no "TBD"/"TODO"/"similar to Task N".

**Type consistency:** `pending_level_up: dict[str, int]` used identically in Tasks 1, 3, 4, 5, 7. `current_threshold: int` used identically in Tasks 2, 8. `LevelUpModal` field names match between Task 10 Step 2 (model) and Step 5 (template).

---

**Plan complete and saved to `docs/superpowers/plans/2026-06-05-advancement-ux.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
