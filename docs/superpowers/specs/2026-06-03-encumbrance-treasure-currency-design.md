# Faithful encumbrance, treasure weight & multi-coin currency

**Date:** 2026-06-03
**Status:** Approved (design)

## Problem

Three related defects, all rooted in the same area (encumbrance & treasure):

1. **Encumbrance is implemented incorrectly.** The current engine
   (`aose/engine/encumbrance.py`) keys movement off an `(armour class ×
   weight band)` table (`_TABLE_HUMAN`) with bands `400/800/1200/1600`.
   This matches neither AOSE encumbrance option. It also scales movement
   for demihumans by `base/120`, which is dead code (no race file sets
   `base_movement < 120`) and contrary to AOSE's absolute movement tables.

2. **Gems, jewellery, and coins contribute no weight.** `valuables.py`
   documents gems/jewellery as "weightless"; `gold` never contributes
   weight. Per the book, a coin (any type) is 1 cn, a gem is 1 cn, and a
   piece of jewellery is 10 cn.

3. **Only gold is tracked.** `CharacterSpec.gold: int` is the sole purse.
   The book has five denominations (pp/gp/ep/sp/cp) with conversion rates,
   and every coin weighs 1 cn regardless of type — so correct encumbrance
   requires actual per-denomination counts.

## Source rules (AOSE, Encumbrance optional rule)

**Treasure encumbrance (coins of weight):** Coin (any type) 1 · Gem 1 ·
Jewellery (1 piece) 10 · Potion 10 · Rod 20 · Scroll 1 · Staff 40 · Wand 10.
The referee decides the weight of other treasure.

**Maximum load:** 1,600 cn. Carrying more → cannot move.

**Option 1 — Basic.** Equipment weight untracked. Treasure weight tracked
only to enforce the 1,600 cap. Movement is set by armour worn × whether the
character is carrying a significant amount of treasure (referee judgement);
actual treasure weight does not affect the rate.

| Armour Worn | Without Treasure | Carrying Treasure |
|---|--:|--:|
| Unarmoured | 120' (40') | 90' (30') |
| Light armour | 90' (30') | 60' (20') |
| Heavy armour | 60' (20') | 30' (10') |

**Option 2 — Detailed.** Track coins + treasure + armour + weapons by
listed weight. Miscellaneous adventuring gear (backpack, spikes, sacks…)
may be counted as a flat 80 cn. Movement by total weight:

| Encumbrance | Movement Rate |
|---|--:|
| Up to 400 cn | 120' (40') |
| Up to 600 cn | 90' (30') |
| Up to 800 cn | 60' (20') |
| Up to 1,600 cn | 30' (10') |

**Coin conversion:** 1pp = 5gp · 1gp = 2ep · 1gp = 10sp · 1gp = 100cp.

## Decisions (from brainstorming)

- **Currency model:** separate per-denomination coin counts (not a single
  gp balance). `gold` stays as the gp / shop-spendable balance; four new
  count fields are added alongside. Lower churn than restructuring `gold`
  (21 code refs + 23 test files reference it), identical faithfulness.
- **Detailed gear weight:** flat 80 cn (book RAW), not summed per-item.
  Applied only when the character carries some non-armour/non-weapon gear
  (0 if none).
- **Basic "carrying treasure":** a manual toggle (referee judgement), not
  auto-derived from treasure weight.
- **Treasure-weight scope:** the full treasure table — coins, gems,
  jewellery, and carried potions/scrolls/rods/staves/wands (including
  spell-source scrolls, which currently contribute zero).
- **Demihuman scaling:** removed. AOSE movement tables are absolute.

## Part A — Currency (multi-coin purse)

### Model
`CharacterSpec` gains `platinum: int = 0`, `electrum: int = 0`,
`silver: int = 0`, `copper: int = 0`. `gold: int` is unchanged and remains
the gp / spendable balance. No backward-compat migration (app not deployed).

### Engine — `aose/engine/currency.py` (cycle-free; imports models only)
- `RATES` in a copper base to avoid floats:
  `pp=500, gp=100, ep=50, sp=10, cp=1` (cp-equivalents).
- `total_value_cp(spec) -> int` and `total_value_gp(spec) -> int` — for the
  sheet's treasure-value display.
- `coin_count(spec) -> int` = `pp + gp + ep + sp + cp` — the weight
  contribution (1 cn per coin).
- `convert(spec, frm, to, count)` — make change at official rates; result
  must be whole coins or it raises `CurrencyError` (routes → HTTP 400).
  Returns updated denomination values (no in-place mutation of inputs).

### Routes
- `/coins/add` — `denom` + signed `amount`, clamped ≥ 0 per denomination.
- `/coins/convert` — `from`, `to`, `count`.
- The existing `/gold` route remains (adds gp). Shop / ammo / magic-item
  purchases continue to spend `gold` unchanged; a player short on gp
  converts other coins to gp first.

## Part B — Treasure weight

- `valuables.py`: gems weigh 1 cn each (`count × 1`); jewellery 10 cn each.
  Add `valuables_weight_cn(spec) -> int`. Remove the "weightless" docstrings.
- Catalog data — set `weight_cn` per the treasure table:
  potions **10**, wands **10**, rods **20**, staves **40**
  (`data/equipment/magic_items.yaml`); protection scrolls **1**
  (`data/equipment/scrolls.yaml`). These already flow into carried weight
  via the existing `magic_items` loop once the data is correct.
- Spell-source **scrolls** (`spec.spell_sources`, kind `scroll`): count
  **1 cn** each in carried weight (currently zero). **Spellbooks** are not
  in the treasure table → remain weightless, documented.
- Coins: `currency.coin_count(spec)` added to carried weight.

## Part C — Encumbrance rewrite (`aose/engine/encumbrance.py`)

Remove `_TABLE_HUMAN`, the demihuman `_scale` helper, and the `(armour ×
band)` model. Split weight into clear helpers:

- `treasure_weight_cn(spec, data)` — coins (`currency.coin_count`) + gems
  (1 cn each) + jewellery (10 cn each) + carried treasure magic items
  (potions/rods/staves/wands by catalog `weight_cn`) + scrolls (1 cn).
- `equipment_weight_cn(spec, data)` (detailed only) — carried weapons by
  weight + carried armour by weight (keeping the enchanted
  `weight_multiplier`) + flat **80 cn** when any misc adventuring gear is
  carried, else 0.

### `basic`
Movement = armour worn × the new manual `CharacterSpec.carrying_treasure:
bool = False` toggle:

| Armour (`movement_impact`) | No treasure | Carrying |
|---|--:|--:|
| Unarmoured (`none`) | 120 | 90 |
| Light (`leather`) | 90 | 60 |
| Heavy (`metal`) | 60 | 30 |

Equipment weight untracked. `treasure_weight_cn` is computed solely to
enforce the 1,600 cap → over 1,600 yields 0 movement regardless of the
toggle.

### `detailed`
Single-axis by total weight (no armour column). Total =
`equipment_weight_cn` + `treasure_weight_cn`. Bands **400 / 600 / 800 /
1,600**:

| Total | Move |
|---|--:|
| ≤ 400 | 120 |
| ≤ 600 | 90 |
| ≤ 800 | 60 |
| ≤ 1,600 | 30 |
| > 1,600 | 0 |

### `none`
Unchanged — returns the race base movement.

## Part D — Sheet & display

- `CharacterSpec.carrying_treasure: bool = False` (Part C).
- Rework `EncumbranceTable` into the two real shapes:
  - basic — 3×2 (armour × treasure), current cell highlighted;
  - detailed — single-axis 4-band, current band highlighted.
- Show treasure weight against the 1,600 cap in both modes.
- Basic mode: render the carrying-treasure toggle (route to flip it).
- New coin-purse UI: pp/gp/ep/sp/cp with add + convert; treasure value
  shown in gp (`currency.total_value_gp`).
- Valuables section displays gem/jewellery weight.
- Update `ENCUMBRANCE_DESCRIPTIONS` to describe the real Basic/Detailed
  rules.

## Non-goals / out of scope

- Restructuring `gold` into a `Coins` submodel.
- Per-item gear weights driving the detailed band (flat-80 supersedes this;
  container per-item weights still display in inventory).
- Spellbook weight (not in the treasure table).
- "Other treasure" weights beyond the table (referee's call).

## Testing

- `currency.py`: conversion round-trips, whole-coin enforcement, value &
  coin-count totals, clamping.
- `valuables.py`: gem/jewellery weight; total weight integration.
- `encumbrance.py`: basic table (all six armour×treasure cells + 1,600
  cap), detailed bands (all five thresholds incl. flat-80 trigger on/off
  and the >1,600 immobile case), `none` passthrough, treasure-weight
  composition (coins + gems + jewellery + magic-item treasure + scrolls).
- Regression: existing `gold`/shop/ammo/magic tests stay green.
