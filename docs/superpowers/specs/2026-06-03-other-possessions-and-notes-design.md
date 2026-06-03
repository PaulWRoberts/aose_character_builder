# Other Possessions + Notes — Design

**Date:** 2026-06-03
**Status:** Approved

## Summary

Two small, independent additions to the live character sheet:

1. **Other Possessions** — a list of discrete free-text entries, each an
   implied/untracked item. Use case: the DM says "you find a bronze key" and
   the player jots it down without modelling it as catalog inventory.
2. **Notes** — a single open-ended free-text block, uncoupled from inventory
   entirely (general scratch space).

Both are **sheet-only** (play-time, not creation-time) and carry no
derivations — no weight, no value, no encumbrance impact.

## Data model (`aose/models/character.py`)

Two new fields on `CharacterSpec`:

```python
# Free-text "other possessions" — discrete entries, each an implied item the
# DM handed out ("a bronze key"). Untracked: no weight, value, or encumbrance.
other_possessions: list[str] = Field(default_factory=list)
# Open-ended scratch notes, unrelated to inventory.
notes: str = ""
```

Duplicates are allowed in `other_possessions`. Both default empty, so existing
saved characters load unchanged — no migration needed (app is not deployed;
per project convention).

## Engine (`aose/engine/possessions.py` — new)

A small, pure, cycle-free module (imports models only), mirroring the style of
`aose/engine/valuables.py`, including a `PossessionError` for invalid ops.

- `add_possession(items: list[str], text: str) -> list[str]`
  Returns a new list with `text.strip()` appended. Empty / whitespace-only
  input is ignored (returns the list unchanged) — not an error.
- `remove_possession(items: list[str], index: int) -> list[str]`
  Returns a new list with the entry at `index` removed. An out-of-range index
  **raises `PossessionError`** (consistent with `valuables.ValuableError`).

Notes need no engine — setting a string is done inline in the route.

## Routes (`aose/web/routes.py`)

Following the gem/jewellery pattern (load spec → mutate → save → 303 redirect;
`PossessionError` → `HTTPException(400)`):

- `POST /character/{character_id}/possessions/add` — form field `text`
- `POST /character/{character_id}/possessions/remove` — form field `index` (int)
- `POST /character/{character_id}/notes/set` — form field `notes` (overwrites
  the whole block)

## Sheet view + templates

- `CharacterSheet` (`aose/sheet/view.py`) gains `other_possessions: list[str]`
  and `notes: str`, copied straight from the spec in `build_sheet` (no
  computation).
- `sheet.html`: an **Other Possessions** subsection near the inventory area —
  a text input + Add button, and each entry rendered as a row with a delete
  (remove-by-index) button. A separate **Notes** section: a textarea
  pre-filled with the current notes + a Save button.
- `sheet_print.html`: render both read-only so they appear on a printed sheet.

## Tests

- **Engine** (`tests/`): `add_possession` trims and skips empty;
  `remove_possession` removes by index and raises on a bad index.
- **Routes**: round-trip persistence for all three endpoints (add an entry,
  remove it, set notes) — assert the saved `CharacterSpec` reflects the change.

## Out of scope (YAGNI)

- Wizard integration — these are play-time discoveries.
- Per-entry inline editing — delete + re-add instead.
- Rich text, weight, value, or any catalog linkage for possessions.
