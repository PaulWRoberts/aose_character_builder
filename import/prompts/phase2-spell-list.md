# Phase 2 — Define a spell list

Add or update entries in `data/spell_lists.yaml` for the spell pools a book
introduces.

- Read the schema crib at `import/cribs/spell-list.md`.
- Output ONLY YAML — append mappings to the existing list (one per pool).
- Decide `caster_type` per the crib's rule (spell book = arcane; prayer / whole
  list = divine). Decide it once; classes and spells just reference the id.
- A pool that already exists must not be duplicated.
