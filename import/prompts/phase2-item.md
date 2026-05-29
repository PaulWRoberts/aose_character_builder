# Phase 2 — Structure mundane items into YAML

Convert the provided equipment markdown into YAML matching the `Item` union.

- Read the schema crib at `import/cribs/item.md` (ChatGPT: pasted above).
- Output ONLY YAML — a LIST of item mappings; choose `item_type` per entry.
- Transcribe cost (gp) and weight (cn) exactly; set both weapon damage values.
- Keep ids snake_case and unique across data/equipment/. Mark unclear values
  `# TODO: confirm`.

Append the result into `data/equipment/<book>_items.yaml`.
