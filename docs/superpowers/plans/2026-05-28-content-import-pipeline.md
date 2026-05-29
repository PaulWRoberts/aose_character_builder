# Content Import Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable, prompt-driven pipeline that imports OSE PDF content (classes, races, race-as-class, spells, items, magic items) into the app's strict YAML, gated by a small validator and tracked by a manifest.

**Architecture:** Three model changes unblock the data layer (`Spell.source`, `Spell.classes`→`spell_lists`, `CharClass.spell_lists`). One new tool, `tools/validate_import.py`, loads candidate YAML against the real Pydantic models, runs the full loader, and enforces cross-file ID uniqueness. The rest is authored artifacts under `import/`: one Phase-1 extraction prompt, per-type Phase-2 prompts, per-type schema cribs, a seed manifest, and a README. Prompts **reference** cribs by path (no embedding) to stay DRY; the README documents the ChatGPT concatenation fallback.

**Tech Stack:** Python 3.14, Pydantic v2, PyYAML, pytest. Windows venv: `.venv\Scripts\python.exe`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `aose/models/spell.py` | Add `source`; rename `classes`→`spell_lists` |
| `aose/models/character_class.py` | Add `CharClass.spell_lists` |
| `tools/validate_import.py` | The validator (only new code beyond models) |
| `tests/test_validate_import.py` | Validator tests |
| `tests/test_data_loading.py` | Extend: spell loads with new fields |
| `import/prompts/phase1-extract.md` | Universal PDF→markdown prompt |
| `import/prompts/phase2-{class,race,spell,item,magic-item}.md` | Per-type structuring prompts |
| `import/cribs/{class,race,spell,item,magic-item}.md` | Canonical schema cribs + examples |
| `import/manifest.yaml` | Seed manifest (machine-managed status fields) |
| `import/README.md` | How to run the pipeline (CC + ChatGPT) |
| `.gitignore` | Add `import/pdfs/` |

> **DRY note (deviation from spec wording):** the spec said Phase-2 prompts "inline" their crib. To avoid maintaining two copies, prompts instead **reference** `import/cribs/<type>.md`. For Claude Code, point the agent at both files; for the ChatGPT fallback, the README says to paste the crib then the prompt. Same effect, single source of truth.

---

## Task 1: Spell model — add `source`, rename `classes`→`spell_lists`

**Files:**
- Modify: `aose/models/spell.py`
- Test: `tests/test_data_loading.py`

Nothing currently consumes `Spell` (no engine/web references; no spell data files), so the rename is safe.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_data_loading.py`:

```python
def test_spell_model_fields():
    from aose.models import Spell

    s = Spell(
        id="magic_missile",
        name="Magic Missile",
        level=1,
        spell_lists=["magic_user"],
        source="ose-advanced",
        range="150'",
        duration="instant",
        description="A glowing dart strikes unerringly for 1d6+1 damage.",
    )
    assert s.spell_lists == ["magic_user"]
    assert s.source == "ose-advanced"
    # `classes` must no longer exist (renamed).
    assert not hasattr(s, "classes")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py::test_spell_model_fields -v`
Expected: FAIL — `TypeError`/`ValidationError` on `spell_lists`/`source` (fields don't exist yet).

- [ ] **Step 3: Edit the model**

Replace the body of `aose/models/spell.py` with:

```python
from pydantic import BaseModel, ConfigDict, Field


class Spell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    level: int
    # Spell-list IDs this spell belongs to (e.g. ["magic_user"], ["cleric",
    # "druid"]). The list ID is decoupled from class ID, so race-as-class
    # entries can reuse a list (elf -> magic_user) without re-tagging spells.
    spell_lists: list[str] = Field(default_factory=list)
    # Book of origin, for a future selector to group/filter/toggle by source.
    source: str | None = None
    range: str
    duration: str
    description: str
    reversible: bool = False
    reverse_name: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py::test_spell_model_fields -v`
Expected: PASS

- [ ] **Step 5: Run the full suite (rename safety check)**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all pass (ignore the known `pytest-current` PermissionError on Windows).

- [ ] **Step 6: Commit**

```bash
git add aose/models/spell.py tests/test_data_loading.py
git commit -m "feat: add Spell.source and rename classes->spell_lists"
```

---

## Task 2: CharClass — add `spell_lists`

**Files:**
- Modify: `aose/models/character_class.py:39-55`
- Test: `tests/test_data_loading.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_data_loading.py`:

```python
def test_charclass_spell_lists_field():
    from aose.models import CharClass

    caster = CharClass(
        id="magic_user",
        name="Magic-User",
        prime_requisites=["INT"],
        hit_die="1d4",
        weapons_allowed=["dagger"],
        armor_allowed=[],
        shields_allowed=False,
        spell_lists=["magic_user"],
    )
    assert caster.spell_lists == ["magic_user"]

    # Non-casters default to an empty list.
    fighter = CharClass(
        id="fighter", name="Fighter", prime_requisites=["STR"],
        hit_die="1d8", weapons_allowed="all", armor_allowed="all",
        shields_allowed=True,
    )
    assert fighter.spell_lists == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py::test_charclass_spell_lists_field -v`
Expected: FAIL — `ValidationError` (extra field `spell_lists` forbidden).

- [ ] **Step 3: Add the field**

In `aose/models/character_class.py`, add to the `CharClass` body (after `progression` / before `race_locked`):

```python
    # Spell-list IDs this class casts from (e.g. ["magic_user"]). Empty = non-caster.
    # How-many-slots lives in progression[].spell_slots; this is which-pool.
    spell_lists: list[str] = Field(default_factory=list)
```

(`Field` is already imported in that file.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py::test_charclass_spell_lists_field -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add aose/models/character_class.py tests/test_data_loading.py
git commit -m "feat: add CharClass.spell_lists (which spell pool a class casts from)"
```

---

## Task 3: Validator — per-file model validation

**Files:**
- Create: `tools/validate_import.py`
- Test: `tests/test_validate_import.py`

The validator imports models from `aose.models` (never copies) so it can't drift.

- [ ] **Step 1: Write the failing test**

Create `tests/test_validate_import.py`:

```python
from pathlib import Path

import pytest

from tools.validate_import import validate_file


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_validate_file_good_class(tmp_path):
    f = _write(tmp_path / "fighter.yaml", """
id: fighter
name: Fighter
prime_requisites: [STR]
hit_die: 1d8
weapons_allowed: all
armor_allowed: all
shields_allowed: true
""")
    assert validate_file(f, "class") == []


def test_validate_file_bad_class_extra_field(tmp_path):
    f = _write(tmp_path / "bad.yaml", """
id: bad
name: Bad
prime_requisites: [STR]
hit_die: 1d8
weapons_allowed: all
armor_allowed: all
shields_allowed: true
nonsense_field: 1
""")
    errors = validate_file(f, "class")
    assert errors
    assert any("nonsense_field" in e for e in errors)


def test_validate_file_list_of_items(tmp_path):
    f = _write(tmp_path / "items.yaml", """
- id: club
  item_type: weapon
  name: Club
  category: weapons
  cost_gp: 3
  weight_cn: 50
  damage: {default: "1d6", variable: "1d4"}
- id: torch
  item_type: gear
  name: Torch
  category: adventuring_gear
  cost_gp: 1
  weight_cn: 20
""")
    assert validate_file(f, "item") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_validate_import.py -v`
Expected: FAIL — `ModuleNotFoundError: tools.validate_import`.

- [ ] **Step 3: Create the module with `validate_file`**

Create `tools/__init__.py` (empty) and `tools/validate_import.py`:

```python
"""Validate candidate import YAML against the real Pydantic models.

Run modes:
    python tools/validate_import.py                  # all incomplete manifest units
    python tools/validate_import.py --unit class/fighter
    python tools/validate_import.py --type spell
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from pydantic import TypeAdapter, ValidationError

from aose.models import CharClass, Item, Race, Spell

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MANIFEST_PATH = ROOT / "import" / "manifest.yaml"

# Per-type Pydantic target. race-as-class and magic-item reuse class/item.
_MODEL = {"race": Race, "class": CharClass, "spell": Spell}
_ITEM_ADAPTER = TypeAdapter(Item)
_TYPE_ALIASES = {"race-as-class": "class", "magic-item": "item"}


def _canonical_type(type_: str) -> str:
    return _TYPE_ALIASES.get(type_, type_)


def _read_objects(path: Path) -> list[dict]:
    """A YAML file may hold one mapping or a list of mappings."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return []
    return list(raw) if isinstance(raw, list) else [raw]


def validate_file(path: Path, type_: str) -> list[str]:
    """Return a list of human-readable validation errors ([] = valid)."""
    canon = _canonical_type(type_)
    errors: list[str] = []
    for i, obj in enumerate(_read_objects(path)):
        where = f"{path.name}[{i}]"
        try:
            if canon == "item":
                _ITEM_ADAPTER.validate_python(obj)
            else:
                _MODEL[canon].model_validate(obj)
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(p) for p in err["loc"])
                errors.append(f"{where}: {loc}: {err['msg']}")
    return errors


def main(argv: list[str] | None = None) -> int:  # filled in Task 6
    raise NotImplementedError


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_validate_import.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/__init__.py tools/validate_import.py tests/test_validate_import.py
git commit -m "feat: add validate_file for per-file model validation"
```

---

## Task 4: Validator — cross-file ID uniqueness + full loader check

**Files:**
- Modify: `tools/validate_import.py`
- Test: `tests/test_validate_import.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_validate_import.py`:

```python
from tools.validate_import import duplicate_ids_in_dir, load_game_data


def test_duplicate_ids_in_dir(tmp_path):
    (tmp_path / "a.yaml").write_text(
        "- {id: x, item_type: gear, name: X, category: g, cost_gp: 1}\n",
        encoding="utf-8",
    )
    (tmp_path / "b.yaml").write_text(
        "- {id: x, item_type: gear, name: X2, category: g, cost_gp: 1}\n",
        encoding="utf-8",
    )
    dupes = duplicate_ids_in_dir(tmp_path)
    assert "x" in dupes
    assert {p.name for p in dupes["x"]} == {"a.yaml", "b.yaml"}


def test_duplicate_ids_clean(tmp_path):
    (tmp_path / "a.yaml").write_text("- {id: x}\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("- {id: y}\n", encoding="utf-8")
    assert duplicate_ids_in_dir(tmp_path) == {}


def test_load_game_data_real_dir():
    # The shipped data/ must load cleanly.
    assert load_game_data() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_validate_import.py -k "duplicate or load_game" -v`
Expected: FAIL — `ImportError` (functions not defined).

- [ ] **Step 3: Add the functions**

Add to `tools/validate_import.py` (after `validate_file`):

```python
def duplicate_ids_in_dir(directory: Path) -> dict[str, list[Path]]:
    """Map any id that appears in more than one *.yaml to the files holding it.

    The loader keys everything by id; a collision silently overwrites, so this
    is the safeguard now that multiple books share data/equipment and data/spells.
    """
    seen: dict[str, list[Path]] = {}
    if not directory.exists():
        return {}
    for path in sorted(directory.glob("*.yaml")):
        for obj in _read_objects(path):
            obj_id = obj.get("id") if isinstance(obj, dict) else None
            if obj_id is None:
                continue
            seen.setdefault(obj_id, [])
            if path not in seen[obj_id]:
                seen[obj_id].append(path)
    return {k: v for k, v in seen.items() if len(v) > 1}


def load_game_data(data_dir: Path = DATA_DIR) -> list[str]:
    """Run the full GameData.load to catch cross-reference problems."""
    from aose.data.loader import GameData

    try:
        GameData.load(data_dir)
    except Exception as exc:  # ValidationError, KeyError, etc.
        return [f"GameData.load failed: {exc}"]
    return []


def all_duplicate_ids(data_dir: Path = DATA_DIR) -> list[str]:
    """Cross-file uniqueness across every loaded directory."""
    errors: list[str] = []
    for sub in ("races", "classes", "spells", "equipment"):
        for obj_id, paths in duplicate_ids_in_dir(data_dir / sub).items():
            names = ", ".join(p.name for p in paths)
            errors.append(f"duplicate id '{obj_id}' in {sub}/: {names}")
    return errors
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_validate_import.py -k "duplicate or load_game" -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/validate_import.py tests/test_validate_import.py
git commit -m "feat: add cross-file id uniqueness + full loader check"
```

---

## Task 5: Validator — manifest read/write + unit iteration

**Files:**
- Modify: `tools/validate_import.py`
- Test: `tests/test_validate_import.py`

Manifest status fields (`md`/`yaml`/`validated`) are machine-managed; the file is rewritten with `yaml.safe_dump` (so avoid comments in it).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_validate_import.py`:

```python
from tools.validate_import import iter_units, load_manifest, mark_validated


_MANIFEST_TEXT = """
- unit: class/fighter
  type: class
  yaml: data/classes/fighter.yaml
  validated: false
- unit: spell/ose-advanced-arcane
  type: spell
  yaml: data/spells/ose_advanced_spells.yaml
  validated: true
"""


def test_load_and_filter_units(tmp_path):
    mpath = tmp_path / "manifest.yaml"
    mpath.write_text(_MANIFEST_TEXT, encoding="utf-8")
    manifest = load_manifest(mpath)

    assert [u["unit"] for u in iter_units(manifest)] == [
        "class/fighter", "spell/ose-advanced-arcane",
    ]
    assert [u["unit"] for u in iter_units(manifest, only_incomplete=True)] == [
        "class/fighter",
    ]
    assert [u["unit"] for u in iter_units(manifest, type_="spell")] == [
        "spell/ose-advanced-arcane",
    ]
    assert [u["unit"] for u in iter_units(manifest, unit="class/fighter")] == [
        "class/fighter",
    ]


def test_mark_validated_round_trips(tmp_path):
    mpath = tmp_path / "manifest.yaml"
    mpath.write_text(_MANIFEST_TEXT, encoding="utf-8")
    mark_validated(mpath, "class/fighter")
    reloaded = load_manifest(mpath)
    fighter = next(u for u in reloaded if u["unit"] == "class/fighter")
    assert fighter["validated"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_validate_import.py -k "units or mark_validated" -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Add the functions**

Add to `tools/validate_import.py`:

```python
def load_manifest(path: Path = MANIFEST_PATH) -> list[dict]:
    if not path.exists():
        return []
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


def _save_manifest(manifest: list[dict], path: Path = MANIFEST_PATH) -> None:
    path.write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def iter_units(
    manifest: list[dict],
    *,
    unit: str | None = None,
    type_: str | None = None,
    only_incomplete: bool = False,
):
    for u in manifest:
        if unit is not None and u.get("unit") != unit:
            continue
        if type_ is not None and u.get("type") != type_:
            continue
        if only_incomplete and u.get("validated") is True:
            continue
        yield u


def mark_validated(path: Path, unit: str, value: bool = True) -> None:
    manifest = load_manifest(path)
    for u in manifest:
        if u.get("unit") == unit:
            u["validated"] = value
    _save_manifest(manifest, path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_validate_import.py -k "units or mark_validated" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/validate_import.py tests/test_validate_import.py
git commit -m "feat: add manifest load/save + unit iteration to validator"
```

---

## Task 6: Validator — CLI `main()` wiring

**Files:**
- Modify: `tools/validate_import.py`
- Test: `tests/test_validate_import.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_validate_import.py`:

```python
from tools.validate_import import main


def test_main_passes_on_clean_repo():
    # Bare run against the real (clean) repo manifest + data.
    assert main([]) == 0


def test_main_reports_bad_unit(tmp_path, monkeypatch, capsys):
    import tools.validate_import as vi

    bad = tmp_path / "bad.yaml"
    bad.write_text("id: x\nname: X\n", encoding="utf-8")  # missing required class fields
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        f"- unit: class/x\n  type: class\n  yaml: {bad.as_posix()}\n  validated: false\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(vi, "MANIFEST_PATH", manifest)
    # Skip the full-loader/uniqueness pass for this isolated unit test.
    monkeypatch.setattr(vi, "load_game_data", lambda *a, **k: [])
    monkeypatch.setattr(vi, "all_duplicate_ids", lambda *a, **k: [])

    rc = main(["--unit", "class/x"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in out
    assert "class/x" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_validate_import.py -k main -v`
Expected: FAIL — `main` raises `NotImplementedError`.

- [ ] **Step 3: Replace `main()`**

Replace the `main` stub in `tools/validate_import.py` with:

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate import YAML.")
    parser.add_argument("--unit", help="validate a single manifest unit by name")
    parser.add_argument("--type", dest="type_", help="validate all units of a type")
    args = parser.parse_args(argv)

    manifest = load_manifest()
    only_incomplete = args.unit is None and args.type_ is None
    units = list(iter_units(
        manifest, unit=args.unit, type_=args.type_, only_incomplete=only_incomplete,
    ))

    failed = False
    for u in units:
        name = u.get("unit", "<unnamed>")
        yaml_rel = u.get("yaml")
        if not yaml_rel:
            print(f"SKIP {name}: no yaml path yet")
            continue
        path = ROOT / yaml_rel if not Path(yaml_rel).is_absolute() else Path(yaml_rel)
        if not path.exists():
            print(f"FAIL {name}: missing file {yaml_rel}")
            failed = True
            continue
        errors = validate_file(path, u.get("type", ""))
        if errors:
            failed = True
            print(f"FAIL {name}:")
            for e in errors:
                print(f"    {e}")
        else:
            mark_validated(MANIFEST_PATH, name)
            print(f"OK   {name}")

    # Repo-wide checks always run.
    for e in load_game_data() + all_duplicate_ids():
        failed = True
        print(f"FAIL repo: {e}")

    print("FAILED" if failed else "ALL OK")
    return 1 if failed else 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_validate_import.py -k main -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full validator test file + whole suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_validate_import.py tests/ -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add tools/validate_import.py tests/test_validate_import.py
git commit -m "feat: wire validate_import CLI (--unit/--type/bare, exit codes)"
```

---

## Task 7: Scaffold the `import/` tree + .gitignore + README + seed manifest

**Files:**
- Create: `import/README.md`, `import/manifest.yaml`
- Create dirs (via `.gitkeep`): `import/pdfs/`, `import/markdown/{classes,races,spells,items,magic-items}/`, `import/prompts/`, `import/cribs/`
- Modify: `.gitignore`

- [ ] **Step 1: Create directories and keepfiles**

```bash
mkdir -p import/pdfs import/prompts import/cribs \
  import/markdown/classes import/markdown/races import/markdown/spells \
  import/markdown/items import/markdown/magic-items
# keep empty dirs in git
for d in import/pdfs import/markdown/classes import/markdown/races \
  import/markdown/spells import/markdown/items import/markdown/magic-items; do
  touch "$d/.gitkeep"
done
```

- [ ] **Step 2: Ignore source PDFs**

Append to `.gitignore`:

```
# Copyrighted source PDFs for the content-import pipeline
import/pdfs/
```

- [ ] **Step 3: Seed `import/manifest.yaml`**

Write `import/manifest.yaml` (one worked example row + comment; user fills the rest from the PDF TOC):

```yaml
# Machine-managed status fields: md / yaml / validated are written by the
# pipeline and tools/validate_import.py. Avoid YAML comments inside list rows
# (the validator rewrites this file with yaml.safe_dump).
- unit: class/fighter
  type: class            # class | race | race-as-class | spell | item | magic-item
  source: ose-advanced
  pdf: ose-advanced.pdf
  pages: "24-25"
  md: null               # -> import/markdown/classes/fighter.md when Phase 1 done
  yaml: null             # -> data/classes/fighter.yaml when Phase 2 done
  validated: false
  notes: ""
```

- [ ] **Step 4: Write `import/README.md`**

```markdown
# Content import pipeline

Two phases per manifest unit:

1. **Phase 1 — PDF -> markdown.** Use `prompts/phase1-extract.md` with the unit's
   PDF pages. Output goes to `markdown/<type>/<id>.md` and is committed.
2. **Phase 2 — markdown -> YAML.** Use `prompts/phase2-<type>.md` + `cribs/<type>.md`
   with that markdown. Output goes straight into `../data/...`.

Then validate and commit:

```
.venv\Scripts\python.exe tools\validate_import.py --unit <unit>
```

## Running on Claude Code (cheap model)
Point the agent at the prompt **and** the matching crib, plus the source pages
(Phase 1) or the markdown file (Phase 2).

## Running on ChatGPT (token-saving fallback)
Paste `cribs/<type>.md` first, then `prompts/phase2-<type>.md`, then the markdown.
Save the reply into the target `data/` file.

## Resuming
`tools/validate_import.py` with no args validates every incomplete unit. The
manifest's `validated` flags tell you where you left off.
```

- [ ] **Step 5: Verify the validator still runs against the seeded (incomplete) manifest**

Run: `.venv\Scripts\python.exe tools\validate_import.py`
Expected: prints `SKIP class/fighter: no yaml path yet`, then `ALL OK`, exit 0 (the unit has no `yaml` yet; repo checks pass).

- [ ] **Step 6: Commit**

```bash
git add .gitignore import/README.md import/manifest.yaml import/**/.gitkeep
git commit -m "chore: scaffold import/ pipeline tree, manifest seed, README"
```

---

## Task 8: Phase-1 extraction prompt

**Files:**
- Create: `import/prompts/phase1-extract.md`

- [ ] **Step 1: Write the prompt**

```markdown
# Phase 1 — Extract PDF pages to faithful markdown

You convert a page range of an OSE rulebook PDF into clean markdown. Your ONLY
job is faithful structural extraction. Do NOT interpret, summarise, or convert
to YAML.

## Rules
- Reproduce ALL text in reading order. De-column multi-column layouts into a
  single top-to-bottom flow.
- Reconstruct every table as a GitHub-flavoured markdown table. Preserve every
  number, symbol, and header label exactly (e.g. `19`, `1d8`, `+1`, `F1`).
- Keep headings as markdown headings (`#`, `##`, `###`) matching the book's
  hierarchy.
- DROP: running page headers/footers, page numbers, art and art captions,
  decorative rules.
- If a cell or word is unreadable, write `[?]` in its place. Never guess a value.
- Do not add commentary, notes, or YAML. Output markdown only.

## Input
- The PDF and a page range (from the manifest unit's `pages`).

## Output
- Markdown saved to `import/markdown/<type>/<id>.md`.
```

- [ ] **Step 2: Commit**

```bash
git add import/prompts/phase1-extract.md
git commit -m "docs: add Phase 1 PDF->markdown extraction prompt"
```

---

## Task 9: Class crib + Phase-2 class prompt (covers race-as-class)

**Files:**
- Create: `import/cribs/class.md`, `import/prompts/phase2-class.md`

- [ ] **Step 1: Write `import/cribs/class.md`**

````markdown
# Crib: class (and race-as-class)

Target model: `CharClass` (`aose/models/character_class.py`). `extra="forbid"`
— no fields beyond those listed. Progression/spell-slot level keys are integers.

## Fields
| Field | Type | Req | Notes |
|---|---|---|---|
| id | str | yes | snake_case, unique within data/classes/ |
| name | str | yes | display name |
| prime_requisites | list[Ability] | yes | subset of STR INT WIS DEX CON CHA |
| ability_requirements | map Ability->int | no | minimum scores to take the class |
| max_level | int | no | default 14 |
| hit_die | str | yes | e.g. "1d8", "1d4" |
| weapons_allowed | list[str] \| "all" | yes | |
| armor_allowed | list[str] \| "all" | yes | `[]` = none |
| shields_allowed | bool | yes | |
| proficiency | {starting_slots:int, new_slot_every_levels:int} | no | omit if not using weapon proficiencies |
| progression | map int->ClassLevelData | no | one entry per character level |
| features | list[ClassFeature] | no | |
| race_locked | str \| null | no | race id, for race-as-class entries |
| spell_lists | list[str] | no | which pool(s) this class casts from; `[]` = non-caster |

`ClassLevelData`: `{xp_required:int, thac0:int, hit_dice:str,
saves:{death,wands,paralysis,breath,spells (ints)}, spell_slots: map int->int | null}`
`ClassFeature`: `{id:str, name:str, text:str, gained_at_level:int=1, mechanical: map | null}`

## Example (non-caster)
```yaml
id: fighter
name: Fighter
prime_requisites: [STR]
max_level: 14
hit_die: 1d8
weapons_allowed: all
armor_allowed: all
shields_allowed: true
proficiency: { starting_slots: 4, new_slot_every_levels: 3 }
progression:
  1:
    xp_required: 0
    thac0: 19
    hit_dice: 1d8
    saves: { death: 12, wands: 13, paralysis: 14, breath: 15, spells: 16 }
features:
  - id: combat_focus
    name: Combat Focus
    text: "Fighters have unrestricted use of weapons, armor, and shields."
    gained_at_level: 1
```

## Caster progression rows
Read the SEPARATE spell-progression grid (character level x spell level) into
each row's `spell_slots`, and set the class's `spell_lists`:
```yaml
spell_lists: [magic_user]
progression:
  1:
    xp_required: 0
    thac0: 19
    hit_dice: 1d4
    saves: { death: 13, wands: 14, paralysis: 13, breath: 16, spells: 15 }
    spell_slots: { 1: 1 }          # one 1st-level spell at level 1
  3:
    xp_required: 5000
    thac0: 19
    hit_dice: 3d4
    saves: { death: 13, wands: 14, paralysis: 13, breath: 16, spells: 15 }
    spell_slots: { 1: 2, 2: 1 }
```
- Casting that begins later (e.g. cleric at level 2) means the level-1 row has
  NO `spell_slots`; the level-2 row is the first with one.
- Non-casters: omit `spell_lists` and every `spell_slots`.

## Race-as-class rules
- Set `race_locked` to the race id (e.g. `dwarf`).
- Mirror the race's ability requirements into `ability_requirements`.
- If the race casts via a borrowed list, set `spell_lists` to that list
  (elf -> `[magic_user]`, gnome -> `[illusionist]`), NOT to its own id.

## General rules
- Omit optional fields you can't source rather than guessing.
- If a value is unclear, emit it with a trailing `# TODO: confirm` comment.
````

- [ ] **Step 2: Write `import/prompts/phase2-class.md`**

```markdown
# Phase 2 — Structure a class into YAML

Convert the provided class markdown into YAML matching the `CharClass` model.

- Read the schema crib at `import/cribs/class.md` (ChatGPT: it is pasted above).
- Output ONLY YAML — a single mapping (one class per file).
- Transcribe the XP/THAC0/saves progression table into `progression`, and the
  separate spell-progression grid into each row's `spell_slots`.
- For race-as-class entries set `race_locked`, mirror ability requirements, and
  set `spell_lists` to the borrowed list.
- Omit optional fields not present in the source; mark uncertain values with
  `# TODO: confirm`. Never invent numbers.

Write the result to `data/classes/<id>.yaml`.
```

- [ ] **Step 3: Commit**

```bash
git add import/cribs/class.md import/prompts/phase2-class.md
git commit -m "docs: add class crib + Phase 2 class prompt"
```

---

## Task 10: Race crib + Phase-2 race prompt

**Files:**
- Create: `import/cribs/race.md`, `import/prompts/phase2-race.md`

- [ ] **Step 1: Write `import/cribs/race.md`**

````markdown
# Crib: race

Target model: `Race` (`aose/models/race.py`). `extra="forbid"`.

## Fields
| Field | Type | Req | Notes |
|---|---|---|---|
| id | str | yes | snake_case |
| name | str | yes | |
| ability_requirements | map Ability->int | no | minimum scores |
| ability_maxima | map Ability->int | no | caps |
| ability_minima | map Ability->int | no | floors |
| infravision | int | no | feet; default 0 |
| base_movement | int | no | default 120 |
| languages | list[str] | no | |
| allowed_classes | list[str] | no | `[]` = ANY class (the human case) |
| class_level_caps | map str->int | no | per-class level cap; missing = no cap |
| allowed_multiclass_combos | list[list[str]] | no | only under the Multiclassing rule |
| features | list[RaceFeature] | no | |

`RaceFeature`: `{id:str, name:str, text:str, mechanical: map | null}`

## Example
```yaml
id: elf
name: Elf
ability_requirements:
  INT: 9
infravision: 60
base_movement: 120
languages: [common, elvish, gnoll, hobgoblin, orcish]
allowed_classes: [fighter, magic_user]
class_level_caps: { fighter: 10, magic_user: 10 }
allowed_multiclass_combos:
  - [fighter, magic_user]
features:
  - id: detect_secret_doors
    name: Detect Secret Doors
    text: "When actively searching, elves find secret doors on 1-2 on 1d6."
```

## Rules
- `allowed_classes: []` means "any class" — use it only for human-like races.
- Omit optional fields you can't source. Mark unclear values `# TODO: confirm`.
````

- [ ] **Step 2: Write `import/prompts/phase2-race.md`**

```markdown
# Phase 2 — Structure a race into YAML

Convert the provided race markdown into YAML matching the `Race` model.

- Read the schema crib at `import/cribs/race.md` (ChatGPT: pasted above).
- Output ONLY YAML — a single mapping (one race per file).
- Remember `allowed_classes: []` means "any class"; only use it for human-like
  races. List restrictions explicitly otherwise.
- Omit optional fields not present; mark uncertain values `# TODO: confirm`.

Write the result to `data/races/<id>.yaml`.
```

- [ ] **Step 3: Commit**

```bash
git add import/cribs/race.md import/prompts/phase2-race.md
git commit -m "docs: add race crib + Phase 2 race prompt"
```

---

## Task 11: Spell crib + Phase-2 spell prompt

**Files:**
- Create: `import/cribs/spell.md`, `import/prompts/phase2-spell.md`

- [ ] **Step 1: Write `import/cribs/spell.md`**

````markdown
# Crib: spell

Target model: `Spell` (`aose/models/spell.py`). `extra="forbid"`.
One book's spells go in ONE list file: `data/spells/<book>_spells.yaml`.

## Fields
| Field | Type | Req | Notes |
|---|---|---|---|
| id | str | yes | snake_case, unique across ALL spell files |
| name | str | yes | |
| level | int | yes | spell level |
| spell_lists | list[str] | no | pool IDs: magic_user, cleric, druid, illusionist, kineticist… |
| source | str | no | book of origin, e.g. ose-advanced, carcass-crawler-1 |
| range | str | yes | e.g. "150'", "Touch", "0 (caster)" |
| duration | str | yes | e.g. "instant", "6 turns", "1 turn/level" |
| description | str | yes | full rules text |
| reversible | bool | no | default false |
| reverse_name | str \| null | no | name of the reversed form if any |

## Example
```yaml
- id: magic_missile
  name: Magic Missile
  level: 1
  spell_lists: [magic_user]
  source: ose-advanced
  range: "150'"
  duration: instant
  description: >-
    A glowing dart speeds toward a target and strikes unerringly for 1d6+1
    damage. +1 missile at levels 6, 11, and 16.
- id: cure_light_wounds
  name: Cure Light Wounds
  level: 1
  spell_lists: [cleric]
  source: ose-advanced
  range: Touch
  duration: instant
  description: "Heals 1d6+1 hit points, or cures paralysis."
  reversible: true
  reverse_name: Cause Light Wounds
```

## Rules
- A spell on two lists gets both: `spell_lists: [cleric, druid]`.
- For a race-as-class that reuses a list, do NOT tag the spell with the race;
  tag it with the list (the class references the list via its own `spell_lists`).
- Set `source` to the book id; keep it consistent with the manifest unit.
- Keep ids unique across every spell file (the validator enforces this).
````

- [ ] **Step 2: Write `import/prompts/phase2-spell.md`**

```markdown
# Phase 2 — Structure spells into YAML

Convert the provided spell-list markdown into YAML matching the `Spell` model.

- Read the schema crib at `import/cribs/spell.md` (ChatGPT: pasted above).
- Output ONLY YAML — a LIST of spell mappings (append to the book's single file).
- Set `level`, `spell_lists` (pool IDs, not class names), and `source`.
- Detect reversible spells: set `reversible: true` and `reverse_name`.
- Keep ids snake_case and unique. Mark uncertain values `# TODO: confirm`.

Append the result into `data/spells/<book>_spells.yaml`.
```

- [ ] **Step 3: Commit**

```bash
git add import/cribs/spell.md import/prompts/phase2-spell.md
git commit -m "docs: add spell crib + Phase 2 spell prompt"
```

---

## Task 12: Item crib + Phase-2 item prompt

**Files:**
- Create: `import/cribs/item.md`, `import/prompts/phase2-item.md`

- [ ] **Step 1: Write `import/cribs/item.md`**

````markdown
# Crib: item (mundane)

Target: the `Item` discriminated union (`aose/models/item.py`), keyed by
`item_type`. `extra="forbid"`. One book's mundane items go in ONE list file:
`data/equipment/<book>_items.yaml` (mixed item_types allowed).

## Common (ItemBase) fields
`id` (str), `name` (str), `category` (str), `cost_gp` (float), `weight_cn`
(int, default 0), `description` (str | null), `magic` (bool, default false).

## Variants
- **weapon** (`item_type: weapon`): `damage: {default, variable, variable_two_handed?}`,
  `hands` (int=1), `versatile` (bool), `melee` (bool=true), `ranged` (bool=false),
  `range_short/medium/long` (int | null), `qualities` (list[str]),
  `proficiency_group` (str | null), `magic_bonus` (int=0),
  `conditional_bonus: {vs:str, bonus:int} | null`.
- **armor** (`item_type: armor`): `ac_descending` (int), `movement_impact`
  (none|leather|metal), `is_shield` (bool), `magic_bonus` (int=0),
  `weight_multiplier` (float=1.0).
- **gear** (`item_type: gear`): common fields only.
- **poison** (`item_type: poison`): `save_modifier` (int=0), `onset` (str|null),
  `effect` (str|null).
- **container** (`item_type: container`): `capacity_cn` (int|null),
  `weight_multiplier` (float=1.0).

## Example
```yaml
- id: club
  item_type: weapon
  name: Club
  category: weapons
  cost_gp: 3
  weight_cn: 50
  damage: { default: "1d6", variable: "1d4" }
  hands: 1
  proficiency_group: bludgeon
- id: leather_armor
  item_type: armor
  name: Leather Armor
  category: armor
  cost_gp: 20
  weight_cn: 200
  ac_descending: 7
  movement_impact: leather
- id: torch
  item_type: gear
  name: Torch
  category: adventuring_gear
  cost_gp: 1
  weight_cn: 20
```

## Rules
- Pick the right `item_type` per entry; one file may mix types.
- `damage.default` is the standard 1d6; `damage.variable` is the Variable Weapon
  Damage value. Set both.
- Leave `magic_bonus` at 0 / omit for mundane items (magic items: see magic-item crib).
- ids unique across ALL of data/equipment/ (validator enforces).
````

- [ ] **Step 2: Write `import/prompts/phase2-item.md`**

```markdown
# Phase 2 — Structure mundane items into YAML

Convert the provided equipment markdown into YAML matching the `Item` union.

- Read the schema crib at `import/cribs/item.md` (ChatGPT: pasted above).
- Output ONLY YAML — a LIST of item mappings; choose `item_type` per entry.
- Transcribe cost (gp) and weight (cn) exactly; set both weapon damage values.
- Keep ids snake_case and unique across data/equipment/. Mark unclear values
  `# TODO: confirm`.

Append the result into `data/equipment/<book>_items.yaml`.
```

- [ ] **Step 3: Commit**

```bash
git add import/cribs/item.md import/prompts/phase2-item.md
git commit -m "docs: add item crib + Phase 2 item prompt"
```

---

## Task 13: Magic-item crib + Phase-2 magic-item prompt

**Files:**
- Create: `import/cribs/magic-item.md`, `import/prompts/phase2-magic-item.md`

- [ ] **Step 1: Write `import/cribs/magic-item.md`**

````markdown
# Crib: magic item

Two encodings, by kind. `extra="forbid"`. One book's magic items go in ONE list
file: `data/equipment/<book>_magic_items.yaml`. All entries set `magic: true`.

## A. Magic weapons / armour — use the NATIVE weapon/armor type
Keep `item_type: weapon` or `item_type: armor` and add a `magic_bonus`.
- Weapon: optional `conditional_bonus: {vs, bonus}` for "+X vs Y".
- Armour: `weight_multiplier: 0.5` for half-weight enchanted armour.

```yaml
- id: sword_plus_1
  name: Sword +1
  category: magic_swords
  item_type: weapon
  magic: true
  cost_gp: 0
  weight_cn: 60
  damage: { default: "1d6", variable: "1d8" }
  melee: true
  proficiency_group: sword
  magic_bonus: 1
- id: chain_mail_plus_1
  name: Chain Mail +1
  category: magic_armour
  item_type: armor
  magic: true
  cost_gp: 0
  weight_cn: 400
  ac_descending: 5
  movement_impact: metal
  magic_bonus: 1
  weight_multiplier: 0.5
```

## B. Everything else — use `item_type: magic` with modifiers
Fields: `equippable` (bool), `modifiers` (list[Modifier]),
`max_charges` (int | null) OR `charge_dice` (str | null, rolled at acquisition),
`description`.

`Modifier`: `{target: str, op: add|set|set_min|set_max, value: int}`.
Valid targets: `ability:STR…CHA`, `ac`, `save:all`,
`save:death|wands|paralysis|breath|spells`, `attack`, `damage`,
`carry_capacity`, `thac0`. `op` order applied per target: set → add → set_min
→ set_max. `add` always means "better for the character".

```yaml
- id: gauntlets_of_ogre_power
  name: Gauntlets of Ogre Power
  category: miscellaneous_magic_items
  item_type: magic
  magic: true
  cost_gp: 0
  weight_cn: 0
  equippable: true
  description: "Wearer has Strength 18; carrying capacity +1000 cn."
  modifiers:
    - { target: "ability:STR", op: set, value: 18 }
    - { target: carry_capacity, op: add, value: 1000 }
- id: ring_of_protection
  name: Ring of Protection
  category: magic_rings
  item_type: magic
  magic: true
  cost_gp: 0
  weight_cn: 0
  equippable: true
  description: "+1 to Armour Class and all saving throws."
  modifiers:
    - { target: ac, op: add, value: 1 }
    - { target: "save:all", op: add, value: 1 }
- id: potion_of_healing
  name: Potion of Healing
  category: magic_potions
  item_type: gear        # pure-text consumable, no instance/modifiers
  magic: true
  cost_gp: 0
  weight_cn: 10
  description: "Quaffing restores lost hit points (per the referee's table)."
```

## Rules
- Decision: is it a weapon/armour bonus? -> use A (native type + magic_bonus).
  A worn/wielded item with numeric effects? -> B (`item_type: magic` +
  modifiers). A pure-text consumable with no auto-applied numbers? -> `item_type: gear`.
- Only encode effects expressible as a `Modifier`. Anything else goes in
  `description` with a `# TODO:` if it needs manual play.
- `cost_gp: 0` (magic items are Add-only / GM-granted, not bought).
- ids unique across ALL of data/equipment/.
````

- [ ] **Step 2: Write `import/prompts/phase2-magic-item.md`**

```markdown
# Phase 2 — Structure magic items into YAML

Convert the provided magic-item markdown into YAML matching the `Item` union.

- Read the schema crib at `import/cribs/magic-item.md` (ChatGPT: pasted above).
- Output ONLY YAML — a LIST of mappings. Every entry sets `magic: true` and
  `cost_gp: 0`.
- Magic weapons/armour: keep native `item_type: weapon`/`armor` + `magic_bonus`.
- Other magic items: `item_type: magic` with `modifiers` (and `max_charges` or
  `charge_dice` if charged). Pure-text consumables: `item_type: gear`.
- Only encode effects expressible as a Modifier (targets/ops in the crib);
  put the rest in `description` with `# TODO:` where manual play is needed.

Append the result into `data/equipment/<book>_magic_items.yaml`.
```

- [ ] **Step 3: Commit**

```bash
git add import/cribs/magic-item.md import/prompts/phase2-magic-item.md
git commit -m "docs: add magic-item crib + Phase 2 magic-item prompt"
```

---

## Task 14: End-to-end dogfood on one real unit

Validates that the artifacts + validator actually work together. This task is
manual (it needs the PDF and a model); no automated test.

**Files:**
- Create (output of the run): `import/markdown/...` + a file under `data/...`
- Modify: `import/manifest.yaml`

- [ ] **Step 1: Pick a unit not already in `data/`**

Choose something the repo lacks (e.g. the Cleric class, or a short spell list).
Add/confirm its manifest row with real `pdf`, `pages`, `source`.

- [ ] **Step 2: Run Phase 1**

Apply `import/prompts/phase1-extract.md` to the unit's PDF pages. Save markdown
to `import/markdown/<type>/<id>.md`. Set the row's `md` field to that path.

- [ ] **Step 3: Run Phase 2**

Apply `import/prompts/phase2-<type>.md` + `import/cribs/<type>.md` to that
markdown. Write/append the YAML into the correct `data/...` file. Set the row's
`yaml` field.

- [ ] **Step 4: Validate**

Run: `.venv\Scripts\python.exe tools\validate_import.py --unit <unit>`
Expected: `OK <unit>` and `ALL OK`, exit 0. Fix any reported field errors in the
YAML and re-run until clean (Phase 2 can be re-run from the committed markdown
for free).

- [ ] **Step 5: Confirm the app still loads and tests pass**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all pass (the new data loads via `GameData.load`).

- [ ] **Step 6: Commit**

```bash
git add import/markdown import/manifest.yaml data
git commit -m "content: import <unit> via the pipeline (dogfood)"
```

---

## Self-Review

**Spec coverage:**
- `Spell.source` → Task 1. `Spell.classes`→`spell_lists` → Task 1. `CharClass.spell_lists` → Task 2.
- Validator: per-file validation (Task 3), full loader + cross-file ID uniqueness (Task 4), manifest + run modes + CLI (Tasks 5-6).
- Directory layout, gitignore, manifest seed, README → Task 7.
- Phase-1 prompt → Task 8. Per-type cribs + Phase-2 prompts → Tasks 9-13 (class/race-as-class, race, spell, item, magic-item).
- Spell-progression encoding via `progression[].spell_slots` → class crib (Task 9).
- Unit granularity (one file per book for spell/item/magic-item; one per entry for class/race) → cribs + prompts.
- End-to-end repeatable loop → README (Task 7) + dogfood (Task 14).

**Deviation (logged):** Phase-2 prompts reference cribs by path instead of inlining them (DRY); README documents the ChatGPT concatenation step.

**Placeholder scan:** `# TODO: confirm` markers in cribs/prompts are intentional pipeline behavior (instructions to the structuring model), not plan placeholders. No unresolved plan TODOs.

**Type consistency:** validator function names used consistently across tasks —
`validate_file`, `duplicate_ids_in_dir`, `all_duplicate_ids`, `load_game_data`,
`load_manifest`, `iter_units`, `mark_validated`, `main`. Model field names match
Tasks 1-2 (`spell_lists`, `source`).
