# Languages, Literacy & Wisdom Saves Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AOSE ability-table-derived features faithful — a language display-name registry with non-learnable class/race-granted tongues, three-tier INT literacy with a barbarian override, the Wisdom magic-save modifier, conditional racial resilience, and a base→modified saves breakdown modal.

**Architecture:** Pure engine helpers (`languages.py`, `saves.py`) compute everything from `CharacterSpec` + `GameData`; the sheet view assembles them into `CharacterSheet`; Jinja renders. WIS and racial-resilience save bonuses are modeled as `Modifier`s (reusing the existing `condition`/`source` fields) so they flow through one breakdown machine. Conditioned modifiers are already excluded from the headline number, so "show in modal, not in base" falls out for free.

**Tech Stack:** Python 3.14, Pydantic v2, FastAPI, Jinja2, pytest. Run tests with `.venv\Scripts\python.exe -m pytest tests/ -q`.

**Spec:** `docs/superpowers/specs/2026-06-07-languages-literacy-wisdom-saves-design.md`

**Conventions:**
- All tests via `.venv\Scripts\python.exe -m pytest ...`. The trailing `pytest-current` PermissionError on Windows is a known pytest-9 quirk — ignore it.
- This branch is `feature/languages-literacy-wisdom-saves`.

---

## File Structure

| File | Change |
|---|---|
| `aose/models/language.py` | `LanguageData.names: dict[str, str]` |
| `aose/engine/languages.py` | `display_name`, `granted_languages`, `literacy`; `known_languages` gains `granted`; id-based `available_additional`/`known_languages` |
| `data/languages.yaml` | add `names` registry; `additional` becomes a list of ids |
| `data/classes/barbarian.yaml` | `mechanical: {illiterate_below_level: 2}` on the Literacy feature |
| `data/classes/druid.yaml` | `mechanical: {languages: [druidic]}` on the Languages feature |
| `data/races/dwarf.yaml`, `halfling.yaml`, `duergar.yaml` | conditions on resilience `save:death` (`poison`) + duergar `save:paralysis` (`paralysis`) |
| `aose/engine/saves.py` | `wisdom_save_modifiers`, `SaveBreakdown`/`SaveModLine`, `saving_throws_detail`; `saving_throws` delegates |
| `aose/sheet/view.py` | `SheetSave` (base/modified/lines), `CharacterSheet.literacy`, display-name languages, feed breakdowns |
| `aose/web/templates/sheet.html` | literacy line; clickable saves rows + per-save breakdown modal |
| `aose/web/wizard.py` | `_languages_context`: exclude granted, return display-name option pairs |
| `aose/web/templates/wizard/identity.html` | render option labels via display name |
| Tests | `test_languages_engine.py`, `test_wizard_languages.py`, `test_feature_modifiers.py`, `test_sheet.py`, `test_derivation.py`, new `test_saves_breakdown.py` |

---

## Phase 1 — Language registry & display names

### Task 1: `LanguageData.names` + `display_name()`

**Files:**
- Modify: `aose/models/language.py`
- Modify: `aose/engine/languages.py`
- Test: `tests/test_languages_engine.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_languages_engine.py` (import `display_name` in the existing import block):

```python
def test_display_name_uses_registry():
    data = _data()
    assert display_name("common", data.languages) == "Common"
    assert display_name("deepcommon", data.languages) == "Deepcommon"
    assert display_name("lizard_man", data.languages) == "Lizard man"


def test_display_name_fallback_titlecases_unregistered_id():
    data = _data()
    # An id with no registry entry still renders readably (first letter up,
    # underscores -> spaces), preserving flavour wording.
    assert display_name("language_of_earth_elementals", data.languages) == \
        "Language of earth elementals"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_languages_engine.py::test_display_name_uses_registry -v`
Expected: FAIL — `ImportError: cannot import name 'display_name'`.

- [ ] **Step 3: Add the model field**

In `aose/models/language.py`, add to `LanguageData` (above `alignment`):

```python
    names: dict[str, str] = Field(default_factory=dict)
```

- [ ] **Step 4: Implement `display_name`**

In `aose/engine/languages.py`, add (after the `LanguageError` class):

```python
def display_name(lang_id: str, lang_data) -> str:
    """Proper display name for a language id. Registry first; otherwise a
    readable fallback (underscores -> spaces, first letter capitalised) so any
    data-discovered language still renders with a proper name."""
    registered = lang_data.names.get(lang_id)
    if registered:
        return registered
    return lang_id.replace("_", " ").capitalize()
```

- [ ] **Step 5: Add registry data**

In `data/languages.yaml`, add a `names:` block at the top (above `alignment:`):

```yaml
names:
  common: Common
  deepcommon: Deepcommon
  bugbear: Bugbear
  doppelganger: Doppelgänger
  dragon: Dragon
  dwarvish: Dwarvish
  elvish: Elvish
  gargoyle: Gargoyle
  gnoll: Gnoll
  gnomish: Gnomish
  goblin: Goblin
  halfling: Halfling
  harpy: Harpy
  hobgoblin: Hobgoblin
  kobold: Kobold
  lizard_man: Lizard man
  medusa: Medusa
  minotaur: Minotaur
  ogre: Ogre
  orcish: Orcish
  pixie: Pixie
  human_dialect: Human dialect
  secret_language_of_burrowing_mammals: Secret language of burrowing mammals
  druidic: Druidic
```

- [ ] **Step 6: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_languages_engine.py -k display_name -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add aose/models/language.py aose/engine/languages.py data/languages.yaml tests/test_languages_engine.py
git commit -m "feat(languages): display-name registry with readable fallback"
```

---

### Task 2: Convert `additional` to ids (id-based selection)

**Files:**
- Modify: `data/languages.yaml`
- Test: `tests/test_languages_engine.py`

The learnable list must reference the registry by id, and selection must round-trip on ids.

- [ ] **Step 1: Update the failing tests**

In `tests/test_languages_engine.py`, replace the bodies of these two tests:

```python
def test_available_additional_excludes_known_case_insensitively():
    data = _data()
    elf = data.races["elf"]  # native incl. elvish, gnoll, hobgoblin, orcish
    avail = available_additional(data.languages, set(native_languages(elf)))
    assert "elvish" not in avail
    assert "gnoll" not in avail
    assert "orcish" not in avail
    assert "dragon" in avail            # something the elf doesn't speak
    assert len(avail) == len(set(avail))


def test_known_languages_composes_and_dedupes_in_order():
    data = _data()
    human = data.races["human"]  # native: ["common"]
    known = known_languages(["dragon"], human, "law", data.languages)
    assert known == ["common", "Lawful", "dragon"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_languages_engine.py -k "available_additional_excludes or composes_and_dedupes" -v`
Expected: FAIL — `additional` still holds title-case strings, so `"dragon" in avail` is False.

- [ ] **Step 3: Convert the data**

In `data/languages.yaml`, replace the `additional:` list with ids (keep the `names`/`alignment` blocks):

```yaml
additional:
  - bugbear
  - doppelganger
  - dragon
  - dwarvish
  - elvish
  - gargoyle
  - gnoll
  - gnomish
  - goblin
  - halfling
  - harpy
  - hobgoblin
  - kobold
  - lizard_man
  - medusa
  - minotaur
  - ogre
  - orcish
  - pixie
  - human_dialect
```

- [ ] **Step 4: Run the whole languages-engine suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_languages_engine.py -v`
Expected: PASS. (The `validate_languages` tests already pass — they compare case-insensitively, so posting `"Dragon"` still matches id `dragon`; the `rejects_native`/`rejects_alignment`/`rejects_unknown` cases are unaffected.)

- [ ] **Step 5: Commit**

```bash
git add data/languages.yaml tests/test_languages_engine.py
git commit -m "refactor(languages): id-based learnable list keyed to the registry"
```

---

### Task 3: `granted_languages()` — class/race feature tongues

**Files:**
- Modify: `aose/engine/languages.py`
- Test: `tests/test_languages_engine.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_languages_engine.py` (import `granted_languages`):

```python
def _spec(race_id, class_id, *, level=1, int_score=10):
    from aose.models import CharacterSpec, ClassEntry
    return CharacterSpec(
        name="G",
        abilities={"STR": 10, "INT": int_score, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id=race_id, alignment="neutral",
        classes=[ClassEntry(class_id=class_id, level=level, hp_rolls=[5])],
    )


def test_granted_languages_from_race_feature():
    data = _data()
    spec = _spec("gnome", "fighter")   # gnome race grants the burrowing-mammals tongue
    granted = granted_languages(spec, data)
    assert "secret_language_of_burrowing_mammals" in granted


def test_granted_languages_from_class_feature_gated_by_level():
    data = _data()
    spec = _spec("human", "druid", level=1)   # druid Languages feature is L1
    assert "druidic" in granted_languages(spec, data)


def test_granted_languages_excluded_from_learnable():
    data = _data()
    spec = _spec("gnome", "fighter")
    already = set(native_languages(data.races["gnome"])) | set(granted_languages(spec, data))
    avail = available_additional(data.languages, already)
    assert "secret_language_of_burrowing_mammals" not in avail
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_languages_engine.py -k granted_languages -v`
Expected: FAIL — `ImportError: cannot import name 'granted_languages'`.

- [ ] **Step 3: Implement `granted_languages`**

In `aose/engine/languages.py`, add (and add `from aose.models import Ability` at the top of the file):

```python
def granted_languages(spec, data) -> list[str]:
    """Special languages a character's race/class *features* grant — order-stable,
    deduped case-insensitively. Read from ``feature.mechanical['languages']``.
    Race features always count; class features are gated by ``gained_at_level``."""
    out: list[str] = []
    seen: set[str] = set()

    def _add(ids):
        for lang_id in ids or []:
            key = lang_id.casefold()
            if key not in seen:
                seen.add(key)
                out.append(lang_id)

    race = data.races.get(spec.race_id)
    if race is not None:
        for feat in race.features:
            if feat.mechanical:
                _add(feat.mechanical.get("languages"))
    for entry in spec.classes:
        cls = data.classes.get(entry.class_id)
        if cls is None:
            continue
        for feat in cls.features:
            if feat.gained_at_level <= entry.level and feat.mechanical:
                _add(feat.mechanical.get("languages"))
    return out
```

- [ ] **Step 4: Add the druid grant**

In `data/classes/druid.yaml`, on the `- id: languages` feature, add a `mechanical` block (keep the existing `text`/`gained_at_level`):

```yaml
- id: languages
  name: Languages
  text: |-
    Druids speak a secret tongue known only to their sect. At each level above 2nd, a druid also learns to speak a language used by creatures of Sylvan forests (e.g. dryads, green dragons, pixies, treants).
  gained_at_level: 1
  mechanical:
    languages:
    - druidic
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_languages_engine.py -k granted_languages -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add aose/engine/languages.py data/classes/druid.yaml tests/test_languages_engine.py
git commit -m "feat(languages): surface class/race-granted tongues (non-learnable)"
```

---

### Task 4: `literacy()` — three tiers + barbarian override

**Files:**
- Modify: `aose/engine/languages.py`
- Modify: `data/classes/barbarian.yaml`
- Test: `tests/test_languages_engine.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_languages_engine.py` (import `literacy`):

```python
@pytest.mark.parametrize("int_score,expected", [
    (3, "illiterate"), (5, "illiterate"),
    (6, "basic"), (8, "basic"),
    (9, "literate"), (16, "literate"),
])
def test_literacy_tiers_from_int(int_score, expected):
    data = _data()
    spec = _spec("human", "fighter", int_score=int_score)
    assert literacy(spec, data) == expected


def test_barbarian_illiterate_at_level_1_regardless_of_int():
    data = _data()
    spec = _spec("human", "barbarian", level=1, int_score=16)
    assert literacy(spec, data) == "illiterate"


def test_barbarian_literate_at_level_2_per_int_table():
    data = _data()
    spec = _spec("human", "barbarian", level=2, int_score=16)
    assert literacy(spec, data) == "literate"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_languages_engine.py -k literacy -v`
Expected: FAIL — `ImportError: cannot import name 'literacy'`.

- [ ] **Step 3: Implement `literacy`**

In `aose/engine/languages.py`, add:

```python
def literacy(spec, data) -> str:
    """Literacy state: ``"illiterate"`` (INT <= 5), ``"basic"`` (6-8), or
    ``"literate"`` (>= 9). A class feature may force illiteracy below a level via
    ``mechanical['illiterate_below_level']`` (barbarian: illiterate at level 1)."""
    int_score = spec.abilities[Ability.INT]
    if int_score <= 5:
        tier = "illiterate"
    elif int_score <= 8:
        tier = "basic"
    else:
        tier = "literate"

    for entry in spec.classes:
        cls = data.classes.get(entry.class_id)
        if cls is None:
            continue
        for feat in cls.features:
            if not feat.mechanical:
                continue
            floor = feat.mechanical.get("illiterate_below_level")
            if floor is not None and entry.level < floor:
                return "illiterate"
    return tier
```

- [ ] **Step 4: Add the barbarian override**

In `data/classes/barbarian.yaml`, on the `- id: literacy` feature, add a `mechanical` block:

```yaml
- id: literacy
  name: Literacy
  text: A 1st level barbarian cannot read or write, irrespective of INT score.
  gained_at_level: 1
  mechanical:
    illiterate_below_level: 2
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_languages_engine.py -k literacy -v`
Expected: PASS (8 tests).

- [ ] **Step 6: Commit**

```bash
git add aose/engine/languages.py data/classes/barbarian.yaml tests/test_languages_engine.py
git commit -m "feat(languages): three-tier INT literacy with barbarian L1 override"
```

---

## Phase 2 — Sheet wiring (languages + literacy)

### Task 5: Display-name languages, granted tongues & literacy on the sheet

**Files:**
- Modify: `aose/sheet/view.py`
- Modify: `aose/web/templates/sheet.html`
- Test: `tests/test_sheet.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_sheet.py` (use whatever sheet-building helper the file already uses — find an existing test that calls `build_sheet` and mirror its setup; the assertions below assume a `sheet` for a gnome/druid and a barbarian are obtainable). If the file has a helper like `_sheet(spec)`, reuse it; otherwise build via `build_sheet(spec, data)`:

```python
def test_sheet_languages_use_display_names_and_include_granted(sheet_for):
    # sheet_for(race_id, class_id, abilities, ...) -> CharacterSheet
    sheet = sheet_for("gnome", "fighter")
    assert "Common" in sheet.languages                 # display name, not "common"
    assert "Secret language of burrowing mammals" in sheet.languages


def test_sheet_exposes_literacy(sheet_for):
    sheet = sheet_for("human", "barbarian", level=1, int_score=16)
    assert sheet.literacy == "illiterate"
```

> NOTE for the implementer: `tests/test_sheet.py` already constructs sheets — adapt these two tests to that file's existing fixture/helper rather than inventing `sheet_for`. The behavioural assertions (display names present; `sheet.literacy == "illiterate"`) are what matter.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet.py -k "display_names or literacy" -v`
Expected: FAIL — `CharacterSheet` has no `literacy`; languages are lowercase ids.

- [ ] **Step 3: Add the `literacy` field to `CharacterSheet`**

In `aose/sheet/view.py`, in the `CharacterSheet` model near `broken_speech` (around line 317):

```python
    literacy: str                    # "illiterate" / "basic" / "literate"
```

- [ ] **Step 4: Update the import + build call**

In `aose/sheet/view.py`, update the languages import (line ~22):

```python
from aose.engine.languages import (
    broken_speech, display_name, granted_languages, known_languages, literacy,
)
```

Then update the `build_sheet` assignment (around line 1058) for `languages` and add `literacy`:

```python
        languages=[
            display_name(lang, data.languages)
            for lang in known_languages(
                spec.languages, race, spec.alignment, data.languages,
                granted=granted_languages(spec, data),
            )
        ],
        broken_speech=broken_speech(spec.abilities[Ability.INT]),
        literacy=literacy(spec, data),
```

- [ ] **Step 5: Extend `known_languages` to accept `granted`**

In `aose/engine/languages.py`, change the signature and body:

```python
def known_languages(chosen, race, alignment, lang_data, granted=()) -> list[str]:
    """Native + alignment tongue + granted (class/race feature) + chosen
    additional, order-stable + deduped (case-insensitive)."""
    ordered = list(native_languages(race))
    ordered.append(alignment_language(alignment, lang_data))
    ordered.extend(granted)
    ordered.extend(chosen)
    out: list[str] = []
    seen: set[str] = set()
    for lang in ordered:
        key = lang.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(lang)
    return out
```

- [ ] **Step 6: Render literacy on the sheet**

In `aose/web/templates/sheet.html`, in the Languages group (after the broken-speech `<p>` at line ~199):

```html
          <p style="margin:0 0 4px;font-size:11px;">Literacy: <strong>{{ sheet.literacy | capitalize }}</strong></p>
```

- [ ] **Step 7: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet.py -k "display_names or literacy" -v`
Expected: PASS.

- [ ] **Step 8: Run the full sheet suite (catch fallout)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet.py tests/test_languages_engine.py -q`
Expected: PASS (other than the unrelated pre-existing breadcrumb failures noted in CLAUDE.md, which are not in these files).

- [ ] **Step 9: Commit**

```bash
git add aose/sheet/view.py aose/engine/languages.py aose/web/templates/sheet.html tests/test_sheet.py
git commit -m "feat(sheet): display-name languages, granted tongues & literacy line"
```

---

## Phase 3 — Wizard languages step

### Task 6: Exclude granted tongues + show display-name options

**Files:**
- Modify: `aose/web/wizard.py`
- Modify: `aose/web/templates/wizard/identity.html`
- Test: `tests/test_wizard_languages.py`

- [ ] **Step 1: Update the failing tests**

In `tests/test_wizard_languages.py`, three tests post/assert title-case values that are now ids. Update them:

`test_identity_renders_language_section_with_native_and_pickers` — change `assert "common" in r.text` to:

```python
    assert "Common" in r.text                       # native tongue, display name
```

`test_identity_stores_chosen_languages` — change the post + assertion to ids:

```python
    r = client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Sage", "alignment": "law", "language": ["dragon", "ogre"]},
    )
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["languages"] == ["dragon", "ogre"]
```

`test_finalized_character_keeps_languages` — post id, assert display name on the sheet:

```python
    client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Polyglot", "alignment": "law", "language": ["dragon"]},
    )
    ...
    assert "Dragon" in page.text
    assert "Lawful" in page.text
```

And in the two "downstream clears" tests, change `["Dragon"]` posts to `["dragon"]` and the `== ["Dragon"]` assertion to `== ["dragon"]`.

Add a new test:

```python
def test_identity_does_not_offer_granted_language_as_pick(tmp_path):
    client = _make_client(tmp_path)
    # Gnome druid: both the gnome burrowing-mammals tongue and druidic are granted.
    draft_id = _drive_to_identity(client, HIGH_INT, race="gnome", cls="druid")
    r = client.get(f"/wizard/{draft_id}/identity")
    # Granted tongues must never appear as a learnable checkbox value.
    assert 'value="druidic"' not in r.text
    assert 'value="secret_language_of_burrowing_mammals"' not in r.text
```

> NOTE: confirm gnome allows druid in `data/races/gnome.yaml allowed_classes`; if not, pick a race/class pair where a granted language exists and the class is allowed (e.g. `race="human", cls="druid"` for `druidic`). Adjust the asserted value accordingly.

- [ ] **Step 2: Run to verify failures**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_languages.py -v`
Expected: the edited tests + new test FAIL (options still title-case; granted not excluded).

- [ ] **Step 3: Update `_languages_context`**

In `aose/web/wizard.py`, replace `_languages_context` body so options carry `{id, name}` and granted tongues are excluded:

```python
def _languages_context(draft: dict[str, Any], data) -> dict:
    """Languages section state for the Identity page."""
    from aose.engine.languages import (
        additional_language_count,
        alignment_language,
        available_additional,
        broken_speech,
        display_name,
        granted_languages,
        native_languages,
    )

    race = data.races[draft["race_id"]]
    final_int = _creation_abilities(draft, data)["INT"]
    native = native_languages(race)

    already = set(native)
    align_tongue = None
    alignment = draft.get("alignment")
    if alignment in data.languages.alignment:
        align_tongue = alignment_language(alignment, data.languages)
        already.add(align_tongue)

    # Granted (class/race feature) tongues are known, never learnable.
    spec_like = _draft_spec_for_languages(draft, data)
    granted = granted_languages(spec_like, data) if spec_like else []
    already.update(granted)

    chosen = draft.get("languages", [])
    options = [
        {"id": lang_id, "name": display_name(lang_id, data.languages)}
        for lang_id in available_additional(data.languages, already)
    ]
    return {
        "native_languages": [display_name(n, data.languages) for n in native],
        "alignment_language": align_tongue,
        "granted_languages": [display_name(g, data.languages) for g in granted],
        "language_slots": additional_language_count(final_int),
        "language_options": options,
        "chosen_languages": chosen,
        "broken_speech": broken_speech(final_int),
    }
```

Add a small helper just above `_languages_context` to build a minimal spec for granted-language lookup from the draft (race + chosen classes + levels):

```python
def _draft_spec_for_languages(draft: dict[str, Any], data):
    """A throwaway CharacterSpec good enough for granted_languages (race + classes).
    Returns None if the draft has no race/class chosen yet."""
    from aose.models import CharacterSpec, ClassEntry

    race_id = draft.get("race_id")
    class_ids = draft.get("class_ids") or ([draft["class_id"]] if draft.get("class_id") else [])
    if not race_id or not class_ids:
        return None
    abil = _creation_abilities(draft, data)
    return CharacterSpec(
        name=draft.get("name") or "draft",
        abilities=abil,
        race_id=race_id,
        alignment=draft.get("alignment") or "neutral",
        classes=[ClassEntry(class_id=c, level=1, hp_rolls=[1]) for c in class_ids],
    )
```

> NOTE: confirm how the draft stores class selection (`draft["class_id"]` vs `draft["class_ids"]`). Inspect `post_class` in `wizard.py` and match it. The helper above handles both single- and multi-class drafts; trim to whichever the draft actually uses.

- [ ] **Step 4: Update the identity template**

In `aose/web/templates/wizard/identity.html`, render native via the (now display-name) list — no change needed for `native_languages` (still a joined list). Add a granted line after the alignment tongue line (~line 54):

```html
        {% if granted_languages %}
        <p class="muted small">Granted: {{ granted_languages | join(", ") }}</p>
        {% endif %}
```

Then update the checkbox loop (lines ~62-65) to use `{id, name}` pairs:

```html
        {% for lang in language_options %}
            <label class="check">
                <input type="checkbox" name="language" value="{{ lang.id }}"
                       {% if lang.id in chosen_languages %}checked{% endif %}>
                {{ lang.name }}
            </label>
        {% endfor %}
```

> NOTE: preserve the exact surrounding markup/classes already in the file; only the `value=`/label text change from a bare string to `lang.id`/`lang.name`.

- [ ] **Step 5: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_languages.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/web/wizard.py aose/web/templates/wizard/identity.html tests/test_wizard_languages.py
git commit -m "feat(wizard): display-name language options; exclude granted tongues"
```

---

## Phase 4 — Conditional racial resilience (data)

### Task 7: Make resilience death/paralysis bonuses conditional

**Files:**
- Modify: `data/races/dwarf.yaml`, `data/races/halfling.yaml`, `data/races/duergar.yaml`
- Test: `tests/test_feature_modifiers.py`

The resilience bonus is vs **poison** (not death-ray) and, for duergar, **paralysis** (not petrify). Add `condition` to the `save:death` and `save:paralysis` granted modifiers so they drop out of the umbrella headline.

- [ ] **Step 1: Update the failing headline tests**

In `tests/test_feature_modifiers.py`, the death/paralysis headline expectations must change (the bonus moves to a conditional line). Replace these tests:

```python
def test_dwarf_resilience_plus3_at_con13():
    base = _saves("human", "fighter", 13)
    dwarf = _saves("dwarf", "fighter", 13)
    assert dwarf["death"] == base["death"]           # poison-only: NOT in death headline
    assert dwarf["spells"] == base["spells"] - 3
    assert dwarf["wands"] == base["wands"] - 3
    assert dwarf["paralysis"] == base["paralysis"]
    assert dwarf["breath"] == base["breath"]


def test_dwarf_resilience_plus5_at_con18():
    base = _saves("human", "fighter", 18)
    dwarf = _saves("dwarf", "fighter", 18)
    assert dwarf["death"] == base["death"]           # headline unchanged
    assert dwarf["spells"] == base["spells"] - 5     # full-category bonus stays


def test_duergar_resilience_includes_paralysis():
    base = _saves("human", "fighter", 13)
    duergar = _saves("duergar", "fighter", 13)
    assert duergar["paralysis"] == base["paralysis"]  # paralysis-only: NOT in headline
    assert duergar["death"] == base["death"]          # poison-only: NOT in headline
    assert duergar["spells"] == base["spells"] - 3    # full-category bonus stays
```

Leave `test_dwarf_resilience_zero_at_low_con` (still equal) and `test_gnome_magic_resistance_excludes_poison` (gnome death already unaffected; spells/wands still −3) as they are — they still hold.

Replace `test_classic_dwarf_resilience_not_doubled` (death headline no longer carries it) with a breakdown-based assertion:

```python
def test_classic_dwarf_resilience_single_poison_line():
    from aose.engine.saves import saving_throws_detail
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="R", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 13, "CHA": 10},
        race_id="dwarf", alignment="neutral",
        classes=[ClassEntry(class_id="dwarf", level=1, hp_rolls=[8])],
    )
    detail = saving_throws_detail(spec, DATA)
    poison_lines = [ln for ln in detail["death"].lines if ln.note.startswith("poison")]
    assert len(poison_lines) == 1          # granted once (race only)
    assert poison_lines[0].bonus == 3
```

> NOTE: this new test depends on `saving_throws_detail` (Task 9). Mark it `@pytest.mark.skip(reason="needs Task 9")` if executing Phase 4 before Phase 5, then un-skip in Task 9. Subagent-driven execution should order Task 9 before un-skipping.

- [ ] **Step 2: Run to verify failures**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -k resilience -v`
Expected: the three edited headline tests FAIL (death still −3/−5; paralysis still −3).

- [ ] **Step 3: Edit dwarf**

In `data/races/dwarf.yaml`, on the resilience `- target: save:death` granted modifier, add `condition: poison` (directly under `op: add`):

```yaml
  - target: save:death
    op: add
    condition: poison
    scale:
      by: ability:CON
      table:
        7: 2
        11: 3
        15: 4
        18: 5
```

Leave `save:spells` and `save:wands` modifiers unchanged.

- [ ] **Step 4: Edit halfling**

In `data/races/halfling.yaml`, apply the identical `condition: poison` to its resilience `- target: save:death` modifier.

- [ ] **Step 5: Edit duergar**

In `data/races/duergar.yaml`, add `condition: poison` to `- target: save:death`, and `condition: paralysis` to `- target: save:paralysis`. Leave `save:spells`/`save:wands` unchanged.

- [ ] **Step 6: Run to verify headline tests pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -k resilience -v`
Expected: PASS (the new `test_classic_dwarf_resilience_single_poison_line` stays skipped until Task 9).

- [ ] **Step 7: Commit**

```bash
git add data/races/dwarf.yaml data/races/halfling.yaml data/races/duergar.yaml tests/test_feature_modifiers.py
git commit -m "fix(data): racial resilience poison/paralysis bonuses are conditional"
```

---

## Phase 5 — WIS saves + breakdown engine

### Task 8: `wisdom_save_modifiers()`

**Files:**
- Modify: `aose/engine/saves.py`
- Test: new `tests/test_saves_breakdown.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_saves_breakdown.py`:

```python
"""WIS magic saves + breakdown view model."""
from pathlib import Path

from aose.models import CharacterSpec, ClassEntry

DATA_DIR = Path(__file__).parent.parent / "data"


def _data():
    from aose.data.loader import GameData
    return GameData.load(DATA_DIR)


DATA = _data()


def _spec(*, wis=10, con=10, race="human", cls="fighter", level=1):
    return CharacterSpec(
        name="W",
        abilities={"STR": 10, "INT": 10, "WIS": wis, "DEX": 10, "CON": con, "CHA": 10},
        race_id=race, alignment="neutral",
        classes=[ClassEntry(class_id=cls, level=level, hp_rolls=[8])],
    )


def test_wisdom_mods_unconditional_on_spells_and_wands():
    from aose.engine.saves import wisdom_save_modifiers
    mods = wisdom_save_modifiers(_spec(wis=16), DATA)   # +2
    by_target = {(m.target, m.condition): m for m in mods}
    assert by_target[("save:spells", None)].value == 2
    assert by_target[("save:wands", None)].value == 2


def test_wisdom_mods_conditional_on_death_and_paralysis():
    from aose.engine.saves import wisdom_save_modifiers
    mods = wisdom_save_modifiers(_spec(wis=16), DATA)
    by_target = {(m.target, m.condition): m for m in mods}
    assert by_target[("save:death", "magical")].value == 2
    assert by_target[("save:paralysis", "magical")].value == 2
    # WIS never targets breath.
    assert not any(m.target == "save:breath" for m in mods)


def test_wisdom_mods_empty_when_zero():
    from aose.engine.saves import wisdom_save_modifiers
    assert wisdom_save_modifiers(_spec(wis=10), DATA) == []


def test_wisdom_mods_negative_penalty():
    from aose.engine.saves import wisdom_save_modifiers
    mods = wisdom_save_modifiers(_spec(wis=4), DATA)    # -2
    assert all(m.value == -2 for m in mods)
    assert all(m.source == "Wisdom" for m in mods)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_saves_breakdown.py -k wisdom_mods -v`
Expected: FAIL — `cannot import name 'wisdom_save_modifiers'`.

- [ ] **Step 3: Implement `wisdom_save_modifiers`**

In `aose/engine/saves.py`, update imports and add the function:

```python
from aose.data.loader import GameData
from aose.models import Ability, CharacterSpec, Modifier

from .ability_mods import ability_modifier
from .features import all_modifiers
from .magic import effective_abilities

SAVE_FLOOR = 2

_WIS_UNCONDITIONAL = ("save:spells", "save:wands")
_WIS_CONDITIONAL = ("save:death", "save:paralysis")   # magical-origin only


def wisdom_save_modifiers(spec: CharacterSpec, data: GameData) -> list[Modifier]:
    """WIS modifier vs magical effects. Unconditional on spells/wands (always
    magical); conditional (``magical``) on death/paralysis; never breath. Empty
    when the WIS modifier is 0."""
    wis = ability_modifier(effective_abilities(spec, data)[Ability.WIS])
    if wis == 0:
        return []
    mods = [Modifier(target=t, op="add", value=wis, source="Wisdom") for t in _WIS_UNCONDITIONAL]
    mods += [
        Modifier(target=t, op="add", value=wis, condition="magical", source="Wisdom")
        for t in _WIS_CONDITIONAL
    ]
    return mods
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_saves_breakdown.py -k wisdom_mods -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/saves.py tests/test_saves_breakdown.py
git commit -m "feat(saves): WIS magic-save modifiers (conditional on death/paralysis)"
```

---

### Task 9: `saving_throws_detail()` + breakdown view models

**Files:**
- Modify: `aose/engine/saves.py`
- Test: `tests/test_saves_breakdown.py`, un-skip in `tests/test_feature_modifiers.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_saves_breakdown.py`:

```python
def test_detail_headline_includes_wis_on_spells_only():
    from aose.engine.saves import saving_throws, saving_throws_detail
    base = saving_throws(_spec(wis=10), DATA)
    hi = saving_throws_detail(_spec(wis=16), DATA)        # +2
    assert hi["spells"].modified == base["spells"] - 2    # WIS in headline
    assert hi["wands"].modified == base["wands"] - 2
    assert hi["death"].modified == base["death"]          # conditional: not in headline
    assert hi["paralysis"].modified == base["paralysis"]
    assert hi["breath"].modified == base["breath"]


def test_detail_death_has_conditional_wis_line():
    from aose.engine.saves import saving_throws_detail
    detail = saving_throws_detail(_spec(wis=16), DATA)
    wis_lines = [ln for ln in detail["death"].lines
                 if ln.source == "Wisdom" and ln.conditional]
    assert len(wis_lines) == 1
    assert wis_lines[0].bonus == 2
    assert "magical" in wis_lines[0].note


def test_detail_base_is_class_progression():
    from aose.engine.saves import saving_throws_detail
    detail = saving_throws_detail(_spec(wis=16), DATA)
    # Base excludes all modifiers; fighter L1 death base is 12.
    assert detail["death"].base == 12


def test_detail_dwarf_poison_and_spells_lines():
    from aose.engine.saves import saving_throws_detail
    detail = saving_throws_detail(_spec(con=13, race="dwarf"), DATA)
    # spells: unconditional resilience line, in the headline.
    spells_res = [ln for ln in detail["spells"].lines if ln.source == "Resilience"]
    assert spells_res and spells_res[0].conditional is False and spells_res[0].bonus == 3
    # death: conditional poison line, NOT in the headline.
    death_res = [ln for ln in detail["death"].lines if ln.source == "Resilience"]
    assert death_res and death_res[0].conditional is True
    assert death_res[0].note.startswith("poison")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_saves_breakdown.py -k detail -v`
Expected: FAIL — `cannot import name 'saving_throws_detail'`.

- [ ] **Step 3: Implement the breakdown**

In `aose/engine/saves.py`, add the models + functions and refactor `saving_throws` to delegate. Add `from pydantic import BaseModel` at the top.

```python
from pydantic import BaseModel

_CONDITION_NOTES = {
    "magical": "magical effects only",
    "poison": "poison only (not death magic)",
    "paralysis": "paralysis only (not petrification)",
}


class SaveModLine(BaseModel):
    source: str          # feature/item name, or "Wisdom"
    bonus: int           # +N = bonus (better), -N = penalty (worse)
    conditional: bool    # True when the modifier carries a condition
    note: str            # condition note ("" when unconditional)


class SaveBreakdown(BaseModel):
    category: str        # death / wands / paralysis / breath / spells
    base: int            # class progression best (no modifiers)
    modified: int        # headline (unconditional modifiers, floored)
    lines: list[SaveModLine]


def _base_saves(spec: CharacterSpec, data: GameData) -> dict[str, int]:
    best: dict[str, int] = {}
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        ld = _level_data(cls, entry.level)
        for name, value in ld.saves.items():
            if name not in best or value < best[name]:
                best[name] = value
    return best


def _all_save_mods(spec: CharacterSpec, data: GameData) -> list[Modifier]:
    return all_modifiers(spec, data) + wisdom_save_modifiers(spec, data)


def saving_throws_detail(spec: CharacterSpec, data: GameData) -> dict[str, SaveBreakdown]:
    """Per-category base, headline (unconditional mods only), and every
    contributing add-modifier as a line (conditional ones flagged, excluded from
    the headline)."""
    base = _base_saves(spec, data)
    mods = _all_save_mods(spec, data)
    out: dict[str, SaveBreakdown] = {}
    for name, base_val in base.items():
        wanted = ("save:all", f"save:{name}")
        relevant = [m for m in mods if m.target in wanted]
        uncond = [m for m in relevant if m.condition is None]

        target = base_val
        sets = [m.value for m in uncond if m.op == "set"]
        if sets:
            target = sets[-1]
        target -= sum(m.value for m in uncond if m.op == "add")
        for m in uncond:
            if m.op == "set_min":
                target = max(target, m.value)
            elif m.op == "set_max":
                target = min(target, m.value)
        modified = max(SAVE_FLOOR, target)

        lines = [
            SaveModLine(
                source=m.source or "—",
                bonus=m.value,
                conditional=m.condition is not None,
                note=_CONDITION_NOTES.get(m.condition, "") if m.condition else "",
            )
            for m in relevant if m.op == "add"
        ]
        out[name] = SaveBreakdown(category=name, base=base_val, modified=modified, lines=lines)
    return out


def saving_throws(spec: CharacterSpec, data: GameData) -> dict[str, int]:
    """Headline (modified) save number per category — thin view over
    ``saving_throws_detail``."""
    return {name: bd.modified for name, bd in saving_throws_detail(spec, data).items()}
```

Remove the old `saving_throws` body (the one that looped and applied mods inline) — it is fully replaced by the delegation above.

- [ ] **Step 4: Run the breakdown + feature-modifier suites**

Un-skip `test_classic_dwarf_resilience_single_poison_line` in `tests/test_feature_modifiers.py` (remove the `@pytest.mark.skip`).

Run: `.venv\Scripts\python.exe -m pytest tests/test_saves_breakdown.py tests/test_feature_modifiers.py -q`
Expected: PASS.

- [ ] **Step 5: Run the broader save consumers**

Run: `.venv\Scripts\python.exe -m pytest tests/test_derivation.py tests/test_magic_items.py -q`
Expected: `test_derivation.py` FAILS at the dwarf death assertion (line ~97) — that is fixed in Task 10. Note the failure and proceed.

- [ ] **Step 6: Commit**

```bash
git add aose/engine/saves.py tests/test_saves_breakdown.py tests/test_feature_modifiers.py
git commit -m "feat(saves): base/modified breakdown view model; saving_throws delegates"
```

---

## Phase 6 — Saves UI

### Task 10: `SheetSave` base/modified/lines + clickable breakdown modal

**Files:**
- Modify: `aose/sheet/view.py`
- Modify: `aose/web/templates/sheet.html`
- Test: `tests/test_sheet.py`, `tests/test_derivation.py`

- [ ] **Step 1: Update the failing tests**

In `tests/test_derivation.py` (~line 97), the dwarf death headline no longer includes resilience:

```python
    assert s["death"] == 10  # L4 base 10; dwarf poison bonus is conditional, not in headline
```

In `tests/test_sheet.py` (~line 58), `sheet.saves[0]` (death) now exposes `.modified` equal to the base (resilience is conditional):

```python
    assert sheet.saves[0].modified == 12  # L1 fighter death base; dwarf poison bonus conditional
```

Add a sheet-level breakdown test:

```python
def test_sheet_save_exposes_breakdown(sheet_for):
    sheet = sheet_for("dwarf", "fighter", con=13)
    death = next(s for s in sheet.saves if s.name == "death")
    assert death.base == 12
    assert death.modified == 12
    poison = [ln for ln in death.lines if ln.note.startswith("poison")]
    assert poison and poison[0].bonus == 3 and poison[0].conditional
```

> NOTE: adapt `sheet_for` to the file's existing sheet helper, and pass `con=13` however that helper accepts abilities.

- [ ] **Step 2: Run to verify failures**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet.py tests/test_derivation.py -k "save or death" -v`
Expected: FAIL — `SheetSave` has no `modified`/`base`/`lines`.

- [ ] **Step 3: Extend the sheet view models**

In `aose/sheet/view.py`, replace `SheetSave` (lines ~70-73) and add a line model:

```python
class SheetSaveLine(BaseModel):
    source: str
    bonus: int
    conditional: bool
    note: str


class SheetSave(BaseModel):
    name: str
    label: str
    base: int
    modified: int
    lines: list[SheetSaveLine]
```

- [ ] **Step 4: Build the rows from the breakdown**

In `aose/sheet/view.py`, replace the `save_dict`/`save_rows` construction (lines ~1002-1006):

```python
    save_detail = saves.saving_throws_detail(spec, data)
    save_rows = [
        SheetSave(
            name=name,
            label=SAVE_LABELS[name],
            base=save_detail[name].base,
            modified=save_detail[name].modified,
            lines=[
                SheetSaveLine(source=ln.source, bonus=ln.bonus,
                              conditional=ln.conditional, note=ln.note)
                for ln in save_detail[name].lines
            ],
        )
        for name in SAVE_ORDER
        if name in save_detail
    ]
```

- [ ] **Step 5: Update the saves block + add the modal**

In `aose/web/templates/sheet.html`, make each save row a modal trigger (lines ~129-135):

```html
            {% for s in sheet.saves %}
            <div class="save clickable" data-modal="modal-save-{{ s.name }}">
              <span class="cap">{{ s.label[0] }}</span>
              <span class="nm">{{ s.label }}</span>
              <span class="tg">{{ s.modified }}{% if s.modified != s.base %}<sup class="muted">({{ s.base }})</sup>{% endif %}</span>
            </div>
            {% endfor %}
```

Then add one modal per save near the other bottom-of-page modals (e.g. just after the `modal-feature` block around line 645):

```html
{% for s in sheet.saves %}
<div class="overlay modal" id="modal-save-{{ s.name }}" role="dialog" aria-label="{{ s.label }} save">
  <div class="ov-head"><h3>{{ s.label }}</h3><button class="x" data-close>×</button></div>
  <div class="ov-body" style="font-size:14px">
    <p style="margin:0 0 6px">Base <strong>{{ s.base }}</strong> → Modified <strong>{{ s.modified }}</strong></p>
    {% if s.lines %}
    <ul style="list-style:none;margin:0;padding:0">
      {% for ln in s.lines %}
      <li style="margin:2px 0">
        <strong>{{ ln.source }}:</strong>
        {% if ln.bonus >= 0 %}+{{ ln.bonus }} bonus{% else %}{{ ln.bonus }} penalty{% endif %}
        {% if ln.conditional %}<span class="muted">— {{ ln.note }}</span>{% endif %}
      </li>
      {% endfor %}
    </ul>
    {% else %}
    <p class="muted" style="margin:0">No modifiers — base value applies.</p>
    {% endif %}
  </div>
</div>
{% endfor %}
```

- [ ] **Step 6: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet.py tests/test_derivation.py -q`
Expected: PASS.

- [ ] **Step 7: Visual check (preview)**

Start the app and open a dwarf character's sheet; click the Death / Poison save row and confirm the modal shows base 12, the conditional "+3 bonus — poison only" Resilience line, and (with WIS ≠ 10) a conditional Wisdom line. (Use the preview workflow; this is observable in the browser.)

```powershell
.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload
```

- [ ] **Step 8: Commit**

```bash
git add aose/sheet/view.py aose/web/templates/sheet.html tests/test_sheet.py tests/test_derivation.py
git commit -m "feat(sheet): base/modified saves with click-through breakdown modal"
```

---

## Phase 7 — Full-suite verification

### Task 11: Run everything & fix fallout

**Files:** none (verification)

- [ ] **Step 1: Full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS except the two pre-existing breadcrumb-label failures in `test_wizard_class_setup` / `test_wizard_identity` documented in CLAUDE.md. If any *other* test fails, it is fallout from this work — fix it (most likely another hard-coded save number or a lowercase-language assertion).

- [ ] **Step 2: Update CLAUDE.md**

Add a "Current state (2026-06-07, languages/literacy/WIS-saves)" section summarizing: the language registry + `display_name` fallback, `granted_languages`, three-tier `literacy` + `illiterate_below_level`, WIS `wisdom_save_modifiers`, conditional resilience (`poison`/`paralysis`), and the `saving_throws_detail` breakdown + sheet modal.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: note languages/literacy/WIS-saves feature in CLAUDE.md"
```

---

## Self-Review

**Spec coverage:**
- A1 registry + display names → Tasks 1, 2 ✓
- A2 granted languages (non-learnable) → Tasks 3, 5, 6 ✓
- A3 three-tier literacy + barbarian override → Task 4, 5 ✓
- B1 WIS synthetic modifiers → Task 8 ✓
- B1a conditional resilience (poison/paralysis) → Task 7 ✓
- B2 headline vs breakdown split → Task 9 ✓
- B3 breakdown view model + bonus/penalty framing → Tasks 9, 10 ✓
- B4 category + condition labels → `_CONDITION_NOTES` (Task 9) + `SAVE_LABELS` (existing, Task 10) ✓
- B5 clickable rows + modal → Task 10 ✓

**Type consistency:** `SaveModLine`/`SaveBreakdown` (engine, Task 9) mirror `SheetSaveLine`/`SheetSave` (view, Task 10) field-for-field (`source`, `bonus`, `conditional`, `note`; `base`, `modified`, `lines`). `known_languages(..., granted=())` defined in Task 5 and called in Task 5. `display_name`/`granted_languages`/`literacy` signatures consistent across Tasks 1/3/4/5/6.

**Open implementer NOTES (intentional, must be resolved during execution):**
1. Task 5/10 — adapt the `sheet_for`/sheet helper to whatever `tests/test_sheet.py` already uses.
2. Task 6 — confirm the draft's class-selection key (`class_id` vs `class_ids`) against `post_class`; confirm a race/class pair where a granted language exists and the class is allowed.
3. Task 9 — fighter L1 death base assumed 12 (matches the existing `test_sheet.py` comment); verify against `data/classes/fighter.yaml` if a test disagrees.
