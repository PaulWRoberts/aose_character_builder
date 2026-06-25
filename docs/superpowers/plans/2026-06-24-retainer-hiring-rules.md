# Retainer Hiring Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make hiring a retainer obey the hiring character's edition (Basic vs Advanced), content (`disabled_content`), and demihuman restrictions — sharing one availability source of truth with the creation wizard.

**Architecture:** Extract the wizard's inline class/race availability logic into four pure predicates in `engine/sources.py`. Reuse them in the wizard (duplication removal, no behavior change), in a new `retainers.retainer_class_ids` helper, in the sheet's option builders, and in the hire route's server-side validation. Fix `generate_retainer` to pass the optional-human-benefits flag through.

**Tech Stack:** Python 3, FastAPI, Pydantic v2, Jinja2, pytest. Run tests with `.venv\Scripts\python.exe -m pytest`.

---

## File Structure

| File | Responsibility |
|---|---|
| `aose/engine/sources.py` | + `class_available`, `race_available`, `class_allowed_for_race`, `class_level_cap` (pure predicates) |
| `aose/web/wizard.py` | Consume shared predicates; delete local `_class_allowed_for_race` and inline guards |
| `aose/engine/retainers.py` | + `retainer_class_ids` helper; pass `include_optional` in `generate_retainer` |
| `aose/sheet/view.py` | `_retainer_class_options` via helper; + `_retainer_race_options`; + sheet field |
| `aose/web/templates/_companions.html` | Race `<select>` in Advanced; none in Basic |
| `aose/web/routes.py` | Validate class/race/combo/level in `retainer_add` |
| `tests/test_sources_engine.py` | Predicate tests |
| `tests/test_retainer_hiring.py` | `retainer_class_ids` + option-builder tests |
| `tests/test_retainer_generation.py` | Human-benefits + single-class tests |
| `tests/test_retainer_routes.py` | Route guard tests |
| `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md` | Keep current |

**Test data facts (verified against `data/`):**
- `dwarf` race: `source: ose_advanced_fantasy`, `allowed_classes: [assassin, cleric, fighter, thief]` (so `magic_user` is forbidden), `class_level_caps.fighter == 10`.
- `acolyte` class: non-race-locked, `source: carcass_crawler_1`.
- `elf`, `dwarf` classes: `race_locked` (race-as-class entries).
- A `fighter` PC yields `allowed_retainer_classes(...) == "any"`.

---

## Task 1: Shared availability predicates in `engine/sources.py`

**Files:**
- Modify: `aose/engine/sources.py`
- Test: `tests/test_sources_engine.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sources_engine.py`:

```python
from aose.engine.sources import (
    class_available,
    race_available,
    class_allowed_for_race,
    class_level_cap,
)

DATA = GameData.load(DATA_DIR)


def _cls(cid):
    return DATA.classes[cid]


def _race(rid):
    return DATA.races[rid]


def test_class_available_hides_race_as_class_in_advanced():
    rs = RuleSet(separate_race_class=True)
    assert class_available(_cls("fighter"), rs) is True
    assert class_available(_cls("elf"), rs) is False  # race-locked, hidden


def test_class_available_shows_race_as_class_in_basic():
    rs = RuleSet(separate_race_class=False)
    assert class_available(_cls("elf"), rs) is True


def test_class_available_respects_disabled_content():
    rs = RuleSet(disabled_content=["carcass_crawler_1:classes"])
    assert class_available(_cls("acolyte"), rs) is False
    assert class_available(_cls("fighter"), rs) is True


def test_race_available_respects_disabled_content():
    rs = RuleSet(disabled_content=["ose_advanced_fantasy:classes"])
    assert race_available(_race("dwarf"), rs) is False
    assert race_available(_race("human"), rs) is True


def test_class_allowed_for_race_enforces_allowed_classes():
    rs = RuleSet()
    assert class_allowed_for_race("fighter", _race("dwarf"), rs) is True
    assert class_allowed_for_race("magic_user", _race("dwarf"), rs) is False


def test_class_allowed_for_race_lifted():
    rs = RuleSet(lift_demihuman_restrictions=True)
    assert class_allowed_for_race("magic_user", _race("dwarf"), rs) is True


def test_class_level_cap_lookup_and_lift():
    rs = RuleSet()
    assert class_level_cap(_race("dwarf"), "fighter", rs) == 10
    assert class_level_cap(_race("human"), "fighter", rs) is None
    assert class_level_cap(_race("dwarf"), "fighter",
                           RuleSet(lift_demihuman_restrictions=True)) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sources_engine.py -q`
Expected: FAIL with `ImportError: cannot import name 'class_available'`.

- [ ] **Step 3: Implement the predicates**

Append to `aose/engine/sources.py` (the module already imports `RuleSet`):

```python
def class_available(cls, ruleset: RuleSet) -> bool:
    """Whether a class is offerable under this ruleset: its source/category is
    enabled, and it is not a race-as-class entry hidden by Advanced mode.

    In Basic (``separate_race_class`` off) race-locked demihuman classes ARE
    offered; in Advanced they are not (the player picks race + a normal class).
    The caller decides how to treat ``normal_human``."""
    if not content_enabled(cls.source, "classes", ruleset):
        return False
    if ruleset.separate_race_class and cls.race_locked:
        return False
    return True


def race_available(race, ruleset: RuleSet) -> bool:
    """Whether a race may be chosen under this ruleset (its source is enabled)."""
    return content_enabled(race.source, "classes", ruleset)


def class_allowed_for_race(class_id: str, race, ruleset: RuleSet) -> bool:
    """Whether a race may take a class under this ruleset.

    ``lift_demihuman_restrictions`` -> any class. An empty ``allowed_classes``
    means "no restriction" (the human-style default); a populated list is
    enforced."""
    if ruleset.lift_demihuman_restrictions:
        return True
    if not race.allowed_classes:
        return True
    return class_id in race.allowed_classes


def class_level_cap(race, class_id: str, ruleset: RuleSet) -> int | None:
    """The demihuman level cap for a race+class, or ``None`` when uncapped or
    when ``lift_demihuman_restrictions`` is on."""
    if ruleset.lift_demihuman_restrictions:
        return None
    return race.class_level_caps.get(class_id)
```

Change the top import to include `RuleSet`:

```python
from aose.models import RuleSet, CONTENT_CATEGORIES
```
(It already imports `RuleSet`; leave as-is if so.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sources_engine.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/sources.py tests/test_sources_engine.py
git commit -m "feat(sources): shared class/race availability predicates"
```

---

## Task 2: Wizard reuses the shared predicates (no behavior change)

**Files:**
- Modify: `aose/web/wizard.py` (import line ~100; `get_class` ~706-724; `get_race` ~613; delete `_class_allowed_for_race` ~666-677)

- [ ] **Step 1: Run the existing wizard tests to capture the green baseline**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py tests/ -q -k "class or race"`
Expected: PASS (these guard the behavior we must preserve).

- [ ] **Step 2: Update the import**

In `aose/web/wizard.py`, change:

```python
from aose.engine.sources import content_enabled
```
to:
```python
from aose.engine.sources import (
    content_enabled,
    class_available,
    race_available,
    class_allowed_for_race,
    class_level_cap,
)
```

- [ ] **Step 3: Delete the local `_class_allowed_for_race`**

Remove the whole function `def _class_allowed_for_race(class_id, race, ruleset) -> bool:` (and its docstring/body, ~lines 666-677). Its call sites now resolve to the imported `class_allowed_for_race`.

- [ ] **Step 4: Simplify the `get_class` per-class guards**

In `get_class`, replace these three lines:

```python
        if ruleset.separate_race_class and cls.race_locked:
            continue
        if cls.id == "normal_human":   # retainer-only class; not player-choosable
            continue
        if not content_enabled(cls.source, "classes", ruleset):
            continue
```
with:
```python
        if cls.id == "normal_human":   # retainer-only class; not player-choosable
            continue
        if not class_available(cls, ruleset):
            continue
```

Then replace the level-cap block:

```python
            level_cap = (
                race.class_level_caps.get(cls.id)
                if not ruleset.lift_demihuman_restrictions
                else None
            )
```
with:
```python
            level_cap = class_level_cap(race, cls.id, ruleset)
```

The `_class_allowed_for_race(cls.id, race, ruleset)` call becomes `class_allowed_for_race(cls.id, race, ruleset)` automatically via the import.

- [ ] **Step 5: Simplify the `get_race` content guard**

In `get_race`, replace:

```python
        if not content_enabled(race.source, "classes", ruleset):
            continue
```
with:
```python
        if not race_available(race, ruleset):
            continue
```

- [ ] **Step 6: Run the wizard tests to verify still green**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q -k "class or race or wizard"`
Expected: PASS (unchanged behavior).

- [ ] **Step 7: Commit**

```bash
git add aose/web/wizard.py
git commit -m "refactor(wizard): reuse shared availability predicates"
```

---

## Task 3: `generate_retainer` applies optional human benefits

**Files:**
- Modify: `aose/engine/retainers.py:62-64`
- Test: `tests/test_retainer_generation.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_retainer_generation.py` (use the existing module's imports; add what's missing):

```python
from aose.models import RuleSet


def _human_pc(ruleset):
    return CharacterSpec(
        name="PC",
        abilities={"STR": 12, "INT": 12, "WIS": 10, "DEX": 12, "CON": 10, "CHA": 12},
        race_id="human",
        classes=[{"class_id": "fighter", "level": 3}],
        alignment="neutral",
        ruleset=ruleset,
    )


def test_human_benefits_applied_in_advanced():
    rs = RuleSet(separate_race_class=True, human_racial_abilities=True)
    base = retainers.generate_retainer(
        name="H", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=_human_pc(rs), data=DATA,
        rng=__import__("random").Random(1))
    rs2 = RuleSet(separate_race_class=True, human_racial_abilities=False)
    plain = retainers.generate_retainer(
        name="H", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=_human_pc(rs2), data=DATA,
        rng=__import__("random").Random(1))
    human = DATA.races["human"]
    if human.optional_ability_modifiers:
        assert base.spec.abilities != plain.spec.abilities


def test_human_benefits_ignored_in_basic():
    rs = RuleSet(separate_race_class=False, human_racial_abilities=True)
    ret = retainers.generate_retainer(
        name="H", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=_human_pc(rs), data=DATA,
        rng=__import__("random").Random(1))
    # Basic mode applies no racial modifiers at all; a fighter's only floor is
    # its ability requirements, so non-requirement scores stay at baseline 10.
    assert ret.spec.abilities["CHA"] == 10


def test_retainer_is_single_class_even_with_multiclassing():
    rs = RuleSet(multiclassing=True, separate_race_class=True)
    ret = retainers.generate_retainer(
        name="H", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=_human_pc(rs), data=DATA)
    assert len(ret.spec.classes) == 1
```

Confirm `DATA` and `retainers`/`CharacterSpec` are already imported at the top of the file; if not, add:
```python
from pathlib import Path
from aose.data.loader import GameData
from aose.engine import retainers
from aose.models import CharacterSpec
DATA = GameData.load(Path("data"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_generation.py -q -k "human_benefits or single_class"`
Expected: `test_human_benefits_applied_in_advanced` FAILS (benefits not applied yet); the other two may already pass.

- [ ] **Step 3: Pass the optional flag through**

In `aose/engine/retainers.py`, change:

```python
    elif hiring_spec.ruleset.separate_race_class and race_id in data.races:
        abilities = apply_racial_modifiers(abilities, data.races[race_id])
```
to:
```python
    elif hiring_spec.ruleset.separate_race_class and race_id in data.races:
        abilities = apply_racial_modifiers(
            abilities, data.races[race_id],
            include_optional=hiring_spec.ruleset.human_racial_abilities,
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_generation.py -q -k "human_benefits or single_class"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/retainers.py tests/test_retainer_generation.py
git commit -m "feat(retainers): apply optional human benefits to hired humans"
```

---

## Task 4: `retainer_class_ids` helper + option builders

**Files:**
- Modify: `aose/engine/retainers.py` (add helper; add import)
- Modify: `aose/sheet/view.py:1301-1308` (`_retainer_class_options`); add `_retainer_race_options`; add sheet field (~461) and populate (~1819)
- Test: `tests/test_retainer_hiring.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_retainer_hiring.py`:

```python
from aose.models import RuleSet
from aose.sheet.view import _retainer_class_options, _retainer_race_options


def _pc_rs(cls, level, ruleset):
    return CharacterSpec(
        name="PC", abilities={"STR": 12, "INT": 12, "WIS": 10, "DEX": 12,
                              "CON": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": cls, "level": level}],
        alignment="neutral", ruleset=ruleset)


def test_class_ids_always_include_normal_human():
    pc = _pc_rs("fighter", 1, RuleSet())
    assert "normal_human" in retainers.retainer_class_ids(pc, DATA)


def test_class_ids_exclude_disabled_content():
    pc = _pc_rs("fighter", 1, RuleSet(disabled_content=["carcass_crawler_1:classes"]))
    assert "acolyte" not in retainers.retainer_class_ids(pc, DATA)


def test_class_ids_exclude_race_as_class_in_advanced():
    pc = _pc_rs("fighter", 1, RuleSet(separate_race_class=True))
    ids = retainers.retainer_class_ids(pc, DATA)
    assert "elf" not in ids
    assert "fighter" in ids


def test_class_ids_include_race_as_class_in_basic():
    pc = _pc_rs("fighter", 1, RuleSet(separate_race_class=False))
    assert "elf" in retainers.retainer_class_ids(pc, DATA)


def test_class_ids_intersect_allowed_retainer_classes():
    # An assassin L5 PC may only hire assassins (per allowed_retainer_classes),
    # plus normal_human is always allowed.
    pc = _pc_rs("assassin", 5, RuleSet())
    ids = retainers.retainer_class_ids(pc, DATA)
    assert ids == {"assassin", "normal_human"}


def test_race_options_empty_in_basic():
    pc = _pc_rs("fighter", 1, RuleSet(separate_race_class=False))
    assert _retainer_race_options(pc, DATA) == []


def test_race_options_advanced_filtered_by_content():
    pc = _pc_rs("fighter", 1, RuleSet(separate_race_class=True))
    ids = {r["id"] for r in _retainer_race_options(pc, DATA)}
    assert "human" in ids and "dwarf" in ids
    pc2 = _pc_rs("fighter", 1,
                 RuleSet(separate_race_class=True,
                         disabled_content=["ose_advanced_fantasy:classes"]))
    ids2 = {r["id"] for r in _retainer_race_options(pc2, DATA)}
    assert "dwarf" not in ids2
    assert "human" in ids2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_hiring.py -q`
Expected: FAIL with `AttributeError: module 'aose.engine.retainers' has no attribute 'retainer_class_ids'` (and missing `_retainer_race_options`).

- [ ] **Step 3: Add `retainer_class_ids` to `engine/retainers.py`**

Add the import near the top (with the other engine imports):

```python
from aose.engine.sources import class_available
```

Add this function right after `allowed_retainer_classes`:

```python
def retainer_class_ids(hiring_spec: CharacterSpec, data: GameData) -> set[str]:
    """The class ids a retainer may be hired as: ``normal_human`` always, plus
    every class that is content/edition-available to the player AND permitted by
    the AOSE per-class hiring tier (``allowed_retainer_classes``)."""
    allowed = allowed_retainer_classes(hiring_spec, data)
    rs = hiring_spec.ruleset
    ids: set[str] = set()
    for c in data.classes.values():
        if c.id == "normal_human":
            ids.add(c.id)
            continue
        if not class_available(c, rs):
            continue
        if allowed == "any" or (isinstance(allowed, set) and c.id in allowed):
            ids.add(c.id)
    return ids
```

- [ ] **Step 4: Rewrite `_retainer_class_options` and add `_retainer_race_options` in `sheet/view.py`**

Replace the existing `_retainer_class_options` body:

```python
def _retainer_class_options(spec: CharacterSpec, data: GameData) -> list[dict]:
    from aose.engine.retainers import retainer_class_ids
    ids = retainer_class_ids(spec, data)
    return [
        {"id": c.id, "name": c.name}
        for c in data.classes.values()
        if c.id in ids
    ]


def _retainer_race_options(spec: CharacterSpec, data: GameData) -> list[dict]:
    """Race choices for an Advanced retainer hire (content-filtered). Empty in
    Basic mode, where a retainer has no separately-chosen race."""
    from aose.engine.sources import race_available
    if not spec.ruleset.separate_race_class:
        return []
    return [
        {"id": r.id, "name": r.name}
        for r in sorted(data.races.values(), key=lambda r: r.name)
        if race_available(r, spec.ruleset)
    ]
```

- [ ] **Step 5: Add the sheet field and populate it**

In the `CharacterSheet` model (near line 461, beside `retainer_class_options`), add:

```python
    retainer_race_options: list[dict] = Field(default_factory=list)
```

In `build_sheet(...)` (near line 1819, beside `retainer_class_options=...`), add:

```python
        retainer_race_options=_retainer_race_options(spec, data),
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_hiring.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add aose/engine/retainers.py aose/sheet/view.py tests/test_retainer_hiring.py
git commit -m "feat(retainers): content/edition-gated class and race options"
```

---

## Task 5: Hire form shows a race picker in Advanced

**Files:**
- Modify: `aose/web/templates/_companions.html:104-114`

- [ ] **Step 1: Replace the hidden race field with a conditional select**

In the `.retainer-add-expanded` form, replace:

```html
          <input type="hidden" name="race_id" value="{{ sheet.race_id }}">
```
with:
```html
          {% if sheet.retainer_race_options %}
          <select name="race_id">
            {% for r in sheet.retainer_race_options %}<option value="{{ r.id }}">{{ r.name }}</option>{% endfor %}
          </select>
          {% endif %}
```

(When `retainer_race_options` is empty — Basic mode — no race control is rendered; the route's `race_id` parameter defaults to `"human"`.)

- [ ] **Step 2: Manual render check via an existing route test**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_routes.py -q`
Expected: PASS (existing tests still render the sheet without error).

- [ ] **Step 3: Commit**

```bash
git add aose/web/templates/_companions.html
git commit -m "feat(ui): race picker on the retainer hire form in Advanced mode"
```

---

## Task 6: Server-side validation in `retainer_add`

**Files:**
- Modify: `aose/web/routes.py:1722-1740`
- Test: `tests/test_retainer_routes.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_retainer_routes.py`:

```python
from aose.models import RuleSet


def _save_char_rs(client, ruleset) -> str:
    spec = CharacterSpec(
        name="Boss",
        abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 13},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=11, hp_rolls=[8] * 9)],
        alignment="neutral", gold=50, ruleset=ruleset,
    )
    save_character("boss", spec, client._characters_dir)
    return "boss"


def test_hire_rejects_disabled_class(client):
    cid = _save_char_rs(client, RuleSet(disabled_content=["carcass_crawler_1:classes"]))
    resp = client.post(f"/character/{cid}/retainer/add", data={
        "name": "X", "class_id": "acolyte", "level": "1",
        "race_id": "human", "alignment": "neutral"})
    assert resp.status_code == 400


def test_hire_rejects_illegal_demihuman_combo(client):
    cid = _save_char_rs(client, RuleSet(separate_race_class=True))
    resp = client.post(f"/character/{cid}/retainer/add", data={
        "name": "X", "class_id": "magic_user", "level": "1",
        "race_id": "dwarf", "alignment": "neutral"})
    assert resp.status_code == 400


def test_hire_allows_combo_when_restrictions_lifted(client):
    cid = _save_char_rs(client, RuleSet(separate_race_class=True,
                                        lift_demihuman_restrictions=True))
    resp = client.post(f"/character/{cid}/retainer/add", data={
        "name": "X", "class_id": "magic_user", "level": "1",
        "race_id": "dwarf", "alignment": "neutral"})
    assert resp.status_code == 303


def test_hire_rejects_level_above_race_cap(client):
    # PC is fighter L11; dwarf fighter cap is 10, so level 11 is illegal.
    cid = _save_char_rs(client, RuleSet(separate_race_class=True))
    resp = client.post(f"/character/{cid}/retainer/add", data={
        "name": "X", "class_id": "fighter", "level": "11",
        "race_id": "dwarf", "alignment": "neutral"})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_routes.py -q -k "hire"`
Expected: FAIL (currently the route accepts all of these → 303 instead of 400, or 303 where 400 expected).

- [ ] **Step 3: Add validation to the route**

In `aose/web/routes.py`, update the import block near the retainer routes:

```python
from aose.engine import retainers as retainers_engine
```
to also import the predicates:
```python
from aose.engine import retainers as retainers_engine
from aose.engine.sources import class_allowed_for_race, class_level_cap
```

Replace the body of `retainer_add` (between loading `spec`/`data` and the `try:`) so it reads:

```python
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    rs = spec.ruleset
    pc_level = max((e.level for e in spec.classes), default=1)
    if class_id != "normal_human" and level > pc_level:
        raise HTTPException(400, "A retainer may not exceed your level")

    if class_id not in retainers_engine.retainer_class_ids(spec, data):
        raise HTTPException(400, f"{class_id!r} is not available to hire")

    if rs.separate_race_class and class_id != "normal_human":
        race = data.races.get(race_id)
        if race is None:
            raise HTTPException(400, f"Unknown race {race_id!r}")
        if not class_allowed_for_race(class_id, race, rs):
            raise HTTPException(
                400, f"{race.name} may not be a {data.classes[class_id].name}")
        cap = class_level_cap(race, class_id, rs)
        if cap is not None and level > cap:
            raise HTTPException(
                400, f"{race.name} {data.classes[class_id].name} is capped at level {cap}")

    try:
        ret = retainers_engine.generate_retainer(
            name=name, class_ids=[class_id], level=level, race_id=race_id,
            alignment=alignment, hiring_spec=spec, data=data)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))
    spec.retainers.append(ret)
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_routes.py -q`
Expected: PASS (new guards plus the existing route tests).

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_retainer_routes.py
git commit -m "feat(routes): validate retainer class/race/combo/level on hire"
```

---

## Task 7: Full suite, docs, final commit

**Files:**
- Modify: `docs/ARCHITECTURE.md` (retainers section), `docs/CHANGELOG.md`

- [ ] **Step 1: Run the full test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the known trailing `pytest-current` PermissionError on Windows).

- [ ] **Step 2: Update `docs/ARCHITECTURE.md`**

In the retainers subsystem section, edit in place to state: retainer hiring now mirrors the hiring PC's edition and content rules — Basic offers all classes incl. race-as-class with no separate race; Advanced offers a class + a content-filtered race, excludes race-as-class entries, and enforces demihuman `allowed_classes`/level caps (governed by `lift_demihuman_restrictions`); optional human benefits apply in Advanced only; class/race availability shares the `engine/sources` predicates (`class_available`, `race_available`, `class_allowed_for_race`, `class_level_cap`); retainers are always single-class. Mention the `retainer_class_ids` helper as the single source of truth used by the sheet options and the hire route.

- [ ] **Step 3: Add a `docs/CHANGELOG.md` row**

Add to the top of the ledger:

```
| 2026-06-24 | Retainer hiring follows hiring PC's class/edition/demihuman rules | feat/retainer-hiring-rules | 2026-06-24-retainer-hiring-rules |
```
(Match the existing column format in the file.)

- [ ] **Step 4: Commit**

```bash
git add docs/ARCHITECTURE.md docs/CHANGELOG.md
git commit -m "docs: retainer hiring mirrors PC edition/content/demihuman rules"
```

---

## Self-Review Notes

- **Spec coverage:** Basic (all classes incl. race-as-class, no race) → Task 1 `class_available` + Task 4 race options empty in Basic + Task 5 no picker. Advanced (class + race, race-as-class excluded) → Task 1 + Task 4 + Task 5 picker. Content gate → `class_available`/`race_available` (Tasks 1/4). Demihuman restrictions per `lift_demihuman_restrictions` → `class_allowed_for_race`/`class_level_cap` (Tasks 1/6). Human benefits Advanced-only → Task 3. No multiclass → Task 3 invariant test. Shared with wizard → Task 2. Server-side validation → Task 6. Docs → Task 7.
- **Type consistency:** `retainer_class_ids` returns `set[str]`; `_retainer_class_options`/`_retainer_race_options` return `list[dict]`; predicates return `bool`/`int | None`. Names are consistent across tasks (`class_available`, `race_available`, `class_allowed_for_race`, `class_level_cap`, `retainer_class_ids`).
- **No placeholders:** every code step shows full code; commands include expected pass/fail.
```
