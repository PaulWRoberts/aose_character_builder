# Gems & Jewellery — Design Spec

Date: 2026-06-03
Status: Approved (pending implementation plan)

## Goal

Let a character own **gems** and **jewellery** as value-bearing treasure,
acquired for free (GM grant / loot), tracked per-instance on the live sheet.
These are not catalog shop items — each carries its own value (and, for
jewellery, a damaged flag). They have **no weight**, are **sheet-only**
(not in the wizard), and **Add-only** (no gold spent to acquire), mirroring
how magic items and spell books / scrolls are handled.

Source rule text (Advanced Fantasy, Gems and Jewellery):

- **Gems** — value per the table: d20 1–4 → 10gp, 5–9 → 50gp, 10–15 → 100gp,
  16–19 → 500gp, 20 → 1,000gp.
- **Jewellery** — each piece is worth `3d6 × 100gp` (or more at the referee's
  discretion).
- **Damaged jewellery** — rough treatment reduces a piece's value by 50%.

## What already exists (patterns to mirror)

- Per-instance ownership lists on `CharacterSpec`, each separate from
  `inventory`, with a focused engine module and a shared sheet/route surface:
  `ContainerInstance`, `AmmoStack`, `MagicItemInstance`, `SpellSource`.
- **Add-only acquisition** (GM grant, no gold): `add_free_*` helpers; sheet-only,
  the wizard is untouched.
- `sell_gp = int(cost // 2)` floor convention in `engine/shop.py`.
- The project does not deploy; **no data-shape migrations** are written for new
  optional fields (new lists default empty on old saves).

## Decisions (confirmed)

1. **Gems acquire two ways** — pick one of the five table increments
   (10/50/100/500/1000 gp) from a dropdown, **or** set a custom value. Both
   produce an ordinary gem of that value. The five increments are an engine
   constant feeding the dropdown; they are **not** a hard model constraint
   (a 250gp custom gem is valid). Validation: `value > 0`.
2. **Gems stack with a count** — one row per `(value, label)`; adding a gem
   with the same value and label increments the count. Counts are adjusted
   manually (no auto-spend).
3. **Jewellery is individual** — each piece is its own entry.
4. **Jewellery value** — added either as a random roll (`3d6 × 100`, rolled on
   add) or a set value.
5. **Damaged flag** — stored as full `value` + a `damaged: bool`. Damaged halves
   the value at **display/sell** time (`value // 2`, floor). The flag is a
   **toggle on the sheet** — un-damaging restores full value (reversible).
6. **Optional label on both** — free-text name (e.g. "ruby", "gold necklace");
   blank is fine. Gems stack only when value **and** label match.
7. **Selling / removing** — two actions, no "refund" mode (these were free):
   - **sell** — adds the item's current value to `spec.gold` (damaged jewellery
     contributes its halved value; a gem sale adds one gem's value and
     decrements the stack).
   - **drop** — removes with no gold change.
8. **No weight** — gems and jewellery never touch `encumbrance.py`.
9. **Out of scope** — treasure-type generation tables, "more at referee's
   discretion above 3rd level" automation (the custom-value option covers it
   manually), gem/jewellery as buyable shop stock.

## Data model — `aose/models/valuable.py`

```python
class GemStack(BaseModel):
    instance_id: str          # uuid4 hex
    value: int                # gp per gem; > 0 (table increment or custom)
    count: int = 1            # number of identical gems in this stack
    label: str = ""           # optional free-text name

class JewelleryPiece(BaseModel):
    instance_id: str          # uuid4 hex
    value: int                # full (un-halved) gp value; > 0
    damaged: bool = False     # halves effective value when True
    label: str = ""           # optional free-text name
```

`CharacterSpec` gains:

```python
gems: list[GemStack] = Field(default_factory=list)
jewellery: list[JewelleryPiece] = Field(default_factory=list)
```

Both `extra="forbid"`, consistent with the other instance models. No migration.

## Engine — `aose/engine/valuables.py`

Cycle-free: imports only models + `engine/dice`. Nothing imports it back. All
mutators return new lists (no in-place mutation), raising `ValueableError`
(a `ValueError` subclass) on bad input; routes map it to HTTP 400.

Constant:

```python
GEM_INCREMENTS = (10, 50, 100, 500, 1000)   # dropdown affordance, not a constraint
```

Gems:

- `add_gem(gems, value, count=1, label="") -> list[GemStack]` — validates
  `value > 0` and `count > 0`; stacks onto an existing entry with the same
  `(value, label)`, else appends a new stack with a fresh `instance_id`.
- `adjust_gem_count(gems, instance_id, delta) -> list[GemStack]` — clamps at 0;
  a stack reaching 0 is removed.
- `remove_gem(gems, instance_id) -> list[GemStack]` — drops the whole stack.
- `sell_gem(gems, gold, instance_id) -> tuple[list[GemStack], int]` —
  decrements the stack by one and adds that gem's `value` to `gold`; empties → row
  removed.
- `sell_gem_all(gems, gold, instance_id) -> tuple[list[GemStack], int]` —
  sells the whole stack at once, adding `value * count` to `gold` and removing
  the row.

Jewellery:

- `roll_jewellery_value(rng=None) -> int` — `roll("3d6", rng) * 100`.
- `add_jewellery(jewellery, value, damaged=False, label="") -> list[JewelleryPiece]`
  — validates `value > 0`; appends a piece with a fresh `instance_id`.
- `set_jewellery_damaged(jewellery, instance_id, damaged) -> list[JewelleryPiece]`
  — toggle.
- `remove_jewellery(jewellery, instance_id) -> list[JewelleryPiece]` — drop.
- `sell_jewellery(jewellery, gold, instance_id) -> tuple[list[JewelleryPiece], int]`
  — removes the piece and adds its **effective** value to `gold`.

Value helpers (pure):

- `gem_stack_value(stack) -> int` = `value * count`.
- `jewellery_value(piece) -> int` = `value // 2 if damaged else value`.
- `total_value(spec) -> int` = sum of all gem-stack values + all jewellery
  effective values.

## Sheet — `aose/sheet/view.py`

A `valuables_view(spec) -> ValuablesView` builds the data for a new
**"Gems & Jewellery"** section (placed near the Magic Items section). It carries:

- gem rows (`instance_id`, `value`, `count`, `label`, `stack_value`),
- jewellery rows (`instance_id`, `value`, `damaged`, `label`, `effective_value`),
- `total_value`.

The section is added to the `CharacterSheet` model (`Field(default_factory=...)`)
and assembled in `build_sheet`. Weight is never computed for these — the
encumbrance path is untouched, and a test asserts that.

Template (`sheet.html`): a collapsible section with two inline **Add** forms —

- Gem: value dropdown (the five increments) **or** a custom-value field, a count
  field, an optional label; Add.
- Jewellery: a Random / Set-value choice (Random ignores the value field and
  rolls `3d6×100`), an optional label, a damaged checkbox; Add.

Each row shows value (and count for gems), with **Sell** and **Drop** buttons;
gem rows also get a **Sell all** button; jewellery rows show a **damaged** toggle. The section footer shows total
treasure value. Sheet-only; the wizard renders nothing for valuables.

## Routes — `aose/web/routes.py` (sheet-only)

Mirroring `/spell-sources/*`, each loads the spec, mutates via the engine, saves,
and 303-redirects back to the sheet:

- `POST /character/{id}/gems/add` — `value` (custom or chosen increment), `count`,
  `label`.
- `POST /character/{id}/gems/adjust` — `instance_id`, `delta`.
- `POST /character/{id}/gems/sell` — `instance_id` (sells one).
- `POST /character/{id}/gems/sell-all` — `instance_id` (sells the whole stack).
- `POST /character/{id}/gems/remove` — `instance_id`.
- `POST /character/{id}/jewellery/add` — `mode` (random|set), `value` (when set),
  `damaged`, `label`.
- `POST /character/{id}/jewellery/toggle-damaged` — `instance_id`, `damaged`.
- `POST /character/{id}/jewellery/sell` — `instance_id`.
- `POST /character/{id}/jewellery/remove` — `instance_id`.

## Testing

Engine unit tests:
- gem stacking by `(value, label)`; custom (non-increment) value accepted;
  `value <= 0` / `count <= 0` rejected.
- `adjust_gem_count` clamp-and-remove at 0.
- `roll_jewellery_value` range via seeded rng (300–1800, multiples of 100).
- `jewellery_value` halving with floor (e.g. 125 damaged → 62).
- `sell_gem` decrements stack + adds one gem's value; empties → row removed.
- `sell_gem_all` adds `value * count` and removes the row.
- `sell_jewellery` adds effective value (damaged → halved) and removes the piece.
- `drop`/`remove` add no gold.
- `total_value` across mixed holdings.

Route tests: add (gem increment, gem custom, jewellery random, jewellery set),
sell adds value, drop adds nothing, toggle-damaged round-trips.

Sheet-view test: a character holding gems + jewellery shows zero weight
contribution (encumbrance unchanged) and a correct `total_value`.

## Files

- New: `aose/models/valuable.py`, `aose/engine/valuables.py`,
  tests under `tests/`.
- Edit: `aose/models/__init__.py` (export new models),
  `aose/models/character.py` (two new lists), `aose/sheet/view.py`
  (`valuables_view` + `CharacterSheet` field + `build_sheet`),
  `aose/web/routes.py` (8 routes), `aose/web/templates/sheet.html`
  (section + forms), `CLAUDE.md` (feature note).
