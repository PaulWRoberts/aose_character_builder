# Energy Drain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a permanent, GM-applied "energy drain" action on the live character sheet that removes one or more experience levels LIFO, stripping the matching Hit Dice, XP, and now-inaccessible spells — and kills the character if the loss would drop them below level 1.

**Architecture:** A new cycle-free engine module `aose/engine/energy_drain.py` exposes one mutator `energy_drain(spec, data, levels, xp_mode)`. It reuses `leveling._prime_req_multiplier` (to find the most-recently-leveled class deterministically), `hp.max_hp` (to zero out HP on death), and the spells engine (`accessible_levels`/`memorizable_slots`/`caster_type_of`) to trim spells. A new POST route in `aose/web/routes.py` wires it to the sheet, and a danger control in `aose/web/templates/sheet.html` drives it.

**Tech Stack:** Python 3, Pydantic v2 models, FastAPI, Jinja2, pytest. Run everything through the venv: `.venv\Scripts\python.exe -m pytest tests/ -q`.

---

## Background the engineer needs

**Per-class state.** A character (`CharacterSpec`) has `classes: list[ClassEntry]`. Each `ClassEntry` has `class_id`, `level` (default 1), `xp`, `hp_rolls: list[int]` (index 0 = the creation roll, one entry per level), `spellbook: list[str]` (arcane known spells), and `slots: list[SpellSlot]` (prepared loadout; each `SpellSlot` has `level`, `spell_id`, `reversed`, `spent`). Pydantic v2 models are **mutable** — `entry.level -= 1`, `entry.hp_rolls.pop()`, `entry.slots = [...]` all work in place.

**XP tables.** `data.classes[class_id].progression` is `dict[int, ClassLevelData]`; `progression[level].xp_required` is the XP threshold for that level. Level 1's `xp_required` is 0 in every class. A level with no progression row does not exist for that class.

**Prime-req multiplier.** `aose.engine.leveling._prime_req_multiplier(cls, abilities)` returns the class's XP multiplier (e.g. 1.10) from its prime requisite score(s); `1.0` when the class has no prime requisites. It is already imported and used inside `leveling.py`.

**Most-recently-leveled class (LIFO key).** XP is split evenly across classes and each class banks at its own multiplier, so the shared "global" XP a class's current level represents is `xp_required(level) / prime_req_multiplier`. The class with the **highest** such value (among classes with `level > 1`) leveled most recently. Because `xp_required(1) == 0`, a level-1 class scores 0 and is never picked while another class is above level 1 — so classes bottom out together at level 1, and when every class is at level 1 a further drain is fatal.

**HP / death.** `aose.engine.hp.max_hp(spec, data)` returns floored max HP. Current HP is `max(0, max_hp - spec.damage_taken)`; a character is dead when current HP is 0. To kill: set `spec.damage_taken = max_hp(spec, data)`.

**Spells trim.** `aose.engine.spells.caster_type_of(cls, data)` returns `"arcane"`, `"divine"`, or `None` (non-caster). `accessible_levels(entry, cls)` is the set of castable spell levels at the entry's level. `memorizable_slots(entry, cls)` is `{spell_level: slot_count}` at the entry's level (also the per-level spellbook cap under standard rules). Whether the spellbook is capped depends on `spec.ruleset.advanced_spell_books` (advanced = uncapped book).

**Existing test patterns.** `tests/test_leveling.py` shows the fixtures to mirror: a module-scoped `data` fixture (`GameData.load(DATA_DIR)`), a `_spec(...)` helper, `_NEUTRAL_ABILITIES` (all prime reqs in the 9–12 band → 1.00× multiplier so thresholds read cleanly), and a `client`/`_seed` pair for route tests. `fighter` L2 threshold is 2000; `magic_user` L2 threshold is 2500. Reuse these in the new test file.

---

## File Structure

- **Create** `aose/engine/energy_drain.py` — the engine module (public `energy_drain`, helpers `_xp_required`, `_most_recently_leveled`, `_trim_to_accessible`, `_kill`).
- **Create** `tests/test_energy_drain.py` — engine + route tests.
- **Modify** `aose/web/routes.py` — add the `/character/{character_id}/energy-drain` POST route and import `energy_drain`.
- **Modify** `aose/web/templates/sheet.html` — add the Energy Drain danger control inside the Advancement section.

---

## Task 1: Engine — single-class drain, both XP modes

**Files:**
- Create: `aose/engine/energy_drain.py`
- Test: `tests/test_energy_drain.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_energy_drain.py`:

```python
"""Tests for the energy-drain engine and route."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character, save_settings
from aose.data.loader import GameData
from aose.engine.energy_drain import energy_drain
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# All prime reqs in the 9-12 band -> 1.00x multiplier, so XP thresholds read cleanly.
_NEUTRAL_ABILITIES = {"STR": 12, "INT": 12, "WIS": 12, "DEX": 12, "CON": 14, "CHA": 10}


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def _spec(level=1, xp=0, hp_rolls=None, multi=False, ruleset=None, abilities=None):
    if ruleset is None:
        ruleset = RuleSet(multiclassing=True) if multi else RuleSet()
    if multi:
        classes = [
            ClassEntry(class_id="fighter", level=level, xp=xp,
                       hp_rolls=hp_rolls or [8] * level),
            ClassEntry(class_id="magic_user", level=level, xp=xp,
                       hp_rolls=hp_rolls or [4] * level),
        ]
    else:
        classes = [ClassEntry(class_id="fighter", level=level, xp=xp,
                              hp_rolls=hp_rolls or [8] * level)]
    return CharacterSpec(
        name="Test",
        abilities=abilities or dict(_NEUTRAL_ABILITIES),
        race_id="dwarf" if not multi else "elf",
        classes=classes,
        alignment="law",
        ruleset=ruleset,
    )


def test_drain_one_level_drops_level_hp_and_xp_new_min(data):
    spec = _spec(level=3, xp=8000, hp_rolls=[8, 5, 6])
    energy_drain(spec, data, levels=1, xp_mode="new_min")
    e = spec.classes[0]
    assert e.level == 2
    assert e.hp_rolls == [8, 5]            # last Hit Die removed
    assert e.xp == 2000                    # fighter L2 threshold (new-level minimum)


def test_drain_one_level_midpoint_lands_in_new_band(data):
    spec = _spec(level=3, xp=8000, hp_rolls=[8, 5, 6])
    energy_drain(spec, data, levels=1, xp_mode="midpoint")
    e = spec.classes[0]
    assert e.level == 2
    # halfway between fighter L2 (2000) and L3 (4000) thresholds
    assert e.xp == 3000
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_energy_drain.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aose.engine.energy_drain'`.

- [ ] **Step 3: Write the engine module**

Create `aose/engine/energy_drain.py`:

```python
"""Energy drain — the permanent, GM-applied loss of experience levels.

A sheet-manager-only mutation (no wizard, no RuleSet flag). Removes levels
LIFO: the most recently gained level across all of a character's classes goes
first. Each lost level drops the class's last Hit Die roll and trims its
now-inaccessible spells; saves / THAC0 / attacks fall out of the reduced level
automatically.

Multi-class LIFO is deterministic with no stored timeline: XP is split evenly
across classes and each class has its own XP table, so the class that levelled
most recently is the one whose current-level XP threshold, converted back to the
shared "global" XP it represents (threshold / prime-req multiplier), is highest.
Level 1 needs 0 XP in every OSE table, so a level-1 class never wins that
comparison while another class is above 1 — classes bottom out together at
creation. When every class is at level 1 and a level must still be removed, the
drain is fatal.
"""
from __future__ import annotations

from typing import Literal

from aose.data.loader import GameData
from aose.engine.hp import max_hp
from aose.engine.leveling import _prime_req_multiplier
from aose.engine.spells import accessible_levels, caster_type_of, memorizable_slots
from aose.models import CharacterSpec, ClassEntry, RuleSet

XpMode = Literal["midpoint", "new_min"]


def _xp_required(cls, level: int) -> int:
    """XP threshold for ``level`` from the class table (0 if no such row)."""
    row = cls.progression.get(level)
    return row.xp_required if row is not None else 0


def _most_recently_leveled(spec: CharacterSpec, data: GameData) -> ClassEntry | None:
    """The class entry whose current level was attained latest in shared-XP
    terms (``xp_required(level) / prime_req_multiplier``), among classes above
    level 1. ``None`` when every class is at level 1."""
    candidates = [e for e in spec.classes if e.level > 1]
    if not candidates:
        return None

    def global_xp(entry: ClassEntry) -> float:
        cls = data.classes[entry.class_id]
        return _xp_required(cls, entry.level) / _prime_req_multiplier(cls, spec.abilities)

    return max(candidates, key=global_xp)


def _trim_to_accessible(entry: ClassEntry, data: GameData, ruleset: RuleSet) -> None:
    """Drop spells the class can no longer use at its reduced level: prepared
    slots above the accessible levels or beyond the per-level cap, and arcane
    spellbook entries above the accessible levels (and beyond the per-level cap
    under standard spell-book rules). Mutates ``entry`` in place. No-op for
    non-casters and divine known-spells (which are derived, not stored)."""
    cls = data.classes.get(entry.class_id)
    if cls is None or caster_type_of(cls, data) is None:
        return
    levels = accessible_levels(entry, cls)
    caps = memorizable_slots(entry, cls)

    kept = []
    used: dict[int, int] = {}
    for slot in entry.slots:
        if slot.level not in levels:
            continue
        if used.get(slot.level, 0) >= caps.get(slot.level, 0):
            continue
        used[slot.level] = used.get(slot.level, 0) + 1
        kept.append(slot)
    entry.slots = kept

    if caster_type_of(cls, data) == "arcane":
        book = []
        bused: dict[int, int] = {}
        for spell_id in entry.spellbook:
            spell = data.spells.get(spell_id)
            if spell is None or spell.level not in levels:
                continue
            if not ruleset.advanced_spell_books:
                if bused.get(spell.level, 0) >= caps.get(spell.level, 0):
                    continue
                bused[spell.level] = bused.get(spell.level, 0) + 1
            book.append(spell_id)
        entry.spellbook = book


def _kill(spec: CharacterSpec, data: GameData) -> None:
    """Fatal drain: reset every class to level 1 / one Hit Die / 0 XP, trim
    spells, then set current HP to 0."""
    for entry in spec.classes:
        entry.level = 1
        entry.hp_rolls = entry.hp_rolls[:1]
        entry.xp = 0
        _trim_to_accessible(entry, data, spec.ruleset)
    spec.damage_taken = max_hp(spec, data)


def energy_drain(spec: CharacterSpec, data: GameData, levels: int,
                 xp_mode: XpMode) -> None:
    """Remove ``levels`` experience levels LIFO, mutating ``spec`` in place.

    ``levels`` must be >= 1. ``xp_mode`` sets each drained class's XP afterward:
    ``midpoint`` = halfway between its former and new level thresholds (only
    valid for a single-level drain); ``new_min`` = the new level's threshold. If
    the drain exhausts the character (a level must be removed while every class
    is at level 1), the character dies."""
    if levels < 1:
        raise ValueError("levels must be at least 1")
    if xp_mode not in ("midpoint", "new_min"):
        raise ValueError(f"unknown xp_mode {xp_mode!r}")
    if xp_mode == "midpoint" and levels != 1:
        raise ValueError("midpoint XP is only valid for a single-level drain")

    former: dict[str, int] = {}  # class_id -> level before this drain
    for _ in range(levels):
        target = _most_recently_leveled(spec, data)
        if target is None:
            _kill(spec, data)
            return
        former.setdefault(target.class_id, target.level)
        target.level -= 1
        if target.hp_rolls:
            target.hp_rolls.pop()
        _trim_to_accessible(target, data, spec.ruleset)

    for class_id, former_level in former.items():
        entry = next(e for e in spec.classes if e.class_id == class_id)
        cls = data.classes[entry.class_id]
        new_req = _xp_required(cls, entry.level)
        if xp_mode == "midpoint":
            entry.xp = (new_req + _xp_required(cls, former_level)) // 2
        else:
            entry.xp = new_req
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_energy_drain.py -q`
Expected: PASS (2 passed). The trailing `pytest-current` PermissionError on Windows is a known quirk — ignore it.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/energy_drain.py tests/test_energy_drain.py
git commit -m "feat(engine): energy_drain single-class level/HP/XP loss"
```

---

## Task 2: Engine — input validation

**Files:**
- Test: `tests/test_energy_drain.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_energy_drain.py`:

```python
def test_drain_zero_levels_raises(data):
    spec = _spec(level=3, xp=8000)
    with pytest.raises(ValueError, match="at least 1"):
        energy_drain(spec, data, levels=0, xp_mode="new_min")


def test_drain_unknown_xp_mode_raises(data):
    spec = _spec(level=3, xp=8000)
    with pytest.raises(ValueError, match="unknown xp_mode"):
        energy_drain(spec, data, levels=1, xp_mode="bogus")


def test_drain_midpoint_multi_level_raises(data):
    spec = _spec(level=3, xp=8000)
    with pytest.raises(ValueError, match="single-level drain"):
        energy_drain(spec, data, levels=2, xp_mode="midpoint")
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_energy_drain.py -q`
Expected: PASS — the validation guards were written in Task 1, so these confirm them (5 passed total).

- [ ] **Step 3: Commit**

```bash
git add tests/test_energy_drain.py
git commit -m "test(engine): energy_drain input validation"
```

---

## Task 3: Engine — multi-level cascade and new_min XP per class

**Files:**
- Test: `tests/test_energy_drain.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_energy_drain.py`:

```python
def test_drain_multi_level_single_class_cascades(data):
    spec = _spec(level=4, xp=99000, hp_rolls=[8, 5, 6, 7])
    energy_drain(spec, data, levels=2, xp_mode="new_min")
    e = spec.classes[0]
    assert e.level == 2
    assert e.hp_rolls == [8, 5]            # two Hit Dice removed (LIFO)
    assert e.xp == 2000                    # fighter L2 threshold
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_energy_drain.py::test_drain_multi_level_single_class_cascades -q`
Expected: PASS — the Task 1 loop already handles multi-level drains for a single class. This locks the behavior in.

- [ ] **Step 3: Commit**

```bash
git add tests/test_energy_drain.py
git commit -m "test(engine): energy_drain multi-level single-class cascade"
```

---

## Task 4: Engine — multi-class LIFO targeting

**Files:**
- Test: `tests/test_energy_drain.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_energy_drain.py`. The fighter L3 threshold (4000) exceeds the magic-user L3 threshold (5000)? No — verify with the actual data via the global-XP key. With neutral abilities both multipliers are 1.0, so the most-recently-leveled class is the one with the higher `xp_required(level)`. magic_user L3 = 5000 > fighter L3 = 4000, so the magic-user is drained first:

```python
def test_drain_multi_class_targets_most_recently_leveled(data):
    # Both at L3, neutral abilities (1.0x). magic_user L3 threshold (5000) >
    # fighter L3 (4000), so the magic-user leveled most recently -> drained first.
    spec = _spec(level=3, xp=6000, multi=True,
                 hp_rolls=None)  # fighter [8,8,8], magic_user [4,4,4]
    energy_drain(spec, data, levels=1, xp_mode="new_min")
    levels = {e.class_id: e.level for e in spec.classes}
    assert levels == {"fighter": 3, "magic_user": 2}
    mu = next(e for e in spec.classes if e.class_id == "magic_user")
    assert mu.hp_rolls == [4, 4]           # one Hit Die removed from the MU
    assert mu.xp == 2500                   # magic_user L2 threshold
    fighter = next(e for e in spec.classes if e.class_id == "fighter")
    assert fighter.xp == 6000              # untouched class keeps its XP
```

> If this assertion is wrong because the seeded `magic_user` L3 threshold differs from 5000, read `data/classes/magic_user.yaml` and adjust the expected class/threshold — the *principle* under test (higher global-XP class drained first; untouched class keeps XP) is what matters.

- [ ] **Step 2: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_energy_drain.py::test_drain_multi_class_targets_most_recently_leveled -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_energy_drain.py
git commit -m "test(engine): energy_drain multi-class LIFO targeting"
```

---

## Task 5: Engine — death on over-drain (single and multi-class)

**Files:**
- Test: `tests/test_energy_drain.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_energy_drain.py`:

```python
def test_drain_below_level_one_kills_single_class(data):
    spec = _spec(level=2, xp=5000, hp_rolls=[8, 5])
    energy_drain(spec, data, levels=3, xp_mode="new_min")  # only 1 level to lose
    e = spec.classes[0]
    assert e.level == 1
    assert e.hp_rolls == [8]               # back to the creation roll only
    assert e.xp == 0
    from aose.engine.hp import current_hp, is_dead
    assert current_hp(spec, data) == 0
    assert is_dead(spec, data) is True


def test_drain_exhausting_all_classes_kills_multi(data):
    spec = _spec(level=2, xp=5000, multi=True)  # fighter+MU both L2
    energy_drain(spec, data, levels=5, xp_mode="new_min")
    assert [e.level for e in spec.classes] == [1, 1]
    assert all(e.xp == 0 for e in spec.classes)
    assert all(len(e.hp_rolls) == 1 for e in spec.classes)
    from aose.engine.hp import is_dead
    assert is_dead(spec, data) is True
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_energy_drain.py -q`
Expected: PASS (all tests so far green).

- [ ] **Step 3: Commit**

```bash
git add tests/test_energy_drain.py
git commit -m "test(engine): energy_drain death on over-drain"
```

---

## Task 6: Engine — spell auto-trim on level loss

**Files:**
- Test: `tests/test_energy_drain.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_energy_drain.py`. This builds a magic-user with a 2nd-level spell prepared and known, drains to a level that can no longer cast 2nd-level spells, and asserts both are trimmed. Discover real spell IDs from the data so the test stays valid:

```python
def _arcane_spell_at_level(data, level):
    """An arbitrary magic_user spell id at the given spell level, from seed data."""
    for s in sorted(data.spells.values(), key=lambda s: s.id):
        if s.level == level and "magic_user" in s.spell_lists:
            return s.id
    raise AssertionError(f"no magic_user level-{level} spell in seed data")


def test_drain_trims_inaccessible_spells(data):
    from aose.models import SpellSlot
    lvl1 = _arcane_spell_at_level(data, 1)
    lvl2 = _arcane_spell_at_level(data, 2)
    # Magic-user level 3 can cast 2nd-level spells; level 1 cannot.
    spec = _spec(level=3, xp=99000, hp_rolls=[4, 3, 2])
    spec.classes[0] = spec.classes[0].model_copy(update={
        "class_id": "magic_user",
        "spellbook": [lvl1, lvl2],
        "slots": [SpellSlot(level=1, spell_id=lvl1), SpellSlot(level=2, spell_id=lvl2)],
    })
    energy_drain(spec, data, levels=2, xp_mode="new_min")  # -> magic_user L1
    e = spec.classes[0]
    assert e.level == 1
    assert lvl2 not in e.spellbook         # 2nd-level spell no longer accessible
    assert lvl1 in e.spellbook
    assert all(slot.level == 1 for slot in e.slots)   # 2nd-level slot dropped
```

> The single-class `_spec` helper seeds `class_id="fighter"`; here we rewrite class entry 0 to `magic_user`. `race_id="dwarf"` is fine for the engine test (no race/class gating runs in `energy_drain`).

- [ ] **Step 2: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_energy_drain.py::test_drain_trims_inaccessible_spells -q`
Expected: PASS. If it fails because the standard-rules per-level book cap at L1 also trims `lvl1`, confirm the magic_user L1 `spell_slots` includes one level-1 slot (it does in seed data) so `lvl1` is retained.

- [ ] **Step 3: Commit**

```bash
git add tests/test_energy_drain.py
git commit -m "test(engine): energy_drain trims inaccessible spells"
```

---

## Task 7: Route — POST /character/{id}/energy-drain

**Files:**
- Modify: `aose/web/routes.py`
- Test: `tests/test_energy_drain.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_energy_drain.py`:

```python
@pytest.fixture
def client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, RuleSet())
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    c = TestClient(app, follow_redirects=False)
    c._characters_dir = characters_dir
    return c


def _seed(client, **overrides):
    spec = _spec(**overrides)
    save_character("test", spec, client._characters_dir)
    return spec


def test_energy_drain_route_reduces_level(client):
    _seed(client, level=3, xp=8000, hp_rolls=[8, 5, 6])
    r = client.post("/character/test/energy-drain",
                    data={"levels": "1", "xp_mode": "new_min"})
    assert r.status_code == 303
    assert r.headers["location"] == "/character/test"
    spec = load_character("test", client._characters_dir)
    assert spec.classes[0].level == 2
    assert spec.classes[0].xp == 2000


def test_energy_drain_route_midpoint_multi_level_400s(client):
    _seed(client, level=3, xp=8000)
    r = client.post("/character/test/energy-drain",
                    data={"levels": "2", "xp_mode": "midpoint"})
    assert r.status_code == 400


def test_energy_drain_route_missing_character_404s(client):
    r = client.post("/character/nobody/energy-drain",
                    data={"levels": "1", "xp_mode": "new_min"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_energy_drain.py -k route -q`
Expected: FAIL — the route does not exist yet (the drain/midpoint test gets 404/405 instead of 303/400).

- [ ] **Step 3: Add the route**

In `aose/web/routes.py`, extend the leveling import (around line 10) to include `energy_drain`:

```python
from aose.engine.energy_drain import energy_drain as _energy_drain
```

Add this route immediately after the `level_up_class` route (after line 257):

```python
@router.post("/character/{character_id}/energy-drain")
async def energy_drain_route(request: Request, character_id: str,
                             levels: int = Form(...),
                             xp_mode: str = Form("new_min")):
    """Permanently drain experience levels LIFO (GM action). Removes the
    matching Hit Dice and now-inaccessible spells, resets XP per ``xp_mode``,
    and kills the character if the loss would drop them below level 1.
    Returns 400 on invalid input (levels < 1, unknown xp_mode, or midpoint
    with more than one level)."""
    spec = _load_spec_or_404(request, character_id)
    try:
        _energy_drain(spec, request.app.state.game_data, levels, xp_mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_energy_drain.py -q`
Expected: PASS (all engine + route tests green).

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_energy_drain.py
git commit -m "feat(web): energy-drain route on the character sheet"
```

---

## Task 8: UI — Energy Drain control in the Advancement section

**Files:**
- Modify: `aose/web/templates/sheet.html`
- Modify: `aose/web/static/sheet.css`
- Test: `tests/test_energy_drain.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_energy_drain.py`:

```python
def test_sheet_renders_energy_drain_form(client):
    _seed(client, level=3, xp=8000, hp_rolls=[8, 5, 6])
    r = client.get("/character/test")
    assert 'action="/character/test/energy-drain"' in r.text
    assert 'name="levels"' in r.text
    assert 'name="xp_mode"' in r.text
    assert 'value="midpoint"' in r.text
    assert 'value="new_min"' in r.text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_energy_drain.py::test_sheet_renders_energy_drain_form -q`
Expected: FAIL — the form is not in the template yet.

- [ ] **Step 3: Add the control to the template**

In `aose/web/templates/sheet.html`, inside the Advancement `<section>`, immediately after the Grant-XP form (after line 249, before the closing `</section>` on line 250), insert. The inline `oninput` references the radios by `id` (no nested-quote selectors), toggling Midpoint off and forcing New-level-minimum whenever Levels > 1:

```html
                <form method="post" action="/character/{{ character_id }}/energy-drain"
                      class="energy-drain-form no-print"
                      onsubmit="return confirm('Energy drain ' + this.levels.value + ' level(s)? This is permanent.');">
                    <label class="energy-drain-label">Energy Drain
                        <input type="number" name="levels" value="1" min="1"
                               style="width:4em"
                               oninput="var multi = Number(this.value) > 1;
                                        var mid = document.getElementById('ed-midpoint');
                                        var min = document.getElementById('ed-new-min');
                                        mid.disabled = multi;
                                        if (multi) min.checked = true;">
                    </label>
                    <label class="small"><input type="radio" id="ed-midpoint" name="xp_mode" value="midpoint"> Midpoint</label>
                    <label class="small"><input type="radio" id="ed-new-min" name="xp_mode" value="new_min" checked> New level minimum</label>
                    <button type="submit" class="danger">Drain</button>
                </form>
```

- [ ] **Step 4: Add a `.danger` button style**

The `danger` button class does not exist yet. In `aose/web/static/sheet.css`, immediately after the `.button.primary:hover` rule (line 334), add:

```css
.button.danger, button.danger {
    background: #8a2c2c;
    color: white;
    border-color: #8a2c2c;
}

.button.danger:hover, button.danger:hover { background: #a13434; }
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_energy_drain.py::test_sheet_renders_energy_drain_form -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/web/templates/sheet.html aose/web/static/sheet.css tests/test_energy_drain.py
git commit -m "feat(web): Energy Drain control on the sheet Advancement section"
```

---

## Task 9: Full suite green

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS — all pre-existing tests plus the new energy-drain tests. (Ignore the trailing `pytest-current` PermissionError; it's the documented Windows quirk.)

- [ ] **Step 2: Manual smoke test (optional but recommended)**

Run the app and exercise the control on a real character:

```powershell
.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload
```

Open a character sheet, set Levels to 2, confirm the Midpoint radio is disabled and New-level-minimum is forced, drain, and confirm level / HP / XP drop. Then drain more levels than the character has and confirm the dead state renders.

- [ ] **Step 3: Commit any cleanup (if needed)**

```bash
git add -A
git commit -m "chore: energy drain feature complete"
```

---

## Self-Review notes (for the implementer)

- **Spec coverage:** Task 1 = single-class level/HP/XP + both modes; Task 2 = validation incl. midpoint-only-single-level; Tasks 3–4 = multi-level cascade + multi-class LIFO; Task 5 = death; Task 6 = spell trim; Task 7 = route; Task 8 = UI (incl. the JS that disables Midpoint when Levels > 1); Task 9 = full suite. Every spec section maps to a task.
- **Type/name consistency:** the public function is `energy_drain` everywhere; the route imports it aliased as `_energy_drain` (matching the file's `_grant_xp`/`_level_up` aliasing convention) and the route handler is named `energy_drain_route` to avoid shadowing. `xp_mode` values are exactly `"midpoint"` / `"new_min"` in engine, route, tests, and template.
- **Data assumptions to verify while implementing:** fighter L2=2000/L3=4000, magic_user L2=2500/L3=5000. If the seeded YAML differs, adjust the expected numbers (the Task 4 note calls this out explicitly) — the behaviors under test do not change.
