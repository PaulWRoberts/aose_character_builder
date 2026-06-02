# Wizard Languages Subsystem (Slice 6b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a languages subsystem to the AOSE builder — native (race) languages, an auto alignment language, and INT-based additional-language selection on the Identity page — surfaced on the character sheet.

**Architecture:** New `LanguageData` model + `data/languages.yaml` loaded into `GameData.languages`; a pure cycle-free `aose/engine/languages.py` core (count/broken-speech/native/alignment/available/known/validate); `CharacterSpec.languages` stores **only the chosen additional** languages (native + alignment are derived). The Identity page (Slice 6a) gains a Languages section; the sheet composes the full list. Downstream-clear helpers drop the chosen languages whenever final INT could shift.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, YAML, pytest. Windows: run via `.venv\Scripts\python.exe`.

---

## Background for the implementer

You have **zero assumed context**. Read these before starting:

- `aose/data/loader.py` — `GameData` dataclass + `GameData.load`. Optional files (spell_lists, secondary_skills, weapon_qualities) each have a `_load_*` helper that returns an empty default when the file is absent so minimal test fixtures still load. You will add `_load_languages` in the same style.
- `aose/models/spell_list.py` — the smallest model in the repo; mirror its style (`model_config = ConfigDict(extra="forbid")`).
- `aose/models/character.py` — `CharacterSpec`. You add one field.
- `aose/engine/spells.py:18` — `class SpellError(ValueError)`; mirror for `LanguageError`.
- `aose/web/wizard.py` — the Identity routes are `get_identity` (line ~778) and `post_identity` (line ~815). `_creation_abilities(draft, data)` (line ~448) returns the **final** ability scores (post-racial + P5 adjustment). The downstream-clear helpers are `_clear_after_abilities`, `_clear_after_race`, `_clear_after_class` (lines ~171-191), plus targeted pops in `_apply_rule_changes` (line ~338) and `post_adjust` (line ~718).
- `aose/sheet/view.py:507` — `languages=race.languages` in `build_sheet`. `Ability`, `GameData` and `ABILITY_ORDER` are already imported there.
- `aose/web/templates/wizard/identity.html` — the page partial you extend.
- `tests/test_wizard_identity.py` — `_make_client` / `_drive_to_identity` helpers you will reuse. `DATA_DIR` points at the real `data/`.
- `tests/test_data_loading.py` — module-scoped `data` fixture = `GameData.load(DATA_DIR)`.

**Key gotcha — casing.** Race languages in `data/races/*.yaml` are **lowercase ids** (`elvish`, `gnoll`, `orcish`, `common`). The additional list in the spec is **title-case display names** (`Elvish`, `Gnoll`, `Orcish`). The exclusion logic in `available_additional` / `known_languages` MUST compare **case-insensitively** (via `str.casefold()`) so a player can't pick a language they already speak natively. Display values are kept as-is; only the comparison is normalised.

**No migrations** — nothing is deployed. Don't write backward-compat shims.

Run the full suite at the end of each task:

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

(The trailing `PermissionError` on `pytest-current` is a known Windows quirk — ignore it.)

---

## File Structure

| Path | Responsibility | Action |
|---|---|---|
| `data/languages.yaml` | Seed data: alignment tongues + default additional list | Create |
| `aose/models/language.py` | `LanguageData` typed model | Create |
| `aose/models/__init__.py` | Export `LanguageData` | Modify |
| `aose/data/loader.py` | `_load_languages` + `GameData.languages` field | Modify |
| `aose/models/character.py` | `CharacterSpec.languages` field | Modify |
| `aose/engine/languages.py` | Pure cycle-free language engine + `LanguageError` | Create |
| `aose/sheet/view.py` | Compose known languages + broken-speech flag | Modify |
| `aose/web/wizard.py` | Identity GET/POST languages section + clears | Modify |
| `aose/web/templates/wizard/identity.html` | Languages section UI | Modify |
| `tests/test_languages_engine.py` | Engine unit tests | Create |
| `tests/test_wizard_languages.py` | Wizard + sheet integration tests | Create |
| `tests/test_data_loading.py` | `languages.yaml` loads | Modify |

---

## Task 1: Data file + `LanguageData` model + loader wiring

**Files:**
- Create: `data/languages.yaml`
- Create: `aose/models/language.py`
- Modify: `aose/models/__init__.py`
- Modify: `aose/data/loader.py`
- Test: `tests/test_data_loading.py`

- [ ] **Step 1: Create the data file**

Create `data/languages.yaml` (UTF-8 — note the diacritic in "Doppelgänger"):

```yaml
alignment:
  law: Lawful
  neutral: Neutral
  chaos: Chaotic
additional:
  - Bugbear
  - Doppelgänger
  - Dragon
  - Dwarvish
  - Elvish
  - Gargoyle
  - Gnoll
  - Gnomish
  - Goblin
  - Halfling
  - Harpy
  - Hobgoblin
  - Kobold
  - Lizard man
  - Medusa
  - Minotaur
  - Ogre
  - Orcish
  - Pixie
  - Human dialect
```

- [ ] **Step 2: Create the model**

Create `aose/models/language.py`:

```python
from pydantic import BaseModel, ConfigDict, Field


class LanguageData(BaseModel):
    """Campaign language registry.  ``alignment`` maps an alignment id
    (law / neutral / chaos) to its tongue's display name; ``additional`` is the
    selectable list of extra languages an intelligent character may learn.

    Defaults are empty so the loader stays usable with minimal test data dirs.
    """
    model_config = ConfigDict(extra="forbid")

    alignment: dict[str, str] = Field(default_factory=dict)
    additional: list[str] = Field(default_factory=list)
```

- [ ] **Step 3: Export it from the models package**

In `aose/models/__init__.py`, add the import after the `spell_list` import line and add `"LanguageData"` to `__all__`:

```python
from .spell_list import SpellList
from .language import LanguageData
```

```python
    "SpellList",
    "LanguageData",
```

- [ ] **Step 4: Write the failing loader test**

Add to `tests/test_data_loading.py` (the `data` fixture already exists):

```python
def test_languages_loaded(data):
    langs = data.languages
    assert langs.alignment["law"] == "Lawful"
    assert langs.alignment["neutral"] == "Neutral"
    assert langs.alignment["chaos"] == "Chaotic"
    assert "Elvish" in langs.additional
    # UTF-8 diacritic survives the load round-trip.
    assert "Doppelgänger" in langs.additional
```

- [ ] **Step 5: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py::test_languages_loaded -q`
Expected: FAIL — `AttributeError: 'GameData' object has no attribute 'languages'`.

- [ ] **Step 6: Wire the loader**

In `aose/data/loader.py`:

Add `LanguageData` to the model import block:

```python
from aose.models import (
    CharClass,
    Item,
    LanguageData,
    Race,
    Spell,
    SpellList,
    WeaponQuality,
)
```

Add a loader helper next to `_load_spell_lists`:

```python
def _load_languages(data_dir: Path) -> LanguageData:
    """Read ``languages.yaml`` (a mapping with ``alignment`` + ``additional``).

    Returns an empty ``LanguageData`` when the file is absent so minimal test
    fixtures (a bare data dir) still load.
    """
    path = data_dir / "languages.yaml"
    if not path.exists():
        return LanguageData()
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError("languages.yaml must be a YAML mapping")
    return LanguageData.model_validate(raw)
```

Add the field to the `GameData` dataclass (after `secondary_skills`):

```python
    secondary_skills: list[str] = field(default_factory=list)
    languages: LanguageData = field(default_factory=LanguageData)
```

Add it to `GameData.load`'s constructor call (after `secondary_skills=...`):

```python
            secondary_skills=_load_secondary_skills(data_dir),
            languages=_load_languages(data_dir),
```

- [ ] **Step 7: Run the loader test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py::test_languages_loaded -q`
Expected: PASS.

- [ ] **Step 8: Add `CharacterSpec.languages` field + test**

In `aose/models/character.py`, add to `CharacterSpec` (after `secondary_skill`):

```python
    secondary_skill: str | None = None
    # Chosen *additional* languages only (INT-based picks).  Native (race) and
    # alignment tongues are derived at display time, never stored here.
    languages: list[str] = Field(default_factory=list)
```

Add to `tests/test_data_loading.py`:

```python
def test_character_spec_languages_defaults_empty():
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="X", abilities={}, race_id="human",
        classes=[ClassEntry(class_id="fighter")], alignment="law",
    )
    assert spec.languages == []
```

- [ ] **Step 9: Run both tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py -q`
Expected: PASS.

- [ ] **Step 10: Commit**

```powershell
git add data/languages.yaml aose/models/language.py aose/models/__init__.py aose/data/loader.py aose/models/character.py tests/test_data_loading.py
git commit -m "feat(languages): LanguageData model + data file + CharacterSpec.languages field"
```

---

## Task 2: Engine — `additional_language_count` + `broken_speech` + `LanguageError`

**Files:**
- Create: `aose/engine/languages.py`
- Test: `tests/test_languages_engine.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_languages_engine.py`:

```python
import pytest

from aose.engine.languages import (
    LanguageError,
    additional_language_count,
    broken_speech,
)


@pytest.mark.parametrize("score,expected", [
    (3, 0), (8, 0), (12, 0), (13, 1), (15, 1), (16, 2), (17, 2), (18, 3),
])
def test_additional_language_count(score, expected):
    assert additional_language_count(score) == expected


def test_broken_speech_only_at_three():
    assert broken_speech(3) is True
    assert broken_speech(4) is False
    assert broken_speech(12) is False


def test_language_error_is_valueerror():
    assert issubclass(LanguageError, ValueError)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_languages_engine.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aose.engine.languages'`.

- [ ] **Step 3: Write the minimal implementation**

Create `aose/engine/languages.py`:

```python
"""Languages subsystem — pure / cycle-free.

Imports only models (no engine, no web).  Native languages come from the race;
the alignment tongue is auto-determined by alignment; additional languages are
INT-gated player picks.  All exclusion/dedup comparisons are case-insensitive
(race langs are lowercase ids like ``elvish``; the additional list is
title-case display names like ``Elvish``).
"""
from __future__ import annotations


class LanguageError(ValueError):
    """Raised when a language selection is invalid."""


def additional_language_count(int_score: int) -> int:
    """Number of additional languages granted by *final* INT (OSE table)."""
    if int_score >= 18:
        return 3
    if int_score >= 16:
        return 2
    if int_score >= 13:
        return 1
    return 0


def broken_speech(int_score: int) -> bool:
    """INT 3 speaks in broken sentences — a display note, grants 0 additional."""
    return int_score == 3
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_languages_engine.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add aose/engine/languages.py tests/test_languages_engine.py
git commit -m "feat(languages): INT->count table + broken-speech + LanguageError"
```

---

## Task 3: Engine — `native_languages`, `alignment_language`, `available_additional`, `known_languages`

**Files:**
- Modify: `aose/engine/languages.py`
- Test: `tests/test_languages_engine.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_languages_engine.py` (top-of-file additions + new tests):

```python
from pathlib import Path

from aose.data.loader import GameData
from aose.engine.languages import (
    available_additional,
    alignment_language,
    known_languages,
    native_languages,
)

DATA_DIR = Path(__file__).parent.parent / "data"


def _data():
    return GameData.load(DATA_DIR)


def test_native_languages_from_race():
    data = _data()
    elf = data.races["elf"]
    assert native_languages(elf) == elf.languages
    assert "elvish" in native_languages(elf)


def test_alignment_language_lookup():
    data = _data()
    assert alignment_language("law", data.languages) == "Lawful"
    assert alignment_language("chaos", data.languages) == "Chaotic"


def test_available_additional_excludes_known_case_insensitively():
    data = _data()
    elf = data.races["elf"]  # native incl. elvish, gnoll, hobgoblin, orcish
    avail = available_additional(data.languages, set(native_languages(elf)))
    # Title-case "Elvish" must be excluded even though native is "elvish".
    assert "Elvish" not in avail
    assert "Gnoll" not in avail
    assert "Orcish" not in avail
    # Something the elf doesn't natively speak is still offered.
    assert "Dragon" in avail
    # No duplicates.
    assert len(avail) == len(set(avail))


def test_known_languages_composes_and_dedupes_in_order():
    data = _data()
    human = data.races["human"]  # native: ["common"]
    known = known_languages(["Dragon"], human, "law", data.languages)
    # native, then alignment, then chosen — stable order.
    assert known == ["common", "Lawful", "Dragon"]


def test_known_languages_dedupes_case_insensitively():
    data = _data()
    elf = data.races["elf"]
    # Even if a chosen value duplicates a native tongue by case, it appears once.
    known = known_languages(["elvish"], elf, "neutral", data.languages)
    lowered = [k.casefold() for k in known]
    assert len(lowered) == len(set(lowered))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_languages_engine.py -q`
Expected: FAIL — `ImportError: cannot import name 'available_additional'`.

- [ ] **Step 3: Write the implementation**

Append to `aose/engine/languages.py`:

```python
def native_languages(race) -> list[str]:
    """The character's racial native tongues (already includes Common)."""
    return list(race.languages)


def alignment_language(alignment: str, lang_data) -> str:
    """The tongue for an alignment id (law / neutral / chaos)."""
    return lang_data.alignment[alignment]


def available_additional(lang_data, already_known: set[str]) -> list[str]:
    """The additional list minus any language already known, compared
    case-insensitively.  Order-stable, no duplicates."""
    known = {k.casefold() for k in already_known}
    out: list[str] = []
    seen: set[str] = set()
    for lang in lang_data.additional:
        key = lang.casefold()
        if key in known or key in seen:
            continue
        seen.add(key)
        out.append(lang)
    return out


def known_languages(chosen, race, alignment, lang_data) -> list[str]:
    """Native + alignment tongue + chosen additional, order-stable + deduped
    (case-insensitive)."""
    ordered = list(native_languages(race))
    ordered.append(alignment_language(alignment, lang_data))
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

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_languages_engine.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add aose/engine/languages.py tests/test_languages_engine.py
git commit -m "feat(languages): native/alignment/available/known composition helpers"
```

---

## Task 4: Engine — `validate_languages`

**Files:**
- Modify: `aose/engine/languages.py`
- Test: `tests/test_languages_engine.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_languages_engine.py`:

```python
from aose.engine.languages import validate_languages


def test_validate_languages_within_limit_passes():
    data = _data()
    human = data.races["human"]  # INT 16 -> 2 additional allowed
    validate_languages(["Dragon", "Ogre"], human, "law", 16, data.languages)


def test_validate_languages_empty_always_passes():
    data = _data()
    human = data.races["human"]
    validate_languages([], human, "law", 9, data.languages)


def test_validate_languages_too_many_fails():
    data = _data()
    human = data.races["human"]  # INT 13 -> only 1 allowed
    with pytest.raises(LanguageError):
        validate_languages(["Dragon", "Ogre"], human, "law", 13, data.languages)


def test_validate_languages_rejects_native_tongue():
    data = _data()
    elf = data.races["elf"]  # natively speaks elvish
    with pytest.raises(LanguageError):
        validate_languages(["Elvish"], elf, "neutral", 18, data.languages)


def test_validate_languages_rejects_alignment_tongue():
    data = _data()
    human = data.races["human"]
    with pytest.raises(LanguageError):
        validate_languages(["Lawful"], human, "law", 18, data.languages)


def test_validate_languages_rejects_duplicates():
    data = _data()
    human = data.races["human"]
    with pytest.raises(LanguageError):
        validate_languages(["Dragon", "Dragon"], human, "law", 18, data.languages)


def test_validate_languages_rejects_unknown():
    data = _data()
    human = data.races["human"]
    with pytest.raises(LanguageError):
        validate_languages(["Klingon"], human, "law", 18, data.languages)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_languages_engine.py -q`
Expected: FAIL — `ImportError: cannot import name 'validate_languages'`.

- [ ] **Step 3: Write the implementation**

Append to `aose/engine/languages.py`:

```python
def validate_languages(chosen, race, alignment, final_int, lang_data) -> None:
    """Raise ``LanguageError`` unless the chosen additional languages are valid:

    * at most ``additional_language_count(final_int)`` of them,
    * no case-insensitive duplicates within the choices,
    * each is in ``available_additional`` (i.e. in the data list AND not already
      native or the alignment tongue).
    """
    limit = additional_language_count(final_int)
    if len(chosen) > limit:
        raise LanguageError(
            f"At most {limit} additional language(s) at INT {final_int}; "
            f"got {len(chosen)}."
        )

    seen: set[str] = set()
    for lang in chosen:
        key = lang.casefold()
        if key in seen:
            raise LanguageError(f"Duplicate language: {lang!r}")
        seen.add(key)

    already = set(native_languages(race)) | {alignment_language(alignment, lang_data)}
    allowed = {a.casefold() for a in available_additional(lang_data, already)}
    for lang in chosen:
        if lang.casefold() not in allowed:
            raise LanguageError(f"{lang!r} is not a selectable additional language.")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_languages_engine.py -q`
Expected: PASS (all engine tests).

- [ ] **Step 5: Commit**

```powershell
git add aose/engine/languages.py tests/test_languages_engine.py
git commit -m "feat(languages): validate_languages selection guard"
```

---

## Task 5: Sheet integration — composed languages + broken-speech note

**Files:**
- Modify: `aose/sheet/view.py:154` (add `broken_speech` field), `aose/sheet/view.py:507` (compose languages)
- Test: `tests/test_sheet.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_sheet.py` (it already builds specs against the real `data/` — mirror an existing test's fixture style for how `data` / a spec is constructed; use `build_sheet`). Add:

```python
def test_sheet_composes_native_alignment_and_chosen_languages():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.models import CharacterSpec, ClassEntry
    from aose.sheet.view import build_sheet

    data = GameData.load(Path(__file__).parent.parent / "data")
    spec = CharacterSpec(
        name="Linguist",
        abilities={"STR": 10, "INT": 16, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter")],
        alignment="law", languages=["Dragon", "Ogre"],
    )
    sheet = build_sheet(spec, data)
    assert "common" in sheet.languages          # native
    assert "Lawful" in sheet.languages          # alignment tongue
    assert "Dragon" in sheet.languages and "Ogre" in sheet.languages
    assert sheet.broken_speech is False


def test_sheet_flags_broken_speech_at_int_3():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.models import CharacterSpec, ClassEntry
    from aose.sheet.view import build_sheet

    data = GameData.load(Path(__file__).parent.parent / "data")
    spec = CharacterSpec(
        name="Grog",
        abilities={"STR": 13, "INT": 3, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter")],
        alignment="neutral",
    )
    sheet = build_sheet(spec, data)
    assert sheet.broken_speech is True
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet.py::test_sheet_composes_native_alignment_and_chosen_languages tests/test_sheet.py::test_sheet_flags_broken_speech_at_int_3 -q`
Expected: FAIL — `AttributeError: 'CharacterSheet' object has no attribute 'broken_speech'`.

- [ ] **Step 3: Add the import**

In `aose/sheet/view.py`, add to the engine imports (after line 16's leveling import or alongside the others):

```python
from aose.engine.languages import broken_speech, known_languages
```

- [ ] **Step 4: Add the `broken_speech` field to `CharacterSheet`**

In `aose/sheet/view.py`, in the `CharacterSheet` model, change the languages line (line ~154) to add a sibling field:

```python
    languages: list[str]
    broken_speech: bool              # INT 3 — speaks only in broken sentences
```

- [ ] **Step 5: Compose languages in `build_sheet`**

In `aose/sheet/view.py`, replace `languages=race.languages,` (line ~507) with:

```python
        languages=known_languages(spec.languages, race, spec.alignment, data.languages),
        broken_speech=broken_speech(spec.abilities[Ability.INT]),
```

(`spec.abilities` holds the creation-final scores — post-racial + P5 — which is the "final INT" the languages were allocated against. `Ability` is already imported.)

- [ ] **Step 6: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet.py -q`
Expected: PASS.

- [ ] **Step 7: Surface the note in the sheet template**

Read `aose/web/templates/sheet.html:249` (the languages `<p>`). Add the broken-speech note directly after it:

```html
                <p>{{ sheet.languages | join(", ") if sheet.languages else "—" }}</p>
                {% if sheet.broken_speech %}
                <p class="muted small">Speaks only in broken sentences (INT 3).</p>
                {% endif %}
```

- [ ] **Step 8: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (watch for any other test asserting the old `languages=race.languages` value — if one breaks, update it to expect the composed list, since alignment tongue + Common now appear).

- [ ] **Step 9: Commit**

```powershell
git add aose/sheet/view.py aose/web/templates/sheet.html tests/test_sheet.py
git commit -m "feat(languages): compose native+alignment+chosen on sheet + broken-speech note"
```

---

## Task 6: Wizard Identity — render the Languages section (GET)

**Files:**
- Modify: `aose/web/wizard.py` (`get_identity`, new `_languages_context` helper)
- Modify: `aose/web/templates/wizard/identity.html`
- Test: `tests/test_wizard_languages.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_wizard_languages.py`:

```python
"""Languages section on the Identity page + draft clears."""
from pathlib import Path

from fastapi.testclient import TestClient

from aose.characters import load_draft, save_draft, save_settings
from aose.models import RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def _make_client(tmp_path, ruleset=None):
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, ruleset or RuleSet())
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=tmp_path / "characters",
        drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._drafts_dir = tmp_path / "drafts"
    return client


def _drive_to_identity(client, abilities, race="human", cls="fighter"):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = abilities
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": race})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": cls})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    return draft_id


HIGH_INT = {"STR": 13, "INT": 16, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 13}
LOW_INT = {"STR": 13, "INT": 9, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 13}


def test_identity_renders_language_section_with_native_and_pickers(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, HIGH_INT)  # INT 16 -> 2 additional
    r = client.get(f"/wizard/{draft_id}/identity")
    assert r.status_code == 200
    assert "Languages" in r.text
    assert "common" in r.text                       # native tongue shown
    # INT 16 grants 2 additional pickers -> two checkbox inputs named "language".
    assert r.text.count('name="language"') == 2


def test_identity_no_pickers_when_int_low(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, LOW_INT)  # INT 9 -> 0 additional
    r = client.get(f"/wizard/{draft_id}/identity")
    assert r.text.count('name="language"') == 0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_languages.py -k renders -q`
Expected: FAIL — the page has no "Languages" section / no `name="language"` inputs.

- [ ] **Step 3: Add the context helper**

In `aose/web/wizard.py`, add this helper near `_identity_alignment_options` (~line 767):

```python
def _languages_context(draft: dict[str, Any], data) -> dict:
    """Languages section state for the Identity page: native list (from race),
    the alignment tongue for the *current* draft alignment (if chosen yet), the
    INT-gated additional pickers, and the broken-speech note."""
    from aose.engine.languages import (
        additional_language_count,
        alignment_language,
        available_additional,
        broken_speech,
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

    chosen = draft.get("languages", [])
    options = available_additional(data.languages, already)
    return {
        "native_languages": native,
        "alignment_language": align_tongue,
        "language_slots": additional_language_count(final_int),
        "language_options": options,
        "chosen_languages": chosen,
        "broken_speech": broken_speech(final_int),
    }
```

- [ ] **Step 4: Feed it into `get_identity`**

In `aose/web/wizard.py`, in `get_identity` (~line 778), before the final `return templates.TemplateResponse(...)`, add:

```python
    ctx.update(_languages_context(draft, data))
```

- [ ] **Step 5: Render the section in the template**

In `aose/web/templates/wizard/identity.html`, add a Languages fieldset inside the `<form>` (after the Secondary Skill block, before the submit button at line 38):

```html
    <fieldset class="field">
        <legend>Languages</legend>
        <p class="muted small">Native: {{ native_languages | join(", ") }}</p>
        {% if alignment_language %}
        <p class="muted small">Alignment tongue: {{ alignment_language }}</p>
        {% endif %}
        {% if broken_speech %}
        <p class="muted small">Your character speaks only in broken sentences (INT 3) — no additional languages.</p>
        {% endif %}
        {% if language_slots > 0 %}
        <p class="muted small">You may choose up to {{ language_slots }} additional
           language(s). Choosing fewer is allowed.</p>
        <div class="checkbox-stack">
        {% for lang in language_options %}
            <label class="checkbox-row">
                <input type="checkbox" name="language" value="{{ lang }}"
                       {% if lang in chosen_languages %}checked{% endif %}>
                <span>{{ lang }}</span>
            </label>
        {% endfor %}
        </div>
        {% endif %}
    </fieldset>
```

- [ ] **Step 6: Run the GET tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_languages.py -k "renders or no_pickers" -q`
Expected: PASS.

Note: `language_slots` is the *count* the player may pick; the template renders one checkbox per available option (not per slot). The test counts `name="language"` occurrences — keep the test in step with whatever the template emits. With INT 16 the test expects exactly 2; if you render one checkbox per option instead of per slot, change the test to assert the section is present and `language_slots == 2` via a hidden marker. **To keep the test as written, render exactly `language_slots` `<select>` pickers instead of an open checkbox list.** Choose ONE of these two consistent designs and make template + test agree:

- **(A) Checkbox list (recommended):** render one checkbox per option; the cap is enforced server-side in Task 7. Update the GET test to assert `'name="language"' in r.text` and that the count of checkboxes equals `len(language_options)`, plus a copy assertion `"up to 2" in r.text`.
- **(B) N selects:** render `language_slots` `<select name="language">` dropdowns, each listing `language_options` plus a blank option. Then `r.text.count('name="language"') == 2` holds for INT 16.

Pick (A) for a cleaner UX. Adjust the two GET-test assertions accordingly before running:

```python
    assert 'name="language"' in r.text
    assert "up to 2" in r.text
```

and for the low-INT test:

```python
    assert 'name="language"' not in r.text
```

- [ ] **Step 7: Commit**

```powershell
git add aose/web/wizard.py aose/web/templates/wizard/identity.html tests/test_wizard_languages.py
git commit -m "feat(languages): Identity page Languages section (native/alignment/pickers)"
```

---

## Task 7: Wizard Identity — parse, validate, store chosen languages (POST)

**Files:**
- Modify: `aose/web/wizard.py` (`post_identity`)
- Test: `tests/test_wizard_languages.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_wizard_languages.py`:

```python
def test_identity_stores_chosen_languages(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, HIGH_INT)  # INT 16 -> 2 allowed
    r = client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Sage", "alignment": "law", "language": ["Dragon", "Ogre"]},
    )
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["languages"] == ["Dragon", "Ogre"]


def test_identity_allows_fewer_than_max_languages(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, HIGH_INT)  # 2 allowed, choose 0
    r = client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Quiet", "alignment": "law"},
    )
    assert r.status_code == 303
    assert load_draft(draft_id, client._drafts_dir)["languages"] == []


def test_identity_rejects_too_many_languages(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, {"STR": 13, "INT": 13, "WIS": 12,
                                           "DEX": 13, "CON": 14, "CHA": 13})  # 1 allowed
    r = client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Greedy", "alignment": "law", "language": ["Dragon", "Ogre"]},
    )
    assert r.status_code == 400


def test_identity_rejects_unknown_language(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, HIGH_INT)
    r = client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Faker", "alignment": "law", "language": ["Klingon"]},
    )
    assert r.status_code == 400
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_languages.py -k "stores or fewer or too_many or unknown" -q`
Expected: FAIL — `post_identity` ignores `language` (no `draft["languages"]`); the >N/unknown cases return 303 instead of 400.

- [ ] **Step 3: Extend `post_identity`**

In `aose/web/wizard.py`, in `post_identity` (~line 815), after the `draft["alignment"] = alignment` assignment and before `save_draft`, insert:

```python
    from aose.engine.languages import LanguageError, validate_languages

    chosen_languages = list(dict.fromkeys(form.getlist("language")))
    race = data.races[draft["race_id"]]
    final_int = _creation_abilities(draft, data)["INT"]
    try:
        validate_languages(
            chosen_languages, race, alignment, final_int, data.languages,
        )
    except LanguageError as e:
        raise HTTPException(400, str(e))
    draft["languages"] = chosen_languages
```

(`alignment` is already validated against the class-legal set earlier in the handler, so it is a safe input to `validate_languages`.)

- [ ] **Step 4: Run the POST tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_languages.py -q`
Expected: PASS.

- [ ] **Step 5: Wire `languages` into the finalized spec**

In `aose/web/wizard.py`, in `_draft_to_spec` (~line 1583), add to the `CharacterSpec(...)` constructor (after `secondary_skill=...`):

```python
        secondary_skill=draft.get("secondary_skill"),
        languages=list(draft.get("languages", [])),
```

- [ ] **Step 6: Add a finalize round-trip test**

Add to `tests/test_wizard_languages.py`:

```python
def test_finalized_character_keeps_languages(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, HIGH_INT)
    client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Polyglot", "alignment": "law", "language": ["Dragon"]},
    )
    client.get(f"/wizard/{draft_id}/equipment")          # rolls gold
    client.post(f"/wizard/{draft_id}/equipment", data={})  # -> review
    r = client.post(f"/wizard/{draft_id}/finalize")
    assert r.status_code == 303
    # Sheet shows the chosen language alongside native + alignment tongue.
    char_url = r.headers["location"]
    page = client.get(char_url)
    assert "Dragon" in page.text
    assert "Lawful" in page.text
```

- [ ] **Step 7: Run the suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_languages.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add aose/web/wizard.py tests/test_wizard_languages.py
git commit -m "feat(languages): validate+store chosen languages on Identity POST; persist to spec"
```

---

## Task 8: Downstream clears — drop chosen languages when final INT could shift

**Files:**
- Modify: `aose/web/wizard.py` (`_clear_after_abilities`, `_clear_after_race`, `_clear_after_class`, `_apply_rule_changes`, `post_adjust`)
- Test: `tests/test_wizard_languages.py`

The final INT depends on: rolled abilities, race (racial mods), the P5 ability adjustments, and the `human_racial_abilities` rule. When any of those change, the stored `languages` may exceed the new INT's allowance or reference a now-native tongue — so clear them.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_wizard_languages.py`:

```python
def test_languages_cleared_when_race_changes(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, HIGH_INT)
    client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Shifter", "alignment": "law", "language": ["Dragon"]},
    )
    assert load_draft(draft_id, client._drafts_dir)["languages"] == ["Dragon"]
    # Go back and change race (elf meets INT 16).
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "elf"})
    assert "languages" not in load_draft(draft_id, client._drafts_dir)


def test_languages_cleared_when_adjustments_change(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, HIGH_INT)
    client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Tuner", "alignment": "law", "language": ["Dragon"]},
    )
    # Re-submitting the adjust step clears languages (final INT may move).
    client.post(f"/wizard/{draft_id}/adjust", data={})
    assert "languages" not in load_draft(draft_id, client._drafts_dir)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_languages.py -k cleared -q`
Expected: FAIL — `languages` persists across the race change / adjust resubmit.

- [ ] **Step 3: Add `"languages"` to the clear helpers**

In `aose/web/wizard.py`, add `"languages"` to the tuple in each of `_clear_after_abilities`, `_clear_after_race`, and `_clear_after_class` (~lines 171-191). For example `_clear_after_abilities`:

```python
def _clear_after_abilities(draft: dict[str, Any]) -> None:
    for k in ("race_id", "class_id", "class_ids", "ability_adjustments",
              "hp_roll", "hp_rolls", "proficiencies",
              "spellcasting", "spellbooks", "spells_done", "languages"):
        draft.pop(k, None)
```

Apply the same addition (`, "languages"`) to `_clear_after_race` and `_clear_after_class`.

- [ ] **Step 4: Clear on adjustment resubmit**

In `post_adjust` (~line 718), after `draft["ability_adjustments"] = adjustments` and before `save_draft`, add:

```python
    draft.pop("languages", None)  # final INT may have changed
```

- [ ] **Step 5: Clear on the `human_racial_abilities` rule toggle**

In `_apply_rule_changes` (~line 372), inside the existing `if new_rs.human_racial_abilities != old_rs.human_racial_abilities:` block, add a pop:

```python
    if new_rs.human_racial_abilities != old_rs.human_racial_abilities:
        draft.pop("hp_roll", None)
        draft.pop("hp_rolls", None)
        draft.pop("ability_adjustments", None)
        draft.pop("languages", None)
```

- [ ] **Step 6: Run the clear tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_languages.py -k cleared -q`
Expected: PASS.

- [ ] **Step 7: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (the trailing `pytest-current` PermissionError is the known Windows quirk — ignore it).

- [ ] **Step 8: Commit**

```powershell
git add aose/web/wizard.py tests/test_wizard_languages.py
git commit -m "feat(languages): clear chosen languages when final INT could change"
```

---

## Self-Review (completed during planning)

**Spec coverage:**
- §1 Data + model → Task 1 (`languages.yaml`, `LanguageData`, loader, `CharacterSpec.languages`). ✓
- §2 Engine (all 7 functions + `LanguageError`) → Tasks 2-4. ✓
- §3 Identity page Languages section (native / alignment / pickers / broken-speech / optional) → Tasks 6-7. ✓
- §4 Sheet integration (`known_languages`, broken-speech note) → Task 5. ✓
- §5 Downstream clears (abilities/race/class/adjustment/human-flag) → Task 8. ✓ (Alignment change does not clear, per spec — re-validation on POST covers it; Task 7's POST validation is the safety net.)
- §6 Tests → covered across Tasks 1-8 (loader, count/broken-speech, native/alignment/available, validate, final-INT-drives-N via elf+P5 scenario, render N pickers, store fewer, sheet composition + note, clears). ✓

**Note on the "elf raised to INT 13 by P5 → 1 slot" test (spec §6):** this is exercised by `_drive_to_identity` + `_languages_context` using `_creation_abilities(...)["INT"]` (post-racial + P5). To assert it explicitly, an integration test can drive an elf with rolled INT 12, apply a +1 P5 adjustment at `/adjust`, and assert `language_slots == 1` on the Identity page. Add this as an extra assertion in Task 6 if desired — the seam is already correct because `_languages_context` reads `_creation_abilities`, not raw `draft["abilities"]`.

**Placeholder scan:** no TBD/"handle edge cases"/uncoded steps — every code step shows full code. ✓

**Type/name consistency:** `LanguageData.alignment` / `.additional`; engine fns `additional_language_count`, `broken_speech`, `native_languages`, `alignment_language(alignment, lang_data)`, `available_additional(lang_data, already_known)`, `known_languages(chosen, race, alignment, lang_data)`, `validate_languages(chosen, race, alignment, final_int, lang_data)` — used identically in sheet/wizard/tests. `CharacterSheet.broken_speech` field name matches the template/sheet usage. ✓

**Open UX decision (Task 6):** checkbox list (design A) vs N selects (design B). Recommendation: **A**. Whichever you choose, keep template and the GET-test assertions in sync (the task spells out both variants).
