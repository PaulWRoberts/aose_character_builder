# Phase 2 — Structure spells into YAML

Convert the provided spell-list markdown into YAML matching the `Spell` model.

- Read the schema crib at `import/cribs/spell.md` (ChatGPT: pasted above).
- Output ONLY YAML — a LIST of spell mappings (append to the book's single file).
- Set `level`, `spell_lists` (pool IDs, not class names), and `source`.
- Detect reversible spells: set `reversible: true` and `reverse_name`.
- Keep ids snake_case and unique. Mark uncertain values `# TODO: confirm`.

Append the result into `data/spells/<book>_spells.yaml`.
