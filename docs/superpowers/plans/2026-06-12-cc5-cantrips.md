# CC5 Cantrips Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Carcass Crawler 5's optional **Cantrips** rule (and dependent **Read Magic Cantrip** rule), modelling cantrips as level-0 arcane spells that ride the existing spellbook/slot machinery for dedicated arcane casters.

**Architecture:** Cantrips are `level: 0` arcane spells stored in the existing `ClassEntry.spellbook` / `slots`. Two new `RuleSet` bool flags gate them. The spell engine (`aose/engine/spells.py`) gains a cantrip cap (2/3/4 by level), a "dedicated arcane caster" predicate, and optional `data`/`ruleset` params on the level/slot accessors that inject a level-0 group when the rule applies. Everything else (sheet group, prepare/cast, copying under Advanced rules, wizard picker) reuses existing paths.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, pytest. YAML game data.

**Reference spec:** `docs/superpowers/specs/2026-06-12-cc5-cantrips-design.md`

**Run tests with:** `.venv\Scripts\python.exe -m pytest tests/ -q` (the trailing `pytest-current` PermissionError on Windows is a known pytest-9 tempdir quirk — ignore it). Run a single test file with e.g. `.venv\Scripts\python.exe -m pytest tests/test_cantrips.py -q`.

**Run the app with:** `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`

---

## Task 1: RuleSet flags

**Files:**
- Modify: `aose/models/ruleset.py`
- Test: `tests/test_cantrips.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_cantrips.py`:

```python
from aose.models import RuleSet


def test_cantrip_flags_default_off():
    rs = RuleSet()
    assert rs.cantrips is False
    assert rs.read_magic_cantrip is False


def test_cantrip_flags_settable():
    rs = RuleSet(cantrips=True, read_magic_cantrip=True)
    assert rs.cantrips is True
    assert rs.read_magic_cantrip is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips.py -q`
Expected: FAIL — `RuleSet` has `extra="forbid"`, so `cantrips`/`read_magic_cantrip` raise a validation error.

- [ ] **Step 3: Add the fields**

In `aose/models/ruleset.py`, after the `combat_talents: bool = False` line (line 33), add:

```python
    combat_talents: bool = False
    cantrips: bool = False
    read_magic_cantrip: bool = False
```

(Keep the existing `combat_talents` line; just add the two new lines beneath it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/models/ruleset.py tests/test_cantrips.py
git commit -m "feat(rules): add cantrips + read_magic_cantrip RuleSet flags"
```

---

## Task 2: Settings / wizard rules UI registration

**Files:**
- Modify: `aose/web/settings_routes.py` (RULE_LABELS ~18, IMPLEMENTED_RULES ~38, RULE_DESCRIPTIONS ~60, SOURCE_RULES ~118)
- Test: `tests/test_cantrips_settings.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_cantrips_settings.py`:

```python
from aose.web.settings_routes import (
    RULE_LABELS, RULE_DESCRIPTIONS, IMPLEMENTED_RULES, SOURCE_RULES,
    flatten_rule_fields, parse_ruleset_from_form,
)


def test_cantrip_rules_registered_and_implemented():
    for field in ("cantrips", "read_magic_cantrip"):
        assert field in RULE_LABELS
        assert field in RULE_DESCRIPTIONS
        assert field in IMPLEMENTED_RULES  # never renders a "pending" badge


def test_cantrip_rules_attached_to_carcass_crawler_5():
    fields = flatten_rule_fields(SOURCE_RULES["carcass_crawler_5"])
    assert "cantrips" in fields
    assert "read_magic_cantrip" in fields


def test_read_magic_cantrip_forced_off_when_cantrips_off():
    # read_magic_cantrip checked but its parent cantrips unchecked -> forced off
    form = {"read_magic_cantrip": "on"}
    rs = parse_ruleset_from_form(form)
    assert rs.cantrips is False
    assert rs.read_magic_cantrip is False


def test_read_magic_cantrip_kept_when_cantrips_on():
    form = {"cantrips": "on", "read_magic_cantrip": "on"}
    rs = parse_ruleset_from_form(form)
    assert rs.cantrips is True
    assert rs.read_magic_cantrip is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips_settings.py -q`
Expected: FAIL — `KeyError: 'carcass_crawler_5'` and the rules missing from the label/description/implemented sets.

- [ ] **Step 3: Register the rules**

In `aose/web/settings_routes.py`:

(a) In `RULE_LABELS` (add after `"combat_talents": "Combat Talents",`):

```python
    "combat_talents": "Combat Talents",
    "cantrips": "Cantrips",
    "read_magic_cantrip": "Read Magic Cantrip",
```

(b) In `IMPLEMENTED_RULES` (add after `"combat_talents",`):

```python
    "combat_talents",
    "cantrips",
    "read_magic_cantrip",
```

(c) In `RULE_DESCRIPTIONS` (add after the `"combat_talents": ...` entry, before the closing `}`):

```python
    "cantrips":
        "Dedicated arcane spell casters (magic-users, illusionists) know minor "
        "level-0 spells called cantrips: 2 at levels 1–2, 3 at 3–4, 4 at 5+ "
        "(both known and memorised).",
    "read_magic_cantrip":
        "Read magic is demoted from a 1st-level spell to a cantrip that arcane "
        "casters know automatically, in addition to their normal cantrips. Makes "
        "found scrolls easier to use.",
```

(d) In `SOURCE_RULES`, add a `carcass_crawler_5` entry (place it after the `carcass_crawler_1` block, before `ose_classic_fantasy`):

```python
    "carcass_crawler_1": [
        _rule("combat_talents"),
    ],
    "carcass_crawler_5": [
        _rule("cantrips",
              _rule("read_magic_cantrip")),
    ],
    "ose_classic_fantasy": [
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips_settings.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the settings regression guard**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py -q`
Expected: PASS (the "no pending badge" guard still holds because both rules are in `IMPLEMENTED_RULES`).

- [ ] **Step 6: Commit**

```bash
git add aose/web/settings_routes.py tests/test_cantrips_settings.py
git commit -m "feat(settings): surface CC5 cantrips rules with read-magic dependency"
```

---

## Task 3: Cantrip spell data (13 level-0 spells)

**Files:**
- Create: `data/spells/carcass_crawler_5_cantrips.yaml`
- Test: `tests/test_cantrips.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cantrips.py`:

```python
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

CANTRIP_IDS = {
    "cantrip_book_leaf", "cantrip_cleaning_brush", "cantrip_coloured_flame",
    "cantrip_floating_trinket", "cantrip_magic_quill", "cantrip_open_close_portal",
    "cantrip_rune", "cantrip_sense_magic", "cantrip_smoke_rings", "cantrip_spark",
    "cantrip_vanish", "cantrip_wizard_flame",
}


def test_cantrip_spells_load_at_level_zero():
    from aose.data.loader import GameData
    data = GameData.load(DATA_DIR)
    for sid in CANTRIP_IDS:
        spell = data.spells[sid]
        assert spell.level == 0
        assert spell.source == "carcass_crawler_5"
        assert "magic_user" in spell.spell_lists
        assert "illusionist" in spell.spell_lists


def test_read_magic_cantrip_loads():
    from aose.data.loader import GameData
    data = GameData.load(DATA_DIR)
    rm = data.spells["read_magic_cantrip"]
    assert rm.level == 0
    assert rm.source == "carcass_crawler_5"
    assert set(rm.spell_lists) == {"magic_user", "illusionist"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips.py -q`
Expected: FAIL — `KeyError` on the cantrip ids (file does not exist yet).

- [ ] **Step 3: Create the data file**

Create `data/spells/carcass_crawler_5_cantrips.yaml`:

```yaml
- id: cantrip_book_leaf
  name: Book Leaf
  level: 0
  spell_lists: [magic_user, illusionist]
  source: carcass_crawler_5
  range: 10'
  duration: Concentration
  description: |-
    The caster can magically open a book and leaf through its pages without touching it.
- id: cantrip_cleaning_brush
  name: Cleaning Brush
  level: 0
  spell_lists: [magic_user, illusionist]
  source: carcass_crawler_5
  range: Touch
  duration: 1 turn
  description: |-
    A broom or mop takes on a life of its own and cleans an area designated by the caster (up to a 30' x 30' area in 1 turn).
- id: cantrip_coloured_flame
  name: Coloured Flame
  level: 0
  spell_lists: [magic_user, illusionist]
  source: carcass_crawler_5
  range: 20'
  duration: 1 turn
  description: |-
    A flame within range is imbued with a hue of the caster's choosing.
- id: cantrip_floating_trinket
  name: Floating Trinket
  level: 0
  spell_lists: [magic_user, illusionist]
  source: carcass_crawler_5
  range: 10'
  duration: Concentration
  description: |-
    The caster causes a small possession within range to levitate and float through the air at up to 1' per round.

    Object weight limit: 10 coins or less.

    Possessions: Only objects owned by the caster for at least a day can be affected.

    Manipulation: The object cannot be manipulated with enough force or precision to enact its function as a tool.
- id: cantrip_magic_quill
  name: Magic Quill
  level: 0
  spell_lists: [magic_user, illusionist]
  source: carcass_crawler_5
  range: 10'
  duration: Concentration
  description: |-
    A quill floats and moves of its own accord, magically transcribing the caster's words onto a page.
- id: cantrip_open_close_portal
  name: Open / Close Portal
  level: 0
  spell_lists: [magic_user, illusionist]
  source: carcass_crawler_5
  range: 20'
  duration: Instant
  description: |-
    An unlocked portal (e.g. door, window, chest lid) within range swings open or shut as the caster desires.
- id: cantrip_rune
  name: Rune
  level: 0
  spell_lists: [magic_user, illusionist]
  source: carcass_crawler_5
  range: Touch
  duration: 1 turn
  description: |-
    The caster traces a glowing sigil in the air or on a surface or object.

    Personal sigil: Each caster's rune is unique and can be used to identify them.
- id: cantrip_sense_magic
  name: Sense Magic
  level: 0
  spell_lists: [magic_user, illusionist]
  source: carcass_crawler_5
  range: Touch
  duration: Concentration
  description: |-
    The caster attunes their mind to subtle arcane energies, attempting to detect magic on a creature or object touched.

    Chance: Each turn the caster spends in concentration, they have a 2-in-6 chance of detecting magic on the subject. The referee should roll this chance, as the caster does not know if the roll failed or if there is no magic present.
- id: cantrip_smoke_rings
  name: Smoke Rings
  level: 0
  spell_lists: [magic_user, illusionist]
  source: carcass_crawler_5
  range: The caster
  duration: Concentration
  description: |-
    While smoking a pipe, the caster gains the ability to blow impressive smoke rings of any colour desired.
- id: cantrip_spark
  name: Spark
  level: 0
  spell_lists: [magic_user, illusionist]
  source: carcass_crawler_5
  range: Touch
  duration: Instant
  description: |-
    A tiny spark of flame flashes at the caster's fingertip.

    Light: The spark sheds momentary light in a 5' radius.

    Igniting: The spark can be used to ignite flammable material (e.g. oil, tinder).
- id: cantrip_vanish
  name: Vanish
  level: 0
  spell_lists: [magic_user, illusionist]
  source: carcass_crawler_5
  range: Touch
  duration: 1 round
  description: |-
    A small object touched by the caster becomes invisible for 1 round.

    Object weight limit: 10 coins or less.
- id: cantrip_wizard_flame
  name: Wizard Flame
  level: 0
  spell_lists: [magic_user, illusionist]
  source: carcass_crawler_5
  range: Touch
  duration: Concentration
  description: |-
    A wan flame wreathes the caster's hand, producing flickering, heatless light.

    Radius of light: 5'.
- id: read_magic_cantrip
  name: Read Magic
  level: 0
  spell_lists: [magic_user, illusionist]
  source: carcass_crawler_5
  range: The caster
  duration: 1 turn
  description: |-
    By means of read magic, the caster can decipher magical inscriptions or runes, as follows:

    Scrolls: The magical script of a scroll of arcane spells can be understood. The caster is then able to activate the scroll at any time in the future.

    Spell books: A spell book written by another arcane spell caster can be deciphered.

    Inscriptions: Runes or magical words inscribed on an object or surface can be understood.

    Reading again: Once the caster has read a magical inscription using read magic, they are thereafter able to read that particular writing without recourse to the use of this spell.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips.py -q`
Expected: PASS.

- [ ] **Step 5: Sanity-check the loader still loads everything**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py -q`
Expected: PASS (the spell glob auto-discovers the new file; no loader edit needed).

- [ ] **Step 6: Commit**

```bash
git add data/spells/carcass_crawler_5_cantrips.yaml tests/test_cantrips.py
git commit -m "feat(data): add CC5 cantrip spells (level-0 arcane)"
```

---

## Task 4: Engine — cantrip count + dedicated-arcane predicate

**Files:**
- Modify: `aose/engine/spells.py` (add helpers after `powers_known_cap`, ~line 67)
- Test: `tests/test_cantrips.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cantrips.py`:

```python
def test_cantrip_count_bands():
    from aose.engine import spells
    assert spells.cantrip_count(1) == 2
    assert spells.cantrip_count(2) == 2
    assert spells.cantrip_count(3) == 3
    assert spells.cantrip_count(4) == 3
    assert spells.cantrip_count(5) == 4
    assert spells.cantrip_count(14) == 4


def test_is_dedicated_arcane():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    assert spells.is_dedicated_arcane(data.classes["magic_user"], data) is True
    assert spells.is_dedicated_arcane(data.classes["illusionist"], data) is True
    # divine caster
    assert spells.is_dedicated_arcane(data.classes["cleric"], data) is False
    # non-caster
    assert spells.is_dedicated_arcane(data.classes["fighter"], data) is False
    # scroll-only arcane (no slots at L1)
    assert spells.is_dedicated_arcane(data.classes["mage"], data) is False
    # arcane but first casts at L2
    assert spells.is_dedicated_arcane(data.classes["arcane_bard"], data) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips.py -k "cantrip_count or dedicated" -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'cantrip_count'`.

- [ ] **Step 3: Add the helpers**

In `aose/engine/spells.py`, add module-level constants near the top (after `CasterType = Literal[...]`, ~line 15):

```python
CasterType = Literal["arcane", "divine", "mental"]

# CC5 Cantrips: level-0 arcane spells. Demoted Read Magic ids (hidden when the
# Read Magic Cantrip rule is on) and the level-0 replacement id.
DEMOTED_READ_MAGIC_IDS = {"magic_user_read_magic", "illusionist_read_magic"}
READ_MAGIC_CANTRIP_ID = "read_magic_cantrip"
```

Then add these functions after `powers_known_cap` (~line 67):

```python
def cantrip_count(level: int) -> int:
    """CC5 cantrips known/memorisable by character level: 2 (1-2), 3 (3-4), 4 (5+)."""
    if level <= 2:
        return 2
    if level <= 4:
        return 3
    return 4


def is_dedicated_arcane(cls: CharClass, data: GameData) -> bool:
    """A 'dedicated arcane spell caster' (CC5): arcane caster type AND the class
    grants a 1st-level spell slot at character level 1 (casts arcane spells with
    access to spells at level 1). Excludes scroll-only/no-slot arcane classes
    (Mage) and arcane classes that first cast above level 1 (Arcane Bard)."""
    if caster_type_of(cls, data) != "arcane":
        return False
    row = cls.progression.get(1)
    return bool(row and row.spell_slots and row.spell_slots.get(1, 0) > 0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips.py -k "cantrip_count or dedicated" -q`
Expected: PASS. (If `arcane_bard` or `mage` ids differ, confirm via `data.classes` keys — they are defined in `data/classes/`.)

- [ ] **Step 5: Commit**

```bash
git add aose/engine/spells.py tests/test_cantrips.py
git commit -m "feat(engine): cantrip_count + is_dedicated_arcane helpers"
```

---

## Task 5: Engine — level-0 injection into accessible_levels / memorizable_slots

**Files:**
- Modify: `aose/engine/spells.py` (`accessible_levels` ~47, `memorizable_slots` ~55; add private `_cantrip_cap` + public `beginning_cantrip_count`)
- Test: `tests/test_cantrips.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cantrips.py`:

```python
from aose.models import RuleSet, ClassEntry


def test_level_zero_injected_only_when_rule_and_dedicated():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    cls = data.classes["magic_user"]
    e1 = ClassEntry(class_id="magic_user", level=1)
    rs_on = RuleSet(cantrips=True)
    rs_off = RuleSet()

    # Off / no args -> unchanged base behaviour
    assert spells.memorizable_slots(e1, cls) == {1: 1}
    assert spells.accessible_levels(e1, cls) == {1}
    assert spells.memorizable_slots(e1, cls, data, rs_off) == {1: 1}

    # On -> level-0 cap = 2 at level 1
    assert spells.memorizable_slots(e1, cls, data, rs_on) == {0: 2, 1: 1}
    assert 0 in spells.accessible_levels(e1, cls, data, rs_on)

    # Cantrip cap scales with level
    e5 = ClassEntry(class_id="magic_user", level=5)
    assert spells.memorizable_slots(e5, cls, data, rs_on)[0] == 4


def test_level_zero_not_injected_for_non_dedicated():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    rs_on = RuleSet(cantrips=True)
    e = ClassEntry(class_id="cleric", level=1)
    cls = data.classes["cleric"]
    assert 0 not in spells.memorizable_slots(e, cls, data, rs_on)


def test_beginning_cantrip_count():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    mu = ClassEntry(class_id="magic_user", level=1)
    assert spells.beginning_cantrip_count(mu, data.classes["magic_user"], data,
                                          RuleSet(cantrips=True)) == 2
    assert spells.beginning_cantrip_count(mu, data.classes["magic_user"], data,
                                          RuleSet()) == 0
    cl = ClassEntry(class_id="cleric", level=1)
    assert spells.beginning_cantrip_count(cl, data.classes["cleric"], data,
                                          RuleSet(cantrips=True)) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips.py -k "level_zero or beginning_cantrip" -q`
Expected: FAIL — `memorizable_slots()` takes 2 positional args; `beginning_cantrip_count` missing.

- [ ] **Step 3: Add `_cantrip_cap` and rewrite the two accessors**

In `aose/engine/spells.py`, add after `is_dedicated_arcane` (from Task 4):

```python
def _cantrip_cap(entry: ClassEntry, cls: CharClass,
                 data: GameData | None, ruleset: "RuleSet | None") -> int:
    """Number of cantrips (level-0 spells) this caster may know/memorise, or 0
    when the rule is off, args are missing, or the class is not dedicated arcane."""
    if data is None or ruleset is None or not getattr(ruleset, "cantrips", False):
        return 0
    if not is_dedicated_arcane(cls, data):
        return 0
    return cantrip_count(entry.level)


def beginning_cantrip_count(entry: ClassEntry, cls: CharClass,
                            data: GameData, ruleset: "RuleSet") -> int:
    """Cantrips a dedicated arcane caster begins with (= the level cap), else 0."""
    return _cantrip_cap(entry, cls, data, ruleset)
```

Replace `accessible_levels` (currently lines ~47-52):

```python
def accessible_levels(entry: ClassEntry, cls: CharClass,
                      data: GameData | None = None,
                      ruleset: "RuleSet | None" = None) -> set[int]:
    """Spell levels the class can cast at the entry's level (has >=1 slot). With
    ``data``+``ruleset`` and the Cantrips rule on, includes level 0 for dedicated
    arcane casters."""
    row = _level_row(entry, cls)
    levels = set() if (row is None or not row.spell_slots) else {
        lvl for lvl, n in row.spell_slots.items() if n > 0
    }
    if _cantrip_cap(entry, cls, data, ruleset) > 0:
        levels.add(0)
    return levels
```

Replace `memorizable_slots` (currently lines ~55-61):

```python
def memorizable_slots(entry: ClassEntry, cls: CharClass,
                      data: GameData | None = None,
                      ruleset: "RuleSet | None" = None) -> dict[int, int]:
    """spell-level -> slot count at the entry's level. With ``data``+``ruleset``
    and the Cantrips rule on, includes ``{0: cantrip_count(level)}`` for a
    dedicated arcane caster (the level-0 memorise cap)."""
    row = _level_row(entry, cls)
    slots = {} if (row is None or not row.spell_slots) else dict(row.spell_slots)
    cap = _cantrip_cap(entry, cls, data, ruleset)
    if cap > 0:
        slots[0] = cap
    return slots
```

Note: `RuleSet` is already imported at the top of `spells.py` (`from aose.models import ... RuleSet ...`), so the string annotations resolve; using it unquoted is fine too.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips.py -k "level_zero or beginning_cantrip" -q`
Expected: PASS.

- [ ] **Step 5: Run the existing spell + energy-drain tests (no regressions)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py tests/test_data_loading.py -q` and `.venv\Scripts\python.exe -m pytest tests/ -q -k energy_drain`
Expected: PASS — base callers pass no `data`/`ruleset`, so behaviour is unchanged.

- [ ] **Step 6: Commit**

```bash
git add aose/engine/spells.py tests/test_cantrips.py
git commit -m "feat(engine): inject level-0 cantrip cap into slot/level accessors"
```

---

## Task 6: Engine — read-magic demotion + auto-grant in known/learnable

**Files:**
- Modify: `aose/engine/spells.py` (`known_spells` ~74, `learnable_spells` ~93; add `_read_magic_demoted`)
- Test: `tests/test_cantrips.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cantrips.py`:

```python
def test_read_magic_demotion_hides_l1_and_grants_cantrip():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    cls = data.classes["magic_user"]
    rs = RuleSet(cantrips=True, read_magic_cantrip=True)
    # Spellbook holds the old L1 read magic; demotion should hide it and surface
    # the level-0 cantrip as auto-known.
    e = ClassEntry(class_id="magic_user", level=1,
                   spellbook=["magic_user_read_magic", "magic_user_magic_missile"])
    known = {s.id for s in spells.known_spells(e, cls, data, rs)}
    assert "magic_user_read_magic" not in known
    assert "read_magic_cantrip" in known          # auto-granted
    assert "magic_user_magic_missile" in known

    learnable = {s.id for s in spells.learnable_spells(e, cls, data, rs)}
    assert "magic_user_read_magic" not in learnable
    assert "read_magic_cantrip" not in learnable   # already auto-known


def test_read_magic_not_demoted_when_rule_off():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    cls = data.classes["magic_user"]
    rs = RuleSet(cantrips=True)  # read_magic_cantrip OFF
    e = ClassEntry(class_id="magic_user", level=1,
                   spellbook=["magic_user_read_magic"])
    known = {s.id for s in spells.known_spells(e, cls, data, rs)}
    assert "magic_user_read_magic" in known
    assert "read_magic_cantrip" not in known
    learnable = {s.id for s in spells.learnable_spells(e, cls, data, rs)}
    assert "magic_user_read_magic" not in learnable  # already in book
    assert "read_magic_cantrip" in learnable          # a learnable cantrip
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips.py -k "read_magic" -q`
Expected: FAIL — `known_spells()`/`learnable_spells()` take no `ruleset`; demotion/auto-grant absent.

- [ ] **Step 3: Add `_read_magic_demoted` and thread `ruleset` through both functions**

In `aose/engine/spells.py`, add after `_cantrip_cap`:

```python
def _read_magic_demoted(cls: CharClass, data: GameData | None,
                        ruleset: "RuleSet | None") -> bool:
    """True when Read Magic Cantrip applies to this caster: both rules on and a
    dedicated arcane caster."""
    if data is None or ruleset is None:
        return False
    if not (getattr(ruleset, "cantrips", False)
            and getattr(ruleset, "read_magic_cantrip", False)):
        return False
    return is_dedicated_arcane(cls, data)
```

Replace `known_spells` (lines ~74-90). Add the `ruleset` param and the arcane demotion/auto-grant:

```python
def known_spells(entry: ClassEntry, cls: CharClass, data: GameData,
                 ruleset: "RuleSet | None" = None) -> list[Spell]:
    """Spells the character knows.

    arcane: the resolved spellbook (in stored order); with Read Magic Cantrip on,
    the L1 read magic is hidden and the level-0 read-magic cantrip is auto-known
    (beyond the cantrip cap).
    divine: every spell on the class's lists at an accessible level (by level,name).
    """
    ctype = caster_type_of(cls, data)
    if ctype in ("arcane", "mental"):
        out = [data.spells[s] for s in entry.spellbook if s in data.spells]
        if ctype == "arcane" and _read_magic_demoted(cls, data, ruleset):
            out = [s for s in out if s.id not in DEMOTED_READ_MAGIC_IDS]
            rm = data.spells.get(READ_MAGIC_CANTRIP_ID)
            if rm is not None and rm.id not in entry.spellbook and _on_class_lists(rm, cls):
                out.append(rm)
        return out
    if ctype == "divine":
        levels = accessible_levels(entry, cls)
        return sorted(
            (s for s in data.spells.values()
             if _on_class_lists(s, cls) and s.level in levels),
            key=lambda s: (s.level, s.name),
        )
    return []
```

Replace `learnable_spells` (lines ~93-111). Add `ruleset`, pass it to `accessible_levels`, and hide demoted ids:

```python
def learnable_spells(entry: ClassEntry, cls: CharClass, data: GameData,
                     ruleset: "RuleSet | None" = None) -> list[Spell]:
    """Arcane: accessible-level spells on the class's lists not yet known (with the
    Cantrips rule, level-0 cantrips are accessible; demoted/auto-known read magic
    is excluded). Mental: every on-list power not yet known (no level filter)."""
    ctype = caster_type_of(cls, data)
    known = set(entry.spellbook)
    if ctype == "mental":
        return sorted(
            (s for s in data.spells.values()
             if _on_class_lists(s, cls) and s.id not in known),
            key=lambda s: (s.level, s.name),
        )
    if ctype != "arcane":
        return []
    levels = accessible_levels(entry, cls, data, ruleset)
    hide: set[str] = set()
    if _read_magic_demoted(cls, data, ruleset):
        hide = DEMOTED_READ_MAGIC_IDS | {READ_MAGIC_CANTRIP_ID}
    return sorted(
        (s for s in data.spells.values()
         if _on_class_lists(s, cls) and s.level in levels
         and s.id not in known and s.id not in hide),
        key=lambda s: (s.level, s.name),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips.py -k "read_magic" -q`
Expected: PASS.

- [ ] **Step 5: Run existing spell tests (no regressions)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py tests/test_mental_powers.py -q`
Expected: PASS — `known_spells`/`learnable_spells` keep working when `ruleset` is omitted.

- [ ] **Step 6: Commit**

```bash
git add aose/engine/spells.py tests/test_cantrips.py
git commit -m "feat(engine): read-magic demotion + cantrip auto-grant in known/learnable"
```

---

## Task 7: Engine — learn / assign_slot obey cantrip caps (standard) + advanced block

**Files:**
- Modify: `aose/engine/spells.py` (`_free_slots_at` ~223, `assign_slot` ~229, `learn` ~162)
- Test: `tests/test_cantrips.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cantrips.py`:

```python
def test_learn_cantrips_standard_obeys_cap():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    cls = data.classes["magic_user"]
    rs = RuleSet(cantrips=True)  # standard spell books
    e = ClassEntry(class_id="magic_user", level=1)
    e = spells.learn(e, cls, data, rs, "cantrip_spark")
    e = spells.learn(e, cls, data, rs, "cantrip_vanish")
    assert e.spellbook == ["cantrip_spark", "cantrip_vanish"]
    # Third cantrip exceeds the level-1 cap of 2 -> rejected
    try:
        spells.learn(e, cls, data, rs, "cantrip_rune")
        assert False, "expected SpellError for exceeding cantrip cap"
    except spells.SpellError:
        pass


def test_learn_cantrips_advanced_is_copy_only():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    cls = data.classes["magic_user"]
    rs = RuleSet(cantrips=True, advanced_spell_books=True)
    e = ClassEntry(class_id="magic_user", level=1)
    try:
        spells.learn(e, cls, data, rs, "cantrip_spark")
        assert False, "expected SpellError: cantrips are copy-only under advanced"
    except spells.SpellError:
        pass


def test_assign_cantrip_slot_and_memorise_cap():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    cls = data.classes["magic_user"]
    rs = RuleSet(cantrips=True)
    e = ClassEntry(class_id="magic_user", level=1,
                   spellbook=["cantrip_spark", "cantrip_vanish"])
    e = spells.assign_slot(e, cls, data, 0, "cantrip_spark", ruleset=rs)
    e = spells.assign_slot(e, cls, data, 0, "cantrip_vanish", ruleset=rs)
    assert len([s for s in e.slots if s.level == 0]) == 2
    # No third level-0 slot (cap 2)
    try:
        spells.assign_slot(e, cls, data, 0, "cantrip_spark", ruleset=rs)
        assert False, "expected SpellError: level-0 cap reached"
    except spells.SpellError:
        pass


def test_assign_auto_granted_read_magic_cantrip_is_memorisable():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    cls = data.classes["magic_user"]
    rs = RuleSet(cantrips=True, read_magic_cantrip=True)
    e = ClassEntry(class_id="magic_user", level=1)  # not in spellbook, auto-known
    e = spells.assign_slot(e, cls, data, 0, "read_magic_cantrip", ruleset=rs)
    assert any(s.spell_id == "read_magic_cantrip" for s in e.slots)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips.py -k "learn_cantrips or assign" -q`
Expected: FAIL — `learn` rejects level-0 (no `0` in `accessible_levels` without args / standard cap is 0); `assign_slot` has no `ruleset` kwarg.

- [ ] **Step 3: Thread `data`/`ruleset` into the cap/level lookups**

In `aose/engine/spells.py`:

(a) Replace `_free_slots_at` (lines ~223-226):

```python
def _free_slots_at(entry: ClassEntry, cls: CharClass, level: int,
                   data: GameData | None = None,
                   ruleset: "RuleSet | None" = None) -> int:
    cap = memorizable_slots(entry, cls, data, ruleset).get(level, 0)
    used = sum(1 for s in entry.slots if s.level == level)
    return cap - used
```

(b) In `learn` (lines ~162-205), change the two internal accessor calls to pass `data, ruleset`:

- The accessible-level check (was `if spell.level not in accessible_levels(entry, cls):`):

```python
    if spell.level not in accessible_levels(entry, cls, data, ruleset):
        raise SpellError(f"{spell_id!r} (level {spell.level}) is not castable yet")
```

- The standard-rules cap (was `cap = memorizable_slots(entry, cls).get(spell.level, 0)`):

```python
        cap = memorizable_slots(entry, cls, data, ruleset).get(spell.level, 0)
```

The existing `if ruleset.advanced_spell_books: raise SpellError("...must be copied...")` guard stays as-is and **above** the cantrip path — that is what makes cantrips copy-only under Advanced (no carve-out needed).

(c) Replace `assign_slot` signature + the two internal calls (lines ~229-249). Add a `ruleset` parameter (keyword, defaults None) and pass `data, ruleset`:

```python
def assign_slot(entry: ClassEntry, cls: CharClass, data: GameData, level: int,
                spell_id: str, reversed: bool = False,
                ruleset: "RuleSet | None" = None) -> ClassEntry:
    """Memorize ``spell_id`` into a free slot at ``level`` (level 0 = a cantrip
    when the Cantrips rule is on)."""
    spell = _require_spell(data, spell_id)
    if spell.level != level:
        raise SpellError(f"{spell_id!r} is level {spell.level}, not {level}")
    known_ids = {s.id for s in known_spells(entry, cls, data, ruleset)}
    if spell_id not in known_ids:
        raise SpellError(f"{spell_id!r} is not known and cannot be memorized")
    if _free_slots_at(entry, cls, level, data, ruleset) <= 0:
        cap = memorizable_slots(entry, cls, data, ruleset).get(level, 0)
        raise SpellError(f"No free level-{level} slot (cap {cap})")
    if reversed and not (caster_type_of(cls, data) == "arcane" and spell.reversible):
        raise SpellError(f"{spell_id!r} cannot be memorized reversed")
    new = SpellSlot(level=level, spell_id=spell_id, reversed=reversed, spent=False)
    return entry.model_copy(update={"slots": [*entry.slots, new]})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips.py -k "learn_cantrips or assign" -q`
Expected: PASS.

- [ ] **Step 5: Run existing spell tests (no regressions)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py -q`
Expected: PASS — `assign_slot` callers that omit `ruleset` keep the old behaviour.

- [ ] **Step 6: Commit**

```bash
git add aose/engine/spells.py tests/test_cantrips.py
git commit -m "feat(engine): cantrips obey standard cap / advanced copy-only via learn+assign"
```

---

## Task 8: Spell books & scrolls — cantrips copyable under Advanced

**Files:**
- Modify: `aose/engine/spell_sources.py` (`copyable_spell_ids` ~138, `copy_spell` ~169)
- Test: `tests/test_cantrips.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cantrips.py`:

```python
def test_cantrip_copyable_from_source_under_advanced():
    import random
    from aose.data.loader import GameData
    from aose.engine import spell_sources as ss
    data = GameData.load(DATA_DIR)
    cls = data.classes["magic_user"]
    rs = RuleSet(cantrips=True, advanced_spell_books=True)
    e = ClassEntry(class_id="magic_user", level=1)
    sources = ss.add_spell_source([], "spellbook", "arcane", ["cantrip_spark"], data)
    inst = sources[0].instance_id
    copyable = ss.copyable_spell_ids(sources[0], e, cls, data, rs)
    assert "cantrip_spark" in copyable
    # Force a success (INT 18 + roll 1) and confirm it lands in the spellbook.
    new_e, _src, ok = ss.copy_spell(e, cls, data, rs, 18, sources, inst,
                                    "cantrip_spark", rng=random.Random(0))
    assert ok is True
    assert "cantrip_spark" in new_e.spellbook
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips.py -k "copyable" -q`
Expected: FAIL — `copyable_spell_ids()` takes 4 positional args (no `ruleset`), and the level-0 cantrip is not in `learnable_spells` without `ruleset`, so it is never copyable.

- [ ] **Step 3: Thread `ruleset` into copyable_spell_ids and its caller**

In `aose/engine/spell_sources.py`:

(a) Replace `copyable_spell_ids` (lines ~138-150):

```python
def copyable_spell_ids(source: SpellSource, entry: ClassEntry, cls: CharClass,
                       data: GameData, ruleset=None) -> set[str]:
    """Spell ids in ``source`` an arcane caster may attempt to copy right now:
    arcane source, spell arcane-learnable for this class (on-list, accessible
    level — including level-0 cantrips when the rule is on — not already known),
    and not already marked ``copy_failed`` on this source."""
    if source.caster_type != "arcane":
        return set()
    learnable = {s.id for s in spell_engine.learnable_spells(entry, cls, data, ruleset)}
    return {
        e.spell_id for e in source.entries
        if not e.copy_failed and e.spell_id in learnable
    }
```

(b) In `copy_spell` (line ~169), pass `ruleset` to the call:

```python
    if spell_id not in copyable_spell_ids(src, entry, cls, data, ruleset):
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips.py -k "copyable" -q`
Expected: PASS. (If `random.Random(0)` does not yield a success, the test forces INT 18 = 90% chance; pick a seed whose first `1d100` roll ≤ 90 — `Random(0)` rolls low. If needed, swap to `random.Random(1)`.)

- [ ] **Step 5: Run existing spell-sources tests**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q -k "spell_source or scroll or copy"`
Expected: PASS — `copyable_spell_ids` callers that omit `ruleset` are unaffected.

- [ ] **Step 6: Commit**

```bash
git add aose/engine/spell_sources.py tests/test_cantrips.py
git commit -m "feat(engine): level-0 cantrips copyable from books/scrolls under advanced"
```

---

## Task 9: Sheet view — surface cantrips + read-magic auto-grant

**Files:**
- Modify: `aose/sheet/view.py` (`spells_view` ~785-826, `spellbook_view` ~842-843, `OPTIONAL_RULE_LABELS` ~45)
- Modify: `aose/web/routes.py` (`sheet_spell_assign` ~1028)
- Test: `tests/test_cantrips.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cantrips.py`:

```python
def test_optional_rule_labels_include_cantrips():
    from aose.sheet.view import OPTIONAL_RULE_LABELS
    assert "cantrips" in OPTIONAL_RULE_LABELS
    assert "read_magic_cantrip" in OPTIONAL_RULE_LABELS


def test_spells_view_shows_cantrip_group():
    from aose.data.loader import GameData
    from aose.sheet.view import spells_view
    from aose.models import CharacterSpec, ClassEntry, RuleSet
    data = GameData.load(DATA_DIR)
    spec = CharacterSpec(
        name="Zed", abilities={"STR": 9, "DEX": 9, "CON": 9, "INT": 12, "WIS": 9, "CHA": 9},
        alignment="neutral",
        classes=[ClassEntry(class_id="magic_user", level=1,
                            spellbook=["cantrip_spark"])],
        ruleset=RuleSet(cantrips=True),
    )
    block = next(b for b in spells_view(spec, data) if b.class_id == "magic_user")
    levels = {g.level for g in block.slot_groups}
    assert 0 in levels
    g0 = next(g for g in block.slot_groups if g.level == 0)
    assert g0.cap == 2
    assert "cantrip_spark" in {s.id for s in block.known}
```

Note: confirm the exact `CharacterSpec` constructor shape from an existing sheet test (e.g. `tests/test_sheet*.py` or `tests/test_spells.py`) and match it — abilities may be a dict of ability rows. Adjust the fixture to the real minimal-spec helper if one exists.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips.py -k "optional_rule_labels or spells_view" -q`
Expected: FAIL — labels missing; `spells_view` calls `memorizable_slots`/`known_spells` without `ruleset`, so no level-0 group.

- [ ] **Step 3: Add labels and thread `spec.ruleset` through the views**

In `aose/sheet/view.py`:

(a) `OPTIONAL_RULE_LABELS` (~line 45) — add two entries before the closing `}`:

```python
    "individual_initiative": "Individual Initiative",
    "cantrips": "Cantrips",
    "read_magic_cantrip": "Read Magic Cantrip",
```

(b) In `spells_view`, update the three engine calls (current lines ~785, 786, 825):

```python
        known = spell_engine.known_spells(entry, cls, data, spec.ruleset)
        caps = spell_engine.memorizable_slots(entry, cls, data, spec.ruleset)
```

and the learnable list (inside the `SpellClassView(...)` construction):

```python
            learnable=(
                [] if spec.ruleset.advanced_spell_books
                else [_spell_entry(s)
                      for s in spell_engine.learnable_spells(entry, cls, data, spec.ruleset)]
            ),
```

(c) In `spellbook_view`, update the two engine calls (current lines ~842, 843):

```python
        caps = spell_engine.memorizable_slots(entry, cls, data, spec.ruleset)
        known = spell_engine.known_spells(entry, cls, data, spec.ruleset)
```

(d) In `aose/web/routes.py` `sheet_spell_assign` (~line 1028), pass the ruleset so cantrip slots memorise:

```python
        spec.classes[idx] = spell_engine.assign_slot(
            spec.classes[idx], data.classes[class_id], data, level, spell_id, rev,
            ruleset=spec.ruleset,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips.py -k "optional_rule_labels or spells_view" -q`
Expected: PASS.

- [ ] **Step 5: Run sheet + spell tests**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q -k "sheet or spell"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/sheet/view.py aose/web/routes.py tests/test_cantrips.py
git commit -m "feat(sheet): surface cantrip group + read-magic auto-grant on the sheet"
```

---

## Task 10: Sheet templates — "Cantrips" label for the level-0 group

**Files:**
- Modify: `aose/web/templates/sheet.html` (level headers ~240, 247, 268; drawer ~554, 632/638)
- Modify: `aose/web/templates/sheet_print.html` (level headers — find with grep)

- [ ] **Step 1: Find every level header**

Run:
```bash
grep -n "Level {{ lvl.level }}\|L{{ lvl.level }}\|level-{{ lvl.level }}\|Level {{ grp.level }}\|level', 'equalto', grp.level" aose/web/templates/sheet.html aose/web/templates/sheet_print.html
```
Expected: the spellbook-display headers (`sheet.html` ~240, ~247, ~268), the management-drawer header (`sheet.html` ~554) and its "No level-N spells" hint, plus any mirror in `sheet_print.html`.

- [ ] **Step 2: Replace each level label with a cantrip-aware conditional**

In `aose/web/templates/sheet.html`:

- Line ~240 (meta pips): replace `L{{ lvl.level }} {{ lvl.used }}/{{ lvl.cap }}` with
  `{% if lvl.level == 0 %}Cantrips{% else %}L{{ lvl.level }}{% endif %} {{ lvl.used }}/{{ lvl.cap }}`
- Line ~247 (group header): replace `<span>Level {{ lvl.level }}</span>` with
  `<span>{% if lvl.level == 0 %}Cantrips{% else %}Level {{ lvl.level }}{% endif %}</span>`
- Line ~268 (empty hint): replace `No level-{{ lvl.level }} spells in book yet.` with
  `{% if lvl.level == 0 %}No cantrips in book yet.{% else %}No level-{{ lvl.level }} spells in book yet.{% endif %}`
- Line ~554 (drawer header): replace `<span>Level {{ grp.level }}</span>` with
  `<span>{% if grp.level == 0 %}Cantrips{% else %}Level {{ grp.level }}{% endif %}</span>`

In `aose/web/templates/sheet_print.html`: apply the same `{% if ... == 0 %}Cantrips{% else %}Level N{% endif %}` substitution to whichever spell-level header(s) the grep surfaced.

- [ ] **Step 3: Smoke-test rendering**

Start the app: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`, create (or open) a magic-user with the Cantrips rule on, and confirm the spells section shows a **Cantrips** group with the learnable cantrip list and a 0/2 count. Stop the server when done.

(If a sheet-rendering test exists — e.g. `tests/test_sheet_render.py` — run it: `.venv\Scripts\python.exe -m pytest tests/ -q -k render`.)

- [ ] **Step 4: Commit**

```bash
git add aose/web/templates/sheet.html aose/web/templates/sheet_print.html
git commit -m "feat(sheet): label the level-0 spell group 'Cantrips'"
```

---

## Task 11: Wizard — cantrip picker + cascade clear

**Files:**
- Modify: `aose/web/wizard.py` (`_caster_entries` ~1505-1542, `_apply_spells` ~1546-1575, `_apply_rule_changes` ~451-459)
- Modify: `aose/web/templates/wizard/class_setup.html` (spells section ~139-166)
- Test: `tests/test_cantrips_wizard.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_cantrips_wizard.py`. Match the existing wizard-test style (see `tests/test_wizard*.py` for the draft fixture / TestClient helper; adapt the fixture below to the real helper if one exists):

```python
from pathlib import Path
from aose.data.loader import GameData
from aose.web import wizard

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _mu_draft():
    return {
        "abilities": {"STR": 9, "DEX": 9, "CON": 9, "INT": 12, "WIS": 9, "CHA": 9},
        "class_id": "magic_user",
        "ruleset": {"cantrips": True},
        "spellbooks": {},
    }


def test_caster_entries_exposes_cantrip_block():
    data = GameData.load(DATA_DIR)
    rows = wizard._caster_entries(_mu_draft(), data)
    row = next(r for r in rows if r["class_id"] == "magic_user")
    assert row["cantrip_required"] == 2
    cantrip_ids = {c["id"] for c in row["cantrip_candidates"]}
    assert "cantrip_spark" in cantrip_ids
    assert "read_magic_cantrip" not in cantrip_ids  # rule off -> not auto, still a candidate? see note


def test_apply_spells_stores_cantrips_with_spells():
    data = GameData.load(DATA_DIR)
    draft = _mu_draft()

    class FakeForm:
        def __init__(self, d): self._d = d
        def getlist(self, k): return self._d.get(k, [])

    form = FakeForm({
        "spell_magic_user": ["magic_user_magic_missile"],
        "cantrip_magic_user": ["cantrip_spark", "cantrip_vanish"],
    })
    wizard._apply_spells(draft, form, data)
    book = draft["spellbooks"]["magic_user"]
    assert "magic_user_magic_missile" in book
    assert "cantrip_spark" in book and "cantrip_vanish" in book


def test_toggle_cantrips_off_clears_level_zero():
    from aose.models import RuleSet
    data = GameData.load(DATA_DIR)
    draft = _mu_draft()
    draft["spellbooks"] = {"magic_user": ["cantrip_spark", "magic_user_magic_missile"]}
    wizard._apply_rule_changes(draft, RuleSet(cantrips=True), RuleSet(cantrips=False), data)
    book = draft["spellbooks"]["magic_user"]
    assert "cantrip_spark" not in book
    assert "magic_user_magic_missile" in book
```

Note on the first test's `read_magic_cantrip` assertion: with the Cantrips rule on but Read Magic Cantrip **off**, `read_magic_cantrip` *is* a normal selectable cantrip candidate. Decide the wizard policy and assert accordingly: simplest is to **include** all level-0 cantrips as candidates and let `read_magic_cantrip` be pickable when the dependent rule is off, but **exclude** it (and the demoted L1 read magic) when the dependent rule is on (it is then auto-granted). Adjust the assertion to: `assert "read_magic_cantrip" in cantrip_ids` for a `cantrips=True, read_magic_cantrip=False` draft. Keep the implementation in Step 3 consistent with whatever you assert.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips_wizard.py -q`
Expected: FAIL — `_caster_entries` rows have no `cantrip_required`/`cantrip_candidates`; `_apply_spells` ignores `cantrip_*`; `_apply_rule_changes` does not clear level-0.

- [ ] **Step 3: Implement the cantrip picker in the wizard**

In `aose/web/wizard.py`:

(a) In `_caster_entries`, inside the per-class loop, after computing `candidates` and before `rows.append({...})`, build the cantrip block:

```python
        is_dedicated = (ctype == "arcane"
                        and spell_engine.is_dedicated_arcane(cls, data))
        cantrip_required = (spell_engine.beginning_cantrip_count(entry, cls, data, ruleset)
                            if is_dedicated else 0)
        cantrip_candidates = []
        if cantrip_required:
            hide = set()
            if ruleset.read_magic_cantrip:
                hide = spell_engine.DEMOTED_READ_MAGIC_IDS | {spell_engine.READ_MAGIC_CANTRIP_ID}
            cantrip_candidates = [
                {"id": s.id, "name": s.name, "level": s.level,
                 "description": s.description,
                 "selected": s.id in books.get(cid, [])}
                for s in sorted(
                    (sp for sp in data.spells.values()
                     if sp.level == 0 and set(sp.spell_lists) & enabled_lists
                     and sp.id not in hide),
                    key=lambda sp: sp.name,
                )
            ]
```

Then add to the appended row dict:

```python
        rows.append({
            "class_id": cid,
            "class_name": cls.name,
            "caster_type": ctype,
            "required": (spell_engine.beginning_spell_count(entry, cls, int_score, ruleset)
                         if ctype in ("arcane", "mental") else 0),
            "advanced": ruleset.advanced_spell_books,
            "candidates": [...],          # unchanged
            "cantrip_required": cantrip_required,
            "cantrip_candidates": cantrip_candidates,
        })
```

(b) In `_apply_spells`, after the existing per-class spell handling that builds `chosen` and validates it (but still inside the `for cid in _class_ids(draft)` loop, after `books[cid] = chosen` is computed — and only for arcane), append cantrip handling. Replace the arcane storage so cantrips merge into the same book:

```python
        chosen = list(dict.fromkeys(form.getlist(f"spell_{cid}")))
        required = spell_engine.beginning_spell_count(entry, cls, int_score, ruleset)
        noun = "power" if ctype == "mental" else "starting spell"
        if len(chosen) != required:
            raise HTTPException(
                400, f"{cls.name} must choose exactly {required} {noun}(s); "
                     f"got {len(chosen)}."
            )
        accessible = spell_engine.accessible_levels(entry, cls)
        for sid in chosen:
            spell = data.spells.get(sid)
            on_list = spell is not None and bool(set(spell.spell_lists) & set(cls.spell_lists))
            if not on_list or (ctype == "arcane" and spell.level not in accessible):
                raise HTTPException(400, f"{sid!r} is not a valid {cls.name} {noun}.")

        # Cantrips (CC5): a separate pick, merged into the same spell book.
        cantrips_chosen: list[str] = []
        if ctype == "arcane" and spell_engine.is_dedicated_arcane(cls, data):
            cantrip_required = spell_engine.beginning_cantrip_count(entry, cls, data, ruleset)
            cantrips_chosen = list(dict.fromkeys(form.getlist(f"cantrip_{cid}")))
            if len(cantrips_chosen) != cantrip_required:
                raise HTTPException(
                    400, f"{cls.name} must choose exactly {cantrip_required} cantrip(s); "
                         f"got {len(cantrips_chosen)}."
                )
            for sid in cantrips_chosen:
                spell = data.spells.get(sid)
                on_list = spell is not None and bool(set(spell.spell_lists) & set(cls.spell_lists))
                if not on_list or spell.level != 0:
                    raise HTTPException(400, f"{sid!r} is not a valid {cls.name} cantrip.")
        books[cid] = [*chosen, *cantrips_chosen]
```

(Remove the old `books[cid] = chosen` line — it is replaced by the combined assignment above. Keep the `if ctype == "divine": books[cid] = []; continue` branch unchanged.)

(c) In `_apply_rule_changes`, add a clear block (place it near the `combat_talents` clear, ~line 459, and only when `data is not None`):

```python
    if old_rs.cantrips and not new_rs.cantrips and data is not None:
        books = dict(draft.get("spellbooks", {}))
        for cid, ids in books.items():
            books[cid] = [sid for sid in ids
                          if sid in data.spells and data.spells[sid].level != 0]
        draft["spellbooks"] = books
```

- [ ] **Step 4: Add the cantrip picker to the template**

In `aose/web/templates/wizard/class_setup.html`, inside the `{% for c in caster_classes %}` loop, after the arcane spell `{% else %}...{% endif %}` block (after line ~163's counter, before the closing `</div>` of `.spell-class` at line ~165), add:

```html
        {% if c.cantrip_required %}
        <h5 style="margin-top:10px">Cantrips</h5>
        <p>Choose <strong>{{ c.cantrip_required }}</strong> cantrip(s) (level-0 spells) for your spell book.</p>
        <div class="card-grid" data-required="{{ c.cantrip_required }}">
            {% for s in c.cantrip_candidates %}
            <label class="card {% if s.selected %}selected{% endif %}">
                <input type="checkbox" name="cantrip_{{ c.class_id }}" value="{{ s.id }}"
                       class="spell-checkbox" {% if s.selected %}checked{% endif %}>
                <div class="card-name">{{ s.name }}</div>
                <div class="card-detail small">{{ s.description }}</div>
            </label>
            {% endfor %}
        </div>
        <p class="muted spell-counter">Pick exactly {{ c.cantrip_required }}.</p>
        {% endif %}
```

The existing per-grid JS (lines ~167-186) and `csValidate` (lines ~285-289) already iterate **every** `.spell-class .card-grid[data-required]` with `.spell-checkbox` boxes, so the cantrip grid is counted and gated with no JS change.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cantrips_wizard.py -q`
Expected: PASS.

- [ ] **Step 6: Run the full wizard test suite (no regressions)**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q -k wizard`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add aose/web/wizard.py aose/web/templates/wizard/class_setup.html tests/test_cantrips_wizard.py
git commit -m "feat(wizard): cantrip picker on the spells step + cascade clear"
```

---

## Task 12: Docs + full suite

**Files:**
- Modify: `docs/CHANGELOG.md` (top row)
- Modify: `docs/ARCHITECTURE.md` (Spells subsystem + Content sources/optional rules)

- [ ] **Step 1: Add the CHANGELOG row**

At the top of the dated table in `docs/CHANGELOG.md`, add a one-line row:

```
| 2026-06-12 | CC5 Cantrips optional rule (+ Read Magic Cantrip) | feat/cc5-cantrips | 2026-06-12-cc5-cantrips |
```

(Match the existing column shape in that file — adjust columns to whatever the table uses.)

- [ ] **Step 2: Update ARCHITECTURE.md in place**

In the **Spells, spell books & mental powers** section, edit the existing prose to note cantrips. Replace the sentence "There is **no special Read Magic rule** — it's an ordinary magic-user spell." with:

```
**Cantrips (CC5, `cantrips` rule)** are level-0 arcane spells for *dedicated
arcane casters* (`spells.is_dedicated_arcane`: arcane caster type + a L1 spell
slot). They ride the normal spellbook/slots — `memorizable_slots` /
`accessible_levels` inject `{0: cantrip_count(level)}` (2/3/4 by level) when
passed `data`+`ruleset`, so the sheet renders a "Cantrips" group and prepare/cast
reuse the spell path. Cantrips obey the active book rule: standard = free learn,
book cap = memorise cap = the cantrip table; advanced = copy-only from books/
scrolls, uncapped book; the memorise cap stays 2/3/4 in both. The dependent
`read_magic_cantrip` rule hides the L1 read magic (`DEMOTED_READ_MAGIC_IDS`) and
auto-grants a level-0 `read_magic_cantrip` (beyond the cap) to dedicated arcane
casters. Spells: `data/spells/carcass_crawler_5_cantrips.yaml`.
```

In the **Content sources & optional rules** section, add `cantrips` / `read_magic_cantrip` to the mental note that every `RuleSet` flag is integrated (no structural change needed — they are wired through `SOURCE_RULES["carcass_crawler_5"]`).

- [ ] **Step 3: Run the full test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing `pytest-current` PermissionError — known Windows quirk).

- [ ] **Step 4: Commit**

```bash
git add docs/CHANGELOG.md docs/ARCHITECTURE.md
git commit -m "docs: record CC5 cantrips in changelog + architecture"
```

---

## Self-review notes (for the implementer)

- **Spec coverage:** flags (T1), settings UI + dependency (T2), data (T3), predicate/count (T4), level-0 injection (T5), read-magic demote/grant (T6), standard cap + advanced copy-only (T7, T8), sheet surfacing + label (T9, T10), wizard picker + clear (T11), docs (T12). Every spec section maps to a task.
- **Backward compatibility:** every new engine param defaults to `None`/off, so `energy_drain.py` and existing tests are untouched (verified in T5/T6/T7 regression steps).
- **Type/name consistency:** `cantrip_count`, `is_dedicated_arcane`, `_cantrip_cap`, `beginning_cantrip_count`, `_read_magic_demoted`, `DEMOTED_READ_MAGIC_IDS`, `READ_MAGIC_CANTRIP_ID` are defined in T4–T6 and reused verbatim in T7–T11.
- **Watch-outs:** confirm the real class ids (`mage`, `arcane_bard`, `illusionist`) and the `CharacterSpec`/wizard-draft fixture shapes against existing tests before writing T4/T9/T11 fixtures; they are the only places this plan assumes a helper it did not read end-to-end.
