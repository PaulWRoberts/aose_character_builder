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
