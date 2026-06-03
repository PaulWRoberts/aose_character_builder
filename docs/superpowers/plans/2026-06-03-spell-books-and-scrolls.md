# Spell Books & Scrolls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add owned spell books and magic scrolls as per-character documents with chosen contents, support casting from scrolls and the Advanced Spell Book "copy from a source" mechanic (with per-source failure), and add the four Scrolls of Protection as catalog data.

**Architecture:** A unified per-instance `SpellSource` model (kind = spellbook | scroll) on `CharacterSpec.spell_sources`, mirroring `ContainerInstance`/`AmmoStack`. A new cycle-free engine module `aose/engine/spell_sources.py` owns create/remove/cast/copy. Copy-failure is stored on the source entry, never on the character. Sheet gets a new section + four routes; protection scrolls are plain `MagicItem` YAML.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, pytest. Windows venv: run everything via `.venv\Scripts\python.exe`.

**Spec:** `docs/superpowers/specs/2026-06-03-spell-books-and-scrolls-design.md`

---

## File Structure

- **Create** `aose/engine/spell_sources.py` — cycle-free engine: validation, add/remove, cast (expend), copy (roll), and pure predicates for the view/routes.
- **Modify** `aose/models/character.py` — add `SpellSourceEntry`, `SpellSource`, and `CharacterSpec.spell_sources`.
- **Modify** `aose/models/__init__.py` — export the two new models.
- **Modify** `aose/engine/spells.py` — add `copy_chance_for_int`; guard `learn()` under the advanced rule.
- **Modify** `aose/sheet/view.py` — add `SpellSourceView`/`SpellSourceEntryView` + `spell_sources_view`; add `spell_source_add_options`; add `spell_sources` to `CharacterSheet`; hide `learnable` under the advanced rule.
- **Modify** `aose/web/routes.py` — add `/spell-sources/{add,remove,cast,copy}` and pass `spell_source_add_options` into the sheet context.
- **Modify** `aose/web/templates/sheet.html` — new "Spell Books & Scrolls" section + Add form.
- **Create** `aose/web/static/spell_source_add.js` — progressive-enhancement filter for the Add form's spell picker.
- **Create** `data/equipment/scrolls.yaml` — four Scrolls of Protection (`MagicItem`).
- **Modify** test files as noted per task; **create** `tests/test_spell_sources.py`.
- **Modify** `CLAUDE.md` — Current-state note.

---

## Task 1: SpellSource model + CharacterSpec field

**Files:**
- Modify: `aose/models/character.py`
- Modify: `aose/models/__init__.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_models.py`:

```python
def test_spell_source_round_trips():
    from aose.models import CharacterSpec, ClassEntry, SpellSource, SpellSourceEntry
    src = SpellSource(
        instance_id="abc", kind="scroll", caster_type="arcane", name="Found Scroll",
        entries=[SpellSourceEntry(spell_id="magic_user_magic_missile"),
                 SpellSourceEntry(spell_id="magic_user_sleep", copy_failed=True)],
    )
    spec = CharacterSpec(
        name="X", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="magic_user", level=1)],
        alignment="neutral", spell_sources=[src],
    )
    reloaded = CharacterSpec.model_validate(spec.model_dump())
    assert reloaded.spell_sources[0].kind == "scroll"
    assert reloaded.spell_sources[0].entries[1].copy_failed is True
    # default is an empty list
    bare = CharacterSpec(
        name="Y", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="magic_user", level=1)],
        alignment="neutral",
    )
    assert bare.spell_sources == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models.py::test_spell_source_round_trips -q`
Expected: FAIL — `ImportError: cannot import name 'SpellSource'`.

- [ ] **Step 3: Implement the models**

In `aose/models/character.py`, add these two classes just above `class SpellSlot`:

```python
class SpellSourceEntry(BaseModel):
    """One spell recorded in a SpellSource document.  ``copy_failed`` is set when
    an Advanced-rule copy attempt from THIS source failed — it bars retrying the
    same spell from this source only, never from any other source, and is never
    recorded on the character."""
    model_config = ConfigDict(extra="forbid")

    spell_id: str
    copy_failed: bool = False


class SpellSource(BaseModel):
    """A physical document the character owns — an arcane spell book or a magic
    scroll — with custom contents chosen at acquisition (Add-only, sheet).  Not
    stored in ``inventory``; carries its own existence like ContainerInstance.
    Scroll spells are expended (the entry removed) when cast; spell books are
    never expended.  ``caster_type`` is always ``arcane`` for a spellbook."""
    model_config = ConfigDict(extra="forbid")

    instance_id: str                              # uuid4 hex
    kind: Literal["spellbook", "scroll"]
    caster_type: Literal["arcane", "divine"]
    name: str = ""                                # optional label
    entries: list[SpellSourceEntry] = Field(default_factory=list)
```

Then add the field to `CharacterSpec`, right after the `loaded_ammo` line:

```python
    # Owned spell books / scrolls (custom contents).  Not in `inventory`.
    spell_sources: list[SpellSource] = Field(default_factory=list)
```

- [ ] **Step 4: Export the models**

In `aose/models/__init__.py`, update the `from .character import (...)` block to include `SpellSource, SpellSourceEntry`, and add both names to `__all__` (keep alphabetical-ish grouping with the other character models):

```python
from .character import (
    AmmoStack, CharacterSpec, ClassEntry, ContainerInstance, EnchantedInstance,
    MagicItemInstance, SpellSlot, SpellSource, SpellSourceEntry,
)
```

and in `__all__` add `"SpellSource",` and `"SpellSourceEntry",`.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models.py::test_spell_source_round_trips -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/models/character.py aose/models/__init__.py tests/test_models.py
git commit -m "feat: SpellSource model + CharacterSpec.spell_sources"
```

---

## Task 2: copy_chance_for_int in spells engine

**Files:**
- Modify: `aose/engine/spells.py`
- Test: `tests/test_spells.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_spells.py`:

```python
def test_copy_chance_for_int_table():
    from aose.engine import spells
    assert spells.copy_chance_for_int(3) == 20
    assert spells.copy_chance_for_int(4) == 30
    assert spells.copy_chance_for_int(5) == 30
    assert spells.copy_chance_for_int(7) == 35
    assert spells.copy_chance_for_int(9) == 40
    assert spells.copy_chance_for_int(12) == 50
    assert spells.copy_chance_for_int(14) == 70
    assert spells.copy_chance_for_int(16) == 75
    assert spells.copy_chance_for_int(17) == 85
    assert spells.copy_chance_for_int(18) == 90
    assert spells.copy_chance_for_int(20) == 90   # 18+
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py::test_copy_chance_for_int_table -q`
Expected: FAIL — `AttributeError: module 'aose.engine.spells' has no attribute 'copy_chance_for_int'`.

- [ ] **Step 3: Implement**

In `aose/engine/spells.py`, replace the existing `_INT_BEGINNING_SPELLS` table and `beginning_spells_for_int` with a combined table plus the new lookup (keep `beginning_spells_for_int` behaviour identical):

```python
# (INT ceiling, beginning spells, copy chance %) — OSE Advanced Spell Book table.
_INT_SPELL_TABLE = [
    (3, 1, 20), (5, 1, 30), (7, 2, 35), (9, 2, 40), (12, 3, 50),
    (14, 3, 70), (16, 4, 75), (17, 4, 85), (18, 5, 90),
]


def beginning_spells_for_int(int_score: int) -> int:
    """OSE Advanced 'Advanced Spell Book Rules' beginning-spells table (p112)."""
    for ceiling, count, _chance in _INT_SPELL_TABLE:
        if int_score <= ceiling:
            return count
    return 5  # INT 18+


def copy_chance_for_int(int_score: int) -> int:
    """OSE Advanced 'Chance of Copying' percentage (p112) for the given INT."""
    for ceiling, _count, chance in _INT_SPELL_TABLE:
        if int_score <= ceiling:
            return chance
    return 90  # INT 18+
```

Delete the old `_INT_BEGINNING_SPELLS = [...]` list (now folded into `_INT_SPELL_TABLE`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -q`
Expected: PASS (new test + the existing `test_beginning_spell_count_standard_vs_advanced` still passes).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/spells.py tests/test_spells.py
git commit -m "feat: copy_chance_for_int (Advanced Spell Book copy %)"
```

---

## Task 3: learn() becomes copy-only under the advanced rule

**Files:**
- Modify: `aose/engine/spells.py:134-158`
- Test: `tests/test_spells.py` (new test + update one existing test)

- [ ] **Step 1: Write the failing test + fix the obsolete one**

Add to `tests/test_spells.py`:

```python
def test_learn_rejected_under_advanced_rule():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="magic_user", level=1, spellbook=[])
    cls = data.classes["magic_user"]
    with pytest.raises(spells.SpellError):
        spells.learn(e, cls, data, RuleSet(advanced_spell_books=True),
                     "magic_user_magic_missile")
```

Replace the obsolete tail of `test_learn_standard_caps_at_memorizable` (the two lines that currently assert advanced free-learn succeeds) so the whole test reads:

```python
def test_learn_standard_caps_at_memorizable():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_user_magic_missile"])
    cls = data.classes["magic_user"]
    with pytest.raises(spells.SpellError):
        spells.learn(e, cls, data, RuleSet(), "magic_user_sleep")
    # Under the advanced rule, learn() is copy-only and refuses free adds.
    with pytest.raises(spells.SpellError):
        spells.learn(e, cls, data, RuleSet(advanced_spell_books=True), "magic_user_sleep")
```

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py::test_learn_rejected_under_advanced_rule -q`
Expected: FAIL — no exception raised (learn currently allows free add under advanced).

- [ ] **Step 3: Implement the guard**

In `aose/engine/spells.py`, at the top of `learn()` (right after the arcane-caster check), add:

```python
    if ruleset.advanced_spell_books:
        raise SpellError(
            "under advanced rules, spells must be copied from a source "
            "(use a spell book or scroll), not learned freely"
        )
```

Place it immediately after the existing:

```python
    if caster_type_of(cls, data) != "arcane":
        raise SpellError(f"{cls.id!r} is not an arcane caster; nothing to learn")
```

The standard-rule cap logic below is now only reached when `advanced_spell_books` is False; leave it unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/spells.py tests/test_spells.py
git commit -m "feat: learn() is copy-only under the advanced spell-book rule"
```

---

## Task 4: spell_sources engine — create / add / remove

**Files:**
- Create: `aose/engine/spell_sources.py`
- Test: `tests/test_spell_sources.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_spell_sources.py`:

```python
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine import spell_sources as ss

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def test_new_spell_source_validates_caster_type(data):
    src = ss.new_spell_source("scroll", "arcane",
                              ["magic_user_magic_missile", "magic_user_sleep"], data)
    assert src.kind == "scroll"
    assert src.caster_type == "arcane"
    assert [e.spell_id for e in src.entries] == ["magic_user_magic_missile", "magic_user_sleep"]
    assert len(src.instance_id) == 32  # uuid4 hex


def test_new_spell_source_spellbook_forces_arcane(data):
    src = ss.new_spell_source("spellbook", "divine", ["magic_user_sleep"], data)
    assert src.caster_type == "arcane"


def test_new_spell_source_rejects_off_type_spell(data):
    # faerie_fire is a divine spell; cannot go in an arcane document.
    with pytest.raises(ss.SpellSourceError):
        ss.new_spell_source("scroll", "arcane", ["faerie_fire"], data)


def test_new_spell_source_rejects_duplicates(data):
    with pytest.raises(ss.SpellSourceError):
        ss.new_spell_source("scroll", "arcane",
                            ["magic_user_sleep", "magic_user_sleep"], data)


def test_new_spell_source_rejects_unknown_spell(data):
    with pytest.raises(ss.SpellSourceError):
        ss.new_spell_source("scroll", "arcane", ["nope_not_a_spell"], data)


def test_new_spell_source_list_id_constraint(data):
    # list_id pins membership to one list (used by the spellbook UI).
    src = ss.new_spell_source("spellbook", "arcane", ["magic_user_sleep"], data,
                              list_id="magic_user")
    assert src.entries[0].spell_id == "magic_user_sleep"
    with pytest.raises(ss.SpellSourceError):
        ss.new_spell_source("spellbook", "arcane", ["faerie_fire"], data,
                            list_id="magic_user")


def test_add_and_remove(data):
    sources = ss.add_spell_source([], "scroll", "arcane",
                                  ["magic_user_magic_missile"], data, name="A")
    assert len(sources) == 1
    iid = sources[0].instance_id
    sources = ss.remove_spell_source(sources, iid)
    assert sources == []
    with pytest.raises(ss.SpellSourceError):
        ss.remove_spell_source(sources, "missing")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aose.engine.spell_sources'`.

- [ ] **Step 3: Implement create/add/remove**

Create `aose/engine/spell_sources.py`:

```python
"""Spell books & scrolls — the cycle-free core for owned spell documents.

A ``SpellSource`` is a physical document (spell book or scroll) with custom
contents.  This module validates contents, adds/removes documents, expends a
scroll spell on cast, and runs the Advanced-rule copy-from-source attempt.

Imports only models + the data loader + the dice/spells/magic engines (like
``engine/ammo.py``); nothing imports it back.  Copy-failure state is written
ONLY onto the source document, never onto the character.
"""
from __future__ import annotations

import random
import uuid
from typing import Literal, Optional

from aose.data.loader import GameData
from aose.engine import spells as spell_engine
from aose.engine.dice import roll
from aose.models import (
    CharClass, CharacterSpec, ClassEntry, Spell, SpellSource, SpellSourceEntry,
)

Kind = Literal["spellbook", "scroll"]
CasterType = Literal["arcane", "divine"]


class SpellSourceError(ValueError):
    """All spell-document validation / mutation errors (routes map to HTTP 400)."""


def _spell_caster_type(spell: Spell, data: GameData) -> CasterType | None:
    """The caster type a spell belongs to via its lists (arcane/divine).  None
    if it is on no known list."""
    for list_id in spell.spell_lists:
        sl = data.spell_lists.get(list_id)
        if sl is not None:
            return sl.caster_type
    return None


def new_spell_source(kind: Kind, caster_type: CasterType, spell_ids: list[str],
                     data: GameData, name: str = "",
                     list_id: str | None = None) -> SpellSource:
    """Build a validated SpellSource.

    Spellbooks are coerced to ``arcane``.  Every spell must exist and match
    ``caster_type`` (or, when ``list_id`` is given, be on that exact list).
    Duplicates within one document are rejected.  No spell-level filter — a
    document may hold spells of any level."""
    if kind == "spellbook":
        caster_type = "arcane"
    if not spell_ids:
        raise SpellSourceError("a spell book / scroll must contain at least one spell")
    if len(set(spell_ids)) != len(spell_ids):
        raise SpellSourceError("a document cannot list the same spell twice")
    for sid in spell_ids:
        spell = data.spells.get(sid)
        if spell is None:
            raise SpellSourceError(f"Unknown spell {sid!r}")
        if list_id is not None:
            if list_id not in spell.spell_lists:
                raise SpellSourceError(f"{sid!r} is not on spell list {list_id!r}")
        elif _spell_caster_type(spell, data) != caster_type:
            raise SpellSourceError(f"{sid!r} is not a {caster_type} spell")
    return SpellSource(
        instance_id=uuid.uuid4().hex,
        kind=kind, caster_type=caster_type, name=name.strip(),
        entries=[SpellSourceEntry(spell_id=sid) for sid in spell_ids],
    )


def add_spell_source(sources: list[SpellSource], kind: Kind, caster_type: CasterType,
                     spell_ids: list[str], data: GameData, name: str = "",
                     list_id: str | None = None) -> list[SpellSource]:
    """Add-only append (GM grant / loot); no gold."""
    return [*sources, new_spell_source(kind, caster_type, spell_ids, data, name, list_id)]


def _index(sources: list[SpellSource], instance_id: str) -> int:
    for i, s in enumerate(sources):
        if s.instance_id == instance_id:
            return i
    raise SpellSourceError(f"No spell document with id {instance_id!r}")


def remove_spell_source(sources: list[SpellSource], instance_id: str) -> list[SpellSource]:
    idx = _index(sources, instance_id)
    return [*sources[:idx], *sources[idx + 1:]]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/spell_sources.py tests/test_spell_sources.py
git commit -m "feat: spell_sources engine — create/add/remove documents"
```

---

## Task 5: cast_from_scroll + caster-type predicates

**Files:**
- Modify: `aose/engine/spell_sources.py`
- Test: `tests/test_spell_sources.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_spell_sources.py`:

```python
from aose.models import CharacterSpec, ClassEntry, RuleSet


def _mu_spec(advanced=False, sources=None):
    return CharacterSpec(
        name="Mu", abilities={"STR": 10, "INT": 13, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="magic_user", level=1)],
        alignment="neutral", ruleset=RuleSet(advanced_spell_books=advanced),
        spell_sources=sources or [],
    )


def test_cast_from_scroll_consumes_one(data):
    sources = ss.add_spell_source([], "scroll", "arcane",
                                  ["magic_user_magic_missile", "magic_user_sleep"], data)
    iid = sources[0].instance_id
    sources = ss.cast_from_scroll(sources, iid, "magic_user_magic_missile")
    assert len(sources) == 1
    assert [e.spell_id for e in sources[0].entries] == ["magic_user_sleep"]


def test_cast_last_spell_removes_scroll(data):
    sources = ss.add_spell_source([], "scroll", "arcane", ["magic_user_sleep"], data)
    iid = sources[0].instance_id
    sources = ss.cast_from_scroll(sources, iid, "magic_user_sleep")
    assert sources == []


def test_cast_rejects_non_scroll_and_missing(data):
    sources = ss.add_spell_source([], "spellbook", "arcane", ["magic_user_sleep"], data)
    iid = sources[0].instance_id
    with pytest.raises(ss.SpellSourceError):
        ss.cast_from_scroll(sources, iid, "magic_user_sleep")          # not a scroll
    scroll = ss.add_spell_source([], "scroll", "arcane", ["magic_user_sleep"], data)
    with pytest.raises(ss.SpellSourceError):
        ss.cast_from_scroll(scroll, scroll[0].instance_id, "magic_user_magic_missile")  # absent


def test_can_cast_scroll_matches_caster_type(data):
    arcane_scroll = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], data)
    divine_scroll = ss.new_spell_source("scroll", "divine", ["faerie_fire"], data)
    spec = _mu_spec()
    assert ss.can_cast_scroll(arcane_scroll, spec, data) is True
    assert ss.can_cast_scroll(divine_scroll, spec, data) is False
    # spell books are never castable
    book = ss.new_spell_source("spellbook", "arcane", ["magic_user_sleep"], data)
    assert ss.can_cast_scroll(book, spec, data) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources.py -k "cast or can_cast" -q`
Expected: FAIL — `AttributeError: module 'aose.engine.spell_sources' has no attribute 'cast_from_scroll'`.

- [ ] **Step 3: Implement**

Append to `aose/engine/spell_sources.py`:

```python
def cast_from_scroll(sources: list[SpellSource], instance_id: str,
                     spell_id: str) -> list[SpellSource]:
    """Expend one spell from a scroll: remove that entry.  If the scroll empties,
    drop the whole document (the parchment is now blank).  Validates document
    integrity only — caller checks caster-type usability via ``can_cast_scroll``."""
    idx = _index(sources, instance_id)
    src = sources[idx]
    if src.kind != "scroll":
        raise SpellSourceError("only scrolls can be cast from")
    pos = next((i for i, e in enumerate(src.entries) if e.spell_id == spell_id), None)
    if pos is None:
        raise SpellSourceError(f"{spell_id!r} is not on this scroll")
    remaining = [e for i, e in enumerate(src.entries) if i != pos]
    if not remaining:
        return [*sources[:idx], *sources[idx + 1:]]
    updated = src.model_copy(update={"entries": remaining})
    return [*sources[:idx], updated, *sources[idx + 1:]]


def character_caster_types(spec: CharacterSpec, data: GameData) -> set[str]:
    """The caster types the character can use (across all class entries)."""
    out: set[str] = set()
    for entry in spec.classes:
        cls = data.classes.get(entry.class_id)
        if cls is None:
            continue
        ctype = spell_engine.caster_type_of(cls, data)
        if ctype is not None:
            out.add(ctype)
    return out


def can_cast_scroll(source: SpellSource, spec: CharacterSpec, data: GameData) -> bool:
    """A scroll is castable if it is a scroll and the character has a class whose
    caster type matches the scroll's (arcane↔arcane, divine↔divine)."""
    if source.kind != "scroll":
        return False
    return source.caster_type in character_caster_types(spec, data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/spell_sources.py tests/test_spell_sources.py
git commit -m "feat: cast_from_scroll + caster-type usability predicates"
```

---

## Task 6: copy_spell (Advanced-rule copy from a source)

**Files:**
- Modify: `aose/engine/spell_sources.py`
- Test: `tests/test_spell_sources.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_spell_sources.py`:

```python
class _FixedRng:
    """Stand-in for random.Random whose 1d100 always returns ``value``."""
    def __init__(self, value):
        self.value = value
    def randint(self, a, b):
        return self.value


def test_copy_success_adds_to_spellbook(data):
    src = ss.new_spell_source("scroll", "arcane", ["magic_user_magic_missile"], data)
    entry = ClassEntry(class_id="magic_user", level=1, spellbook=[])
    cls = data.classes["magic_user"]
    new_entry, new_sources, ok = ss.copy_spell(
        entry, cls, data, RuleSet(advanced_spell_books=True), int_score=13,
        sources=[src], instance_id=src.instance_id,
        spell_id="magic_user_magic_missile", rng=_FixedRng(1),   # 1 <= 70 -> success
    )
    assert ok is True
    assert new_entry.spellbook == ["magic_user_magic_missile"]
    # source entry is not failed, source not consumed
    assert new_sources[0].entries[0].copy_failed is False


def test_copy_failure_burns_only_this_source(data):
    src = ss.new_spell_source("scroll", "arcane", ["magic_user_magic_missile"], data)
    entry = ClassEntry(class_id="magic_user", level=1, spellbook=[])
    cls = data.classes["magic_user"]
    new_entry, new_sources, ok = ss.copy_spell(
        entry, cls, data, RuleSet(advanced_spell_books=True), int_score=13,
        sources=[src], instance_id=src.instance_id,
        spell_id="magic_user_magic_missile", rng=_FixedRng(100),  # 100 > 70 -> fail
    )
    assert ok is False
    assert new_entry.spellbook == []
    assert new_sources[0].entries[0].copy_failed is True
    # retry from the SAME source is now rejected
    with pytest.raises(ss.SpellSourceError):
        ss.copy_spell(new_entry, cls, data, RuleSet(advanced_spell_books=True),
                      int_score=13, sources=new_sources, instance_id=src.instance_id,
                      spell_id="magic_user_magic_missile", rng=_FixedRng(1))


def test_copy_same_spell_from_a_second_source(data):
    failed = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], data)
    failed.entries[0].copy_failed = True
    other = ss.new_spell_source("spellbook", "arcane", ["magic_user_sleep"], data)
    entry = ClassEntry(class_id="magic_user", level=1, spellbook=[])
    cls = data.classes["magic_user"]
    new_entry, _src, ok = ss.copy_spell(
        entry, cls, data, RuleSet(advanced_spell_books=True), int_score=18,
        sources=[failed, other], instance_id=other.instance_id,
        spell_id="magic_user_sleep", rng=_FixedRng(1),
    )
    assert ok is True
    assert new_entry.spellbook == ["magic_user_sleep"]


def test_copy_requires_advanced_rule(data):
    src = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], data)
    entry = ClassEntry(class_id="magic_user", level=1)
    cls = data.classes["magic_user"]
    with pytest.raises(ss.SpellSourceError):
        ss.copy_spell(entry, cls, data, RuleSet(advanced_spell_books=False),
                      int_score=13, sources=[src], instance_id=src.instance_id,
                      spell_id="magic_user_sleep", rng=_FixedRng(1))


def test_copy_rejects_divine_source_and_known_and_uncastable(data):
    cls = data.classes["magic_user"]
    rs = RuleSet(advanced_spell_books=True)
    # divine source
    div = ss.new_spell_source("scroll", "divine", ["faerie_fire"], data)
    with pytest.raises(ss.SpellSourceError):
        ss.copy_spell(ClassEntry(class_id="magic_user", level=1), cls, data, rs,
                      13, [div], div.instance_id, "faerie_fire", rng=_FixedRng(1))
    # already known
    src = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], data)
    known = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_user_sleep"])
    with pytest.raises(ss.SpellSourceError):
        ss.copy_spell(known, cls, data, rs, 13, [src], src.instance_id,
                      "magic_user_sleep", rng=_FixedRng(1))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources.py -k copy -q`
Expected: FAIL — `AttributeError: ... has no attribute 'copy_spell'`.

- [ ] **Step 3: Implement**

Append to `aose/engine/spell_sources.py`:

```python
def copyable_spell_ids(source: SpellSource, entry: ClassEntry, cls: CharClass,
                       data: GameData) -> set[str]:
    """Spell ids in ``source`` an arcane caster may attempt to copy right now:
    arcane source, spell arcane-learnable for this class (on-list, accessible
    level, not already known — see ``spells.learnable_spells``), and not already
    marked ``copy_failed`` on this source.  Empty for non-arcane sources/casters."""
    if source.caster_type != "arcane":
        return set()
    learnable = {s.id for s in spell_engine.learnable_spells(entry, cls, data)}
    return {
        e.spell_id for e in source.entries
        if not e.copy_failed and e.spell_id in learnable
    }


def copy_spell(entry: ClassEntry, cls: CharClass, data: GameData, ruleset,
               int_score: int, sources: list[SpellSource], instance_id: str,
               spell_id: str, rng: Optional[random.Random] = None
               ) -> tuple[ClassEntry, list[SpellSource], bool]:
    """Attempt to copy ``spell_id`` from the source into the arcane caster's
    spellbook (Advanced rule only).

    Validates: advanced rule on; spell is currently copyable from this source
    (``copyable_spell_ids``).  Rolls 1d100 vs ``spells.copy_chance_for_int``:
      success -> append to ``entry.spellbook``; source unchanged.
      failure -> set ``copy_failed`` on this source's entry; spellbook unchanged.
    Returns ``(entry, sources, success)`` — neither input is mutated."""
    if not ruleset.advanced_spell_books:
        raise SpellSourceError("copying from a source requires the Advanced Spell Book rule")
    idx = _index(sources, instance_id)
    src = sources[idx]
    if spell_id not in copyable_spell_ids(src, entry, cls, data):
        raise SpellSourceError(
            f"{spell_id!r} cannot be copied from this source "
            "(wrong type, not castable yet, already known, or already failed here)"
        )
    chance = spell_engine.copy_chance_for_int(int_score)
    success = roll("1d100", rng) <= chance
    if success:
        new_entry = entry.model_copy(update={"spellbook": [*entry.spellbook, spell_id]})
        return new_entry, list(sources), True
    new_entries = [
        e.model_copy(update={"copy_failed": True}) if e.spell_id == spell_id else e
        for e in src.entries
    ]
    new_src = src.model_copy(update={"entries": new_entries})
    return entry, [*sources[:idx], new_src, *sources[idx + 1:]], False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/spell_sources.py tests/test_spell_sources.py
git commit -m "feat: copy_spell — Advanced-rule copy-from-source with per-source failure"
```

---

## Task 7: Scrolls of Protection catalog data

**Files:**
- Create: `data/equipment/scrolls.yaml`
- Test: `tests/test_data_loading.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_data_loading.py`:

```python
def test_protection_scrolls_loaded():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.models import MagicItem
    data = GameData.load(Path(__file__).parent.parent / "data")
    for sid in ("scroll_of_protection_from_elementals",
                "scroll_of_protection_from_lycanthropes",
                "scroll_of_protection_from_magic",
                "scroll_of_protection_from_undead"):
        item = data.items[sid]
        assert isinstance(item, MagicItem)
        assert item.magic is True
        assert item.category == "scrolls"
        assert item.description
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py::test_protection_scrolls_loaded -q`
Expected: FAIL — `KeyError: 'scroll_of_protection_from_elementals'`.

- [ ] **Step 3: Create the data file**

Create `data/equipment/scrolls.yaml`:

```yaml
- id: scroll_of_protection_from_elementals
  item_type: magic
  name: Scroll of Protection from Elementals
  category: scrolls
  cost_gp: 0
  magic: true
  equippable: false
  description: |-
    Reading the script aloud (in a non-magical language, usually Common) conjures
    a 10' radius circle of protection around the reader.

    No elemental may enter the circle. If the reader moves, the circle follows
    them. The circle does not prevent elementals from using magic or missile
    attacks against those within it. If anyone within the circle attacks an
    affected elemental in melee, the circle is broken.

    Duration: 2 turns, unless broken. One use only — the words disappear when read.

- id: scroll_of_protection_from_lycanthropes
  item_type: magic
  name: Scroll of Protection from Lycanthropes
  category: scrolls
  cost_gp: 0
  magic: true
  equippable: false
  description: |-
    Reading the script aloud conjures a 10' radius circle of protection around
    the reader. A number of lycanthropes are barred from entering, depending on
    their Hit Dice: 1–3 HD: 1d10 affected; 4–5 HD: 1d8 affected; 6+ HD: 1d4
    affected.

    If the reader moves, the circle follows them. The circle does not prevent
    lycanthropes from using magic or missile attacks against those within it. If
    anyone within the circle attacks an affected lycanthrope in melee, the circle
    is broken.

    Duration: 6 turns, unless broken. One use only — the words disappear when read.

- id: scroll_of_protection_from_magic
  item_type: magic
  name: Scroll of Protection from Magic
  category: scrolls
  cost_gp: 0
  magic: true
  equippable: false
  description: |-
    Reading the script aloud conjures a barrier that spells and spell-like
    effects (e.g. from magic items) cannot cross. The barrier prevents magic from
    entering the circle, but also from leaving it.

    Duration: 1d4 turns. Can only be dispelled by a wish. One use only — the
    words disappear when read.

- id: scroll_of_protection_from_undead
  item_type: magic
  name: Scroll of Protection from Undead
  category: scrolls
  cost_gp: 0
  magic: true
  equippable: false
  description: |-
    Reading the script aloud conjures a 10' radius circle of protection around
    the reader. A number of undead monsters are barred from entering, depending
    on their Hit Dice: 1–3 HD: 2d12 affected; 4–5 HD: 2d6 affected; 6+ HD: 1d6
    affected.

    If the reader moves, the circle follows them. The circle does not prevent
    undead from using magic or missile attacks against those within it. If anyone
    within the circle attacks an affected undead monster in melee, the circle is
    broken.

    Duration: 6 turns, unless broken. One use only — the words disappear when read.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py::test_protection_scrolls_loaded -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data/equipment/scrolls.yaml tests/test_data_loading.py
git commit -m "feat: Scrolls of Protection catalog data"
```

---

## Task 8: Sheet view — spell_sources_view + add options + hide learnable under advanced

**Files:**
- Modify: `aose/sheet/view.py`
- Test: `tests/test_spells.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_spells.py`:

```python
def test_learnable_hidden_under_advanced_rule():
    from aose.data.loader import GameData
    from aose.sheet.view import spells_view
    data = GameData.load(DATA_DIR)
    spec = _spec("magic_user", spellbook=["magic_user_magic_missile"], advanced=True)
    block = spells_view(spec, data)[0]
    assert block.can_learn is True          # forget still available
    assert block.learnable == []            # no free pick under advanced


def test_spell_sources_view_cast_and_copy_flags():
    from aose.data.loader import GameData
    from aose.engine import spell_sources as ss
    from aose.sheet.view import spell_sources_view
    data = GameData.load(DATA_DIR)
    scroll = ss.new_spell_source("scroll", "arcane",
                                 ["magic_user_magic_missile", "magic_user_sleep"], data)
    spec = _spec("magic_user", spellbook=["magic_user_magic_missile"], advanced=True)
    spec.spell_sources = [scroll]
    view = spell_sources_view(spec, data)
    assert len(view) == 1
    sv = view[0]
    assert sv.kind == "scroll"
    assert sv.arcane_class_id == "magic_user"
    by_id = {e.spell_id: e for e in sv.entries}
    # both castable (arcane caster, arcane scroll)
    assert by_id["magic_user_sleep"].can_cast is True
    # sleep is copyable (level 1, not known); magic_missile already known -> not copyable
    assert by_id["magic_user_sleep"].can_copy is True
    assert by_id["magic_user_magic_missile"].can_copy is False


def test_spell_sources_view_copy_hidden_under_standard_rule():
    from aose.data.loader import GameData
    from aose.engine import spell_sources as ss
    from aose.sheet.view import spell_sources_view
    data = GameData.load(DATA_DIR)
    scroll = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], data)
    spec = _spec("magic_user", advanced=False)
    spec.spell_sources = [scroll]
    sv = spell_sources_view(spec, data)[0]
    assert sv.entries[0].can_copy is False   # copy is advanced-only
    assert sv.entries[0].can_cast is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -k "spell_sources_view or learnable_hidden" -q`
Expected: FAIL — `ImportError: cannot import name 'spell_sources_view'`.

- [ ] **Step 3: Implement**

In `aose/sheet/view.py`:

(a) At the import for the spell engine, add the new engine module. Find the existing
`from aose.engine import spells as spell_engine` (used by `spells_view`) and add below it:

```python
from aose.engine import spell_sources as spell_source_engine
```

(b) Near the other view models (after `class SpellClassView`), add:

```python
class SpellSourceEntryView(BaseModel):
    spell_id: str
    name: str
    level: int
    copy_failed: bool
    can_cast: bool
    can_copy: bool


class SpellSourceView(BaseModel):
    instance_id: str
    kind: str                 # "spellbook" | "scroll"
    caster_type: str
    name: str                 # display label (falls back to a default)
    arcane_class_id: str | None  # the class whose book a Copy targets, if any
    entries: list[SpellSourceEntryView]


class SpellSourceOptionGroup(BaseModel):
    list_id: str | None       # set for arcane spellbook lists; None for scroll type buckets
    label: str
    caster_type: str
    spells: list[SpellEntryView]


class SpellSourceAddOptions(BaseModel):
    arcane_lists: list[SpellSourceOptionGroup]   # spellbook: one group per arcane list
    arcane_spells: list[SpellEntryView]          # scroll arcane: all arcane spells
    divine_spells: list[SpellEntryView]          # scroll divine: all divine spells
```

(c) In `spells_view`, change the `learnable=` argument so it is empty under the
advanced rule. Replace:

```python
            learnable=[_spell_entry(s) for s in spell_engine.learnable_spells(entry, cls, data)],
```

with:

```python
            learnable=(
                [] if spec.ruleset.advanced_spell_books
                else [_spell_entry(s) for s in spell_engine.learnable_spells(entry, cls, data)]
            ),
```

(d) Add the new view builder + options builder (place after `spells_view`):

```python
def _first_arcane_class_id(spec: CharacterSpec, data: GameData) -> str | None:
    for entry in spec.classes:
        cls = data.classes.get(entry.class_id)
        if cls is not None and spell_engine.caster_type_of(cls, data) == "arcane":
            return entry.class_id
    return None


def _default_source_name(source) -> str:
    if source.name:
        return source.name
    kind = "Spell Book" if source.kind == "spellbook" else "Scroll"
    n = len(source.entries)
    return f"{kind} ({n} spell{'s' if n != 1 else ''})"


def spell_sources_view(spec: CharacterSpec, data: GameData) -> list[SpellSourceView]:
    """One row per owned spell book / scroll, with per-spell cast/copy flags.

    ``can_cast`` (scrolls): the character has a class matching the scroll's caster
    type.  ``can_copy`` (advanced rule only): arcane caster, arcane source, spell
    castable-level + on-list + not known + not failed on this source."""
    arcane_cid = _first_arcane_class_id(spec, data)
    arcane_entry = None
    arcane_cls = None
    if arcane_cid is not None:
        arcane_entry = next(e for e in spec.classes if e.class_id == arcane_cid)
        arcane_cls = data.classes[arcane_cid]

    advanced = spec.ruleset.advanced_spell_books
    out: list[SpellSourceView] = []
    for source in spec.spell_sources:
        castable = spell_source_engine.can_cast_scroll(source, spec, data)
        copyable: set[str] = set()
        if advanced and arcane_entry is not None:
            copyable = spell_source_engine.copyable_spell_ids(
                source, arcane_entry, arcane_cls, data)
        entries: list[SpellSourceEntryView] = []
        for e in source.entries:
            spell = data.spells.get(e.spell_id)
            entries.append(SpellSourceEntryView(
                spell_id=e.spell_id,
                name=spell.name if spell else e.spell_id,
                level=spell.level if spell else 0,
                copy_failed=e.copy_failed,
                can_cast=castable,
                can_copy=e.spell_id in copyable,
            ))
        out.append(SpellSourceView(
            instance_id=source.instance_id,
            kind=source.kind,
            caster_type=source.caster_type,
            name=_default_source_name(source),
            arcane_class_id=arcane_cid,
            entries=entries,
        ))
    return out


def spell_source_add_options(data: GameData) -> SpellSourceAddOptions:
    """Selectable spells for the Add-document form, grouped for the UI."""
    def entry(s) -> SpellEntryView:
        return _spell_entry(s)

    arcane_list_ids = {lid for lid, sl in data.spell_lists.items() if sl.caster_type == "arcane"}
    divine_list_ids = {lid for lid, sl in data.spell_lists.items() if sl.caster_type == "divine"}

    arcane_lists: list[SpellSourceOptionGroup] = []
    for lid in sorted(arcane_list_ids):
        sl = data.spell_lists[lid]
        spells = sorted(
            (s for s in data.spells.values() if lid in s.spell_lists),
            key=lambda s: (s.level, s.name),
        )
        arcane_lists.append(SpellSourceOptionGroup(
            list_id=lid, label=sl.name, caster_type="arcane",
            spells=[entry(s) for s in spells],
        ))

    def bucket(list_ids) -> list[SpellEntryView]:
        spells = sorted(
            (s for s in data.spells.values() if set(s.spell_lists) & list_ids),
            key=lambda s: (s.level, s.name),
        )
        return [entry(s) for s in spells]

    return SpellSourceAddOptions(
        arcane_lists=arcane_lists,
        arcane_spells=bucket(arcane_list_ids),
        divine_spells=bucket(divine_list_ids),
    )
```

(e) Add `spell_sources` to `CharacterSheet`. In the `class CharacterSheet` definition,
add a field next to `spells`:

```python
    spell_sources: list[SpellSourceView] = []
```

(f) In `build_sheet`, where it sets `spells=spells_view(spec, data)`, add:

```python
        spell_sources=spell_sources_view(spec, data),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/sheet/view.py tests/test_spells.py
git commit -m "feat: spell_sources_view + add options; hide free learn under advanced"
```

---

## Task 9: Routes — add / remove / cast / copy

**Files:**
- Modify: `aose/web/routes.py`
- Test: `tests/test_spell_routes.py`

- [ ] **Step 1: Write the failing test + fix the obsolete one**

In `tests/test_spell_routes.py`, change `test_sheet_learn_route` so the free-learn
route is exercised under the **standard** rule (advanced now rejects it):

```python
def test_sheet_learn_route(client):
    _save_mu(client, advanced=False)
    r = client.post("/character/mu/spells/learn",
                    data={"class_id": "magic_user", "spell_id": "magic_user_magic_missile"})
    assert r.status_code == 303
    spec = load_character("mu", client._characters_dir)
    assert spec.classes[0].spellbook == ["magic_user_magic_missile"]
```

Add these new tests:

```python
def _add_scroll(client, spell_ids, caster_type="arcane", kind="scroll"):
    r = client.post("/character/mu/spell-sources/add",
                    data=[("kind", kind), ("caster_type", caster_type), ("name", "")]
                         + [("spell_ids", s) for s in spell_ids])
    assert r.status_code == 303
    return load_character("mu", client._characters_dir).spell_sources[-1]


def test_add_and_remove_spell_source(client):
    _save_mu(client)
    src = _add_scroll(client, ["magic_user_magic_missile", "magic_user_sleep"])
    assert {e.spell_id for e in src.entries} == {"magic_user_magic_missile", "magic_user_sleep"}
    client.post("/character/mu/spell-sources/remove", data={"instance_id": src.instance_id})
    assert load_character("mu", client._characters_dir).spell_sources == []


def test_cast_from_scroll_route(client):
    _save_mu(client)
    src = _add_scroll(client, ["magic_user_magic_missile", "magic_user_sleep"])
    r = client.post("/character/mu/spell-sources/cast",
                    data={"instance_id": src.instance_id,
                          "spell_id": "magic_user_magic_missile"})
    assert r.status_code == 303
    after = load_character("mu", client._characters_dir).spell_sources[0]
    assert [e.spell_id for e in after.entries] == ["magic_user_sleep"]


def test_cast_rejects_caster_type_mismatch(client):
    _save_mu(client)  # arcane caster
    src = _add_scroll(client, ["faerie_fire"], caster_type="divine")
    r = client.post("/character/mu/spell-sources/cast",
                    data={"instance_id": src.instance_id, "spell_id": "faerie_fire"})
    assert r.status_code == 400


def test_copy_route_success(client):
    _save_mu(client, advanced=True)  # INT 13 from _save_mu
    src = _add_scroll(client, ["magic_user_sleep"])
    # Force a guaranteed success by monkeypatching the roll via a very high INT
    # is not possible through the route, so we assert the spell-book changes for
    # at least one of the two outcomes by retrying is also not deterministic;
    # instead verify the route wiring: a copy attempt either learns the spell or
    # marks the source entry failed — never both, never neither.
    r = client.post("/character/mu/spell-sources/copy",
                    data={"instance_id": src.instance_id,
                          "class_id": "magic_user", "spell_id": "magic_user_sleep"})
    assert r.status_code == 303
    spec = load_character("mu", client._characters_dir)
    learned = "magic_user_sleep" in spec.classes[0].spellbook
    failed = spec.spell_sources[0].entries[0].copy_failed
    assert learned ^ failed   # exactly one outcome


def test_copy_route_rejected_under_standard_rule(client):
    _save_mu(client, advanced=False)
    src = _add_scroll(client, ["magic_user_sleep"])
    r = client.post("/character/mu/spell-sources/copy",
                    data={"instance_id": src.instance_id,
                          "class_id": "magic_user", "spell_id": "magic_user_sleep"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_routes.py -k "spell_source or cast or copy or add_and_remove" -q`
Expected: FAIL — 404/405 (routes do not exist yet).

- [ ] **Step 3: Implement the routes**

In `aose/web/routes.py`, add an import near the other engine imports at the top:

```python
from aose.engine import spell_sources as spell_source_engine
from aose.engine.spell_sources import SpellSourceError
from aose.models import Ability
```

(If `Ability` is already imported, don't duplicate it.)

Add these routes after the existing `/spells/clear` route (before the Rest section):

```python
# ── Spell books & scrolls on the live sheet ────────────────────────────────

@router.post("/character/{character_id}/spell-sources/add")
async def sheet_spell_source_add(
    request: Request, character_id: str,
    kind: str = Form(...), caster_type: str = Form(...),
    name: str = Form(""), list_id: str = Form(""),
):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    form = await request.form()
    spell_ids = form.getlist("spell_ids")
    try:
        spec.spell_sources = spell_source_engine.add_spell_source(
            spec.spell_sources, kind, caster_type, spell_ids, data,
            name=name, list_id=(list_id or None),
        )
    except (SpellSourceError, ValueError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/spell-sources/remove")
async def sheet_spell_source_remove(request: Request, character_id: str,
                                    instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.spell_sources = spell_source_engine.remove_spell_source(
            spec.spell_sources, instance_id)
    except SpellSourceError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/spell-sources/cast")
async def sheet_spell_source_cast(request: Request, character_id: str,
                                  instance_id: str = Form(...),
                                  spell_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    source = next((s for s in spec.spell_sources if s.instance_id == instance_id), None)
    if source is None:
        raise HTTPException(400, f"No spell document with id {instance_id!r}")
    if not spell_source_engine.can_cast_scroll(source, spec, data):
        raise HTTPException(400, "This character cannot cast from that scroll")
    try:
        spec.spell_sources = spell_source_engine.cast_from_scroll(
            spec.spell_sources, instance_id, spell_id)
    except SpellSourceError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/spell-sources/copy")
async def sheet_spell_source_copy(request: Request, character_id: str,
                                  instance_id: str = Form(...),
                                  class_id: str = Form(...),
                                  spell_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    idx = _find_class_entry(spec, class_id)
    eff_int = effective_abilities(spec, data)[Ability.INT]
    try:
        entry, sources, _success = spell_source_engine.copy_spell(
            spec.classes[idx], data.classes[class_id], data, spec.ruleset,
            eff_int, spec.spell_sources, instance_id, spell_id,
        )
    except SpellSourceError as e:
        raise HTTPException(400, str(e))
    spec.classes[idx] = entry
    spec.spell_sources = sources
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

Add the `effective_abilities` import if not already present at the top of `routes.py`:

```python
from aose.engine.magic import effective_abilities
```

(Check the existing imports first — `routes.py` may already import it; if so, skip.)

- [ ] **Step 4: Pass add options into the sheet context**

In the `character_sheet` GET handler (around line 138), add to the
`TemplateResponse` context dict, next to the other view data:

```python
            "spell_source_add_options": spell_source_add_options(game_data),
```

and import the builder at the top of `routes.py` (alongside `build_sheet`):

```python
from aose.sheet.view import build_sheet, spell_source_add_options
```

(If `build_sheet` is imported on its own line, extend that import.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_routes.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/web/routes.py tests/test_spell_routes.py
git commit -m "feat: spell-source routes (add/remove/cast/copy)"
```

---

## Task 10: Sheet template — Spell Books & Scrolls section + Add form

**Files:**
- Modify: `aose/web/templates/sheet.html`
- Create: `aose/web/static/spell_source_add.js`
- Test: `tests/test_spell_routes.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_spell_routes.py`:

```python
def test_sheet_renders_spell_sources_section(client):
    _save_mu(client, advanced=True)
    src = _add_scroll(client, ["magic_user_magic_missile"])
    r = client.get("/character/mu")
    assert r.status_code == 200
    assert "Spell Books &amp; Scrolls" in r.text or "Spell Books & Scrolls" in r.text
    assert "Magic Missile" in r.text
    # cast action present (arcane caster, arcane scroll)
    assert "/spell-sources/cast" in r.text
    # copy action present (advanced rule)
    assert "/spell-sources/copy" in r.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_routes.py::test_sheet_renders_spell_sources_section -q`
Expected: FAIL — section markup not present.

- [ ] **Step 3: Add the section to `sheet.html`**

Insert a new `<section>` immediately after the closing `</section>` of the Spells
section (after line ~499/500, after the `{% endif %}` that closes the spells block).
Use this markup:

```html
            <section class="section">
                <h2>Spell Books &amp; Scrolls</h2>
                {% for src in sheet.spell_sources %}
                <div class="spell-source">
                    <h3>{{ src.name }}
                        <span class="small muted">({{ src.kind }} · {{ src.caster_type }})</span>
                        <form method="post" class="no-print inline"
                              action="/character/{{ character_id }}/spell-sources/remove">
                            <input type="hidden" name="instance_id" value="{{ src.instance_id }}">
                            <button type="submit" class="link-button">remove</button>
                        </form>
                    </h3>
                    <ul>
                        {% for e in src.entries %}
                        <li {% if e.copy_failed %}class="muted" style="text-decoration: line-through"{% endif %}>
                            <strong>{{ e.name }}</strong> <span class="small muted">(L{{ e.level }})</span>
                            {% if e.copy_failed %}<span class="small muted">— copy failed here</span>{% endif %}
                            {% if e.can_cast %}
                            <form method="post" class="no-print inline"
                                  action="/character/{{ character_id }}/spell-sources/cast">
                                <input type="hidden" name="instance_id" value="{{ src.instance_id }}">
                                <input type="hidden" name="spell_id" value="{{ e.spell_id }}">
                                <button type="submit" class="link-button">cast</button>
                            </form>
                            {% endif %}
                            {% if e.can_copy and src.arcane_class_id %}
                            <form method="post" class="no-print inline"
                                  action="/character/{{ character_id }}/spell-sources/copy">
                                <input type="hidden" name="instance_id" value="{{ src.instance_id }}">
                                <input type="hidden" name="class_id" value="{{ src.arcane_class_id }}">
                                <input type="hidden" name="spell_id" value="{{ e.spell_id }}">
                                <button type="submit" class="link-button">copy to spell book</button>
                            </form>
                            {% endif %}
                        </li>
                        {% endfor %}
                    </ul>
                </div>
                {% else %}
                <p class="small muted">No spell books or scrolls yet.</p>
                {% endfor %}

                <details class="no-print">
                    <summary>Add a spell book or scroll</summary>
                    <form method="post" action="/character/{{ character_id }}/spell-sources/add"
                          id="spell-source-add-form">
                        <label>Type:
                            <select name="kind" id="ss-kind">
                                <option value="spellbook">Spell Book (arcane)</option>
                                <option value="scroll">Spell Scroll</option>
                            </select>
                        </label>
                        <label>Magic:
                            <select name="caster_type" id="ss-caster-type">
                                <option value="arcane">Arcane</option>
                                <option value="divine">Divine</option>
                            </select>
                        </label>
                        <label id="ss-list-label">Spell list:
                            <select name="list_id" id="ss-list">
                                {% for grp in spell_source_add_options.arcane_lists %}
                                <option value="{{ grp.list_id }}">{{ grp.label }}</option>
                                {% endfor %}
                            </select>
                        </label>
                        <label>Name (optional):
                            <input type="text" name="name" placeholder="e.g. Rival's grimoire">
                        </label>
                        <label>Spells (choose one or more):
                            <select name="spell_ids" id="ss-spells" multiple size="10">
                                {% for grp in spell_source_add_options.arcane_lists %}
                                {% for s in grp.spells %}
                                <option value="{{ s.id }}"
                                        data-caster="arcane" data-list="{{ grp.list_id }}">
                                    {{ s.name }} (L{{ s.level }})
                                </option>
                                {% endfor %}
                                {% endfor %}
                                {% for s in spell_source_add_options.divine_spells %}
                                <option value="{{ s.id }}" data-caster="divine" data-list="">
                                    {{ s.name }} (L{{ s.level }})
                                </option>
                                {% endfor %}
                            </select>
                        </label>
                        <button type="submit" class="primary">Add to inventory</button>
                    </form>
                </details>
            </section>
            <script src="/static/spell_source_add.js"></script>
```

Note: the `<select>` deliberately renders **both** arcane (one block per list,
tagged `data-list`) and divine options; the JS hides options that don't match the
chosen kind/type/list. The server re-validates the final selection, so the form is
correct even with JS disabled (the user just sees all options).

- [ ] **Step 4: Create the filter JS**

Create `aose/web/static/spell_source_add.js`:

```javascript
// Progressive enhancement for the Add-spell-document form: show only the spell
// <option>s that match the chosen kind / caster type / list. The server
// re-validates, so this is purely a usability filter.
(function () {
  var form = document.getElementById("spell-source-add-form");
  if (!form) return;
  var kind = document.getElementById("ss-kind");
  var caster = document.getElementById("ss-caster-type");
  var list = document.getElementById("ss-list");
  var listLabel = document.getElementById("ss-list-label");
  var spells = document.getElementById("ss-spells");

  function refresh() {
    var isBook = kind.value === "spellbook";
    // Spell books are always arcane and pick from a single list.
    caster.disabled = isBook;
    if (isBook) caster.value = "arcane";
    listLabel.style.display = isBook ? "" : "none";
    var wantCaster = isBook ? "arcane" : caster.value;
    var wantList = isBook ? list.value : null;
    Array.prototype.forEach.call(spells.options, function (opt) {
      var ok = opt.getAttribute("data-caster") === wantCaster;
      if (ok && wantList !== null) ok = opt.getAttribute("data-list") === wantList;
      opt.hidden = !ok;
      if (!ok) opt.selected = false;
    });
  }

  kind.addEventListener("change", refresh);
  caster.addEventListener("change", refresh);
  list.addEventListener("change", refresh);
  refresh();
})();
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_routes.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/web/templates/sheet.html aose/web/static/spell_source_add.js tests/test_spell_routes.py
git commit -m "feat: Spell Books & Scrolls sheet section + Add form"
```

---

## Task 11: Docs + full suite

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run the full test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing `pytest-current` PermissionError — known Windows quirk).

- [ ] **Step 2: Manual smoke test (optional but recommended)**

Run: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
- Open a magic-user character with the Advanced Spell Book rule on.
- Add a scroll with two arcane spells; confirm Cast removes one and Copy either
  learns it (appears under Spells → Known) or strikes it through ("copy failed here").
- Toggle the rule off on another character; confirm Copy actions disappear and
  Cast remains.

- [ ] **Step 3: Update CLAUDE.md**

Add a "Current state" bullet near the top of the dated section in `CLAUDE.md`:

```markdown
Spell books & scrolls just landed (11-task plan).

- **Spell books & scrolls** — owned documents with custom contents, modelled as a
  per-instance `SpellSource` (`kind` spellbook|scroll, `caster_type`, `entries`
  each with a `copy_failed` flag) on `CharacterSpec.spell_sources`. Cycle-free
  `aose/engine/spell_sources.py` owns create/add/remove, `cast_from_scroll`
  (expends one spell; empties → document dropped; gated by caster-type match via
  `can_cast_scroll`), and `copy_spell` (Advanced-rule only; rolls 1d100 vs
  `spells.copy_chance_for_int(effective INT)`; **failure is recorded on the source
  entry, never on the character**, so the same spell stays copyable from another
  source). `spells.learn()` now refuses free adds under `advanced_spell_books`
  (copy-only); standard rule keeps free learn-on-level-up. Sheet gains a
  "Spell Books & Scrolls" section + `/spell-sources/{add,remove,cast,copy}`
  (sheet-only, Add-only). Protection scrolls (4) added as `MagicItem` catalog data
  in `data/equipment/scrolls.yaml` (`category: scrolls`, no Use action — matches
  potions). Cursed scrolls / treasure maps out of scope. Spec/plan:
  `docs/superpowers/{specs,plans}/2026-06-03-spell-books-and-scrolls*`.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: note spell books & scrolls feature in CLAUDE.md"
```

---

## Self-Review Notes (for the implementer)

- **Spec coverage:** unified `SpellSource` (Task 1) ✓; copy % table (Task 2) ✓;
  copy-only-under-advanced + standard free-learn preserved (Task 3) ✓;
  create/add/remove (Task 4) ✓; scroll casting + caster-type gate (Task 5) ✓;
  copy mechanic with per-source failure (Task 6) ✓; protection scrolls data
  (Task 7) ✓; sheet view + add options + hidden learnable (Task 8) ✓; routes
  (Task 9) ✓; UI section + Add form (Task 10) ✓; docs (Task 11) ✓.
- **Failure-storage invariant:** `copy_spell` only ever writes `copy_failed` onto a
  `SpellSource` entry; the spellbook is touched solely on success. No
  character-global "cannot learn" state exists. Verified by
  `test_copy_failure_burns_only_this_source` and `test_copy_same_spell_from_a_second_source`.
- **Type consistency:** engine `copyable_spell_ids` / `can_cast_scroll` /
  `cast_from_scroll` / `copy_spell` names match their use in `sheet/view.py`
  (`spell_source_engine.*`) and `routes.py`. View models `SpellSourceView` /
  `SpellSourceEntryView` fields (`can_cast`, `can_copy`, `arcane_class_id`) match
  the template and the Task-8 tests.
- **No migration:** `spell_sources` defaults to `[]`; app is not deployed (per
  project memory), so old saves load unchanged.
```
