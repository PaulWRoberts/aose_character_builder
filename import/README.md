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

---

## Starting a fresh session prompt

Copy-paste this into a new Claude Code session (any model) to run the pipeline.
Replace `<<< FILL THIS IN >>>` with the units you want imported.

```
You are running the AOSE content-import pipeline. Import one or more units from
an OSE PDF into the app's strict YAML format. Work entirely from the existing
pipeline scaffolding — do NOT redesign anything.

## Read these first
- import/README.md                  — pipeline overview + how to resume
- import/manifest.yaml              — the work queue (one row per unit)
- import/prompts/phase1-extract.md  — Phase 1 rules (PDF -> faithful markdown)
- import/prompts/phase2-<type>.md   — Phase 2 rules for the unit's type
- import/cribs/<type>.md            — the Pydantic schema crib for that type

## What I want imported
<<< FILL THIS IN, e.g.:
- class/cleric  (book pp.30-31)
- race/elf      (book pp.12-13)
>>>
The PDF is in import/pdfs/. NOTE: book page numbers != PDF page numbers — I'll
give the offset, or check the footer vs. the PDF index.

## Per unit, do this:
1. Add a manifest row if one doesn't exist (unit, type, source, pdf, pages,
   md, yaml, validated:false, notes). Use the book->PDF page mapping I gave.

2. PHASE 1 — extract to markdown.
   The Read tool's PDF rendering fails here (poppler/pdftoppm is NOT installed).
   Instead render pages to PNG with PyMuPDF and read those images:
     .venv/Scripts/python.exe -c "
     import glob, fitz
     doc = fitz.open(glob.glob('import/pdfs/*.pdf')[0])
     page = doc[<PDF_PAGE_INDEX_0_BASED>]
     r = page.rect
     # split into left/right columns at matrix 4.0 so text is legible
     for tag, x0, x1 in (('L',0,0.5),('R',0.5,1.0)):
         clip = fitz.Rect(r.width*x0, 0, r.width*x1, r.height)
         page.get_pixmap(matrix=fitz.Matrix(4.0,4.0), clip=clip).save(f'import/.tmp/p<N>_{tag}.png')
     "
   (pip install pymupdf into .venv first if fitz is missing.)
   For dense tables, re-render just the table region at matrix 7.0 to read
   every number exactly. NEVER guess a digit — use [?] if unreadable.
   Follow phase1-extract.md: de-column, reconstruct tables as GFM tables, keep
   headings, drop page furniture/art. Save to import/markdown/<type>/<id>.md.

3. PHASE 2 — structure to YAML.
   Follow phase2-<type>.md + cribs/<type>.md exactly. extra="forbid", so no
   fields outside the crib. Casters: every progression row gets spell_slots and
   the class gets spell_lists. Race-as-class: set race_locked + mirror ability
   requirements + borrow the spell list. Write to the path the crib specifies
   (e.g. data/classes/<id>.yaml). Don't invent numbers; mark anything uncertain
   with `# TODO: confirm`.

4. VALIDATE:
     .venv/Scripts/python.exe tools/validate_import.py --unit <unit>
   Fix until it prints OK and the repo-wide check prints ALL OK. (The validator
   marks the row validated:true and rewrites manifest.yaml, stripping comments —
   that's expected.)

5. After all units: run the full suite and commit.
     .venv/Scripts/python.exe -m pytest tests/ -q
   Delete the temp renders (rm -rf import/.tmp) before committing — they're not
   gitignored. The PDF itself IS gitignored. Commit the .md, .yaml, and manifest
   only. Don't push unless I ask.

Reference example already in the repo: data/classes/druid.yaml +
import/markdown/classes/druid.md (a completed class dogfood).
```
