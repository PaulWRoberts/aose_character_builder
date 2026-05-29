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
