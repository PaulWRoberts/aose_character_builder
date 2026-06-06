# Inline detail cards for management drawers — design

**Date:** 2026-06-05
**Status:** Approved (brainstorming)

## Problem

On the live character sheet, the two management drawers — **Manage Spells**
(`drawer-spells`) and **Manage Inventory** (`drawer-equip` → `_equipment_ui.html`)
— list spells and items as terse rows with no way to read what they actually do
without leaving the panel. We want a row to **expand in place** to reveal full,
structured details (spell range/duration/description; item stats/description),
and collapse again on a second click. The drawer must **stay open** the whole
time — closing it to pop a modal is a poor workflow.

## Scope

In scope (rows that become expandable):

- **Manage Spells drawer** (`sheet.html` → `drawer-spells`):
  - memorised-slot rows (`SlotView`)
  - known-spell rows (`SpellEntryView`)
- **Inventory drawer** (`_equipment_ui.html`):
  - all plain item rows in the Carried tab: **Equipped / Carried / Stashed**
    (`InventoryRow`, via the shared `inv_table` macro)
  - **Documents tab** embedded spell-book / scroll spells (`SpellSourceEntryView`)

Out of scope:

- Main-sheet per-item / per-spell modals (they already work; the new macro is
  written to be droppable there later, but we don't touch them now).
- Magic-items, gems/jewellery, ammunition, and shop rows.
- The "Learn a spell" `<select>` (a dropdown, not rows).
- Drag-and-drop.

## Interaction model

- A row is the **trigger**: clicking it toggles an inline detail row rendered
  immediately after it.
- **Independent toggles** — opening one row does *not* collapse others; several
  details may be open at once. This matches the existing container-collapse
  behaviour in `inventory.js`.
- Clicking a real control inside a row (the existing memorise / cast / clear /
  equip / buy `<form>` buttons, links) must **not** trigger expand. The handler
  ignores clicks originating inside a `form`, `button`, or `a`.
- This is entirely separate from the overlay controller (`sheet_overlays.js`):
  no scrim, no modal, the drawer stays open. No conflict with the
  one-surface-open overlay model.

## Architecture

Approach **A** (chosen over per-type Jinja macros and a client-fetched JSON
endpoint): a unified presentational view model rendered by **one** macro and
toggled by **one** generalized JS handler. Per-type formatting lives in tested
Python, not Jinja conditionals.

### 1. Data layer — `DetailCard`

New presentational value types (cycle-free; placed so both `aose/sheet/view.py`
and `aose/engine/shop.py` can import them without an import cycle — final
location chosen during planning, e.g. a tiny `aose/sheet/detail.py` or
`view.py` itself if no cycle results):

```python
class StatLine(BaseModel):
    label: str        # "Damage", "Range", "Duration", "AC", "Cost"
    value: str        # pre-formatted, e.g. "1d8", "5/10/15 ft", "5 [14]"

class DetailCard(BaseModel):
    stats: list[StatLine] = []
    description: str | None = None
```

Two pure builders:

- **`spell_card(spell, *, reversed=False) -> DetailCard`**
  - stats: Level, Range, Duration, and a Reversible line
    (`"Yes — <reverse_name>"`) when `spell.reversible`.
  - description = `spell.description`.
  - takes the full `Spell` model so every field is available.

- **`item_card(item) -> DetailCard`** — dispatches on the concrete item type:
  - **Weapon** → Type, Damage (default / variable / variable two-handed as
    available), Range (`short/medium/long ft` when ranged), Hands, Qualities,
    magic bonus and conditional bonus when present, Cost, Weight.
  - **Armor** → Type, AC (`ac_descending [ascending]`), shield flag, movement
    impact, magic bonus when present, Cost, Weight.
  - **Container** → Type, Capacity, weight multiplier, Cost.
  - **AdventuringGear** → Type, bundle count (when > 1), Cost, Weight.
  - **MagicItem** → Type, modifier summary, charges, Cost.
  - **Ammunition** → Type, groups, bundle count.
  - **Poison** → Type, onset/effect/save modifier.
  - description = `item.description`.

Each affected row view model gains `detail: DetailCard | None = None`:

| Row model | File | Detail built by |
|---|---|---|
| `SpellEntryView` (known) | `aose/sheet/view.py` | `spell_card` |
| `SlotView` (memorised) | `aose/sheet/view.py` | `spell_card` (honours `reversed`) |
| `SpellSourceEntryView` (Documents) | `aose/sheet/view.py` | `spell_card` via `data.spells[spell_id]` lookup |
| `InventoryRow` | `aose/engine/shop.py` | `item_card`, built in `inventory_view` (has the catalog item in hand) |

`SpellSourceEntryView` currently has no description/range/duration; the builder
resolves the full spell from `data.spells` to fill the card.

### 2. Presentation — one macro

New shared partial `aose/web/templates/_detail_card.html`:

```jinja
{% macro detail_card(card) %}
<div class="detail-card">
  {% if card.stats %}
  <dl class="detail-stats">
    {% for s in card.stats %}<div><dt>{{ s.label }}</dt><dd>{{ s.value }}</dd></div>{% endfor %}
  </dl>
  {% endif %}
  {% if card.description %}<p class="detail-desc">{{ card.description }}</p>{% endif %}
</div>
{% endmacro %}
```

Each expandable row gets a following `colspan` detail `<tr>`, collapsed by
default, mirroring the existing `container-child` pattern:

```jinja
<tr class="row-detail collapsed" data-detail-for="{{ uid }}">
  <td colspan="N">{{ detail_card(row.detail) }}</td>
</tr>
```

Wiring + colspans:

- `sheet.html` → `drawer-spells`: memorised-slot rows and known-spell rows
  (colspan 3).
- `_equipment_ui.html` → `inv_table` macro: Equipped / Carried / Stashed rows
  (colspan 4) — one edit covers all three states.
- `_equipment_ui.html` → Documents tab: embedded spell rows (colspan 2).

`uid` is a stable per-row id (e.g. `class_id`+`spell_id`+orientation for spells,
inventory state + item id for items) used to pair trigger ↔ detail row.

### 3. Styling

A small block of **zine** CSS added **above** the `LEGACY / SITE-WIDE` banner in
`sheet.css`, using existing tokens only (no new variables):

- `.detail-card` — sunk `--box-sunk` panel with a hairline top border.
- `.detail-stats` — tight grid; `dt` uses `--display` (uppercase, tracked),
  `dd` uses `--body`, lining/tabular numerics for numbers.
- `.detail-desc` — `--body` prose.
- `.row-detail.collapsed` — hidden (same mechanism as `.container-collapsed`).

### 4. JS toggle

Generalize the container-collapse in `aose/web/static/inventory.js` into a
shared, event-delegated row-detail toggle (plain vanilla JS, loaded `defer`):

- Trigger row carries `data-detail-toggle="<uid>"`; the detail `<tr>` carries
  `data-detail-for="<uid>"` and starts `.collapsed`.
- One delegated `click` listener toggles `.collapsed` on the matching detail row
  and flips `aria-expanded` on the trigger.
- The listener **ignores** clicks whose target is inside a `form`, `button`, or
  `a`, so existing management controls keep working.
- Independent toggles (no sibling auto-collapse).
- The existing container collapse keeps working — folded into the same module or
  left beside the new handler, whichever is cleaner.

## Testing

Following the project's pytest approach:

- Unit tests for `spell_card` and `item_card`: correct stat lines per item type
  (weapon / armour / container / gear / magic / ammunition / poison), reversible
  spell formatting, description passthrough, and empty/None handling.
- View-assembly tests: `SpellEntryView`, `SlotView`, `SpellSourceEntryView`, and
  `InventoryRow` each carry a populated `detail`.
- A template-render smoke test (style of existing sheet tests) for a
  caster-with-inventory character: detail rows render with `data-detail-for`
  hooks and the `collapsed` class; existing management forms still render.

## Non-goals / invariants preserved

- No new overlay surfaces; `sheet_overlays.js` untouched; one-surface-open
  overlay model unaffected.
- Static files stay `no-cache`; CSS/JS edits show on refresh under `--reload`.
- New zine CSS stays above the legacy banner.
- `@media print` still degrades gracefully (detail rows are plain table rows;
  collapsed state is display-only).
