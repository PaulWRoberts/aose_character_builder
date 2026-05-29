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
