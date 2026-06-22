# Scroll Spells in the Spell List — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show every spell a character can cast right now — memorized *and*
scroll-borne — in the sheet's per-caster-type spell list, organized by level, with
inline casting gated by Read Magic (arcane) and language (divine).

**Architecture:** Two new `SpellSource` fields (`language`, `unlocked`); the spell
engine gains scroll cast-gating and a "decipher with Read Magic" mutator; the
sheet view injects scroll rows into the existing spellbook blocks; routes +
templates expose inline casting and a Read button; the add-scroll form is reworked
to allow duplicate spells and a divine language.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, Jinja2, vanilla JS, pytest.

**Spec:** `docs/superpowers/specs/2026-06-22-scroll-casting-in-spell-list-design.md`

---

## Background the engineer must know

- **Run the app:** `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
- **Run tests:** `.venv\Scripts\python.exe -m pytest tests/ -q`
  (A trailing `PermissionError` on `pytest-current` is a known Windows quirk — ignore it.)
- The engine is pure and cycle-free: `models → loader → spells/spell_sources`.
  Engine functions take inputs and return **new** objects; they never mutate args.
- `data.spells` is a flat dict `{spell_id: Spell}`. A `Spell` has `.id`, `.name`,
  `.level`, `.spell_lists`, `.reversible`, `.description`.
- `data.spell_lists` is `{list_id: SpellList}` with `.caster_type` in
  `{"arcane","divine","mental"}`.
- Read Magic spell ids (already defined in `aose/engine/spells.py`):
  `DEMOTED_READ_MAGIC_IDS == {"magic_user_read_magic", "illusionist_read_magic"}`
  and `READ_MAGIC_CANTRIP_ID == "read_magic_cantrip"`.
- Languages: `aose/engine/languages.known_languages(chosen, race, alignment,
  lang_data, granted=...)` returns the character's known-language tokens.
  `granted_languages(spec, data)` supplies class/race feature grants.
  `data.languages` is a `LanguageData` with `.names` (`{id: display}`),
  `.alignment` (`{alignment_id: display}`), `.additional` (`list[id]`).
- A memorized spell is a `SpellSlot` in `ClassEntry.slots` with `.level`,
  `.spell_id`, `.reversed`, `.spent`. `spells.cast_slot(entry, index)` returns a
  new entry with that slot `spent=True`.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `aose/models/character.py` | `SpellSource` data shape | add `language`, `unlocked` |
| `aose/engine/spell_sources.py` | scroll/book rules + mutators | dupes-on-scroll, cast gate, read-magic decipher, known-langs helper |
| `aose/sheet/view.py` | sheet assembly | `ScrollSpellRow`, inject into `spellbook_view`; extend `spell_sources_view`, `spell_source_add_options`, `SpellSourceView`, `SpellbookLevelGroup`, `SpellSourceAddOptions` |
| `aose/web/routes.py` | HTTP routes | add `language`, new `/spell-sources/read`, cast already guarded |
| `aose/web/templates/sheet.html` | spell list render | scroll rows in level groups |
| `aose/web/templates/_equipment_ui.html` | Documents tab | Read button, language, reworked add form |
| `aose/web/static/spell_source_add.js` | add-form UX | builder with quantities + language toggle |
| `tests/test_spell_sources.py` | engine tests | update dupes test; add gate/read/lang tests |
| `tests/test_spellbook_view.py` | view tests | scroll-row injection tests |
| `docs/CHANGELOG.md`, `docs/ARCHITECTURE.md` | docs | landing row + subsystem update |

---

## Task 1: Model — `SpellSource.language` and `unlocked`

**Files:**
- Modify: `aose/models/character.py` (the `SpellSource` class, ~line 145)
- Test: `tests/test_spell_sources.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_spell_sources.py`:

```python
def test_spell_source_new_fields_default(data):
    src = ss.new_spell_source("scroll", "divine", ["faerie_fire"], data)
    assert src.language == "Common"
    assert src.unlocked is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources.py::test_spell_source_new_fields_default -v`
Expected: FAIL (`AttributeError`/validation — fields don't exist yet).

- [ ] **Step 3: Add the fields**

In `aose/models/character.py`, in `class SpellSource`, add after `name`:

```python
    name: str = ""                                # optional label
    # Divine scrolls are written in a language (default Common); a divine scroll
    # is castable only by a character who knows it. Ignored for arcane scrolls
    # and spell books.
    language: str = "Common"
    # Arcane scrolls must be deciphered by casting Read Magic on them before their
    # spells can be cast; this flips True permanently once read. Ignored for
    # divine scrolls and spell books.
    unlocked: bool = False
    entries: list[SpellSourceEntry] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources.py::test_spell_source_new_fields_default -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aose/models/character.py tests/test_spell_sources.py
git commit -m "feat(spell-sources): add language + unlocked to SpellSource"
```

---

## Task 2: Engine — allow duplicate spells on scrolls + store language

**Files:**
- Modify: `aose/engine/spell_sources.py` (`new_spell_source`, `add_spell_source`)
- Test: `tests/test_spell_sources.py`

- [ ] **Step 1: Write the failing tests**

Add:

```python
def test_scroll_allows_duplicate_spells(data):
    src = ss.new_spell_source("scroll", "divine",
                              ["cleric_cure_light_wounds"] * 3, data, language="Common")
    assert [e.spell_id for e in src.entries] == ["cleric_cure_light_wounds"] * 3
    assert src.language == "Common"


def test_spellbook_still_rejects_duplicates(data):
    with pytest.raises(ss.SpellSourceError):
        ss.new_spell_source("spellbook", "arcane",
                            ["magic_user_sleep", "magic_user_sleep"], data)


def test_scroll_cap_counts_duplicates(data):
    # 8 charges (even all-same) still exceeds the 7 cap.
    with pytest.raises(ss.SpellSourceError):
        ss.new_spell_source("scroll", "divine",
                            ["cleric_cure_light_wounds"] * 8, data)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources.py::test_scroll_allows_duplicate_spells -v`
Expected: FAIL (currently raises on duplicates).

- [ ] **Step 3: Update `new_spell_source`**

In `aose/engine/spell_sources.py`, change the signature and the duplicate check.
Replace the current signature line and the duplicate guard:

```python
def new_spell_source(kind: Kind, caster_type: CasterType, spell_ids: list[str],
                     data: GameData, name: str = "",
                     list_id: str | None = None,
                     language: str = "Common") -> SpellSource:
    """Build a validated SpellSource.

    Spellbooks are coerced to ``arcane``.  Every spell must exist and match
    ``caster_type`` (or, when ``list_id`` is given, be on that exact list).
    Scrolls may list the same spell more than once (each entry is one charge);
    spell books may not.  ``language`` is stored for divine scrolls (default
    Common).  No spell-level filter — a document may hold spells of any level."""
    if kind == "spellbook":
        caster_type = "arcane"
    if not spell_ids:
        raise SpellSourceError("a spell book / scroll must contain at least one spell")
    if kind == "scroll" and len(spell_ids) > MAX_SCROLL_SPELLS:
        raise SpellSourceError(f"a scroll holds at most {MAX_SCROLL_SPELLS} spells")
    if kind == "spellbook" and len(set(spell_ids)) != len(spell_ids):
        raise SpellSourceError("a spell book cannot list the same spell twice")
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
        language=language.strip() or "Common",
        entries=[SpellSourceEntry(spell_id=sid) for sid in spell_ids],
    )
```

- [ ] **Step 4: Thread `language` through `add_spell_source`**

Replace `add_spell_source`:

```python
def add_spell_source(sources: list[SpellSource], kind: Kind, caster_type: CasterType,
                     spell_ids: list[str], data: GameData, name: str = "",
                     list_id: str | None = None,
                     language: str = "Common") -> list[SpellSource]:
    """Add-only append (GM grant / loot); no gold."""
    return [*sources,
            new_spell_source(kind, caster_type, spell_ids, data, name, list_id, language)]
```

- [ ] **Step 5: Update the now-obsolete duplicate test**

The existing `test_new_spell_source_rejects_duplicates` asserts scrolls reject
dupes — that is no longer true. Replace its body so it targets a spellbook:

```python
def test_new_spell_source_rejects_duplicates(data):
    # Spell books still reject duplicates; scrolls now allow them (see
    # test_scroll_allows_duplicate_spells).
    with pytest.raises(ss.SpellSourceError):
        ss.new_spell_source("spellbook", "arcane",
                            ["magic_user_sleep", "magic_user_sleep"], data)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources.py -v`
Expected: PASS (all, including the updated duplicate test).

- [ ] **Step 7: Commit**

```bash
git add aose/engine/spell_sources.py tests/test_spell_sources.py
git commit -m "feat(spell-sources): allow duplicate spells on scrolls; store language"
```

---

## Task 3: Engine — cast gate (Read Magic / language)

**Files:**
- Modify: `aose/engine/spell_sources.py`
- Test: `tests/test_spell_sources.py`

- [ ] **Step 1: Write the failing tests**

Add (after the existing `_mu_spec` helper). Also add a cleric helper:

```python
def _cleric_spec(sources=None, languages=None):
    return CharacterSpec(
        name="Cl", abilities={"STR": 10, "INT": 10, "WIS": 13, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="cleric", level=1)],
        alignment="neutral", ruleset=RuleSet(),
        languages=list(languages or []),
        spell_sources=sources or [],
    )


def test_arcane_scroll_blocked_until_unlocked(data):
    scroll = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], data)
    spec = _mu_spec()
    assert ss.scroll_cast_block_reason(scroll, spec, data) == "needs Read Magic"
    assert ss.can_cast_scroll(scroll, spec, data) is False
    scroll.unlocked = True
    assert ss.scroll_cast_block_reason(scroll, spec, data) is None
    assert ss.can_cast_scroll(scroll, spec, data) is True


def test_divine_scroll_gated_by_language(data):
    common = ss.new_spell_source("scroll", "divine", ["cleric_cure_light_wounds"], data,
                                 language="Common")
    exotic = ss.new_spell_source("scroll", "divine", ["cleric_cure_light_wounds"], data,
                                 language="dragon")
    spec = _cleric_spec()  # knows Common (native), not Dragon
    assert ss.can_cast_scroll(common, spec, data) is True
    assert ss.scroll_cast_block_reason(exotic, spec, data) == "can't read dragon"
    spec_dragon = _cleric_spec(languages=["dragon"])
    assert ss.can_cast_scroll(exotic, spec_dragon, data) is True


def test_wrong_caster_type_blocked(data):
    divine_scroll = ss.new_spell_source("scroll", "divine", ["cleric_cure_light_wounds"], data)
    assert ss.scroll_cast_block_reason(divine_scroll, _mu_spec(), data) == "not a divine caster"
    book = ss.new_spell_source("spellbook", "arcane", ["magic_user_sleep"], data)
    assert ss.scroll_cast_block_reason(book, _mu_spec(), data) == "not a scroll"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources.py -k "scroll_blocked or gated_by_language or wrong_caster" -v`
Expected: FAIL (`scroll_cast_block_reason` undefined).

- [ ] **Step 3: Implement the gate + known-languages helper**

In `aose/engine/spell_sources.py`, add the import near the top (with the other
engine imports):

```python
from aose.engine import languages as lang_engine
```

Then replace `can_cast_scroll` with the gate pair and add the helper:

```python
def _character_known_languages(spec: CharacterSpec, data: GameData) -> set[str]:
    """Case-folded set of the character's known language tokens."""
    race = data.races.get(spec.race_id)
    if race is None:
        langs = [lang_engine.alignment_language(spec.alignment, data.languages),
                 *spec.languages]
    else:
        langs = lang_engine.known_languages(
            spec.languages, race, spec.alignment, data.languages,
            granted=lang_engine.granted_languages(spec, data),
        )
    return {l.casefold() for l in langs}


def scroll_cast_block_reason(source: SpellSource, spec: CharacterSpec,
                             data: GameData) -> str | None:
    """None when the scroll spell is castable now; otherwise a short reason.

    Arcane scrolls need a matching caster AND to have been deciphered
    (``unlocked``).  Divine scrolls need a matching caster AND knowledge of the
    scroll's ``language``.  Spell books are never castable."""
    if source.kind != "scroll":
        return "not a scroll"
    if source.caster_type not in character_caster_types(spec, data):
        return f"not a {source.caster_type} caster"
    if source.caster_type == "arcane":
        return None if source.unlocked else "needs Read Magic"
    if source.language.casefold() not in _character_known_languages(spec, data):
        return f"can't read {source.language}"
    return None


def can_cast_scroll(source: SpellSource, spec: CharacterSpec, data: GameData) -> bool:
    """True when the scroll spell is castable now (see ``scroll_cast_block_reason``)."""
    return scroll_cast_block_reason(source, spec, data) is None
```

- [ ] **Step 4: Fix the existing caster-type test**

The old `test_can_cast_scroll_matches_caster_type` builds an *unlocked-by-default*
arcane scroll and asserts `True`; that now fails. Update it:

```python
def test_can_cast_scroll_matches_caster_type(data):
    arcane_scroll = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], data)
    arcane_scroll.unlocked = True   # deciphered, so type-match is the question
    divine_scroll = ss.new_spell_source("scroll", "divine", ["cleric_cure_light_wounds"], data)
    spec = _mu_spec()
    assert ss.can_cast_scroll(arcane_scroll, spec, data) is True
    assert ss.can_cast_scroll(divine_scroll, spec, data) is False
    # spell books are never castable
    book = ss.new_spell_source("spellbook", "arcane", ["magic_user_sleep"], data)
    assert ss.can_cast_scroll(book, spec, data) is False
```

- [ ] **Step 5: Run to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add aose/engine/spell_sources.py tests/test_spell_sources.py
git commit -m "feat(spell-sources): gate scroll casting on Read Magic / language"
```

---

## Task 4: Engine — decipher an arcane scroll with Read Magic

**Files:**
- Modify: `aose/engine/spell_sources.py`
- Test: `tests/test_spell_sources.py`

- [ ] **Step 1: Write the failing tests**

Add at the top of the test module (with the other model imports):

```python
from aose.engine import spells as se
```

Then the tests:

```python
def _mu_with_read_magic_memorized(data):
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_user_read_magic"])
    cls = data.classes["magic_user"]
    e = se.assign_slot(e, cls, data, level=1, spell_id="magic_user_read_magic")
    scroll = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], data)
    spec = CharacterSpec(
        name="Mu", abilities={"STR": 10, "INT": 13, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[e], alignment="neutral", ruleset=RuleSet(),
        spell_sources=[scroll],
    )
    return spec, scroll.instance_id


def test_read_scroll_burns_slot_and_unlocks(data):
    spec, iid = _mu_with_read_magic_memorized(data)
    assert ss.ready_read_magic_slot(spec, data) == (0, 0)
    classes, sources = ss.read_scroll(spec, data, iid)
    assert classes[0].slots[0].spent is True          # the Read Magic cast is burned
    assert sources[0].unlocked is True


def test_read_scroll_requires_memorized_read_magic(data):
    scroll = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], data)
    spec = _mu_spec(sources=[scroll])                  # no Read Magic memorized
    assert ss.ready_read_magic_slot(spec, data) is None
    with pytest.raises(ss.SpellSourceError):
        ss.read_scroll(spec, data, scroll.instance_id)


def test_read_scroll_rejects_divine_and_already_unlocked(data):
    divine = ss.new_spell_source("scroll", "divine", ["cleric_cure_light_wounds"], data)
    spec, iid = _mu_with_read_magic_memorized(data)
    spec.spell_sources = [*spec.spell_sources, divine]
    with pytest.raises(ss.SpellSourceError):
        ss.read_scroll(spec, data, divine.instance_id)         # divine needs no reading
    classes, sources = ss.read_scroll(spec, data, iid)
    spec.classes, spec.spell_sources = classes, sources
    with pytest.raises(ss.SpellSourceError):
        ss.read_scroll(spec, data, iid)                        # already unlocked
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources.py -k "read_scroll or ready_read_magic" -v`
Expected: FAIL (`ready_read_magic_slot` / `read_scroll` undefined).

- [ ] **Step 3: Implement decipher**

In `aose/engine/spell_sources.py`, add the import of the read-magic ids at the
top (extend the existing `from aose.engine import spells as spell_engine`):

```python
from aose.engine.spells import DEMOTED_READ_MAGIC_IDS, READ_MAGIC_CANTRIP_ID

READ_MAGIC_IDS = DEMOTED_READ_MAGIC_IDS | {READ_MAGIC_CANTRIP_ID}
```

Then add the two functions:

```python
def ready_read_magic_slot(spec: CharacterSpec, data: GameData) -> tuple[int, int] | None:
    """(class index, slot index) of a memorized, not-yet-spent Read Magic slot in
    any arcane class, or None. Used to decipher an arcane scroll."""
    for ci, entry in enumerate(spec.classes):
        cls = data.classes.get(entry.class_id)
        if cls is None or spell_engine.caster_type_of(cls, data) != "arcane":
            continue
        for si, slot in enumerate(entry.slots):
            if not slot.spent and slot.spell_id in READ_MAGIC_IDS:
                return ci, si
    return None


def read_scroll(spec: CharacterSpec, data: GameData, instance_id: str
                ) -> tuple[list[ClassEntry], list[SpellSource]]:
    """Decipher an arcane scroll: spend a memorized Read Magic cast and mark the
    scroll ``unlocked``.  Returns updated (classes, spell_sources); inputs are not
    mutated.  Raises if the document is not an un-deciphered arcane scroll, or no
    Read Magic is memorized."""
    idx = _index(spec.spell_sources, instance_id)
    src = spec.spell_sources[idx]
    if src.kind != "scroll" or src.caster_type != "arcane":
        raise SpellSourceError("only arcane scrolls are deciphered with Read Magic")
    if src.unlocked:
        raise SpellSourceError("this scroll is already deciphered")
    found = ready_read_magic_slot(spec, data)
    if found is None:
        raise SpellSourceError("no memorized Read Magic available to read the scroll")
    ci, si = found
    classes = list(spec.classes)
    classes[ci] = spell_engine.cast_slot(classes[ci], si)
    new_src = src.model_copy(update={"unlocked": True})
    sources = [*spec.spell_sources[:idx], new_src, *spec.spell_sources[idx + 1:]]
    return classes, sources
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/spell_sources.py tests/test_spell_sources.py
git commit -m "feat(spell-sources): decipher arcane scrolls by burning memorized Read Magic"
```

---

## Task 5: View — extend `SpellSourceView` + add options (read/language)

**Files:**
- Modify: `aose/sheet/view.py` (`SpellSourceView`, `SpellSourceAddOptions`,
  `spell_sources_view`, `spell_source_add_options`)
- Test: `tests/test_detail_views.py` (or wherever `spell_sources_view` is tested) — add to `tests/test_spell_sources.py` is wrong layer; create `tests/test_spell_sources_view.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_spell_sources_view.py`:

```python
from pathlib import Path

from aose.data.loader import GameData
from aose.engine import spell_sources as ss
from aose.engine import spells as se
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.sheet.view import spell_sources_view, spell_source_add_options

DATA = GameData.load(Path(__file__).parent.parent / "data")


def _mu(sources):
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_user_read_magic"])
    e = se.assign_slot(e, DATA.classes["magic_user"], DATA, level=1,
                       spell_id="magic_user_read_magic")
    return CharacterSpec(
        name="M", abilities={"STR": 10, "INT": 13, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[e], alignment="neutral", ruleset=RuleSet(),
        spell_sources=sources,
    )


def test_view_exposes_read_and_unlocked():
    scroll = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], DATA)
    rows = spell_sources_view(_mu([scroll]), DATA)
    v = rows[0]
    assert v.unlocked is False
    assert v.can_read is True          # Read Magic memorized
    assert v.entries[0].can_cast is False   # not deciphered yet


def test_add_options_lists_languages():
    opts = spell_source_add_options(DATA)
    ids = [l.id for l in opts.languages]
    assert "common" in ids
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources_view.py -v`
Expected: FAIL (`SpellSourceView` has no `unlocked`/`can_read`; `languages` missing).

- [ ] **Step 3: Extend the view models**

In `aose/sheet/view.py`, add to `class SpellSourceView` (after `name`):

```python
    name: str                 # display label (falls back to a default)
    language: str = ""        # divine scroll language display (blank otherwise)
    unlocked: bool = False    # arcane scroll deciphered?
    can_read: bool = False    # arcane scroll, not unlocked, Read Magic memorized
    arcane_class_id: str | None  # the class whose book a Copy targets, if any
```

Add a small option model near `SpellSourceAddOptions`:

```python
class LanguageOption(BaseModel):
    id: str
    name: str
```

Add to `class SpellSourceAddOptions`:

```python
    divine_spells: list[SpellEntryView]          # scroll divine: all divine spells
    languages: list[LanguageOption] = Field(default_factory=list)  # divine scroll language picker
```

- [ ] **Step 4: Populate the new fields**

In `spell_sources_view`, inside the `for source in spec.spell_sources:` loop,
replace the `out.append(SpellSourceView(...))` block with:

```python
        can_read = (source.kind == "scroll" and source.caster_type == "arcane"
                    and not source.unlocked
                    and spell_source_engine.ready_read_magic_slot(spec, data) is not None)
        out.append(SpellSourceView(
            instance_id=source.instance_id,
            kind=source.kind,
            caster_type=source.caster_type,
            name=_default_source_name(source),
            language=(display_name(source.language, data.languages)
                      if source.kind == "scroll" and source.caster_type == "divine" else ""),
            unlocked=source.unlocked,
            can_read=can_read,
            arcane_class_id=arcane_cid,
            entries=entries,
        ))
```

> `display_name` is already imported in `view.py` (from `aose.engine.languages`).

In `spell_source_add_options`, change the final `return` to include languages
(Common first, then the rest alphabetically by display name):

```python
    langs = sorted(data.languages.names.items(), key=lambda kv: (kv[0] != "common", kv[1]))
    return SpellSourceAddOptions(
        arcane_lists=arcane_lists,
        arcane_spells=bucket(arcane_list_ids),
        divine_spells=bucket(divine_list_ids),
        languages=[LanguageOption(id=k, name=v) for k, v in langs],
    )
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_sources_view.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add aose/sheet/view.py tests/test_spell_sources_view.py
git commit -m "feat(sheet): expose scroll read/unlocked/language to the view"
```

---

## Task 6: View — inject scroll rows into `spellbook_view`

**Files:**
- Modify: `aose/sheet/view.py` (`SpellbookLevelGroup`, new `ScrollSpellRow`,
  `spellbook_view`)
- Test: `tests/test_spellbook_view.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_spellbook_view.py` (imports at top of that file already cover
`CharacterSpec`, `ClassEntry`, `GameData`, `se`, `spellbook_view`; also import
the engine):

```python
from aose.engine import spell_sources as ss

CURE = "cleric_cure_light_wounds"


def _cleric_with_scrolls():
    e = ClassEntry(class_id="cleric", level=1, hp_rolls=[6])
    spec = CharacterSpec(
        name="C", abilities={"STR": 9, "INT": 10, "WIS": 16, "DEX": 12, "CON": 10, "CHA": 9},
        race_id="human", classes=[e], alignment="neutral",
    )
    s3 = ss.new_spell_source("scroll", "divine", [CURE, CURE, CURE], DATA, language="Common")
    s1 = ss.new_spell_source("scroll", "divine", [CURE], DATA, language="Common")
    spec.spell_sources = [s3, s1]
    return spec


def test_scroll_rows_grouped_by_level_with_charges():
    spec = _cleric_with_scrolls()
    blocks = spellbook_view(spec, DATA)
    divine = next(b for b in blocks if b.caster_type == "divine")
    lvl1 = next(g for g in divine.levels if g.level == 1)
    cures = [r for r in lvl1.scroll_rows if r.spell_id == CURE]
    assert len(cures) == 2                       # one row per scroll
    assert sorted(r.charges for r in cures) == [1, 3]
    assert all(r.castable for r in cures)        # Common is known
    labels = {r.label for r in cures}
    assert labels == {"scroll 1", "scroll 2"}


def test_arcane_scroll_row_locked_until_read():
    e = ClassEntry(class_id="magic_user", level=1, spellbook=[])
    spec = CharacterSpec(
        name="M", abilities={"STR": 9, "INT": 13, "WIS": 9, "DEX": 12, "CON": 10, "CHA": 9},
        race_id="human", classes=[e], alignment="neutral",
    )
    scroll = ss.new_spell_source("scroll", "arcane", ["magic_user_fire_ball"], DATA)
    spec.spell_sources = [scroll]
    blocks = spellbook_view(spec, DATA)
    arcane = next(b for b in blocks if b.caster_type == "arcane")
    # Fireball is L3 — a level this L1 caster can't normally cast; the row still appears.
    lvl3 = next(g for g in arcane.levels if g.level == 3)
    row = next(r for r in lvl3.scroll_rows if r.spell_id == "magic_user_fire_ball")
    assert row.castable is False
    assert row.block_reason == "needs Read Magic"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spellbook_view.py -k "scroll" -v`
Expected: FAIL (`scroll_rows` attribute / behavior missing).

- [ ] **Step 3: Add the row model + level-group field**

In `aose/sheet/view.py`, add before `class SpellbookLevelGroup`:

```python
class ScrollSpellRow(BaseModel):
    scroll_instance_id: str
    label: str                # "scroll N" or the scroll's custom name
    spell_id: str
    name: str
    level: int
    charges: int              # remaining copies of this spell on this scroll
    castable: bool
    block_reason: str | None  # why cast is disabled, if any
```

Add a field to `class SpellbookLevelGroup`:

```python
    rows: list[SpellbookRow]
    scroll_rows: list[ScrollSpellRow] = Field(default_factory=list)
```

- [ ] **Step 4: Build + inject scroll rows**

In `aose/sheet/view.py`, add this helper above `spellbook_view`:

```python
def _scroll_rows_by_level(spec: CharacterSpec, data: GameData, caster_type: str
                          ) -> dict[int, list[ScrollSpellRow]]:
    """Castable-by-type scrolls turned into per-level rows (one per scroll+spell)."""
    by_level: dict[int, list[ScrollSpellRow]] = {}
    scroll_n = 0
    for source in spec.spell_sources:
        if source.kind != "scroll" or source.caster_type != caster_type:
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
            by_level.setdefault(spell.level, []).append(ScrollSpellRow(
                scroll_instance_id=source.instance_id, label=label,
                spell_id=sid, name=spell.name, level=spell.level,
                charges=counts[sid], castable=reason is None, block_reason=reason,
            ))
    return by_level
```

At the **end** of `spellbook_view`, before `return out`, inject into the first
block of each caster type:

```python
    seen_types: set[str] = set()
    for block in out:
        if block.caster_type in seen_types:
            continue
        seen_types.add(block.caster_type)
        by_level = _scroll_rows_by_level(spec, data, block.caster_type)
        if not by_level:
            continue
        for lvl, rows in by_level.items():
            grp = next((g for g in block.levels if g.level == lvl), None)
            if grp is None:
                grp = SpellbookLevelGroup(level=lvl, cap=0, used=0, rows=[])
                block.levels.append(grp)
            grp.scroll_rows.extend(rows)
        block.levels.sort(key=lambda g: g.level)
    return out
```

- [ ] **Step 5: Run to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spellbook_view.py -v`
Expected: PASS (all, including pre-existing tests).

- [ ] **Step 6: Commit**

```bash
git add aose/sheet/view.py tests/test_spellbook_view.py
git commit -m "feat(sheet): inject scroll spell rows into the spell list by level"
```

---

## Task 7: Routes — language on add, new `/spell-sources/read`

**Files:**
- Modify: `aose/web/routes.py` (`sheet_spell_source_add`, add a read route)
- Test: `tests/test_spell_routes.py`

- [ ] **Step 1: Inspect the existing route test harness**

Run: `grep -n "spell-sources\|def test_\|client\|TestClient" tests/test_spell_routes.py | head -40`
Note the fixture name used to build a client and a character id; reuse it in the
new test below (the snippet assumes a `client` fixture and a helper that creates a
character — adapt names to match the file).

- [ ] **Step 2: Write the failing test**

Add to `tests/test_spell_routes.py` (adapt the character-creation/setup to the
file's existing helpers):

```python
def test_read_route_unlocks_scroll(client, character_with_read_magic):
    # character_with_read_magic: a saved magic-user with Read Magic memorized and
    # one arcane scroll. Returns (character_id, scroll_instance_id).
    cid, iid = character_with_read_magic
    resp = client.post(f"/character/{cid}/spell-sources/read",
                       data={"instance_id": iid}, follow_redirects=False)
    assert resp.status_code == 303
    # reload sheet → scroll now deciphered
    page = client.get(f"/character/{cid}").text
    assert "deciphered" in page.lower()
```

> If building such a fixture is heavy, instead assert at the engine boundary in
> `tests/test_spell_sources.py` (already covered in Task 4) and write a lighter
> route test that just checks the endpoint returns 303 for a valid id and 400 for
> a divine scroll. The route must still be implemented per Step 4.

- [ ] **Step 3: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_routes.py -k read_route -v`
Expected: FAIL (404 — route not defined).

- [ ] **Step 4: Add `language` to the add route + new read route**

In `aose/web/routes.py`, in `sheet_spell_source_add`, after
`name = form.get("name", "")` add:

```python
    language = form.get("language", "Common")
```

and pass it through:

```python
        spec.spell_sources = spell_source_engine.add_spell_source(
            spec.spell_sources, kind, caster_type, spell_ids, data,
            name=name, list_id=list_id, language=language,
        )
```

Add a new route after `sheet_spell_source_cast`:

```python
@router.post("/character/{character_id}/spell-sources/read")
async def sheet_spell_source_read(request: Request, character_id: str,
                                  instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        classes, sources = spell_source_engine.read_scroll(spec, data, instance_id)
    except SpellSourceError as e:
        raise HTTPException(400, str(e))
    spec.classes = classes
    spec.spell_sources = sources
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

> The cast route already calls `can_cast_scroll`, which now enforces the full
> gate — no change needed there beyond confirming it still reads
> `spell_source_engine.can_cast_scroll`.

- [ ] **Step 5: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spell_routes.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add aose/web/routes.py tests/test_spell_routes.py
git commit -m "feat(web): scroll language on add + Read-Magic decipher route"
```

---

## Task 8: Template — render scroll rows in the spell list

**Files:**
- Modify: `aose/web/templates/sheet.html` (the spellbook block, ~lines 320-347)

- [ ] **Step 1: Add scroll rows after the memorized rows**

In `aose/web/templates/sheet.html`, inside the `{% for lvl in block.levels %}`
loop, the memorized-rows `{% for row in ... %}...{% else %}...{% endfor %}` block
currently ends around line 346. Immediately after that inner for/else block (and
before the next `{% endfor %}` that closes the level loop), add:

```html
        {% for sr in lvl.scroll_rows %}
        <div class="spell scroll-spell{% if not sr.castable %} locked{% endif %}">
          <span class="snm">{{ sr.name }} <em class="scroll-tag">{{ sr.label }}</em></span>
          {% if sr.castable %}
          <form method="post" action="/character/{{ character_id }}/spell-sources/cast"
                style="display:inline">
            <input type="hidden" name="instance_id" value="{{ sr.scroll_instance_id }}">
            <input type="hidden" name="spell_id" value="{{ sr.spell_id }}">
            <button class="pips btn-bare" type="submit" title="Cast from {{ sr.label }} (expends a charge)">
              {% for _ in range(sr.charges) %}<i class="pip"></i>{% endfor %}
            </button>
          </form>
          {% else %}
          <span class="pips" title="{{ sr.block_reason }}">
            {% for _ in range(sr.charges) %}<i class="pip locked-pip"></i>{% endfor %}
          </span>
          <span class="hint scroll-reason">{{ sr.block_reason }}</span>
          {% endif %}
        </div>
        {% endfor %}
```

- [ ] **Step 2: Fix the "no spells in book" hint to account for scroll-only levels**

The arcane empty-level hint (~line 343) reads
`{% if block.caster_type == "arcane" and lvl.rows|length == 0 %}`. Change it so it
does not show when scroll rows are present:

```html
        {% if block.caster_type == "arcane" and lvl.rows|length == 0 and lvl.scroll_rows|length == 0 %}
```

- [ ] **Step 3: Add minimal styles**

In `sheet.html`'s `<style>` block (or the shared stylesheet, matching where
`.spell`/`.pip` are defined — find with `grep -n "\.scroll-tag\|\.spell\b\|\.pip\b" aose/web/templates/sheet.html`), add:

```css
.scroll-tag { font-style: italic; color: var(--faint); font-weight: 400; }
.spell.scroll-spell.locked { opacity: .65; }
.btn-bare { background: none; border: 0; padding: 0; cursor: pointer; }
.locked-pip { opacity: .4; }
.scroll-reason { margin-left: 6px; }
```

- [ ] **Step 4: Verify in the browser**

Start the app: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
Create/open a divine caster, add a divine scroll with 3× and 1× of one spell
(Documents tab), and confirm the spell list shows:

```
Level 1
<memorized rows…>
Cure …  scroll 1  ●●●
Cure …  scroll 2  ●
```

Add an arcane scroll on a magic-user without Read Magic memorized → its rows show
greyed with "needs Read Magic". Memorize Read Magic, press **Read** in Documents,
reload → arcane rows become castable.

- [ ] **Step 5: Commit**

```bash
git add aose/web/templates/sheet.html
git commit -m "feat(sheet): render castable scroll spells in the spell list"
```

---

## Task 9: Template + JS — Documents tab Read button, language, dup-aware add form

**Files:**
- Modify: `aose/web/templates/_equipment_ui.html` (Documents pane, ~lines 583-689)
- Rewrite: `aose/web/static/spell_source_add.js`

- [ ] **Step 1: Add Read button + language to the scroll list**

In `_equipment_ui.html`, in the Documents pane scroll header row (~line 591-603),
replace the `<tr>` for each source with one that shows language/decipher state and
a Read action. Replace the existing source `<tr>`…`</tr>` (the one with
`<strong>{{ src.name }}</strong>`) with:

```html
    <tr>
      <td>
        <strong>{{ src.name }}</strong>
        <span class="tag faint">{{ src.caster_type }} · {{ src.entries | length }} spell{{ 's' if src.entries | length != 1 }}</span>
        {% if src.kind == "scroll" and src.caster_type == "divine" %}
        <span class="tag faint">{{ src.language }}</span>
        {% endif %}
        {% if src.kind == "scroll" and src.caster_type == "arcane" %}
          {% if src.unlocked %}<span class="tag">deciphered</span>
          {% else %}<span class="tag stamp">sealed</span>{% endif %}
        {% endif %}
      </td>
      <td class="n">
        {% if src.kind == "scroll" and src.caster_type == "arcane" and not src.unlocked %}
        <form method="post" action="{{ coins_url_prefix }}/spell-sources/read" style="display:inline">
          <input type="hidden" name="instance_id" value="{{ src.instance_id }}">
          <button class="btn link" type="submit"{% if not src.can_read %} disabled title="Memorize Read Magic first"{% endif %}>read</button>
        </form>
        {% endif %}
        <form method="post" action="{{ coins_url_prefix }}/spell-sources/remove" style="display:inline">
          <input type="hidden" name="instance_id" value="{{ src.instance_id }}">
          <button class="btn link" type="submit">remove</button>
        </form>
      </td>
    </tr>
```

- [ ] **Step 2: Rework the add form for quantities + language**

In `_equipment_ui.html`, replace the whole `<form … id="spell-source-add-form">`
… `</form>` block (~lines 644-684) with:

```html
<form method="post" action="{{ coins_url_prefix }}/spell-sources/add" id="spell-source-add-form">
  <label class="f"><span class="lab">Type</span>
    <select name="kind" id="ss-kind">
      <option value="spellbook">Spell Book (arcane)</option>
      <option value="scroll">Spell Scroll</option>
    </select>
  </label>
  <label class="f"><span class="lab">Magic</span>
    <select name="caster_type" id="ss-caster-type">
      <option value="arcane">Arcane</option>
      <option value="divine">Divine</option>
    </select>
  </label>
  <label id="ss-list-label" class="f"><span class="lab">Spell list</span>
    <select name="list_id" id="ss-list">
      {% for grp in spell_source_add_options.arcane_lists %}
      <option value="{{ grp.list_id }}">{{ grp.label }}</option>
      {% endfor %}
    </select>
  </label>
  <label id="ss-language-label" class="f" style="display:none"><span class="lab">Language</span>
    <select name="language" id="ss-language">
      {% for l in spell_source_add_options.languages %}
      <option value="{{ l.id }}">{{ l.name }}</option>
      {% endfor %}
    </select>
  </label>
  <label class="f"><span class="lab">Name (optional)</span>
    <input type="text" name="name" placeholder="e.g. Rival's grimoire">
  </label>
  <div class="f"><span class="lab">Add spells<span id="ss-spell-cap" class="hint" style="font-weight:400;text-transform:none;letter-spacing:0"> — a scroll holds up to 7 charges</span></span>
    <div class="inline-form">
      <select id="ss-spell-pick">
        {% for grp in spell_source_add_options.arcane_lists %}{% for s in grp.spells %}
        <option value="{{ s.id }}" data-caster="arcane" data-list="{{ grp.list_id }}" data-label="{{ s.name }} (L{{ s.level }})">{{ s.name }} (L{{ s.level }})</option>
        {% endfor %}{% endfor %}
        {% for s in spell_source_add_options.divine_spells %}
        <option value="{{ s.id }}" data-caster="divine" data-list="" data-label="{{ s.name }} (L{{ s.level }})">{{ s.name }} (L{{ s.level }})</option>
        {% endfor %}
      </select>
      <input type="number" id="ss-spell-qty" value="1" min="1" max="7" style="width:56px">
      <button type="button" class="btn" id="ss-add-spell">Add</button>
    </div>
  </div>
  <ul id="ss-staged" style="list-style:none;padding:0;margin:6px 0"></ul>
  <div id="ss-hidden"></div>
  <button class="btn solid" type="submit" id="ss-submit" disabled>Add to inventory</button>
</form>
<script src="/static/spell_source_add.js" defer></script>
```

- [ ] **Step 3: Rewrite the JS**

Replace the entire contents of `aose/web/static/spell_source_add.js` with:

```javascript
// Add-spell-document form: pick spells (with quantities) into a staged list,
// emit one hidden `spell_ids` input per charge, and toggle list/language fields
// by kind/caster. The server re-validates everything.
(function () {
  var form = document.getElementById("spell-source-add-form");
  if (!form) return;
  var kind = document.getElementById("ss-kind");
  var caster = document.getElementById("ss-caster-type");
  var list = document.getElementById("ss-list");
  var listLabel = document.getElementById("ss-list-label");
  var langLabel = document.getElementById("ss-language-label");
  var pick = document.getElementById("ss-spell-pick");
  var qty = document.getElementById("ss-spell-qty");
  var addBtn = document.getElementById("ss-add-spell");
  var staged = document.getElementById("ss-staged");
  var hidden = document.getElementById("ss-hidden");
  var submit = document.getElementById("ss-submit");
  var cap = document.getElementById("ss-spell-cap");
  var MAX_SCROLL_SPELLS = 7;

  // staged: array of { id, label, n }
  var items = [];

  function isBook() { return kind.value === "spellbook"; }
  function wantCaster() { return isBook() ? "arcane" : caster.value; }
  function wantList() { return isBook() ? list.value : null; }

  function totalCharges() {
    return items.reduce(function (t, it) { return t + it.n; }, 0);
  }

  function refreshControls() {
    caster.disabled = isBook();
    if (isBook()) caster.value = "arcane";
    listLabel.style.display = isBook() ? "" : "none";
    list.disabled = !isBook();
    langLabel.style.display = (!isBook() && caster.value === "divine") ? "" : "none";
    cap.style.display = isBook() ? "none" : "";
    // Filter the pick list to matching spells.
    Array.prototype.forEach.call(pick.options, function (opt) {
      var ok = opt.getAttribute("data-caster") === wantCaster();
      if (ok && wantList() !== null) ok = opt.getAttribute("data-list") === wantList();
      opt.hidden = !ok;
    });
    var firstVisible = Array.prototype.filter.call(pick.options, function (o) { return !o.hidden; })[0];
    if (firstVisible) pick.value = firstVisible.value;
  }

  function renderStaged() {
    staged.innerHTML = "";
    hidden.innerHTML = "";
    items.forEach(function (it, idx) {
      var li = document.createElement("li");
      li.textContent = it.label + (it.n > 1 ? "  ×" + it.n : "") + "  ";
      var rm = document.createElement("button");
      rm.type = "button";
      rm.className = "btn link";
      rm.textContent = "remove";
      rm.addEventListener("click", function () { items.splice(idx, 1); renderStaged(); });
      li.appendChild(rm);
      staged.appendChild(li);
      for (var i = 0; i < it.n; i++) {
        var inp = document.createElement("input");
        inp.type = "hidden"; inp.name = "spell_ids"; inp.value = it.id;
        hidden.appendChild(inp);
      }
    });
    submit.disabled = items.length === 0;
  }

  addBtn.addEventListener("click", function () {
    var opt = pick.options[pick.selectedIndex];
    if (!opt || opt.hidden) return;
    var id = opt.value;
    var label = opt.getAttribute("data-label") || opt.textContent.trim();
    var n = Math.max(1, parseInt(qty.value, 10) || 1);
    // Spell books: one of each (no duplicates).
    if (isBook()) {
      if (items.some(function (it) { return it.id === id; })) return;
      n = 1;
    } else {
      var existing = items.filter(function (it) { return it.id === id; })[0];
      var room = MAX_SCROLL_SPELLS - totalCharges();
      if (room <= 0) return;
      n = Math.min(n, room);
      if (existing) { existing.n += n; renderStaged(); return; }
    }
    items.push({ id: id, label: label, n: n });
    renderStaged();
  });

  // Changing kind/caster/list invalidates the staged picks (different pool).
  function resetStaged() { items = []; renderStaged(); refreshControls(); }
  kind.addEventListener("change", resetStaged);
  caster.addEventListener("change", resetStaged);
  list.addEventListener("change", resetStaged);

  refreshControls();
  renderStaged();
})();
```

- [ ] **Step 4: Verify in the browser**

Restart/refresh. In Documents → Add: choose Scroll + Divine → the **Language**
picker appears. Pick a spell, set quantity 3, **Add**; pick it again ×1 → staged
shows "×3" merged, hidden inputs total 4. Add beyond 7 → blocked. Submit →
the scroll appears with the duplicate charges. For Arcane scroll, no language
picker; once added it shows "sealed" with a **read** button (disabled until Read
Magic is memorized).

- [ ] **Step 5: Commit**

```bash
git add aose/web/templates/_equipment_ui.html aose/web/static/spell_source_add.js
git commit -m "feat(web): Documents tab read button + duplicate/language-aware add form"
```

---

## Task 10: Full suite, docs, finalize

**Files:**
- Modify: `docs/CHANGELOG.md`, `docs/ARCHITECTURE.md`

- [ ] **Step 1: Run the full test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all pass (ignore the trailing `pytest-current` PermissionError).
If any pre-existing test referenced the old duplicate-rejection or the old
`can_cast_scroll` semantics, fix it to match the new behavior (Tasks 2-3 already
cover the known ones).

- [ ] **Step 2: Update CHANGELOG**

Add a row to the **top** of `docs/CHANGELOG.md`:

```markdown
| 2026-06-22 | Cast spells from scrolls in the spell list (Read-Magic unlock, divine language, duplicates) | feat/scroll-casting-spell-list | 2026-06-22-scroll-casting-in-spell-list |
```

> Match the existing table's exact column order/format — open the file and copy a
> recent row's shape before editing.

- [ ] **Step 3: Update ARCHITECTURE**

In `docs/ARCHITECTURE.md`, find the spell-sources / scrolls subsystem section and
edit it **in place** to note: scrolls may hold duplicate spells (charges);
arcane scrolls carry `unlocked` and are deciphered by burning a memorized Read
Magic cast (`read_scroll` / `ready_read_magic_slot`); divine scrolls carry
`language` and are gated by known languages; scroll spells surface in the
spell-list blocks via `spellbook_view` (`ScrollSpellRow`), one row per
scroll+spell at the spell's true level.

- [ ] **Step 4: Commit**

```bash
git add docs/CHANGELOG.md docs/ARCHITECTURE.md
git commit -m "docs: record scroll-casting-in-spell-list feature"
```

- [ ] **Step 5: Final verification**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: green. Then do the browser smoke test from Task 8 Step 4 and Task 9
Step 4 once more end-to-end.

---

## Self-Review notes (author)

- **Spec coverage:** model fields (T1), duplicates + language storage (T2), cast
  gate arcane/divine (T3), Read-Magic decipher burning a memorized slot (T4),
  view exposure + language options (T5), spell-list injection with per-scroll rows
  and true-level grouping (T6), routes incl. read (T7), spell-list render (T8),
  Documents read button + dup/language add form (T9), tests + docs (T10). All spec
  sections map to a task.
- **Type consistency:** `scroll_cast_block_reason`/`can_cast_scroll`,
  `ready_read_magic_slot`/`read_scroll`, `ScrollSpellRow`,
  `SpellbookLevelGroup.scroll_rows`, `SpellSourceView.{language,unlocked,can_read}`,
  `SpellSourceAddOptions.languages`/`LanguageOption` are defined before use.
```
