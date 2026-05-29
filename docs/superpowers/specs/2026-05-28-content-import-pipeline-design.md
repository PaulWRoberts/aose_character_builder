# Content Import Pipeline — Design

**Date:** 2026-05-28
**Status:** Approved (design)

## Purpose

A repeatable, low-cost pipeline to import AOSE/OSE content — classes, races,
race-as-class entries, spells, mundane items, and magic items — from text-based
OSE PDFs into the strict Pydantic-backed YAML the app already loads.

Two phases per unit of content:

1. **Phase 1 — PDF → markdown.** An LLM extracts a page range to clean,
   faithful markdown (no interpretation).
2. **Phase 2 — markdown → YAML.** An LLM structures that markdown into YAML
   matching the target Pydantic model.

The pipeline is **prompt-driven, not script-driven**: the deliverables are
reusable prompt + schema-crib files plus one small validator. It runs primarily
inside Claude Code on a cheaper model (Haiku/Sonnet), and the same prompt files
can be pasted into ChatGPT manually to conserve CC tokens. Work is resumable
across sessions via committed markdown + a manifest.

## Key constraints & facts

- **Targets are strict.** All models use `extra="forbid"`. YAML that doesn't
  match the model fails loudly at load. The models in `aose/models/` are the
  single source of truth: `Race`, `CharClass` (also covers race-as-class via
  `race_locked`), `Spell`, and the `Item` discriminated union
  (`Weapon`/`Armor`/`AdventuringGear`/`Poison`/`Container`/`MagicItem`).
- **The loader already merges files.** `GameData.load(data_dir)`:
  - `data/races/`, `data/classes/`, `data/spells/` — `_load_models` reads every
    `*.yaml`, each file a single mapping **or** a list, merged into a flat dict
    keyed by `id`.
  - `data/equipment/` — `_load_items` does the same via a `TypeAdapter(Item)`.
  - Globs are **flat, non-recursive** — all files of a type sit directly in
    their type directory; no subfolders.
  - Because the dict is keyed by `id`, a later-loaded file with a duplicate `id`
    **silently overwrites** the earlier one. ID uniqueness across all files of a
    type is therefore mandatory and must be enforced by the validator.
- **Spells are modelled but unused.** `Spell` and the `data/spells/` loader path
  exist, but nothing consumes spells yet (no engine logic, wizard step, or
  selector UI). Building the selector is out of scope here; the data design must
  not block it.

## Schema change (in scope)

Add `source: str | None = None` to the `Spell` model
(`aose/models/spell.py`). Lets a future spell selector group/filter/toggle by
book of origin. The pipeline populates it per unit. No other model changes.

## Directory layout

```
import/
  pdfs/                     # source OSE PDFs (gitignored — copyrighted)
  prompts/
    phase1-extract.md       # universal: PDF page-range → clean markdown
    phase2-class.md         # one structuring prompt per type…
    phase2-race.md
    phase2-spell.md
    phase2-item.md
    phase2-magic-item.md
  cribs/                    # compact schema + a real example per type
    class.md  race.md  spell.md  item.md  magic-item.md
  markdown/                 # Phase-1 output, COMMITTED (so Phase 2 re-runs free)
    classes/  races/  spells/  items/  magic-items/
  manifest.yaml             # status of every unit (resumability backbone)

tools/
  validate_import.py        # loads candidate YAML against the real Pydantic models

data/                       # Phase-2 output (existing tree)
  classes/  races/  spells/  equipment/
```

- `import/pdfs/` is gitignored (copyrighted). The committed markdown is the
  reusable structural asset.
- Phase-2 YAML is written **straight into `data/`** — no staging copy — because
  the validator checks before commit and git is the undo.
- Cribs are derived from the actual models; the validator is the backstop that
  catches crib drift.

## Unit granularity

A **unit** is the bite-sized chunk a cheap model handles, and the row tracked in
the manifest. Output-file granularity is separate from the processing chunk:
large sections are extracted/structured in page-range chunks that **append into
a single output file** (within-file append, never cross-file merge).

| Type | One YAML file = | Output path | Processing |
|---|---|---|---|
| class | one class | `data/classes/<id>.yaml` | single pass |
| race | one race | `data/races/<id>.yaml` | single pass |
| race-as-class | one `CharClass` w/ `race_locked` | `data/classes/<id>.yaml` | single pass |
| spell | one book's spells (list) | `data/spells/<book>_spells.yaml` | chunk by pages, append |
| item | one book's mundane items (list, mixed `item_type`) | `data/equipment/<book>_items.yaml` | chunk by pages, append |
| magic item | one book's magic items (list) | `data/equipment/<book>_magic_items.yaml` | chunk by pages, append |

- **Race-as-class** needs no special machinery: it's a `class`-type unit whose
  crib instructs setting `race_locked` and mirroring the racial ability
  requirements.
- **Spells** are one file per book (a list); each entry carries its own `level`,
  `classes[]`, and `source`, so the future selector filters the merged pool —
  no need to split by caster/level. Splitting buys nothing.
- **Items / magic items** are one file per book. New book files coexist with the
  existing seed files (`weapons.yaml`, `armor.yaml`, `magic_items.yaml`, …) —
  the loader merges all by `id`, so cross-file ID uniqueness matters.

## Manifest

`import/manifest.yaml` is the single source of truth for "what's done." Hand-
seeded once from the PDF table of contents; thereafter the pipeline only mutates
`md` / `yaml` / `validated`. Resuming = scan for incomplete units.

```yaml
- unit: class/fighter
  type: class
  source: ose-advanced            # book of origin (also feeds Spell.source)
  pdf: ose-advanced.pdf
  pages: "24-25"
  md: import/markdown/classes/fighter.md    # set when Phase 1 done
  yaml: data/classes/fighter.yaml           # set when Phase 2 done
  validated: true                           # set by validate_import.py
  notes: ""                                 # e.g. "spell table hand-checked"
```

For append-style types (spell/item/magic item), a long section may be split into
several manifest rows sharing one `yaml` target but distinct `pages`/`md`.

## Phase 1 — PDF → markdown

Single universal prompt `import/prompts/phase1-extract.md`. Input: a PDF +
page range from the manifest. Output: clean markdown to
`import/markdown/<type>/<id>.md`.

Job: **faithful structural extraction, no interpretation.** De-column text,
reconstruct tables as markdown tables, preserve every number and heading
verbatim, drop running headers/footers/page numbers and art captions. Must NOT
convert to YAML or invent values. Unreadable cells are written `[?]` so gaps are
visible. Keeping Phase 1 dumb and reviewable lets Phase 2 work from clean text
without re-reading the PDF.

## Phase 2 — markdown → YAML

One structuring prompt per type (`phase2-<type>.md`), each **inlining its crib**
so the file is self-contained and pasteable into ChatGPT. A crib
(`import/cribs/<type>.md`) is three things:

1. **Field table** — every field, type, required/optional, allowed enum values
   (e.g. `weapons_allowed: list | "all"`), transcribed from the Pydantic model.
2. **One real example** — an existing `data/` entry (e.g. `fighter.yaml`) as a
   concrete target.
3. **Type-specific rules** — the judgment calls:
   - *class:* read the XP/THAC0/saves progression table into the `progression`
     map; split prose into `features[]`.
   - *race-as-class:* set `race_locked`; mirror ability requirements.
   - *spell:* set `classes[]`, `level`, `source`; detect `reversible` /
     `reverse_name`.
   - *item:* pick the right `item_type` variant; transcribe cost/weight/damage.
   - *magic item:* choose native `weapon`/`armor` with `magic_bonus` vs. `magic`
     with `modifiers`; translate effects into `Modifier` rows — the hardest
     call, leaning on existing `magic_items.yaml` examples.

Contract: read the markdown unit → emit only YAML matching the crib → if a value
isn't in the source, omit the optional field or emit a `# TODO:` rather than
guessing.

## Validator — `tools/validate_import.py`

The only new code. The per-unit "done" gate.

1. **Per-file model validation** against the real models imported from
   `aose.models` (never a copy): `Race`, `CharClass`, `TypeAdapter(Item)`,
   `Spell`.
2. **Full `GameData.load(data/)`** afterward, to catch cross-reference problems
   a per-file check misses (e.g. a race's `allowed_classes` naming a missing
   class).
3. **Cross-file ID uniqueness** per type — fail loudly on collisions. Key
   safeguard now that multiple books share `data/equipment/` and `data/spells/`.
4. **Reporting** per unit: `OK` / list of errors; writes `validated: true` back
   to the manifest on success.

Run modes: `--unit class/fighter`, `--type spell`, or bare (everything
incomplete). Exit non-zero on any failure so it doubles as a CI/test check. It
guarantees YAML is *loadable and consistent* — it does **not** judge rules
correctness (that's the human eyeball pass).

## End-to-end loop

```
seed manifest (once, by hand from the PDF table of contents)
        │
   ┌────▼─────────────────────────────────────────────┐
   │  pick next incomplete unit from manifest          │
   │  Phase 1:  phase1-extract prompt + PDF pages       │  → import/markdown/<type>/<id>.md  (commit)
   │  Phase 2:  phase2-<type> prompt + that markdown    │  → data/<…>.yaml  (append for list types)
   │  Validate: validate_import.py --unit <id>          │  → manifest validated: true
   │  Eyeball vs. rulebook, then git commit             │
   └────▲─────────────────────────────────────────────┘
        │  repeat next session — manifest says where you left off
```

Cross-session repeatability comes entirely from the committed markdown +
manifest. Re-running Phase 2 alone (e.g. after a crib fix) is free because the
markdown is already present. Prompts are plain files, so each step runs
identically in CC-on-Haiku or pasted into ChatGPT.

## Out of scope

- The spell selector UI / wizard spell step (future work).
- Any rules-correctness automation beyond loadability + consistency.
- Scripted API orchestration (explicitly rejected — removes the ChatGPT
  fallback and needs a key).
- A `source` field on non-Spell models (declined; only `Spell` gets it).
```
