# Phase 2 — Structure a race into YAML

Convert the provided race markdown into YAML matching the `Race` model.

- Read the schema crib at `import/cribs/race.md` (ChatGPT: pasted above).
- Output ONLY YAML — a single mapping (one race per file).
- Remember `allowed_classes: []` means "any class"; only use it for human-like
  races. List restrictions explicitly otherwise.
- Omit optional fields not present; mark uncertain values `# TODO: confirm`.

Write the result to `data/races/<id>.yaml`.
