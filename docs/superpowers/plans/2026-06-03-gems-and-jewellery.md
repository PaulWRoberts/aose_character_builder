# Gems & Jewellery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a character own gems and jewellery as free-acquired, weightless, per-instance treasure on the live sheet, with values per the Advanced Fantasy rules and a damaged-jewellery toggle.

**Architecture:** Two focused per-instance Pydantic models (`GemStack`, `JewelleryPiece`) on `CharacterSpec`, a cycle-free `aose/engine/valuables.py` owning all create/sell/drop/toggle mutations and value math, a `valuables_view` assembled into the sheet, and eight sheet-only POST routes. Mirrors the existing `spell_sources` / `ammo` / `containers` instance-list patterns. No catalog items, no wizard surface, no encumbrance involvement.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, pytest. Windows venv: run everything via `.venv\Scripts\python.exe`.

Spec: `docs/superpowers/specs/2026-06-03-gems-and-jewellery-design.md`

---

### Task 0: Feature branch + commit the spec

**Files:** none (git only)

- [ ] **Step 1: Create the feature branch**

```powershell
git checkout -b feature/gems-and-jewellery
```

- [ ] **Step 2: Commit the design spec (already written, currently untracked)**

```powershell
git add "docs/superpowers/specs/2026-06-03-gems-and-jewellery-design.md" "docs/superpowers/plans/2026-06-03-gems-and-jewellery.md"
git commit -m @'
docs: gems & jewellery design spec + implementation plan

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 1: Models — `GemStack`, `JewelleryPiece`, spec lists, exports

**Files:**
- Create: `aose/models/valuable.py`
- Modify: `aose/models/character.py` (add two list fields to `CharacterSpec`)
- Modify: `aose/models/__init__.py` (import + `__all__`)
- Test: `tests/test_models.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_models.py`:

```python
def test_valuable_models_defaults():
    from aose.models import GemStack, JewelleryPiece, CharacterSpec

    g = GemStack(instance_id="abc", value=100)
    assert g.count == 1
    assert g.label == ""

    j = JewelleryPiece(instance_id="def", value=700)
    assert j.damaged is False
    assert j.label == ""

    spec = CharacterSpec(
        name="T",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[{"class_id": "fighter", "level": 1, "hp_rolls": [8]}],
        alignment="neutral",
    )
    assert spec.gems == []
    assert spec.jewellery == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models.py::test_valuable_models_defaults -v`
Expected: FAIL — `ImportError: cannot import name 'GemStack'`.

- [ ] **Step 3: Create the models file**

Create `aose/models/valuable.py`:

```python
from pydantic import BaseModel, ConfigDict


class GemStack(BaseModel):
    """A stack of identical gems the character owns.  Gems with the same
    (value, label) combine into one stack; counts are adjusted manually.
    ``value`` is gp per gem — one of the table increments or a custom amount.
    Weightless; never stored in ``inventory``."""
    model_config = ConfigDict(extra="forbid")

    instance_id: str          # uuid4 hex
    value: int                # gp per gem; > 0
    count: int = 1            # number of identical gems in this stack
    label: str = ""           # optional free-text name


class JewelleryPiece(BaseModel):
    """A single piece of jewellery.  ``value`` is the full (un-halved) gp worth;
    ``damaged`` halves the effective value at display/sell time (reversible
    toggle).  Weightless; never stored in ``inventory``."""
    model_config = ConfigDict(extra="forbid")

    instance_id: str          # uuid4 hex
    value: int                # full gp value; > 0
    damaged: bool = False
    label: str = ""           # optional free-text name
```

- [ ] **Step 4: Add the spec fields**

In `aose/models/character.py`, inside `CharacterSpec`, add the import at the top of the file (with the other relative model imports):

```python
from .valuable import GemStack, JewelleryPiece
```

Then add these two fields immediately after the `spell_sources` field (around line 185):

```python
    # Owned treasure — gems (stacked by value+label) and jewellery (individual).
    # Weightless; free to acquire; never in `inventory`.
    gems: list[GemStack] = Field(default_factory=list)
    jewellery: list[JewelleryPiece] = Field(default_factory=list)
```

- [ ] **Step 5: Export the new models**

In `aose/models/__init__.py`, add an import line after the `.character` import block:

```python
from .valuable import GemStack, JewelleryPiece
```

And add `"GemStack",` and `"JewelleryPiece",` to `__all__`.

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models.py::test_valuable_models_defaults -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add aose/models/valuable.py aose/models/character.py aose/models/__init__.py tests/test_models.py
git commit -m @'
feat: GemStack & JewelleryPiece models + CharacterSpec lists

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 2: Engine — gem mutations and value math

**Files:**
- Create: `aose/engine/valuables.py`
- Test: `tests/test_valuables.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_valuables.py`:

```python
import random

import pytest

from aose.engine import valuables as v
from aose.models import GemStack


def test_add_gem_creates_stack():
    gems = v.add_gem([], 100, count=2, label="ruby")
    assert len(gems) == 1
    assert gems[0].value == 100
    assert gems[0].count == 2
    assert gems[0].label == "ruby"
    assert len(gems[0].instance_id) == 32  # uuid4 hex


def test_add_gem_stacks_on_value_and_label():
    gems = v.add_gem([], 100, count=1, label="ruby")
    gems = v.add_gem(gems, 100, count=3, label="ruby")
    assert len(gems) == 1
    assert gems[0].count == 4


def test_add_gem_does_not_stack_when_label_differs():
    gems = v.add_gem([], 100, label="ruby")
    gems = v.add_gem(gems, 100, label="emerald")
    assert len(gems) == 2


def test_add_gem_accepts_custom_value():
    gems = v.add_gem([], 250)
    assert gems[0].value == 250


def test_add_gem_rejects_nonpositive_value_or_count():
    with pytest.raises(v.ValuableError):
        v.add_gem([], 0)
    with pytest.raises(v.ValuableError):
        v.add_gem([], 100, count=0)


def test_adjust_gem_count_clamps_and_removes_at_zero():
    gems = v.add_gem([], 50, count=2)
    iid = gems[0].instance_id
    gems2 = v.adjust_gem_count(gems, iid, +3)
    assert gems2[0].count == 5
    gems3 = v.adjust_gem_count(gems, iid, -5)
    assert gems3 == []


def test_remove_gem_drops_whole_stack():
    gems = v.add_gem([], 50, count=9)
    iid = gems[0].instance_id
    assert v.remove_gem(gems, iid) == []


def test_remove_gem_unknown_id_raises():
    with pytest.raises(v.ValuableError):
        v.remove_gem([], "nope")


def test_sell_gem_decrements_and_adds_value():
    gems = v.add_gem([], 100, count=3)
    iid = gems[0].instance_id
    gems2, gold = v.sell_gem(gems, 5, iid)
    assert gold == 105
    assert gems2[0].count == 2


def test_sell_gem_empties_row_when_last():
    gems = v.add_gem([], 100, count=1)
    iid = gems[0].instance_id
    gems2, gold = v.sell_gem(gems, 0, iid)
    assert gems2 == []
    assert gold == 100


def test_sell_gem_all_sells_whole_stack():
    gems = v.add_gem([], 100, count=4)
    iid = gems[0].instance_id
    gems2, gold = v.sell_gem_all(gems, 10, iid)
    assert gems2 == []
    assert gold == 410


def test_gem_stack_value():
    assert v.gem_stack_value(GemStack(instance_id="x", value=100, count=3)) == 300
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_valuables.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aose.engine.valuables'`.

- [ ] **Step 3: Create the engine module with gem helpers**

Create `aose/engine/valuables.py`:

```python
"""Gems & jewellery — the cycle-free core for owned treasure valuables.

Gems stack by (value, label); jewellery pieces are individual with a damaged
toggle.  All weightless and free to acquire (Add-only).  Mutators return new
lists (no in-place mutation) and raise ``ValuableError`` on bad input; routes
map it to HTTP 400.  Imports only models + the dice engine; nothing imports it
back.
"""
from __future__ import annotations

import random
import uuid
from typing import Optional

from aose.engine.dice import roll
from aose.models import CharacterSpec, GemStack, JewelleryPiece

# Table increments — a dropdown affordance only; custom values are also valid.
GEM_INCREMENTS = (10, 50, 100, 500, 1000)


class ValuableError(ValueError):
    """All gem/jewellery validation / mutation errors (routes map to HTTP 400)."""


def _gem_index(gems: list[GemStack], instance_id: str) -> int:
    for i, g in enumerate(gems):
        if g.instance_id == instance_id:
            return i
    raise ValuableError(f"No gem stack with id {instance_id!r}")


def add_gem(gems: list[GemStack], value: int, count: int = 1,
            label: str = "") -> list[GemStack]:
    """Add ``count`` gems worth ``value`` each.  Stacks onto an existing entry
    with the same (value, label); otherwise appends a new stack."""
    if value <= 0:
        raise ValuableError("a gem must be worth more than 0 gp")
    if count <= 0:
        raise ValuableError("gem count must be positive")
    label = label.strip()
    for i, g in enumerate(gems):
        if g.value == value and g.label == label:
            updated = g.model_copy(update={"count": g.count + count})
            return [*gems[:i], updated, *gems[i + 1:]]
    return [*gems, GemStack(instance_id=uuid.uuid4().hex, value=value,
                            count=count, label=label)]


def adjust_gem_count(gems: list[GemStack], instance_id: str,
                     delta: int) -> list[GemStack]:
    """Add ``delta`` (may be negative) to a stack's count, clamped at 0.  A
    stack reaching 0 is removed."""
    idx = _gem_index(gems, instance_id)
    g = gems[idx]
    new_count = max(0, g.count + delta)
    if new_count == 0:
        return [*gems[:idx], *gems[idx + 1:]]
    updated = g.model_copy(update={"count": new_count})
    return [*gems[:idx], updated, *gems[idx + 1:]]


def remove_gem(gems: list[GemStack], instance_id: str) -> list[GemStack]:
    """Drop the whole stack (no gold)."""
    idx = _gem_index(gems, instance_id)
    return [*gems[:idx], *gems[idx + 1:]]


def sell_gem(gems: list[GemStack], gold: int,
             instance_id: str) -> tuple[list[GemStack], int]:
    """Sell one gem from the stack: -1 count, +value gold.  Empties → removed."""
    idx = _gem_index(gems, instance_id)
    g = gems[idx]
    new_gems = adjust_gem_count(gems, instance_id, -1)
    return new_gems, gold + g.value


def sell_gem_all(gems: list[GemStack], gold: int,
                 instance_id: str) -> tuple[list[GemStack], int]:
    """Sell the whole stack at once: +value*count gold, row removed."""
    idx = _gem_index(gems, instance_id)
    g = gems[idx]
    return [*gems[:idx], *gems[idx + 1:]], gold + g.value * g.count


def gem_stack_value(stack: GemStack) -> int:
    return stack.value * stack.count
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_valuables.py -v`
Expected: PASS (all gem tests).

- [ ] **Step 5: Commit**

```powershell
git add aose/engine/valuables.py tests/test_valuables.py
git commit -m @'
feat: valuables engine — gem stacks (add/adjust/remove/sell/sell-all)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 3: Engine — jewellery mutations, value math, total

**Files:**
- Modify: `aose/engine/valuables.py`
- Test: `tests/test_valuables.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_valuables.py`:

```python
def test_roll_jewellery_value_range():
    rng = random.Random(1)
    for _ in range(50):
        val = v.roll_jewellery_value(rng)
        assert 300 <= val <= 1800
        assert val % 100 == 0


def test_add_jewellery_appends_piece():
    jw = v.add_jewellery([], 700, damaged=False, label="necklace")
    assert len(jw) == 1
    assert jw[0].value == 700
    assert jw[0].damaged is False
    assert jw[0].label == "necklace"
    assert len(jw[0].instance_id) == 32


def test_add_jewellery_rejects_nonpositive_value():
    with pytest.raises(v.ValuableError):
        v.add_jewellery([], 0)


def test_set_jewellery_damaged_toggles():
    jw = v.add_jewellery([], 700)
    iid = jw[0].instance_id
    jw = v.set_jewellery_damaged(jw, iid, True)
    assert jw[0].damaged is True
    jw = v.set_jewellery_damaged(jw, iid, False)
    assert jw[0].damaged is False


def test_jewellery_value_halves_when_damaged_with_floor():
    from aose.models import JewelleryPiece
    assert v.jewellery_value(JewelleryPiece(instance_id="x", value=700)) == 700
    assert v.jewellery_value(
        JewelleryPiece(instance_id="x", value=125, damaged=True)) == 62


def test_remove_jewellery_drops_piece():
    jw = v.add_jewellery([], 700)
    iid = jw[0].instance_id
    assert v.remove_jewellery(jw, iid) == []


def test_remove_jewellery_unknown_id_raises():
    with pytest.raises(v.ValuableError):
        v.remove_jewellery([], "nope")


def test_sell_jewellery_adds_effective_value():
    jw = v.add_jewellery([], 700)
    iid = jw[0].instance_id
    jw2, gold = v.sell_jewellery(jw, 5, iid)
    assert jw2 == []
    assert gold == 705


def test_sell_jewellery_damaged_adds_halved_value():
    jw = v.add_jewellery([], 700, damaged=True)
    iid = jw[0].instance_id
    jw2, gold = v.sell_jewellery(jw, 0, iid)
    assert gold == 350


def test_total_value_mixes_gems_and_jewellery():
    from aose.models import CharacterSpec
    spec = CharacterSpec(
        name="T",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[{"class_id": "fighter", "level": 1, "hp_rolls": [8]}],
        alignment="neutral",
    )
    spec.gems = v.add_gem([], 100, count=3)            # 300
    spec.jewellery = v.add_jewellery([], 700)          # 700
    spec.jewellery = v.add_jewellery(spec.jewellery, 200, damaged=True)  # 100
    assert v.total_value(spec) == 1100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_valuables.py -k jewellery -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'roll_jewellery_value'`.

- [ ] **Step 3: Append the jewellery helpers**

Add to the end of `aose/engine/valuables.py`:

```python
def _jewellery_index(jewellery: list[JewelleryPiece], instance_id: str) -> int:
    for i, j in enumerate(jewellery):
        if j.instance_id == instance_id:
            return i
    raise ValuableError(f"No jewellery piece with id {instance_id!r}")


def roll_jewellery_value(rng: Optional[random.Random] = None) -> int:
    """3d6 × 100 gp — the Advanced Fantasy jewellery value (300–1800 gp)."""
    return roll("3d6", rng) * 100


def add_jewellery(jewellery: list[JewelleryPiece], value: int,
                  damaged: bool = False, label: str = "") -> list[JewelleryPiece]:
    """Append a jewellery piece (Add-only).  ``value`` is the full, un-halved
    worth even when ``damaged`` is set."""
    if value <= 0:
        raise ValuableError("a jewellery piece must be worth more than 0 gp")
    return [*jewellery, JewelleryPiece(
        instance_id=uuid.uuid4().hex, value=value,
        damaged=damaged, label=label.strip(),
    )]


def set_jewellery_damaged(jewellery: list[JewelleryPiece], instance_id: str,
                          damaged: bool) -> list[JewelleryPiece]:
    """Toggle the damaged flag (reversible)."""
    idx = _jewellery_index(jewellery, instance_id)
    updated = jewellery[idx].model_copy(update={"damaged": damaged})
    return [*jewellery[:idx], updated, *jewellery[idx + 1:]]


def remove_jewellery(jewellery: list[JewelleryPiece],
                     instance_id: str) -> list[JewelleryPiece]:
    """Drop the piece (no gold)."""
    idx = _jewellery_index(jewellery, instance_id)
    return [*jewellery[:idx], *jewellery[idx + 1:]]


def sell_jewellery(jewellery: list[JewelleryPiece], gold: int,
                   instance_id: str) -> tuple[list[JewelleryPiece], int]:
    """Sell the piece: +effective value gold (halved if damaged), piece removed."""
    idx = _jewellery_index(jewellery, instance_id)
    value = jewellery_value(jewellery[idx])
    return [*jewellery[:idx], *jewellery[idx + 1:]], gold + value


def jewellery_value(piece: JewelleryPiece) -> int:
    """Effective gp worth — full, or floored half when damaged."""
    return piece.value // 2 if piece.damaged else piece.value


def total_value(spec: CharacterSpec) -> int:
    """Sum of all gem-stack values + all jewellery effective values."""
    return (
        sum(gem_stack_value(g) for g in spec.gems)
        + sum(jewellery_value(j) for j in spec.jewellery)
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_valuables.py -v`
Expected: PASS (all gem + jewellery tests).

- [ ] **Step 5: Commit**

```powershell
git add aose/engine/valuables.py tests/test_valuables.py
git commit -m @'
feat: valuables engine — jewellery (roll/add/toggle/remove/sell) + total_value

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 4: Sheet view — `valuables_view` + `CharacterSheet` field + wiring

**Files:**
- Modify: `aose/sheet/view.py`
- Test: `tests/test_sheet.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_sheet.py`. (This file already constructs specs and calls `build_sheet`; reuse its existing imports/fixtures. The test below builds its own spec to stay self-contained — adapt the fixture name if `test_sheet.py` already exposes a `data` fixture.)

```python
def test_valuables_view_and_zero_weight():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.engine import valuables as v
    from aose.engine.encumbrance import carried_weight_cn
    from aose.models import CharacterSpec
    from aose.sheet.view import build_sheet

    data = GameData.load(Path(__file__).parent.parent / "data")
    spec = CharacterSpec(
        name="T",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[{"class_id": "fighter", "level": 1, "hp_rolls": [8]}],
        alignment="neutral",
    )
    baseline_weight = carried_weight_cn(spec, data)
    spec.gems = v.add_gem([], 100, count=2, label="ruby")
    spec.jewellery = v.add_jewellery([], 700)
    spec.jewellery = v.add_jewellery(spec.jewellery, 200, damaged=True)

    sheet = build_sheet(spec, data)
    assert sheet.valuables.total_value == 1000  # 200 + 700 + 100
    assert len(sheet.valuables.gems) == 1
    assert sheet.valuables.gems[0].stack_value == 200
    assert len(sheet.valuables.jewellery) == 2
    damaged_row = next(j for j in sheet.valuables.jewellery if j.damaged)
    assert damaged_row.effective_value == 100
    # Valuables never contribute weight.
    assert carried_weight_cn(spec, data) == baseline_weight
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet.py::test_valuables_view_and_zero_weight -v`
Expected: FAIL — `AttributeError: 'CharacterSheet' object has no attribute 'valuables'`.

- [ ] **Step 3: Add the view models + builder**

In `aose/sheet/view.py`, add this block just before the `CharacterSheet` class definition (the class begins around line 195; place these models above it). Note `BaseModel` and `Field` are already imported in this file:

```python
class GemRow(BaseModel):
    instance_id: str
    value: int
    count: int
    label: str
    stack_value: int


class JewelleryRow(BaseModel):
    instance_id: str
    value: int           # full value
    damaged: bool
    label: str
    effective_value: int


class ValuablesView(BaseModel):
    gems: list[GemRow]
    jewellery: list[JewelleryRow]
    total_value: int
```

Add the `valuables` import near the top of `view.py`, next to the other engine imports (around line 5):

```python
from aose.engine import valuables as valuables_engine
```

Add the builder function (place it near `spell_sources_view`, around line 610):

```python
def valuables_view(spec: CharacterSpec) -> ValuablesView:
    """Gem stacks + jewellery pieces with computed values, plus the section
    total.  Weightless — never touches encumbrance."""
    gems = [
        GemRow(
            instance_id=g.instance_id, value=g.value, count=g.count,
            label=g.label, stack_value=valuables_engine.gem_stack_value(g),
        )
        for g in spec.gems
    ]
    jewellery = [
        JewelleryRow(
            instance_id=j.instance_id, value=j.value, damaged=j.damaged,
            label=j.label, effective_value=valuables_engine.jewellery_value(j),
        )
        for j in spec.jewellery
    ]
    gems.sort(key=lambda r: (-r.value, r.label))
    jewellery.sort(key=lambda r: (-r.value, r.label))
    return ValuablesView(
        gems=gems, jewellery=jewellery,
        total_value=valuables_engine.total_value(spec),
    )
```

- [ ] **Step 4: Add the `CharacterSheet` field**

In the `CharacterSheet` model, add after the `spell_sources` field (around line 241):

```python
    valuables: ValuablesView = Field(default_factory=lambda: ValuablesView(
        gems=[], jewellery=[], total_value=0))
```

- [ ] **Step 5: Wire it into `build_sheet`**

In the `CharacterSheet(...)` construction (around line 802, next to `spell_sources=...`), add:

```python
        valuables=valuables_view(spec),
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet.py::test_valuables_view_and_zero_weight -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add aose/sheet/view.py tests/test_sheet.py
git commit -m @'
feat: valuables_view + Gems & Jewellery sheet data

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 5: Routes — nine sheet-only POST endpoints

**Files:**
- Modify: `aose/web/routes.py`
- Test: `tests/test_valuables_routes.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_valuables_routes.py`:

```python
"""HTTP route tests for gem & jewellery play-state actions."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character
from aose.models import CharacterSpec, ClassEntry
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


def _save_fighter(client, gold=0):
    spec = CharacterSpec(
        name="Bran",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral", gold=gold,
    )
    save_character("bran", spec, client._characters_dir)
    return spec


def test_gem_add_route(client):
    _save_fighter(client)
    r = client.post("/character/bran/gems/add",
                    data={"value": 100, "count": 2, "label": "ruby"})
    assert r.status_code == 303
    spec = load_character("bran", client._characters_dir)
    assert len(spec.gems) == 1
    assert spec.gems[0].count == 2


def test_gem_add_custom_value(client):
    _save_fighter(client)
    client.post("/character/bran/gems/add", data={"value": 250, "count": 1})
    spec = load_character("bran", client._characters_dir)
    assert spec.gems[0].value == 250


def test_gem_sell_route_adds_gold(client):
    _save_fighter(client, gold=5)
    client.post("/character/bran/gems/add", data={"value": 100, "count": 2})
    spec = load_character("bran", client._characters_dir)
    iid = spec.gems[0].instance_id
    client.post("/character/bran/gems/sell", data={"instance_id": iid})
    spec = load_character("bran", client._characters_dir)
    assert spec.gold == 105
    assert spec.gems[0].count == 1


def test_gem_sell_all_route(client):
    _save_fighter(client, gold=0)
    client.post("/character/bran/gems/add", data={"value": 100, "count": 3})
    spec = load_character("bran", client._characters_dir)
    iid = spec.gems[0].instance_id
    client.post("/character/bran/gems/sell-all", data={"instance_id": iid})
    spec = load_character("bran", client._characters_dir)
    assert spec.gold == 300
    assert spec.gems == []


def test_gem_adjust_and_remove(client):
    _save_fighter(client)
    client.post("/character/bran/gems/add", data={"value": 50, "count": 2})
    spec = load_character("bran", client._characters_dir)
    iid = spec.gems[0].instance_id
    client.post("/character/bran/gems/adjust", data={"instance_id": iid, "delta": 3})
    assert load_character("bran", client._characters_dir).gems[0].count == 5
    client.post("/character/bran/gems/remove", data={"instance_id": iid})
    assert load_character("bran", client._characters_dir).gems == []


def test_jewellery_add_set_value(client):
    _save_fighter(client)
    client.post("/character/bran/jewellery/add",
                data={"mode": "set", "value": 700, "label": "necklace"})
    spec = load_character("bran", client._characters_dir)
    assert spec.jewellery[0].value == 700


def test_jewellery_add_random_in_range(client):
    _save_fighter(client)
    client.post("/character/bran/jewellery/add", data={"mode": "random"})
    spec = load_character("bran", client._characters_dir)
    assert 300 <= spec.jewellery[0].value <= 1800


def test_jewellery_toggle_damaged(client):
    _save_fighter(client)
    client.post("/character/bran/jewellery/add", data={"mode": "set", "value": 700})
    spec = load_character("bran", client._characters_dir)
    iid = spec.jewellery[0].instance_id
    client.post("/character/bran/jewellery/toggle-damaged",
                data={"instance_id": iid, "damaged": "true"})
    assert load_character("bran", client._characters_dir).jewellery[0].damaged is True
    client.post("/character/bran/jewellery/toggle-damaged",
                data={"instance_id": iid, "damaged": "false"})
    assert load_character("bran", client._characters_dir).jewellery[0].damaged is False


def test_jewellery_sell_damaged_halves(client):
    _save_fighter(client, gold=0)
    client.post("/character/bran/jewellery/add",
                data={"mode": "set", "value": 700})
    spec = load_character("bran", client._characters_dir)
    iid = spec.jewellery[0].instance_id
    client.post("/character/bran/jewellery/toggle-damaged",
                data={"instance_id": iid, "damaged": "true"})
    client.post("/character/bran/jewellery/sell", data={"instance_id": iid})
    spec = load_character("bran", client._characters_dir)
    assert spec.gold == 350
    assert spec.jewellery == []


def test_jewellery_drop_no_gold(client):
    _save_fighter(client, gold=0)
    client.post("/character/bran/jewellery/add",
                data={"mode": "set", "value": 700})
    spec = load_character("bran", client._characters_dir)
    iid = spec.jewellery[0].instance_id
    client.post("/character/bran/jewellery/remove", data={"instance_id": iid})
    spec = load_character("bran", client._characters_dir)
    assert spec.gold == 0
    assert spec.jewellery == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_valuables_routes.py -v`
Expected: FAIL — routes 404 (`assert 404 == 303`).

- [ ] **Step 3: Add the engine import**

In `aose/web/routes.py`, add near the other engine imports (around line 75):

```python
from aose.engine import valuables as valuables_engine
from aose.engine.valuables import ValuableError
```

- [ ] **Step 4: Add the routes**

Append these routes to `aose/web/routes.py` (after the spell-source routes, ~line 898). They follow the established pattern: `_load_spec_or_404`, mutate via engine, `save_character`, 303 redirect. `damaged` is parsed from the standard HTML truthy strings:

```python
def _truthy(value: str) -> bool:
    return str(value).lower() in ("1", "true", "on", "yes")


@router.post("/character/{character_id}/gems/add")
async def sheet_gem_add(request: Request, character_id: str,
                        value: int = Form(...), count: int = Form(1),
                        label: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.gems = valuables_engine.add_gem(spec.gems, value, count, label)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/gems/adjust")
async def sheet_gem_adjust(request: Request, character_id: str,
                           instance_id: str = Form(...), delta: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.gems = valuables_engine.adjust_gem_count(spec.gems, instance_id, delta)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/gems/sell")
async def sheet_gem_sell(request: Request, character_id: str,
                         instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.gems, spec.gold = valuables_engine.sell_gem(
            spec.gems, spec.gold, instance_id)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/gems/sell-all")
async def sheet_gem_sell_all(request: Request, character_id: str,
                             instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.gems, spec.gold = valuables_engine.sell_gem_all(
            spec.gems, spec.gold, instance_id)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/gems/remove")
async def sheet_gem_remove(request: Request, character_id: str,
                           instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.gems = valuables_engine.remove_gem(spec.gems, instance_id)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/jewellery/add")
async def sheet_jewellery_add(request: Request, character_id: str,
                              mode: str = Form("set"), value: int = Form(0),
                              damaged: str = Form(""), label: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    if mode == "random":
        value = valuables_engine.roll_jewellery_value()
    try:
        spec.jewellery = valuables_engine.add_jewellery(
            spec.jewellery, value, _truthy(damaged), label)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/jewellery/toggle-damaged")
async def sheet_jewellery_toggle_damaged(request: Request, character_id: str,
                                         instance_id: str = Form(...),
                                         damaged: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.jewellery = valuables_engine.set_jewellery_damaged(
            spec.jewellery, instance_id, _truthy(damaged))
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/jewellery/sell")
async def sheet_jewellery_sell(request: Request, character_id: str,
                               instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.jewellery, spec.gold = valuables_engine.sell_jewellery(
            spec.jewellery, spec.gold, instance_id)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/jewellery/remove")
async def sheet_jewellery_remove(request: Request, character_id: str,
                                 instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.jewellery = valuables_engine.remove_jewellery(
            spec.jewellery, instance_id)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_valuables_routes.py -v`
Expected: PASS (all 10 route tests).

- [ ] **Step 6: Commit**

```powershell
git add aose/web/routes.py tests/test_valuables_routes.py
git commit -m @'
feat: gems & jewellery sheet routes (add/adjust/sell/sell-all/remove/toggle)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 6: Template — Gems & Jewellery sheet section + Add forms

**Files:**
- Modify: `aose/web/templates/sheet.html`
- Test: `tests/test_web.py` (append a render smoke test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web.py`. (Reuse the file's existing `client` fixture and character-creation helper if present; the snippet below assumes a `client` fixture like the route tests and saves its own character.)

```python
def test_sheet_renders_valuables_section(tmp_path):
    from pathlib import Path
    from fastapi.testclient import TestClient
    from aose.characters import save_character
    from aose.models import CharacterSpec, ClassEntry
    from aose.engine import valuables as v
    from aose.web.app import create_app

    characters_dir = tmp_path / "characters"
    examples_dir = tmp_path / "examples"; examples_dir.mkdir()
    app = create_app(
        data_dir=Path(__file__).parent.parent / "data",
        characters_dir=characters_dir, drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir, settings_path=tmp_path / "settings.json",
    )
    spec = CharacterSpec(
        name="Bran",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
    )
    spec.gems = v.add_gem([], 100, count=2, label="ruby")
    spec.jewellery = v.add_jewellery([], 700, label="necklace")
    save_character("bran", spec, characters_dir)

    client = TestClient(app, follow_redirects=False)
    html = client.get("/character/bran").text
    assert "Gems &amp; Jewellery" in html
    assert "ruby" in html
    assert "necklace" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_sheet_renders_valuables_section -v`
Expected: FAIL — `assert 'Gems &amp; Jewellery' in html` is False.

- [ ] **Step 3: Add the section to the template**

In `aose/web/templates/sheet.html`, insert this `<section>` immediately after the Spell Books & Scrolls section closes (after `</section>` at line ~590, before the Rest section). It mirrors the spell-source section's markup conventions (`no-print`, `inline`, `link-button`, `details`/`summary`):

```html
            <section class="section">
                <h2>Gems &amp; Jewellery</h2>

                <h3>Gems</h3>
                {% for g in sheet.valuables.gems %}
                <div class="valuable">
                    <strong>{{ g.value }} gp</strong> × {{ g.count }}
                    {% if g.label %}<span class="small muted">{{ g.label }}</span>{% endif %}
                    <span class="small muted">= {{ g.stack_value }} gp</span>
                    <form method="post" class="no-print inline"
                          action="/character/{{ character_id }}/gems/sell">
                        <input type="hidden" name="instance_id" value="{{ g.instance_id }}">
                        <button type="submit" class="link-button">sell one</button>
                    </form>
                    <form method="post" class="no-print inline"
                          action="/character/{{ character_id }}/gems/sell-all">
                        <input type="hidden" name="instance_id" value="{{ g.instance_id }}">
                        <button type="submit" class="link-button">sell all</button>
                    </form>
                    <form method="post" class="no-print inline"
                          action="/character/{{ character_id }}/gems/adjust">
                        <input type="hidden" name="instance_id" value="{{ g.instance_id }}">
                        <input type="hidden" name="delta" value="1">
                        <button type="submit" class="link-button">+1</button>
                    </form>
                    <form method="post" class="no-print inline"
                          action="/character/{{ character_id }}/gems/adjust">
                        <input type="hidden" name="instance_id" value="{{ g.instance_id }}">
                        <input type="hidden" name="delta" value="-1">
                        <button type="submit" class="link-button">−1</button>
                    </form>
                    <form method="post" class="no-print inline"
                          action="/character/{{ character_id }}/gems/remove">
                        <input type="hidden" name="instance_id" value="{{ g.instance_id }}">
                        <button type="submit" class="link-button">drop</button>
                    </form>
                </div>
                {% else %}
                <p class="small muted">No gems.</p>
                {% endfor %}

                <details class="no-print">
                    <summary>Add a gem</summary>
                    <form method="post" action="/character/{{ character_id }}/gems/add">
                        <label>Value:
                            <select name="value">
                                <option value="10">10 gp</option>
                                <option value="50">50 gp</option>
                                <option value="100" selected>100 gp</option>
                                <option value="500">500 gp</option>
                                <option value="1000">1,000 gp</option>
                            </select>
                        </label>
                        <label>or custom gp:
                            <input type="number" name="value" min="1"
                                   placeholder="overrides dropdown">
                        </label>
                        <label>Count:
                            <input type="number" name="count" min="1" value="1">
                        </label>
                        <label>Label (optional):
                            <input type="text" name="label" placeholder="e.g. ruby">
                        </label>
                        <button type="submit" class="primary">Add gem</button>
                    </form>
                </details>

                <h3>Jewellery</h3>
                {% for j in sheet.valuables.jewellery %}
                <div class="valuable">
                    <strong>{{ j.effective_value }} gp</strong>
                    {% if j.damaged %}<span class="small muted">(damaged — full {{ j.value }})</span>{% endif %}
                    {% if j.label %}<span class="small muted">{{ j.label }}</span>{% endif %}
                    <form method="post" class="no-print inline"
                          action="/character/{{ character_id }}/jewellery/toggle-damaged">
                        <input type="hidden" name="instance_id" value="{{ j.instance_id }}">
                        <input type="hidden" name="damaged" value="{{ 'false' if j.damaged else 'true' }}">
                        <button type="submit" class="link-button">
                            {{ 'mark intact' if j.damaged else 'mark damaged' }}</button>
                    </form>
                    <form method="post" class="no-print inline"
                          action="/character/{{ character_id }}/jewellery/sell">
                        <input type="hidden" name="instance_id" value="{{ j.instance_id }}">
                        <button type="submit" class="link-button">sell</button>
                    </form>
                    <form method="post" class="no-print inline"
                          action="/character/{{ character_id }}/jewellery/remove">
                        <input type="hidden" name="instance_id" value="{{ j.instance_id }}">
                        <button type="submit" class="link-button">drop</button>
                    </form>
                </div>
                {% else %}
                <p class="small muted">No jewellery.</p>
                {% endfor %}

                <details class="no-print">
                    <summary>Add jewellery</summary>
                    <form method="post" action="/character/{{ character_id }}/jewellery/add">
                        <label>Value:
                            <select name="mode">
                                <option value="random">Random (3d6 × 100)</option>
                                <option value="set">Set value</option>
                            </select>
                        </label>
                        <label>gp (if set):
                            <input type="number" name="value" min="1">
                        </label>
                        <label>Label (optional):
                            <input type="text" name="label" placeholder="e.g. gold necklace">
                        </label>
                        <label>Damaged:
                            <input type="checkbox" name="damaged" value="true">
                        </label>
                        <button type="submit" class="primary">Add jewellery</button>
                    </form>
                </details>

                <p class="small muted">Total treasure value:
                    <strong>{{ sheet.valuables.total_value }} gp</strong></p>
            </section>
```

Note on the gem Add form: it has two `value` inputs (dropdown + custom number). With duplicate field names, the custom number field — when filled — is the later value in the form submission; FastAPI's `value: int = Form(...)` takes the last occurrence, so a filled custom box overrides the dropdown. Leaving the custom box empty submits only the dropdown value. The route already accepts whatever single int arrives.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_sheet_renders_valuables_section -v`
Expected: PASS.

- [ ] **Step 5: Manually verify the gem custom-value override**

Run the app and confirm a filled custom-gp box wins over the dropdown:

```powershell
.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload
```

Add a gem with the dropdown at 100 but custom box = 250; confirm a 250 gp gem appears. If the empty custom box instead submits an empty string and the route 422s, change the route's `value` handling to read the form manually (last non-empty of `form.getlist("value")`) — but the `Form(...)` last-occurrence behaviour with an empty optional box should be verified here before adding complexity.

- [ ] **Step 6: Commit**

```powershell
git add aose/web/templates/sheet.html tests/test_web.py
git commit -m @'
feat: Gems & Jewellery sheet section + Add forms

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 7: Full suite + docs note

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run the full test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all tests pass (the trailing `pytest-current` PermissionError on Windows is the known, ignorable quirk).

- [ ] **Step 2: Add the feature note to `CLAUDE.md`**

Under the "Current state" area near the top of the feature log, add an entry:

```markdown
Gems & jewellery just landed (on `feature/gems-and-jewellery`).

- **Gems & jewellery** — free-acquired, weightless, sheet-only treasure. Two
  per-instance models on `CharacterSpec`: `GemStack` (value + count + label,
  stacks by value+label) and `JewelleryPiece` (full value + `damaged` toggle +
  label; damaged halves value with floor at display/sell). Cycle-free
  `aose/engine/valuables.py` owns add/adjust/remove/sell/sell-all (gems),
  add/toggle-damaged/remove/sell (jewellery), `roll_jewellery_value` (3d6×100),
  and the value helpers (`gem_stack_value`/`jewellery_value`/`total_value`).
  `GEM_INCREMENTS` is a dropdown affordance, not a constraint (custom values
  allowed). Selling adds value to `gold`; dropping refunds nothing (free
  acquisition). Sheet gains a "Gems & Jewellery" section (`valuables_view`) +
  `/gems/{add,adjust,sell,sell-all,remove}` and `/jewellery/{add,toggle-damaged,
  sell,remove}` (sheet-only). Never touches `encumbrance.py`. Spec/plan:
  `docs/superpowers/{specs,plans}/2026-06-03-gems-and-jewellery*`.
```

- [ ] **Step 3: Commit**

```powershell
git add CLAUDE.md
git commit -m @'
docs: note gems & jewellery feature in CLAUDE.md

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

## Notes for the implementer

- **Run everything via `.venv\Scripts\python.exe`** — bare `python`/`uvicorn`/`pytest` won't see the venv.
- **PowerShell here-strings** for commit messages: the closing `'@` must be at column 0.
- **No data migrations** — the two new `CharacterSpec` lists default empty; old saved characters load unchanged.
- **Test fixtures:** Tasks 4 and 6 assume the existing test files' fixtures; the snippets are written self-contained so they work even if a shared fixture name differs. If `test_sheet.py` / `test_web.py` already expose a `data`/`client` fixture, prefer reusing it and trim the duplicated setup.
- **The one risk spot** is the gem Add form's dual `value` inputs (Task 6, Step 5). Verify the override behaviour in the running app; the fallback (manual `form.getlist`) is described inline if `Form(...)` doesn't handle the empty custom box cleanly.
```
