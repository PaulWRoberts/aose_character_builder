# On-Sheet Character State Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let players manage current HP, spell memorization/casting (as individual slots), and rest recovery directly from the live character sheet during play.

**Architecture:** A "play state" layer over the existing build model. HP is stored as a `damage_taken` counter on `CharacterSpec` (current HP = `max(0, max_hp − damage_taken)`, dead derived from current==0). Prepared spells become `ClassEntry.slots: list[SpellSlot]` (one row per memorized spell, tracking reversed + spent). New pure logic extends the existing cycle-free cores `aose/engine/hp.py` (HP state) and `aose/engine/spells.py` (slot + rest-slot ops); routes orchestrate rest. No data migration — the app is single-user/local (per project convention).

**Tech Stack:** Python, FastAPI, Pydantic v2, Jinja2, pytest. Run app: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`. Run tests: `.venv\Scripts\python.exe -m pytest tests/ -q`.

**Commit convention:** Conventional-commit subject; end every commit message body with the trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

**Spec:** `docs/superpowers/specs/2026-06-02-on-sheet-character-state-design.md`

---

## File map

| File | Responsibility | Action |
|---|---|---|
| `aose/models/character.py` | `SpellSlot` value type; `ClassEntry.slots` (replaces `prepared`); `CharacterSpec.damage_taken` | Modify |
| `aose/models/__init__.py` | Export `SpellSlot` | Modify |
| `aose/engine/hp.py` | HP state fns: `current_hp`, `is_dead`, `apply_damage`, `apply_healing`, `set_current_hp` | Modify |
| `aose/engine/spells.py` | Slot ops: `assign_slot`, `clear_slot`, `cast_slot`, `restore_slot`, `restore_all_slots`, `clear_all_slots`; remove `prepare`/`unprepare` | Modify |
| `aose/sheet/view.py` | `CharacterSheet.current_hp`/`is_dead`; `SlotView`; `SpellLevelGroup`/`spells_view` reworked to slots (`slot_groups`) | Modify |
| `aose/web/routes.py` | HP routes, slot routes, rest routes; remove prepare/unprepare routes; `rest_heal_roll` in sheet GET | Modify |
| `aose/web/templates/sheet.html` | HP block (current/max + status + forms), slot-based Spells UI, Rest controls | Modify |
| `tests/test_hp_state.py` | HP engine unit tests | Create |
| `tests/test_spell_slots.py` | Slot engine unit tests | Create |
| `tests/test_rest_routes.py` | Rest + HP + slot route tests | Create |
| `tests/test_spells.py`, `tests/test_spell_routes.py` | Update `prepared`→`slots` references | Modify |

---

## Task 1: Data model — SpellSlot, ClassEntry.slots, CharacterSpec.damage_taken

**Files:**
- Modify: `aose/models/character.py`
- Modify: `aose/models/__init__.py`
- Test: `tests/test_spells.py` (update existing model tests)

- [ ] **Step 1: Update the failing model tests**

In `tests/test_spells.py`, replace the three model tests that reference `prepared`:

```python
def test_class_entry_has_spellbook_and_slots():
    from aose.models import ClassEntry
    e = ClassEntry(class_id="magic_user", level=1, hp_rolls=[3])
    assert e.spellbook == []
    assert e.slots == []


def test_class_entry_migrates_legacy_chosen_spells():
    # Old saved characters carried an (always-empty) chosen_spells field. Under
    # extra="forbid" that would fail to load; a before-validator strips it so
    # legacy saves survive rather than silently vanishing from the index.
    from aose.models import ClassEntry
    e = ClassEntry(class_id="magic_user", chosen_spells=[])
    assert not hasattr(e, "chosen_spells")
    assert e.spellbook == []
    assert e.slots == []


def test_thorin_example_loads():
    import json
    from aose.models import CharacterSpec
    raw = json.loads((PROJECT_ROOT / "examples" / "thorin.json").read_text(encoding="utf-8"))
    spec = CharacterSpec.model_validate(raw)
    assert spec.classes[0].spellbook == []
    assert spec.classes[0].slots == []
    assert spec.damage_taken == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -k "class_entry or thorin" -q`
Expected: FAIL — `ClassEntry` has no `slots`; `CharacterSpec` has no `damage_taken`.

- [ ] **Step 3: Add `SpellSlot`, swap `prepared`→`slots`, add `damage_taken`**

In `aose/models/character.py`, add `SpellSlot` above `ClassEntry`:

```python
class SpellSlot(BaseModel):
    """One memorized-spell slot in a caster's daily loadout.

    A slot holds at most one spell of a fixed ``level``.  ``reversed`` is an
    arcane-only choice fixed at memorization (divine slots always store False;
    the normal/reversed choice for divine spells is made at cast time and not
    persisted).  ``spent`` flips True when the slot is cast and resets on rest.
    """
    model_config = ConfigDict(extra="forbid")

    level: int
    spell_id: str | None = None
    reversed: bool = False
    spent: bool = False
```

In `ClassEntry`, replace the `prepared` field (and its docstring) with:

```python
    # Daily memorized loadout as individual slots; duplicates allowed (two slots,
    # same spell_id).  Hard-capped per spell level by spell_slots.  Replaces the
    # old flat ``prepared`` list — each slot also tracks reversed/spent state.
    slots: list[SpellSlot] = Field(default_factory=list)
```

In `CharacterSpec`, add after the `gold` field:

```python
    # Play-state: hit points of damage taken.  Current HP is derived as
    # max(0, max_hp − damage_taken); dead == current HP 0.  Tracks live max_hp
    # shifts (e.g. a CON-altering magic item) without rewriting stored state.
    damage_taken: int = 0
```

- [ ] **Step 4: Export `SpellSlot`**

In `aose/models/__init__.py`, update the import and `__all__`:

```python
from .character import CharacterSpec, ClassEntry, ContainerInstance, MagicItemInstance, SpellSlot
```

Add `"SpellSlot",` to `__all__` next to `"ClassEntry",`.

- [ ] **Step 5: Run the model tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -k "class_entry or thorin" -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/models/character.py aose/models/__init__.py tests/test_spells.py
git commit -m "feat(state): SpellSlot model, ClassEntry.slots, damage_taken"
```

---

## Task 2: HP state engine

**Files:**
- Modify: `aose/engine/hp.py`
- Test: `tests/test_hp_state.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_hp_state.py`:

```python
"""Unit tests for the HP play-state engine (current/damage/heal/set)."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine import hp
from aose.models import CharacterSpec, ClassEntry

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def _fighter(max_roll=12, con=10, damage_taken=0):
    """Single-class fighter whose max HP == max_roll (CON 10 → +0)."""
    return CharacterSpec(
        name="Bran",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": con, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[max_roll])],
        alignment="neutral",
        damage_taken=damage_taken,
    )


def test_current_hp_and_not_dead(data):
    spec = _fighter()
    assert hp.max_hp(spec, data) == 12
    assert hp.current_hp(spec, data) == 12
    assert hp.is_dead(spec, data) is False


def test_apply_damage_5_of_12(data):
    spec = _fighter()
    spec.damage_taken = hp.apply_damage(spec, data, 5)
    assert hp.current_hp(spec, data) == 7
    assert hp.is_dead(spec, data) is False


def test_damage_to_zero_marks_dead(data):
    spec = _fighter(damage_taken=5)  # 7/12
    spec.damage_taken = hp.apply_damage(spec, data, 10)
    assert hp.current_hp(spec, data) == 0
    assert hp.is_dead(spec, data) is True


def test_healing_caps_at_max(data):
    spec = _fighter(damage_taken=3)  # 9/12
    spec.damage_taken = hp.apply_healing(spec, data, 6)
    assert hp.current_hp(spec, data) == 12


def test_set_above_max_clamps_to_max(data):
    spec = _fighter(damage_taken=5)
    spec.damage_taken = hp.set_current_hp(spec, data, 99)
    assert hp.current_hp(spec, data) == 12


def test_set_below_zero_clamps_to_zero(data):
    spec = _fighter()
    spec.damage_taken = hp.set_current_hp(spec, data, -4)
    assert hp.current_hp(spec, data) == 0
    assert hp.is_dead(spec, data) is True


def test_negative_amount_rejected(data):
    spec = _fighter()
    with pytest.raises(ValueError):
        hp.apply_damage(spec, data, -1)
    with pytest.raises(ValueError):
        hp.apply_healing(spec, data, -1)


def test_damage_taken_tracks_max_shift(data):
    # Same damage_taken; a higher CON raises max_hp, so current HP rises with it
    # (the damage-taken model never destructively lowers current).
    low = _fighter(con=10, damage_taken=5)    # max 12 → current 7
    high = _fighter(con=16, damage_taken=5)   # CON 16 → +2 → max 14 → current 9
    assert hp.current_hp(low, data) == 7
    assert hp.max_hp(high, data) == 14
    assert hp.current_hp(high, data) == 9
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_hp_state.py -q`
Expected: FAIL — `hp` has no `current_hp` / `apply_damage` / etc.

- [ ] **Step 3: Implement the HP state functions**

Append to `aose/engine/hp.py`:

```python
# ── Play-state: current HP, damage, healing ────────────────────────────────

def current_hp(spec: CharacterSpec, data: GameData) -> int:
    """Current hit points: ``max(0, max_hp − damage_taken)``."""
    return max(0, max_hp(spec, data) - spec.damage_taken)


def is_dead(spec: CharacterSpec, data: GameData) -> bool:
    """A character is dead when current HP is 0 (derived, not stored)."""
    return current_hp(spec, data) == 0


def apply_damage(spec: CharacterSpec, data: GameData, amount: int) -> int:
    """Return the new ``damage_taken`` after taking ``amount`` (>=0) damage,
    capped so current HP never drops below 0."""
    if amount < 0:
        raise ValueError("damage amount must be non-negative")
    return min(max_hp(spec, data), spec.damage_taken + amount)


def apply_healing(spec: CharacterSpec, data: GameData, amount: int) -> int:
    """Return the new ``damage_taken`` after healing ``amount`` (>=0), floored
    at 0 (current HP never exceeds max)."""
    if amount < 0:
        raise ValueError("healing amount must be non-negative")
    return max(0, spec.damage_taken - amount)


def set_current_hp(spec: CharacterSpec, data: GameData, value: int) -> int:
    """Return the ``damage_taken`` that sets current HP to ``value``, clamped to
    ``[0, max_hp]``."""
    m = max_hp(spec, data)
    clamped = max(0, min(m, value))
    return m - clamped
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_hp_state.py -q`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/hp.py tests/test_hp_state.py
git commit -m "feat(state): HP play-state engine (damage/heal/set/current)"
```

---

## Task 3: Spell-slot engine (assign/cast/restore/clear + rest ops)

**Files:**
- Modify: `aose/engine/spells.py`
- Test: `tests/test_spell_slots.py` (create)
- Test: `tests/test_spells.py` (remove the obsolete prepare/unprepare tests)

- [ ] **Step 1: Write the failing slot tests**

Create `tests/test_spell_slots.py`:

```python
"""Unit tests for the spell-slot engine (memorize/cast/restore/clear/rest)."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine import spells
from aose.engine.spells import SpellError
from aose.models import ClassEntry, SpellSlot

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def _mu(spellbook, slots=None):
    return ClassEntry(class_id="magic_user", level=1, hp_rolls=[3],
                      spellbook=spellbook, slots=slots or [])


def test_assign_slot_known_and_level(data):
    cls = data.classes["magic_user"]
    e = _mu(["magic_user_magic_missile"])
    e2 = spells.assign_slot(e, cls, data, 1, "magic_user_magic_missile")
    assert len(e2.slots) == 1
    assert e2.slots[0].spell_id == "magic_user_magic_missile"
    assert e2.slots[0].spent is False
    assert e2.slots[0].reversed is False


def test_assign_slot_rejects_unknown(data):
    cls = data.classes["magic_user"]
    e = _mu(["magic_user_magic_missile"])
    with pytest.raises(SpellError):
        spells.assign_slot(e, cls, data, 1, "magic_user_sleep")  # not in book


def test_assign_slot_rejects_wrong_level(data):
    cls = data.classes["magic_user"]
    e = _mu(["magic_user_magic_missile"])
    with pytest.raises(SpellError):
        spells.assign_slot(e, cls, data, 2, "magic_user_magic_missile")


def test_assign_slot_respects_cap(data):
    cls = data.classes["magic_user"]  # L1 magic-user: one level-1 slot
    e = _mu(["magic_user_magic_missile", "magic_user_sleep"])
    e = spells.assign_slot(e, cls, data, 1, "magic_user_magic_missile")
    with pytest.raises(SpellError):
        spells.assign_slot(e, cls, data, 1, "magic_user_sleep")


def test_assign_slot_reversed_arcane_reversible_ok(data):
    cls = data.classes["magic_user"]
    e = _mu(["magic_user_light"])  # Light is reversible (→ Darkness)
    e2 = spells.assign_slot(e, cls, data, 1, "magic_user_light", reversed=True)
    assert e2.slots[0].reversed is True


def test_assign_slot_reversed_rejected_for_non_reversible(data):
    cls = data.classes["magic_user"]
    e = _mu(["magic_user_magic_missile"])
    with pytest.raises(SpellError):
        spells.assign_slot(e, cls, data, 1, "magic_user_magic_missile", reversed=True)


def test_assign_slot_reversed_rejected_for_divine(data):
    cls = data.classes["druid"]
    e = ClassEntry(class_id="druid", level=1, hp_rolls=[5])
    with pytest.raises(SpellError):
        spells.assign_slot(e, cls, data, 1, "faerie_fire", reversed=True)


def test_cast_slot_spends_only_one_duplicate(data):
    e = ClassEntry(class_id="magic_user", level=1, slots=[
        SpellSlot(level=1, spell_id="magic_user_sleep"),
        SpellSlot(level=1, spell_id="magic_user_sleep"),
    ])
    e2 = spells.cast_slot(e, 0)
    assert e2.slots[0].spent is True
    assert e2.slots[1].spent is False


def test_cast_slot_double_cast_raises(data):
    e = ClassEntry(class_id="magic_user", level=1,
                   slots=[SpellSlot(level=1, spell_id="magic_user_sleep")])
    e = spells.cast_slot(e, 0)
    with pytest.raises(SpellError):
        spells.cast_slot(e, 0)


def test_restore_slot_unspends(data):
    e = ClassEntry(class_id="magic_user", level=1,
                   slots=[SpellSlot(level=1, spell_id="magic_user_sleep", spent=True)])
    e2 = spells.restore_slot(e, 0)
    assert e2.slots[0].spent is False


def test_clear_slot_removes_one_row(data):
    e = ClassEntry(class_id="magic_user", level=1, slots=[
        SpellSlot(level=1, spell_id="magic_user_sleep"),
        SpellSlot(level=1, spell_id="magic_user_magic_missile"),
    ])
    e2 = spells.clear_slot(e, 0)
    assert [s.spell_id for s in e2.slots] == ["magic_user_magic_missile"]


def test_bad_index_raises(data):
    e = ClassEntry(class_id="magic_user", level=1, slots=[])
    for fn in (spells.cast_slot, spells.restore_slot, spells.clear_slot):
        with pytest.raises(SpellError):
            fn(e, 0)


def test_restore_all_and_clear_all(data):
    e = ClassEntry(class_id="magic_user", level=1, slots=[
        SpellSlot(level=1, spell_id="magic_user_sleep", spent=True),
        SpellSlot(level=1, spell_id="magic_user_magic_missile", spent=True),
    ])
    restored = spells.restore_all_slots(e)
    assert all(s.spent is False for s in restored.slots)
    cleared = spells.clear_all_slots(e)
    assert cleared.slots == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_slots.py -q`
Expected: FAIL — `spells` has no `assign_slot` / `cast_slot` / etc.

- [ ] **Step 3: Replace the prepare/unprepare mutators with slot ops**

In `aose/engine/spells.py`, update the model import to include `SpellSlot`:

```python
from aose.models import CharClass, ClassEntry, ClassLevelData, RuleSet, Spell, SpellSlot
```

Delete the `prepare` and `unprepare` functions (the last two in the file). Append the new slot section in their place:

```python
# ── Slot memorization / casting / rest (play state) ────────────────────────

def _check_index(entry: ClassEntry, index: int) -> None:
    if index < 0 or index >= len(entry.slots):
        raise SpellError(f"No slot at index {index}")


def _free_slots_at(entry: ClassEntry, cls: CharClass, level: int) -> int:
    cap = memorizable_slots(entry, cls).get(level, 0)
    used = sum(1 for s in entry.slots if s.level == level)
    return cap - used


def assign_slot(entry: ClassEntry, cls: CharClass, data: GameData, level: int,
                spell_id: str, reversed: bool = False) -> ClassEntry:
    """Memorize ``spell_id`` into a free slot at ``level``.

    Enforces: spell known (arcane spellbook / divine accessible list),
    ``spell.level == level``, a free slot exists at that level (cap from
    ``memorizable_slots``), and ``reversed`` only for a reversible spell on an
    arcane caster.  New slot starts unspent."""
    spell = _require_spell(data, spell_id)
    if spell.level != level:
        raise SpellError(f"{spell_id!r} is level {spell.level}, not {level}")
    known_ids = {s.id for s in known_spells(entry, cls, data)}
    if spell_id not in known_ids:
        raise SpellError(f"{spell_id!r} is not known and cannot be memorized")
    if _free_slots_at(entry, cls, level) <= 0:
        cap = memorizable_slots(entry, cls).get(level, 0)
        raise SpellError(f"No free level-{level} slot (cap {cap})")
    if reversed and not (caster_type_of(cls, data) == "arcane" and spell.reversible):
        raise SpellError(f"{spell_id!r} cannot be memorized reversed")
    new = SpellSlot(level=level, spell_id=spell_id, reversed=reversed, spent=False)
    return entry.model_copy(update={"slots": [*entry.slots, new]})


def _set_slot(entry: ClassEntry, index: int, **changes) -> ClassEntry:
    _check_index(entry, index)
    slots = [s.model_copy(update=changes) if i == index else s
             for i, s in enumerate(entry.slots)]
    return entry.model_copy(update={"slots": slots})


def cast_slot(entry: ClassEntry, index: int) -> ClassEntry:
    """Mark a memorized slot spent.  Raises if empty or already spent."""
    _check_index(entry, index)
    slot = entry.slots[index]
    if slot.spell_id is None:
        raise SpellError(f"Slot {index} is empty")
    if slot.spent:
        raise SpellError(f"Slot {index} is already spent")
    return _set_slot(entry, index, spent=True)


def restore_slot(entry: ClassEntry, index: int) -> ClassEntry:
    """Mark a single slot available again (undo / referee override)."""
    return _set_slot(entry, index, spent=False)


def clear_slot(entry: ClassEntry, index: int) -> ClassEntry:
    """Remove a slot row entirely (un-memorize)."""
    _check_index(entry, index)
    slots = [s for i, s in enumerate(entry.slots) if i != index]
    return entry.model_copy(update={"slots": slots})


def restore_all_slots(entry: ClassEntry) -> ClassEntry:
    """Re-memorize the same loadout: every slot becomes available."""
    slots = [s.model_copy(update={"spent": False}) for s in entry.slots]
    return entry.model_copy(update={"slots": slots})


def clear_all_slots(entry: ClassEntry) -> ClassEntry:
    """Drop the whole loadout, ready for a fresh pick."""
    return entry.model_copy(update={"slots": []})
```

- [ ] **Step 4: Remove the obsolete prepare/unprepare unit tests**

In `tests/test_spells.py`, delete `test_prepare_respects_known_and_slot_cap`, `test_prepare_divine_from_full_list`, and `test_unprepare_removes_one_instance` (the slot engine tests in `tests/test_spell_slots.py` replace them). Also update the `_spec` helper signature in `tests/test_spells.py`: replace the `prepared=None` parameter and its use with `slots=None` / `slots=slots or []` (the sheet-view test in Task 4 supplies slots).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_slots.py -q`
Expected: PASS (13 tests).

- [ ] **Step 6: Commit**

```bash
git add aose/engine/spells.py tests/test_spell_slots.py tests/test_spells.py
git commit -m "feat(state): slot memorize/cast/restore/clear/rest engine"
```

---

## Task 4: Sheet view — current_hp/is_dead + slot groups

**Files:**
- Modify: `aose/sheet/view.py`
- Test: `tests/test_spells.py` (update the spells-view test)

- [ ] **Step 1: Update the failing sheet-view test**

In `tests/test_spells.py`, replace the existing spells-view test (the one asserting on `block.prepared_groups`) with:

```python
def test_spells_view_groups_slots_by_level():
    from aose.models import SpellSlot
    data = GameData.load(DATA_DIR)
    spec = _spec(
        "magic_user",
        spellbook=["magic_user_magic_missile"],
        slots=[SpellSlot(level=1, spell_id="magic_user_magic_missile", spent=True)],
    )
    from aose.sheet.view import spells_view
    blocks = spells_view(spec, data)
    block = blocks[0]
    assert block.caster_type == "arcane"
    grp = block.slot_groups[0]
    assert grp.level == 1
    assert grp.cap == 1
    assert grp.free == 0
    assert len(grp.slots) == 1
    sv = grp.slots[0]
    assert sv.spell_id == "magic_user_magic_missile"
    assert sv.spent is True
    assert sv.index == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -k spells_view -q`
Expected: FAIL — `SpellClassView` has no `slot_groups` / `SlotView` undefined.

- [ ] **Step 3: Add `SlotView`, rework `SpellLevelGroup` and `spells_view`**

In `aose/sheet/view.py`:

Replace the `SpellLevelGroup` class with:

```python
class SlotView(BaseModel):
    index: int          # index into ClassEntry.slots (for cast/clear/restore)
    spell_id: str
    name: str
    display_name: str   # reverse name when reversed
    level: int
    reversible: bool
    reversed: bool
    spent: bool


class SpellLevelGroup(BaseModel):
    level: int
    cap: int                  # memorizable slots at this level
    free: int                 # cap − filled
    slots: list[SlotView]     # filled slots at this level
```

In `SpellClassView`, replace `prepared_groups: list[SpellLevelGroup]` with:

```python
    slot_groups: list[SpellLevelGroup]
```

Replace the body of `spells_view` (keep the signature and the per-entry loop scaffolding) so each block builds slot groups:

```python
def spells_view(spec: CharacterSpec, data: GameData) -> list[SpellClassView]:
    """One block per casting class entry; shared by the live sheet and the
    wizard review.  Arcane blocks expose learnable spells; divine know their
    whole accessible list.  Memorized spells are grouped into per-level slot
    rows (filled slots + free count)."""
    out: list[SpellClassView] = []
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        ctype = spell_engine.caster_type_of(cls, data)
        if ctype is None:
            continue
        known = spell_engine.known_spells(entry, cls, data)
        caps = spell_engine.memorizable_slots(entry, cls)
        groups: list[SpellLevelGroup] = []
        for level in sorted(caps):
            filled = [
                SlotView(
                    index=i,
                    spell_id=slot.spell_id,
                    name=data.spells[slot.spell_id].name,
                    display_name=_slot_display_name(data.spells[slot.spell_id], slot.reversed),
                    level=slot.level,
                    reversible=data.spells[slot.spell_id].reversible,
                    reversed=slot.reversed,
                    spent=slot.spent,
                )
                for i, slot in enumerate(entry.slots)
                if slot.spell_id is not None
                and slot.level == level
                and slot.spell_id in data.spells
            ]
            groups.append(SpellLevelGroup(
                level=level, cap=caps[level],
                free=caps[level] - len(filled), slots=filled,
            ))
        out.append(SpellClassView(
            class_id=entry.class_id,
            class_name=cls.name,
            caster_type=ctype,
            can_learn=(ctype == "arcane"),
            known=[_spell_entry(s) for s in known],
            slot_groups=groups,
            learnable=[_spell_entry(s) for s in spell_engine.learnable_spells(entry, cls, data)],
        ))
    return out
```

Add this helper just above `spells_view`:

```python
def _slot_display_name(spell, reversed: bool) -> str:
    if reversed:
        return spell.reverse_name or f"{spell.name} (reversed)"
    return spell.name
```

- [ ] **Step 4: Add `current_hp`/`is_dead` to `CharacterSheet` and populate them**

In `CharacterSheet`, add next to `max_hp: int`:

```python
    current_hp: int
    is_dead: bool
```

In `build_sheet(...)`, add to the `CharacterSheet(...)` constructor call (next to `max_hp=hp.max_hp(spec, data),`):

```python
        current_hp=hp.current_hp(spec, data),
        is_dead=hp.is_dead(spec, data),
```

- [ ] **Step 5: Run the view tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -k "spells_view" -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/sheet/view.py tests/test_spells.py
git commit -m "feat(state): sheet view exposes current HP and spell slot groups"
```

---

## Task 5: HP routes

**Files:**
- Modify: `aose/web/routes.py`
- Test: `tests/test_rest_routes.py` (create — HP section)

- [ ] **Step 1: Write the failing HP route tests**

Create `tests/test_rest_routes.py`:

```python
"""HTTP route tests for HP, spell-slot, and rest play-state actions."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character
from aose.models import CharacterSpec, ClassEntry, RuleSet, SpellSlot
from aose.web.app import create_app

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    app = create_app(
        data_dir=DATA_DIR, characters_dir=characters_dir, drafts_dir=drafts_dir,
        examples_dir=examples_dir, settings_path=tmp_path / "settings.json",
    )
    c = TestClient(app, follow_redirects=False)
    c._characters_dir = characters_dir
    return c


def _save_fighter(client, damage_taken=0):
    spec = CharacterSpec(
        name="Bran",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[12])],
        alignment="neutral", damage_taken=damage_taken,
    )
    save_character("bran", spec, client._characters_dir)
    return spec


def _save_mu(client, spellbook=None, slots=None):
    spec = CharacterSpec(
        name="Mu",
        abilities={"STR": 10, "INT": 13, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="magic_user", level=1, hp_rolls=[12],
                            spellbook=spellbook or [], slots=slots or [])],
        alignment="neutral",
    )
    save_character("mu", spec, client._characters_dir)
    return spec


def test_hp_damage_route(client):
    _save_fighter(client)
    r = client.post("/character/bran/hp/damage", data={"amount": 5})
    assert r.status_code == 303
    assert load_character("bran", client._characters_dir).damage_taken == 5


def test_hp_heal_route(client):
    _save_fighter(client, damage_taken=5)
    client.post("/character/bran/hp/heal", data={"amount": 3})
    assert load_character("bran", client._characters_dir).damage_taken == 2


def test_hp_set_route_clamps(client):
    _save_fighter(client, damage_taken=4)
    client.post("/character/bran/hp/set", data={"value": 99})
    assert load_character("bran", client._characters_dir).damage_taken == 0


def test_hp_damage_negative_400(client):
    _save_fighter(client)
    r = client.post("/character/bran/hp/damage", data={"amount": -2})
    assert r.status_code == 400
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rest_routes.py -k hp -q`
Expected: FAIL — routes 404 (not defined).

- [ ] **Step 3: Add the HP routes**

In `aose/web/routes.py`, confirm `hp` is importable. Add near the top with the other engine imports:

```python
from aose.engine import hp
```

(If an `aose.engine` import block already exists, add `hp` to it instead.)

Add these routes after `grant_gold` (near line 209):

```python
@router.post("/character/{character_id}/hp/damage")
async def hp_damage(request: Request, character_id: str, amount: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.damage_taken = hp.apply_damage(spec, data, amount)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/hp/heal")
async def hp_heal(request: Request, character_id: str, amount: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.damage_taken = hp.apply_healing(spec, data, amount)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/hp/set")
async def hp_set(request: Request, character_id: str, value: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    spec.damage_taken = hp.set_current_hp(spec, data, value)
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rest_routes.py -k hp -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_rest_routes.py
git commit -m "feat(state): HP damage/heal/set routes"
```

---

## Task 6: Spell-slot routes (replace prepare/unprepare)

**Files:**
- Modify: `aose/web/routes.py`
- Test: `tests/test_rest_routes.py` (slot section); `tests/test_spell_routes.py` (update)

- [ ] **Step 1: Write the failing slot route tests**

Append to `tests/test_rest_routes.py`:

```python
def test_assign_then_cast_and_restore(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"])
    r = client.post("/character/mu/spells/assign",
                    data={"class_id": "magic_user", "level": 1,
                          "spell_id": "magic_user_magic_missile", "reversed": "false"})
    assert r.status_code == 303
    spec = load_character("mu", client._characters_dir)
    assert len(spec.classes[0].slots) == 1 and spec.classes[0].slots[0].spent is False

    client.post("/character/mu/spells/cast",
                data={"class_id": "magic_user", "slot_index": 0})
    assert load_character("mu", client._characters_dir).classes[0].slots[0].spent is True

    client.post("/character/mu/spells/restore",
                data={"class_id": "magic_user", "slot_index": 0})
    assert load_character("mu", client._characters_dir).classes[0].slots[0].spent is False


def test_assign_over_cap_400(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"],
             slots=[SpellSlot(level=1, spell_id="magic_user_magic_missile")])
    r = client.post("/character/mu/spells/assign",
                    data={"class_id": "magic_user", "level": 1,
                          "spell_id": "magic_user_magic_missile", "reversed": "false"})
    assert r.status_code == 400


def test_clear_slot_route(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"],
             slots=[SpellSlot(level=1, spell_id="magic_user_magic_missile")])
    client.post("/character/mu/spells/clear",
                data={"class_id": "magic_user", "slot_index": 0})
    assert load_character("mu", client._characters_dir).classes[0].slots == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rest_routes.py -k "assign or clear_slot" -q`
Expected: FAIL — routes not defined.

- [ ] **Step 3: Replace prepare/unprepare routes with slot routes**

In `aose/web/routes.py`, delete the `sheet_spell_prepare` and `sheet_spell_unprepare` route functions (the `/spells/prepare` and `/spells/unprepare` handlers). Add these in their place:

```python
@router.post("/character/{character_id}/spells/assign")
async def sheet_spell_assign(request: Request, character_id: str,
                             class_id: str = Form(...), level: int = Form(...),
                             spell_id: str = Form(...), reversed: str = Form("false")):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    idx = _find_class_entry(spec, class_id)
    rev = reversed.lower() in ("true", "1", "on", "yes")
    try:
        spec.classes[idx] = spell_engine.assign_slot(
            spec.classes[idx], data.classes[class_id], data, level, spell_id, rev,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/spells/cast")
async def sheet_spell_cast(request: Request, character_id: str,
                           class_id: str = Form(...), slot_index: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = spell_engine.cast_slot(spec.classes[idx], slot_index)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/spells/restore")
async def sheet_spell_restore(request: Request, character_id: str,
                              class_id: str = Form(...), slot_index: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = spell_engine.restore_slot(spec.classes[idx], slot_index)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/spells/clear")
async def sheet_spell_clear(request: Request, character_id: str,
                            class_id: str = Form(...), slot_index: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = spell_engine.clear_slot(spec.classes[idx], slot_index)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Update the obsolete prepare/unprepare route tests**

In `tests/test_spell_routes.py`: (a) in `_save_mu`, replace the `prepared=None` parameter and `prepared=prepared or []` with `slots=None` / `slots=slots or []`; (b) delete `test_sheet_prepare_and_unprepare` and `test_sheet_prepare_over_cap_400` (replaced by the assign/cast tests in `tests/test_rest_routes.py`); (c) in `test_sheet_renders_spells_section`, replace the `prepared=[...]` argument with `slots=[SpellSlot(level=1, spell_id="magic_user_magic_missile")]` and add `from aose.models import SpellSlot` to the imports.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rest_routes.py tests/test_spell_routes.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/web/routes.py tests/test_rest_routes.py tests/test_spell_routes.py
git commit -m "feat(state): slot assign/cast/restore/clear routes"
```

---

## Task 7: Rest routes (night + full-day)

**Files:**
- Modify: `aose/web/routes.py`
- Test: `tests/test_rest_routes.py` (rest section)

- [ ] **Step 1: Write the failing rest route tests**

Append to `tests/test_rest_routes.py`:

```python
def test_rest_night_restore_unspends_all(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"],
             slots=[SpellSlot(level=1, spell_id="magic_user_magic_missile", spent=True)])
    r = client.post("/character/mu/rest/night", data={"mode": "restore"})
    assert r.status_code == 303
    assert load_character("mu", client._characters_dir).classes[0].slots[0].spent is False


def test_rest_night_clear_empties_slots(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"],
             slots=[SpellSlot(level=1, spell_id="magic_user_magic_missile", spent=True)])
    client.post("/character/mu/rest/night", data={"mode": "clear"})
    assert load_character("mu", client._characters_dir).classes[0].slots == []


def test_rest_full_day_heals_and_restores(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"],
             slots=[SpellSlot(level=1, spell_id="magic_user_magic_missile", spent=True)])
    spec = load_character("mu", client._characters_dir)
    spec.damage_taken = 5
    save_character("mu", spec, client._characters_dir)
    r = client.post("/character/mu/rest/full-day",
                    data={"mode": "restore", "heal_amount": 3})
    assert r.status_code == 303
    after = load_character("mu", client._characters_dir)
    assert after.damage_taken == 2
    assert after.classes[0].slots[0].spent is False


def test_rest_blocked_when_dead(client):
    _save_fighter(client, damage_taken=12)  # 0/12 → dead
    r = client.post("/character/bran/rest/night", data={"mode": "restore"})
    assert r.status_code == 400
    r = client.post("/character/bran/rest/full-day",
                    data={"mode": "restore", "heal_amount": 2})
    assert r.status_code == 400
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rest_routes.py -k rest -q`
Expected: FAIL — rest routes not defined.

- [ ] **Step 3: Add the rest routes**

In `aose/web/routes.py`, add this helper near `_find_class_entry` and the two rest routes after the slot routes:

```python
def _apply_rest_mode(entry, mode: str):
    """Apply a rest spell-option to one class entry.

    restore → un-spend the existing loadout; clear → drop it; keep → unchanged.
    Non-casters have no slots, so every mode is a no-op for them."""
    if mode == "restore":
        return spell_engine.restore_all_slots(entry)
    if mode == "clear":
        return spell_engine.clear_all_slots(entry)
    if mode == "keep":
        return entry
    raise HTTPException(400, f"Unknown rest mode {mode!r}")


@router.post("/character/{character_id}/rest/night")
async def rest_night(request: Request, character_id: str, mode: str = Form("restore")):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    if hp.is_dead(spec, data):
        raise HTTPException(400, "A dead character cannot rest")
    spec.classes = [_apply_rest_mode(e, mode) for e in spec.classes]
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/rest/full-day")
async def rest_full_day(request: Request, character_id: str,
                        mode: str = Form("restore"), heal_amount: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    if hp.is_dead(spec, data):
        raise HTTPException(400, "A dead character cannot rest")
    spec.classes = [_apply_rest_mode(e, mode) for e in spec.classes]
    try:
        spec.damage_taken = hp.apply_healing(spec, data, heal_amount)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rest_routes.py -k rest -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_rest_routes.py
git commit -m "feat(state): night and full-day rest routes"
```

---

## Task 8: Templates — HP block, slot UI, rest controls

**Files:**
- Modify: `aose/web/routes.py` (add `rest_heal_roll` to sheet GET context)
- Modify: `aose/web/templates/sheet.html`
- Test: `tests/test_rest_routes.py` (render assertions)

- [ ] **Step 1: Write the failing render tests**

Append to `tests/test_rest_routes.py`:

```python
def test_sheet_renders_hp_and_status(client):
    _save_fighter(client, damage_taken=5)
    r = client.get("/character/bran")
    assert r.status_code == 200
    assert "7 / 12" in r.text       # current / max
    assert "Alive" in r.text


def test_sheet_renders_dead_status(client):
    _save_fighter(client, damage_taken=12)
    r = client.get("/character/bran")
    assert "Dead" in r.text


def test_sheet_renders_slot_cast_button(client):
    _save_mu(client, spellbook=["magic_user_magic_missile"],
             slots=[SpellSlot(level=1, spell_id="magic_user_magic_missile")])
    r = client.get("/character/mu")
    assert "Magic Missile" in r.text
    assert "/character/mu/spells/cast" in r.text
    assert "/character/mu/rest/night" in r.text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rest_routes.py -k "renders" -q`
Expected: FAIL — current/max + status + slot cast markup not present yet.

- [ ] **Step 3: Pass a suggested 1d3 heal roll into the sheet context**

In `aose/web/routes.py`, in the `character_sheet` GET handler (around line 93), add a 1d3 roll to the template context. Add the import near the other engine imports:

```python
from aose.engine import dice
```

Then in the `TemplateResponse(... "sheet.html", {` context dict (around line 97), add:

```python
            "rest_heal_roll": dice.roll("1d3"),
```

- [ ] **Step 4: Replace the Max HP row with a current/max HP block**

In `aose/web/templates/sheet.html`, replace the single Max HP stat row (line 45) with:

```html
                <div class="stat-row">
                    <span>Hit Points</span>
                    <span class="stat-big">{{ sheet.current_hp }} / {{ sheet.max_hp }}</span>
                </div>
                <div class="stat-row">
                    <span>Status</span>
                    <span class="{{ 'status-dead' if sheet.is_dead else 'status-alive' }}">
                        {{ "Dead" if sheet.is_dead else "Alive" }}
                    </span>
                </div>
                <div class="no-print hp-actions">
                    <form method="post" class="inline" action="/character/{{ character_id }}/hp/damage">
                        <input type="number" name="amount" min="0" value="1" style="width:4em">
                        <button type="submit" class="link-button">damage</button>
                    </form>
                    <form method="post" class="inline" action="/character/{{ character_id }}/hp/heal">
                        <input type="number" name="amount" min="0" value="1" style="width:4em">
                        <button type="submit" class="link-button">heal</button>
                    </form>
                    <form method="post" class="inline" action="/character/{{ character_id }}/hp/set">
                        <input type="number" name="value" min="0" max="{{ sheet.max_hp }}"
                               value="{{ sheet.current_hp }}" style="width:4em">
                        <button type="submit" class="link-button">set</button>
                    </form>
                </div>
```

- [ ] **Step 5: Replace the Prepared spells block with the slot UI**

In `aose/web/templates/sheet.html`, replace the `<h4>Prepared</h4>` block and its `{% for grp in block.prepared_groups %}` loop (lines 335–354) with:

```html
                    <h4>Memorized Slots</h4>
                    {% for grp in block.slot_groups %}
                    <div class="spell-level">
                        <strong>Level {{ grp.level }}</strong>
                        <span class="small muted">{{ grp.slots | length }} / {{ grp.cap }}
                            ({{ grp.free }} free)</span>
                        <ul>
                            {% for sv in grp.slots %}
                            <li>
                                {{ sv.display_name }}
                                {% if sv.spent %}
                                <span class="small muted">— Spent</span>
                                <form method="post" class="no-print inline"
                                      action="/character/{{ character_id }}/spells/restore">
                                    <input type="hidden" name="class_id" value="{{ block.class_id }}">
                                    <input type="hidden" name="slot_index" value="{{ sv.index }}">
                                    <button type="submit" class="link-button">restore</button>
                                </form>
                                {% elif block.caster_type == "divine" and sv.reversible %}
                                <form method="post" class="no-print inline"
                                      action="/character/{{ character_id }}/spells/cast">
                                    <input type="hidden" name="class_id" value="{{ block.class_id }}">
                                    <input type="hidden" name="slot_index" value="{{ sv.index }}">
                                    <button type="submit" class="link-button">cast normal</button>
                                </form>
                                <form method="post" class="no-print inline"
                                      action="/character/{{ character_id }}/spells/cast">
                                    <input type="hidden" name="class_id" value="{{ block.class_id }}">
                                    <input type="hidden" name="slot_index" value="{{ sv.index }}">
                                    <button type="submit" class="link-button">cast reversed</button>
                                </form>
                                {% else %}
                                <form method="post" class="no-print inline"
                                      action="/character/{{ character_id }}/spells/cast">
                                    <input type="hidden" name="class_id" value="{{ block.class_id }}">
                                    <input type="hidden" name="slot_index" value="{{ sv.index }}">
                                    <button type="submit" class="link-button">cast</button>
                                </form>
                                {% endif %}
                                <form method="post" class="no-print inline"
                                      action="/character/{{ character_id }}/spells/clear">
                                    <input type="hidden" name="class_id" value="{{ block.class_id }}">
                                    <input type="hidden" name="slot_index" value="{{ sv.index }}">
                                    <button type="submit" class="link-button">clear</button>
                                </form>
                            </li>
                            {% endfor %}
                        </ul>
                    </div>
                    {% endfor %}
```

- [ ] **Step 6: Replace the Known-list "prepare" button with "memorize" assign buttons**

In `aose/web/templates/sheet.html`, in the `<h4>Known</h4>` list, replace the `spells/prepare` form (lines 361–366) with memorize-into-slot buttons:

```html
                            <form method="post" class="no-print inline"
                                  action="/character/{{ character_id }}/spells/assign">
                                <input type="hidden" name="class_id" value="{{ block.class_id }}">
                                <input type="hidden" name="level" value="{{ s.level }}">
                                <input type="hidden" name="spell_id" value="{{ s.id }}">
                                <input type="hidden" name="reversed" value="false">
                                <button type="submit" class="link-button">memorize</button>
                            </form>
                            {% if block.caster_type == "arcane" and s.reversible %}
                            <form method="post" class="no-print inline"
                                  action="/character/{{ character_id }}/spells/assign">
                                <input type="hidden" name="class_id" value="{{ block.class_id }}">
                                <input type="hidden" name="level" value="{{ s.level }}">
                                <input type="hidden" name="spell_id" value="{{ s.id }}">
                                <input type="hidden" name="reversed" value="true">
                                <button type="submit" class="link-button">memorize (reversed)</button>
                            </form>
                            {% endif %}
```

- [ ] **Step 7: Add the Rest controls block**

In `aose/web/templates/sheet.html`, immediately after the spells `<section>` closing tag (after line 400, the `{% endif %}` that closes `{% if sheet.spells %}`), add. The Rest section is **not** gated by `sheet.spells` — full-day healing applies to non-casters too; the loadout selector only appears for casters (a no-op otherwise):

```html
            <section class="section no-print">
                <h2>Rest</h2>
                {% if sheet.is_dead %}
                <p class="small muted">A dead character cannot rest.</p>
                {% else %}
                {% if sheet.spells %}
                <form method="post" action="/character/{{ character_id }}/rest/night">
                    <label>Loadout:
                        <select name="mode">
                            <option value="restore">Restore previous</option>
                            <option value="clear">Clear all</option>
                            <option value="keep">Keep as-is</option>
                        </select>
                    </label>
                    <button type="submit" class="primary">Rest and Memorize Spells</button>
                </form>
                {% endif %}
                <form method="post" action="/character/{{ character_id }}/rest/full-day">
                    {% if sheet.spells %}
                    <label>Loadout:
                        <select name="mode">
                            <option value="restore">Restore previous</option>
                            <option value="clear">Clear all</option>
                            <option value="keep">Keep as-is</option>
                        </select>
                    </label>
                    {% else %}
                    <input type="hidden" name="mode" value="keep">
                    {% endif %}
                    <label>Healing (1d3):
                        <input type="number" name="heal_amount" min="0" max="3"
                               value="{{ rest_heal_roll }}" style="width:4em">
                    </label>
                    <button type="submit" class="primary">Full Day Rest</button>
                </form>
                {% endif %}
            </section>
```

Note: "Choose new loadout" = select **Clear all**, rest, then use the per-spell **memorize** buttons to pick a fresh loadout. A non-caster's Full Day Rest sends `mode=keep` (no slots → harmless) and just heals.

- [ ] **Step 8: Add minimal status styling**

In `aose/web/templates/sheet.html`, find the `<style>` block and add two rules (place near existing `.muted`):

```css
        .status-dead { color: #b00; font-weight: bold; }
        .status-alive { color: #2a7; font-weight: bold; }
```

If the sheet uses a shared stylesheet rather than an inline `<style>` block, add the two rules to that stylesheet file instead.

- [ ] **Step 9: Run the render tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rest_routes.py -k "renders" -q`
Expected: PASS (3 tests).

- [ ] **Step 10: Commit**

```bash
git add aose/web/routes.py aose/web/templates/sheet.html tests/test_rest_routes.py
git commit -m "feat(state): sheet HP block, slot UI, and rest controls"
```

---

## Task 9: Full-suite verification + docs

**Files:**
- Modify: `CLAUDE.md` (Current state note)

- [ ] **Step 1: Run the full test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (the trailing `pytest-current` PermissionError on Windows is a known tempdir quirk — ignore it). Investigate and fix any real failures, especially any remaining references to `prepared` in tests not covered above.

- [ ] **Step 2: Manual smoke check**

Start the app: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
Open a saved magic-user character. Verify: HP block shows current/max + Alive; damage/heal/set work; memorize a known spell → it appears as a slot; cast → "Spent" + restore; Full Day Rest with a 1d3 value heals and un-spends. Confirm a non-caster (fighter) shows the HP block and a Full Day Rest that heals but no loadout selector / night-rest button.

- [ ] **Step 3: Update CLAUDE.md**

In `CLAUDE.md`, under "Current state", add a bullet summarizing the feature:

```markdown
- **On-sheet play state** — current HP via `CharacterSpec.damage_taken`
  (current = `max(0, max_hp − damage_taken)`, dead derived from current 0;
  `aose/engine/hp.py` gains `current_hp`/`is_dead`/`apply_damage`/`apply_healing`/
  `set_current_hp`). Prepared spells are now `ClassEntry.slots: list[SpellSlot]`
  (spell + reversed + spent), replacing the flat `prepared`; slot ops live in
  `aose/engine/spells.py` (`assign_slot`/`cast_slot`/`restore_slot`/`clear_slot`/
  `restore_all_slots`/`clear_all_slots`). Sheet routes: `/hp/{damage,heal,set}`,
  `/spells/{assign,cast,restore,clear}`, `/rest/{night,full-day}` (full-day adds
  1d3 healing; rest blocked when dead). Arcane reversed is fixed at memorize
  time; divine reversed is a cast-time button only (not stored). Spec/plan:
  `docs/superpowers/{specs,plans}/2026-06-02-on-sheet-character-state*`.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: note on-sheet character state feature in CLAUDE.md"
```

---

## Self-review notes (for the implementer)

- **Spec coverage:** HP track/damage/heal/set + dead (Tasks 2, 5, 8); slot model with reversed/spent (Tasks 1, 3); arcane-from-spellbook + divine-from-list (Task 3 via `known_spells`); duplicate memorization (Task 3 cast-one-duplicate test); reversed arcane stored / divine at cast (Tasks 3, 8); cast spends slot + undo/restore (Tasks 3, 6); rest night re-memorize + full-day 1d3 (Task 7); multiclass per-source — slots live on each `ClassEntry`, rest iterates all classes (Tasks 1, 7). All covered.
- **Type consistency:** `slots` (field) vs `slot_groups` (view) vs `SlotView` are intentionally distinct names; `slot_index` (route form) maps to `SlotView.index`. `reversed` is a form string coerced to bool in the assign route.
- **No-JS reversed UX:** memorize uses explicit per-spell buttons (normal / reversed) rather than a dropdown+checkbox, so the assign route only ever receives a valid reversed flag and `assign_slot` can enforce strictly.
