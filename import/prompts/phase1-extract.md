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
