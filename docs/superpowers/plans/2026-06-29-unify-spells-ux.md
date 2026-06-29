# Unify Spells UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render every castable spell — class spellbook/slots, scrolls, and spell-backed innate abilities — in one list per caster type (arcane/divine), each row through one common macro with a source label shown only when the list is ambiguous.

**Architecture:** A new `spell_lists_view` in `aose/sheet/view.py` assembles one `SpellListBlock` per caster type from three sources, producing a single unified `SpellRow` model. Two Jinja macros (`spell_row`, `spell_modal`) render every row and its action modal identically. No engine changes. The per-class "Manage spells" drawer, mental powers, and non-spell innate abilities are untouched.

**Tech Stack:** Python 3 / Pydantic v2 / FastAPI / Jinja2. Tests with pytest. Run via `.venv\Scripts\python.exe`.

**Spec:** `docs/superpowers/specs/2026-06-29-unify-spells-ux-design.md`

---

## File Structure

- `aose/sheet/view.py` — add `SpellRow`, `SpellListLevel`, `SpellListBlock` models; add `spell_lists_view` + helpers `_class_spell_rows`, `_scroll_spell_rows`, `_routed_innate`; change `innate_view` to skip routed abilities; add `spell_lists` field to `CharacterSheet` and populate in `build_sheet`. Later remove `spellbook_view`, `_scroll_rows_by_level`, and the old `SpellbookBlock`/`SpellbookLevelGroup`/`SpellbookRow`/`ScrollSpellRow` models + the `spellbook` field.
- `aose/web/templates/_spells.html` — **new** macro file: `spell_row(row, show_labels)` and `spell_modal(row)`.
- `aose/web/templates/sheet.html` — swap the per-class spell list section + per-class/scroll modal loops to iterate `sheet.spell_lists` via the macros.
- `aose/web/static/sheet.css` — add `.src-tag` style.
- `tests/test_spell_lists_view.py` — **new** unit tests for the assembly.
- `tests/test_spellbook_view.py` — **deleted** in the final task (replaced by the above).
- `tests/test_innate_view.py` — update `test_innate_block_on_sheet` (spell-backed innate now routes into the arcane list).

Reference details (already verified in the codebase):
- `caster_type_of(cls, data)` → `"arcane" | "divine" | "mental" | None` (`aose/engine/spells.py`).
- `spell_source_engine._spell_caster_type(spell, data)` → `"arcane" | "divine" | "mental" | None` based on the spell's lists.
- `spell_source_engine.scroll_cast_block_reason(source, spec, data)` → `None` when castable, else a short reason string.
- `_innate_abilities(spec, data)` (imported in view.py as `_innate_abilities`) yields objects with `.id .name .text .source .spell_id .max_uses .used .remaining`.
- `spell_card(spell, reversed=False)` and `_slot_display_name(spell, reversed)` already exist in `view.py`.
- The pip markup uses `<i class="pip"></i>` (ready), `<i class="pip spent"></i>` (spent), `<i class="pip locked-pip"></i>` (locked). CSS classes `.spell`, `.snm`, `.pips`, `.known-tag`, `.scroll-tag`, `.allspent`, `.locked`, `.cast-legend`, `.lvl-head` already exist.

---

## Task 1: Unified models + class-spell assembly

**Files:**
- Modify: `aose/sheet/view.py` (add models near line 318; add functions near line 928; add `spell_lists` field to `CharacterSheet` ~line 454; populate in `build_sheet` ~line 1961)
- Test: `tests/test_spell_lists_view.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_spell_lists_view.py`:

```python
from pathlib import Path

from aose.data.loader import GameData
from aose.engine import spells as se
from aose.models import CharacterSpec, ClassEntry
from aose.sheet.view import spell_lists_view

DATA = GameData.load(Path(__file__).parent.parent / "data")

MM = "magic_user_magic_missile"
SLEEP = "magic_user_sleep"
SHIELD = "magic_user_shield"


def _abilities():
    return {"STR": 9, "INT": 16, "WIS": 13, "DEX": 12, "CON": 10, "CHA": 9}


def _solo_mu():
    e = ClassEntry(class_id="magic_user", level=3, hp_rolls=[4, 3, 2],
                   spellbook=[MM, SLEEP, SHIELD])
    cls = DATA.classes["magic_user"]
    e = se.assign_slot(e, cls, DATA, level=1, spell_id=MM)
    e = se.assign_slot(e, cls, DATA, level=1, spell_id=MM)
    e = se.cast_slot(e, 0)
    return CharacterSpec(name="M", abilities=_abilities(), race_id="human",
                         classes=[e], alignment="neutral")


def test_solo_arcane_single_block_no_labels():
    blocks = spell_lists_view(_solo_mu(), DATA)
    assert [b.caster_type for b in blocks] == ["arcane"]
    block = blocks[0]
    assert block.show_labels is False               # single source → no tags
    lvl1 = next(g for g in block.levels if g.level == 1)
    mm = next(r for r in lvl1.rows if r.spell_id == MM)
    assert (mm.ready, mm.spent) == (1, 1)
    assert mm.source_kind == "class" and mm.source_label == "Magic User"
    assert mm.modal_id == f"modal-spell-magic_user-{MM}-n"


def test_multiclass_same_type_merges_with_labels():
    mu = ClassEntry(class_id="magic_user", level=3, hp_rolls=[4, 3, 2],
                    spellbook=[MM])
    ill = ClassEntry(class_id="illusionist", level=3, hp_rolls=[4, 3, 2],
                     spellbook=["illusionist_phantasmal_force"])
    spec = CharacterSpec(name="X", abilities=_abilities(), race_id="human",
                         classes=[mu, ill], alignment="neutral")
    blocks = spell_lists_view(spec, DATA)
    arcane = [b for b in blocks if b.caster_type == "arcane"]
    assert len(arcane) == 1                          # merged into one block
    block = arcane[0]
    assert block.show_labels is True
    labels = {r.source_label for lvl in block.levels for r in lvl.rows}
    assert {"Magic User", "Illusionist"} <= labels
```

(If `illusionist` or `illusionist_phantasmal_force` is not present in `data/`, pick any second arcane class + one of its known book spells — confirm with `grep -rl "caster_type: arcane" data/spell_lists.yaml` and the class files.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_lists_view.py -q`
Expected: FAIL — `ImportError: cannot import name 'spell_lists_view'`.

- [ ] **Step 3: Add the models**

In `aose/sheet/view.py`, after the existing `ScrollSpellRow` / `SpellbookBlock` block (~line 358), add:

```python
class SpellRow(BaseModel):
    # display
    spell_id: str
    name: str
    display_name: str
    level: int
    reversible: bool = False
    reversed: bool = False
    description: str = ""
    detail: DetailCard | None = None
    # provenance
    source_label: str
    source_kind: str            # "class" | "scroll" | "innate"
    modal_id: str
    # pips (unified): class = unspent/spent slots; scroll = charges/0; innate = remaining/used
    ready: int = 0
    spent: int = 0
    known: bool = False         # class arcane book spell, not memorised
    castable: bool = True
    block_reason: str | None = None
    # action payloads consumed by the modal macro (source-specific)
    class_id: str | None = None
    ready_slots: list[int] = Field(default_factory=list)
    spent_slots: list[int] = Field(default_factory=list)
    scroll_instance_id: str | None = None
    ability_id: str | None = None
    max_uses: int = 0
    used: int = 0
    ability_text: str = ""
    spell_detail: DetailCard | None = None   # innate: nested spell card for its modal


class SpellListLevel(BaseModel):
    level: int                  # 0 == Cantrips
    cap: int = 0                # summed memorisable slots at this level (class)
    used: int = 0              # summed filled slots at this level (class)
    rows: list[SpellRow] = Field(default_factory=list)


class SpellListBlock(BaseModel):
    caster_type: str            # "arcane" | "divine"
    show_labels: bool = False   # block draws from 2+ distinct source labels
    levels: list[SpellListLevel]
```

- [ ] **Step 4: Add the class-spell helper and the view function**

In `aose/sheet/view.py`, immediately before `def spellbook_view(` (~line 928), add:

```python
def _class_spell_rows(entry, cls, data, ruleset, ctype):
    """(rows_by_level, caps_by_level, used_by_level) for one casting class."""
    caps = spell_engine.memorizable_slots(entry, cls, data, ruleset)
    known = spell_engine.known_spells(entry, cls, data, ruleset)
    known_ids = {s.id for s in known}
    ready: dict[tuple[int, str, bool], int] = {}
    spent: dict[tuple[int, str, bool], int] = {}
    ready_idx: dict[tuple[int, str, bool], list[int]] = {}
    spent_idx: dict[tuple[int, str, bool], list[int]] = {}
    used_by_level: dict[int, int] = {}
    for i, slot in enumerate(entry.slots):
        if slot.spell_id is None:
            continue
        key = (slot.level, slot.spell_id, slot.reversed)
        if slot.spent:
            spent[key] = spent.get(key, 0) + 1
            spent_idx.setdefault(key, []).append(i)
        else:
            ready[key] = ready.get(key, 0) + 1
            ready_idx.setdefault(key, []).append(i)
        used_by_level[slot.level] = used_by_level.get(slot.level, 0) + 1

    def _row(spell, level: int, rev: bool) -> SpellRow:
        key = (level, spell.id, rev)
        return SpellRow(
            spell_id=spell.id, name=spell.name,
            display_name=_slot_display_name(spell, rev),
            level=spell.level, reversible=spell.reversible, reversed=rev,
            description=spell.description, detail=spell_card(spell, reversed=rev),
            source_label=cls.name, source_kind="class",
            modal_id=f"modal-spell-{entry.class_id}-{spell.id}-{'r' if rev else 'n'}",
            known=spell.id in known_ids,
            ready=ready.get(key, 0), spent=spent.get(key, 0),
            class_id=entry.class_id,
            ready_slots=ready_idx.get(key, []), spent_slots=spent_idx.get(key, []),
        )

    rows_by_level: dict[int, list[SpellRow]] = {}
    for level in sorted(caps):
        rows: list[SpellRow] = []
        memo_keys = {(sid, rev)
                     for (lv, sid, rev) in list(ready) + list(spent) if lv == level}
        if ctype == "arcane":
            level_known = [s for s in known if s.level == level]
            known_at = {s.id for s in level_known}
            for s in level_known:
                rows.append(_row(s, level, False))
            for (sid, rev) in sorted(memo_keys):
                if not rev and sid in known_at:
                    continue
                s = data.spells.get(sid)
                if s is not None:
                    rows.append(_row(s, level, rev))
        else:
            for (sid, rev) in sorted(memo_keys):
                s = data.spells.get(sid)
                if s is not None:
                    rows.append(_row(s, level, rev))
        rows_by_level[level] = rows
    return rows_by_level, dict(caps), used_by_level


def spell_lists_view(spec: CharacterSpec, data: GameData) -> list[SpellListBlock]:
    """One block per caster type (arcane/divine), merging every casting class,
    every scroll, and every spell-backed innate ability into a single per-level
    list of unified SpellRows. Source labels are shown only when a block draws
    from 2+ distinct sources."""
    ruleset = spec.ruleset
    rows: dict[str, dict[int, list[SpellRow]]] = {}
    caps: dict[str, dict[int, int]] = {}
    used: dict[str, dict[int, int]] = {}
    labels: dict[str, set[str]] = {}

    def _bucket(ctype: str) -> None:
        rows.setdefault(ctype, {})
        caps.setdefault(ctype, {})
        used.setdefault(ctype, {})
        labels.setdefault(ctype, set())

    # 1) classes
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        ctype = spell_engine.caster_type_of(cls, data)
        if ctype not in ("arcane", "divine"):
            continue
        _bucket(ctype)
        rbl, cbl, ubl = _class_spell_rows(entry, cls, data, ruleset, ctype)
        for lv, rws in rbl.items():
            rows[ctype].setdefault(lv, []).extend(rws)
            if rws:
                labels[ctype].add(cls.name)
        for lv, c in cbl.items():
            caps[ctype][lv] = caps[ctype].get(lv, 0) + c
        for lv, u in ubl.items():
            used[ctype][lv] = used[ctype].get(lv, 0) + u

    # 2) scrolls (Task 2 fills _scroll_spell_rows; for now it returns {} and is a no-op)
    for ctype in ("arcane", "divine"):
        for lv, rws in _scroll_spell_rows(spec, data, ctype).items():
            if not rws:
                continue
            _bucket(ctype)
            rows[ctype].setdefault(lv, []).extend(rws)
            for r in rws:
                labels[ctype].add(r.source_label)

    # 3) spell-backed innate (Task 3 fills _routed_innate; for now returns [])
    for ab, ctype, spell in _routed_innate(spec, data):
        _bucket(ctype)
        rows[ctype].setdefault(spell.level, []).append(SpellRow(
            spell_id=ab.spell_id, name=spell.name, display_name=spell.name,
            level=spell.level, description=spell.description,
            detail=spell_card(spell),
            source_label=ab.source, source_kind="innate",
            modal_id=f"modal-innate-{ab.id}",
            ready=ab.remaining, spent=ab.used,
            ability_id=ab.id, max_uses=ab.max_uses, used=ab.used,
            ability_text=ab.text, spell_detail=spell_card(spell),
        ))
        labels[ctype].add(ab.source)

    out: list[SpellListBlock] = []
    for ctype in ("arcane", "divine"):
        if ctype not in rows:
            continue
        all_levels = set(rows[ctype]) | set(caps[ctype])
        levels: list[SpellListLevel] = []
        for lv in sorted(all_levels):
            lvl_rows = sorted(rows[ctype].get(lv, []),
                              key=lambda r: (r.name, r.source_label, r.reversed))
            levels.append(SpellListLevel(
                level=lv, cap=caps[ctype].get(lv, 0),
                used=used[ctype].get(lv, 0), rows=lvl_rows))
        out.append(SpellListBlock(
            caster_type=ctype, show_labels=len(labels[ctype]) > 1, levels=levels))
    return out
```

- [ ] **Step 5: Add temporary stubs so the file imports**

`spell_lists_view` references `_scroll_spell_rows` and `_routed_innate` (built in Tasks 2-3). Add minimal stubs immediately above `spell_lists_view` so Task 1 runs green:

```python
def _scroll_spell_rows(spec, data, ctype):
    return {}


def _routed_innate(spec, data):
    return []
```

- [ ] **Step 6: Wire into CharacterSheet + build_sheet**

In `CharacterSheet` (~line 454), add alongside `spellbook`:

```python
    spell_lists: list[SpellListBlock] = Field(default_factory=list)
```

In `build_sheet` (~line 1961), add alongside `spellbook=spellbook_view(spec, data),`:

```python
        spell_lists=spell_lists_view(spec, data),
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_lists_view.py -q`
Expected: PASS (both tests).

- [ ] **Step 8: Commit**

```bash
git add aose/sheet/view.py tests/test_spell_lists_view.py
git commit -m "feat(spells): per-caster-type spell list assembly (class rows)"
```

---

## Task 2: Fold scrolls into the unified lists

**Files:**
- Modify: `aose/sheet/view.py` (replace the `_scroll_spell_rows` stub)
- Test: `tests/test_spell_lists_view.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_spell_lists_view.py`:

```python
from aose.engine import spell_sources as ss

CURE = "cleric_cure_light_wounds"


def test_scroll_rows_join_caster_type_block_with_labels():
    e = ClassEntry(class_id="cleric", level=1, hp_rolls=[6])
    spec = CharacterSpec(
        name="C", abilities={"STR": 9, "INT": 10, "WIS": 16, "DEX": 12,
                             "CON": 10, "CHA": 9},
        race_id="human", classes=[e], alignment="neutral")
    spec.spell_sources = [
        ss.new_spell_source("scroll", "divine", [CURE, CURE, CURE], DATA,
                            language="Common"),
        ss.new_spell_source("scroll", "divine", [CURE], DATA, language="Common"),
    ]
    blocks = spell_lists_view(spec, DATA)
    divine = next(b for b in blocks if b.caster_type == "divine")
    assert divine.show_labels is True               # class + 2 scrolls = 3 labels
    lvl1 = next(g for g in divine.levels if g.level == 1)
    scrolls = [r for r in lvl1.rows if r.source_kind == "scroll"]
    assert sorted(r.ready for r in scrolls) == [1, 3]   # charges → ready pips
    assert all(r.castable for r in scrolls)
    assert {r.source_label for r in scrolls} == {"scroll 1", "scroll 2"}
    assert all(r.modal_id.startswith("modal-scroll-") for r in scrolls)


def test_arcane_scroll_row_locked_until_read():
    e = ClassEntry(class_id="magic_user", level=1, spellbook=[])
    spec = CharacterSpec(
        name="M", abilities={"STR": 9, "INT": 13, "WIS": 9, "DEX": 12,
                             "CON": 10, "CHA": 9},
        race_id="human", classes=[e], alignment="neutral")
    spec.spell_sources = [
        ss.new_spell_source("scroll", "arcane", ["magic_user_fire_ball"], DATA)]
    blocks = spell_lists_view(spec, DATA)
    arcane = next(b for b in blocks if b.caster_type == "arcane")
    lvl3 = next(g for g in arcane.levels if g.level == 3)
    row = next(r for r in lvl3.rows if r.spell_id == "magic_user_fire_ball")
    assert row.castable is False
    assert row.block_reason == "needs Read Magic"
    assert row.source_kind == "scroll"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_lists_view.py -q`
Expected: FAIL — scroll rows absent (`StopIteration`/empty), `show_labels` False.

- [ ] **Step 3: Replace the `_scroll_spell_rows` stub**

```python
def _scroll_spell_rows(spec: CharacterSpec, data: GameData,
                       ctype: str) -> dict[int, list[SpellRow]]:
    """Castable-by-type scrolls turned into per-level SpellRows (one per
    scroll+spell). Charges become ready pips; not-yet-castable scrolls are
    locked with a reason."""
    by_level: dict[int, list[SpellRow]] = {}
    scroll_n = 0
    for source in spec.spell_sources:
        if source.kind != "scroll" or source.caster_type != ctype:
            continue
        scroll_n += 1
        label = source.name or f"scroll {scroll_n}"
        reason = spell_source_engine.scroll_cast_block_reason(source, spec, data)
        counts: dict[str, int] = {}
        order: list[str] = []
        for e in source.entries:
            if e.spell_id not in counts:
                order.append(e.spell_id)
            counts[e.spell_id] = counts.get(e.spell_id, 0) + 1
        for sid in order:
            spell = data.spells.get(sid)
            if spell is None:
                continue
            by_level.setdefault(spell.level, []).append(SpellRow(
                spell_id=sid, name=spell.name, display_name=spell.name,
                level=spell.level, description=spell.description,
                detail=spell_card(spell),
                source_label=label, source_kind="scroll",
                modal_id=f"modal-scroll-{source.instance_id}-{sid}",
                ready=counts[sid], spent=0,
                castable=reason is None, block_reason=reason,
                scroll_instance_id=source.instance_id,
            ))
    return by_level
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_lists_view.py -q`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add aose/sheet/view.py tests/test_spell_lists_view.py
git commit -m "feat(spells): fold scrolls into per-caster-type spell lists"
```

---

## Task 3: Route spell-backed innate; keep non-spell innate separate

**Files:**
- Modify: `aose/sheet/view.py` (replace `_routed_innate` stub; update `innate_view`)
- Test: `tests/test_spell_lists_view.py`; `tests/test_innate_view.py` (update one test)

- [ ] **Step 1: Write the failing test (routing)**

Append to `tests/test_spell_lists_view.py`:

```python
from aose.models import Ability, CharClass, ClassFeature, DailyUses


def _data_with_innate():
    data = GameData.load(Path(__file__).parent.parent / "data")
    data.classes["zinn"] = CharClass(
        id="zinn", name="ZInn", prime_requisites=[Ability.STR], hit_die="1d8",
        weapons_allowed="all", armor_allowed="all", shields_allowed=True,
        progression=data.classes["fighter"].progression,
        features=[ClassFeature(id="breath", name="Breath", text="3/day",
                  daily_uses=DailyUses(per_day=3),
                  spell_id="magic_user_magic_missile")],
    )
    return data


def test_spell_backed_innate_routes_into_arcane_list():
    data = _data_with_innate()
    spec = CharacterSpec(name="T", abilities={a: 10 for a in Ability},
                         race_id="human", alignment="neutral",
                         classes=[ClassEntry(class_id="zinn", level=1)],
                         innate_uses={"breath": 1})
    blocks = spell_lists_view(spec, data)
    arcane = next(b for b in blocks if b.caster_type == "arcane")
    rows = [r for lvl in arcane.levels for r in lvl.rows
            if r.source_kind == "innate"]
    assert len(rows) == 1
    row = rows[0]
    assert row.spell_id == "magic_user_magic_missile"
    assert row.ability_id == "breath"
    assert (row.ready, row.spent) == (2, 1)         # 3/day, 1 used → 2 ready
    assert row.modal_id == "modal-innate-breath"
    assert row.source_label == "ZInn"


def test_non_spell_innate_stays_out_of_spell_lists():
    data = GameData.load(Path(__file__).parent.parent / "data")
    data.classes["zinn2"] = CharClass(
        id="zinn2", name="ZInn2", prime_requisites=[Ability.STR], hit_die="1d8",
        weapons_allowed="all", armor_allowed="all", shields_allowed=True,
        progression=data.classes["fighter"].progression,
        features=[ClassFeature(id="spores", name="Spores", text="1/day",
                  daily_uses=DailyUses(per_day=1))],   # no spell_id
    )
    spec = CharacterSpec(name="T", abilities={a: 10 for a in Ability},
                         race_id="human", alignment="neutral",
                         classes=[ClassEntry(class_id="zinn2", level=1)])
    assert spell_lists_view(spec, data) == []         # no spell-backed source
```

(`zinn` source_label is `"ZInn"` — the innate ability's `.source`. If `_innate_abilities` reports the source differently in this synthetic setup, assert on the actual value; the important checks are routing, pips, and modal_id.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_lists_view.py -q`
Expected: FAIL — no innate rows (stub returns `[]`).

- [ ] **Step 3: Replace the `_routed_innate` stub**

```python
def _routed_innate(spec: CharacterSpec, data: GameData):
    """(innate_ability, caster_type, spell) for innate abilities whose spell maps
    to an arcane/divine list. Non-spell innate (and spells on no known list) are
    left to innate_view."""
    out = []
    for ab in _innate_abilities(spec, data):
        if not ab.spell_id:
            continue
        spell = data.spells.get(ab.spell_id)
        if spell is None:
            continue
        ctype = spell_source_engine._spell_caster_type(spell, data)
        if ctype in ("arcane", "divine"):
            out.append((ab, ctype, spell))
    return out
```

- [ ] **Step 4: Update `innate_view` to skip routed abilities**

Replace the body of `innate_view` (~line 1053) with:

```python
def innate_view(spec: CharacterSpec, data: GameData) -> list[InnateAbilityRow]:
    routed = {ab.id for ab, _ctype, _spell in _routed_innate(spec, data)}
    rows: list[InnateAbilityRow] = []
    for ab in _innate_abilities(spec, data):
        if ab.id in routed:
            continue
        detail = spell_card(data.spells[ab.spell_id]) if ab.spell_id in data.spells else None
        rows.append(InnateAbilityRow(
            id=ab.id, name=ab.name, text=ab.text, source=ab.source,
            max_uses=ab.max_uses, used=ab.used, remaining=ab.remaining,
            spell_detail=detail,
        ))
    return rows
```

- [ ] **Step 5: Update the stale innate test**

In `tests/test_innate_view.py`, `test_innate_block_on_sheet` asserts the spell-backed `breath` ability appears in `sheet.innate_abilities`. It now routes into the arcane spell list. Replace that test with:

```python
def test_spell_backed_innate_routes_to_spell_list():
    spec = CharacterSpec(name="T", abilities={a: 10 for a in Ability},
                         race_id="human", alignment="neutral",
                         classes=[ClassEntry(class_id="zinn", level=1)],
                         innate_uses={"breath": 1})
    sheet = build_sheet(spec, _data())
    assert sheet.innate_abilities == []             # routed out of the innate section
    arcane = next(b for b in sheet.spell_lists if b.caster_type == "arcane")
    rows = [r for lvl in arcane.levels for r in lvl.rows
            if r.source_kind == "innate"]
    assert len(rows) == 1 and rows[0].ability_id == "breath"
    assert rows[0].max_uses == 3 and rows[0].ready == 2
```

- [ ] **Step 6: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_lists_view.py tests/test_innate_view.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add aose/sheet/view.py tests/test_spell_lists_view.py tests/test_innate_view.py
git commit -m "feat(spells): route spell-backed innate into caster-type lists"
```

---

## Task 4: Common macros + rewire the sheet template

**Files:**
- Create: `aose/web/templates/_spells.html`
- Modify: `aose/web/templates/sheet.html` (import macros; replace list section ~lines 281-336; replace class+scroll modal loops ~lines 851-920)
- Modify: `aose/web/static/sheet.css` (add `.src-tag`)

This is a UI task — verify via the preview tools, not pytest.

- [ ] **Step 1: Create the macro file**

Create `aose/web/templates/_spells.html`:

```jinja
{% macro spell_row(row, show_labels) %}
<div class="spell{% if row.ready == 0 and row.spent > 0 %} allspent{% endif %}{% if not row.castable %} locked{% endif %}"
     data-modal="{{ row.modal_id }}">
  <span class="snm">{{ row.display_name }}{% if show_labels %} <em class="src-tag">{{ row.source_label }}</em>{% endif %}</span>
  {% if row.ready > 0 or row.spent > 0 %}
  <span class="pips"{% if row.block_reason %} title="{{ row.block_reason }}"{% endif %}>
    {% for _ in range(row.ready) %}<i class="pip{% if not row.castable %} locked-pip{% endif %}"></i>{% endfor %}
    {% for _ in range(row.spent) %}<i class="pip spent"></i>{% endfor %}
  </span>
  {% elif row.known %}
  <span class="known-tag">known</span>
  {% endif %}
  {% if not row.castable and row.block_reason %}
  <span class="hint scroll-reason">{{ row.block_reason }}</span>
  {% endif %}
</div>
{% endmacro %}


{% macro spell_modal(row) %}
<div class="overlay modal" id="{{ row.modal_id }}" role="dialog" aria-label="{{ row.display_name }}">
  <div class="ov-head">
    <h3>{{ row.display_name }}{% if row.source_kind != "class" %} <span style="font-weight:400;font-size:.75em;color:var(--faint)">{{ row.source_label }}</span>{% endif %}</h3>
    <button class="x" data-close>×</button>
  </div>
  <div class="ov-body">
    <div class="prose">{{ (row.ability_text if row.source_kind == "innate" else row.description) | markdown | safe }}</div>

    {% if row.source_kind == "class" %}
      {% if row.ready_slots or row.spent_slots %}
      <div class="row-actions">
        {% if row.ready_slots %}
        <form method="post" action="/character/{{ character_id }}/spells/cast" style="display:inline">
          <input type="hidden" name="class_id" value="{{ row.class_id }}">
          <input type="hidden" name="slot_index" value="{{ row.ready_slots[0] }}">
          <button class="btn solid" type="submit" data-close>Cast</button>
        </form>
        {% endif %}
        {% if row.spent_slots %}
        <form method="post" action="/character/{{ character_id }}/spells/restore" style="display:inline">
          <input type="hidden" name="class_id" value="{{ row.class_id }}">
          <input type="hidden" name="slot_index" value="{{ row.spent_slots[0] }}">
          <button class="btn" type="submit" data-close>Restore</button>
        </form>
        {% endif %}
        <form method="post" action="/character/{{ character_id }}/spells/clear" style="display:inline">
          <input type="hidden" name="class_id" value="{{ row.class_id }}">
          <input type="hidden" name="slot_index" value="{{ (row.ready_slots + row.spent_slots)[0] }}">
          <button class="btn" type="submit" data-close>Clear</button>
        </form>
      </div>
      {% else %}
      <p class="hint" style="margin:0">Memorise this spell from the
        <button class="btn" data-drawer="drawer-spells" style="font-size:10px;padding:3px 7px;">Manage Spells</button> drawer.</p>
      {% endif %}

    {% elif row.source_kind == "scroll" %}
      {% if row.castable %}
      <div class="row-actions">
        <form method="post" action="/character/{{ character_id }}/spell-sources/cast" style="display:inline">
          <input type="hidden" name="instance_id" value="{{ row.scroll_instance_id }}">
          <input type="hidden" name="spell_id" value="{{ row.spell_id }}">
          <button class="btn solid" type="submit" data-close>Cast (expends a charge)</button>
        </form>
      </div>
      {% endif %}

    {% elif row.source_kind == "innate" %}
      {% if row.spell_detail %}
      <details style="margin-top:10px">
        <summary>Spell details</summary>
        <div style="margin-top:6px">{{ detail_card(row.spell_detail) }}</div>
      </details>
      {% endif %}
      <p class="hint" style="margin:10px 0 0">{{ row.ready }} / {{ row.max_uses }} uses remaining today · resets on rest.</p>
      <div class="row-actions">
        <form method="post" action="/character/{{ character_id }}/innate/spend" style="display:inline">
          <input type="hidden" name="ability_id" value="{{ row.ability_id }}">
          <button class="btn solid" type="submit" data-close{% if row.ready == 0 %} disabled{% endif %}>Use</button>
        </form>
        <form method="post" action="/character/{{ character_id }}/innate/restore" style="display:inline">
          <input type="hidden" name="ability_id" value="{{ row.ability_id }}">
          <button class="btn" type="submit" data-close{% if row.used == 0 %} disabled{% endif %}>Restore</button>
        </form>
      </div>
    {% endif %}
  </div>
</div>
{% endmacro %}
```

- [ ] **Step 2: Import the macros in `sheet.html`**

After the existing `{% from "_detail_card.html" import detail_card with context %}` (line 5), add:

```jinja
{% from "_spells.html" import spell_row, spell_modal with context %}
```

- [ ] **Step 3: Replace the list section**

Replace lines 279-336 (`{% if sheet.spellbook or ... %}` opener through the end of the `{% for block in sheet.spellbook %}` loop, i.e. up to and including its `{% endfor %}` at line 336). Change the opener condition and the block loop to:

```jinja
  {% if sheet.spell_lists or sheet.mental_powers or sheet.innate_abilities %}
  <div class="spells-fullwidth">
    {% for block in sheet.spell_lists %}
    <section class="group">
      <div class="bar">Spells — {{ block.caster_type|title }}
        <span class="tools">
          {% for lvl in block.levels %}<span class="meta">{% if lvl.level == 0 %}Cantrips{% else %}L{{ lvl.level }}{% endif %} {{ lvl.used }}/{{ lvl.cap }}</span>{% endfor %}
          <button class="btn tool" data-drawer="drawer-spells">Manage</button>
        </span>
      </div>
      <div class="gbody scroll" style="max-height:360px">
        {% for lvl in block.levels %}
        <div class="lvl-head"><span>{% if lvl.level == 0 %}Cantrips{% else %}Level {{ lvl.level }}{% endif %}</span></div>
        {% for row in lvl.rows %}{{ spell_row(row, block.show_labels) }}
        {% else %}<p class="hint" style="margin:4px 0">None at this level.</p>{% endfor %}
        {% endfor %}
        <div class="cast-legend">
          <span><i class="pip"></i> cast ready</span>
          <span><i class="pip spent"></i> spent</span>
          <span><span class="known-tag">known</span> not memorised</span>
        </div>
      </div>
    </section>
    {% endfor %}
```

Leave the `{% for block in sheet.mental_powers %}` and `{% if sheet.innate_abilities %}` sections that follow exactly as they are.

- [ ] **Step 4: Replace the class + scroll modal loops**

Replace lines 851-920 (the two blocks: `{# MODALS: per-spell management ... #}` through the end of the scroll-modal block's `{% endif %}` at line 920) with a single loop:

```jinja
{# MODALS: per-spell actions (class cast/restore/clear · scroll cast · innate use/restore) #}
{% for block in sheet.spell_lists %}{% for lvl in block.levels %}{% for row in lvl.rows %}{{ spell_modal(row) }}{% endfor %}{% endfor %}{% endfor %}
```

Leave the `{# MODALS: per-innate-ability ... #}` loop (over `sheet.innate_abilities`, ~lines 922-945) exactly as is — it now renders only the non-routed innate abilities.

- [ ] **Step 5: Add the `.src-tag` style**

In `aose/web/static/sheet.css`, after the `.scroll-tag` rule (line 195), add:

```css
.src-tag{ font-style:italic; color:var(--faint); font-weight:400; }
```

- [ ] **Step 6: Verify in the preview**

Start the app and verify rendering with a multiclass arcane caster that also has a scroll and a spell-backed innate ability.

- Run (background): `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
- Use the preview tools: load a character sheet, confirm a single "Spells — Arcane" section with class + scroll + innate rows, source tags showing only when 2+ sources, pips correct, and that clicking a row opens the right modal (Cast / Cast-from-scroll / Use). Check `preview_console_logs` for errors.
- Confirm a solo single-class caster shows no source tags.

- [ ] **Step 7: Commit**

```bash
git add aose/web/templates/_spells.html aose/web/templates/sheet.html aose/web/static/sheet.css
git commit -m "feat(spells): unified spell-row + spell-modal macros on the sheet"
```

---

## Task 5: Remove dead code, update docs, full verification

**Files:**
- Modify: `aose/sheet/view.py` (remove old models/functions + `spellbook` field)
- Delete: `tests/test_spellbook_view.py`
- Modify: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- [ ] **Step 1: Confirm no remaining references to the old API**

Run: `grep -rn "spellbook_view\|SpellbookBlock\|SpellbookLevelGroup\|SpellbookRow\|ScrollSpellRow\|_scroll_rows_by_level\|\.spellbook\b\|spellbook=" aose/ tests/`
Expected remaining hits only: `entry.spellbook` (the model field — keep), `spellbook=books...` in wizard/tests, `kind == "spellbook"` literals. There must be **no** references to `spellbook_view`, the four old view models, `_scroll_rows_by_level`, or `sheet.spellbook` after Task 4. If `tests/test_sheet*.py` reference `sheet.spellbook`, update them to `sheet.spell_lists`.

- [ ] **Step 2: Delete the old view code**

In `aose/sheet/view.py` remove: `class SpellbookRow`, `class ScrollSpellRow`, `class SpellbookLevelGroup`, `class SpellbookBlock` (~lines 318-358); `def _scroll_rows_by_level` (~lines 898-925); `def spellbook_view` (~lines 928-1023); the `spellbook: list[SpellbookBlock]` field on `CharacterSheet` (~line 454); and the `spellbook=spellbook_view(spec, data),` line in `build_sheet` (~line 1961).

- [ ] **Step 3: Delete the superseded test file**

Run: `git rm tests/test_spellbook_view.py`

- [ ] **Step 4: Run the full test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the known trailing `pytest-current` PermissionError on Windows). Fix any failures from lingering `sheet.spellbook` references.

- [ ] **Step 5: Update the docs**

In `docs/ARCHITECTURE.md`, find the spells/spellbook subsystem section and edit it in place: the live sheet now renders one list per caster type via `spell_lists_view` + the `_spells.html` macros; class spells, scrolls, and spell-backed innate abilities share one `SpellRow`; source labels show only when a list has 2+ sources; non-spell innate and mental powers keep their own sections; memorization (the Manage drawer) stays per-class.

In `docs/CHANGELOG.md`, add one row at the top:

```
| 2026-06-29 | Unified spells UX — one list per caster type, source-labelled rows | unify-spells-ux | specs/2026-06-29-unify-spells-ux-design.md · plans/2026-06-29-unify-spells-ux.md |
```

(Match the existing CHANGELOG column format if it differs.)

- [ ] **Step 6: Commit**

```bash
git add aose/sheet/view.py docs/ARCHITECTURE.md docs/CHANGELOG.md
git rm tests/test_spellbook_view.py
git commit -m "refactor(spells): remove per-class spellbook_view; land unified lists + docs"
```

---

## Self-Review notes

- **Spec coverage:** single arcane list regardless of source (Tasks 1-3 assembly + Task 4 render); multiclass merge with labels (Task 1); spell-backed innate labelled by source (Task 3); arcane/divine separate blocks (Task 1 `out` loop); common macros (Task 4). Decisions honoured: non-spell innate stays separate (Task 3 + untouched innate section); labels only-when-ambiguous (`show_labels`); mental powers untouched; print sheet untouched; Manage drawer per-class untouched.
- **Type consistency:** `SpellRow` fields are referenced identically across `_class_spell_rows`, `_scroll_spell_rows`, the innate branch, and both macros (`modal_id`, `source_kind`, `source_label`, `ready`, `spent`, `known`, `castable`, `block_reason`, `ready_slots`/`spent_slots`/`class_id`, `scroll_instance_id`, `ability_id`/`max_uses`/`used`/`ability_text`/`spell_detail`).
- **Ordering note:** unified arcane rows now sort by `(name, source_label, reversed)` rather than book-insertion order — an intentional, uniform ordering across sources.
- **Empty divine levels** render a neutral "None at this level." hint; acceptable per design.
```
