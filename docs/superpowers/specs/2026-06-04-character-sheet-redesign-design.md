# Character Sheet Redesign — Spec

**Status:** approved (design locked via `/frontend-design`, 3 prototype iterations).
**Canonical visual/interaction reference:** `docs/redesign/character-sheet-prototype-3.html`.
**Related memory:** `project_sheet_redesign.md`.

## Goal

Replace the current bloated, vertically-stacked `sheet.html` with a compact,
single-screen **OSR-zine** character sheet that reads like the Old-School Essentials
*Vagabond*/*Underground* paper sheets while preserving **every** existing
character-management feature and route. Resting state shows values; advanced controls
open in overlays (drawer / modal / popover), one at a time.

## Non-goals

- Mobile layout (out of scope; but layout must not block a future swipe-card mobile view).
- New game mechanics. No rules changes. (No data migrations — app is local-only.)
- Changing the print route (`sheet_print.html`) beyond what's needed to keep it working.

## Visual language (zine B&W)

- Fonts: **Oswald** (display/labels/bars) + **Bitter** (body/numbers). Self-host woff2
  under `aose/web/static/fonts/` (app is offline/local — no CDN).
- Tokens: ink `#18160f`, newsprint `#f7f5ed`, box `#fdfcf6`, sunk `#ebe8dc`,
  gray `#6c685b`, faint `#a39e8c`, hair `#cdc8b6`, stamp(red) `#b32a1e`.
- Components: inked **bar** group-headers (reversed white caps), **label-tab** fields
  (black tab + white box; doubles as the click-to-edit affordance), drop-cap saving
  throws, cast-pips, hard offset shadows. **No `feTurbulence` / `mix-blend-mode`**
  (hangs rendering + perf cost) — texture via cheap CSS `repeating-linear-gradient`.

## Layout — bounded "groups"

Each group = inked bar + body with `max-height` + internal scroll, so the sheet stays
~one screen as content grows. Groups (also the future mobile swipe-cards):

1. **Identity** (full-width band, always visible): name, race·class·level·alignment
   (**display-only** — no edit route exists today; editing is a future enhancement),
   per-class XP tracks, Advance button → advancement modal.
2. **Combat** (prominent, thicker frame): HP (popover), AC = **armoured big + unarmoured**
   (no ascending shown — character AC-mode toggle decides which notation), THAC0/attack
   (**click → to-hit matrix modal**), Move = **EX / EN / OV** (exploration/encounter/overland),
   Rest button in the bar.
3. **Abilities & Saves**: 2×3 ability grid (score, mod, temp-mod popover, `✦` modified
   marker) + drop-cap saving throws.
4. **Class & Race Features** (+ **Weapon Proficiencies folded in**, as chips, **no damage
   column**). All chips click → detail modal.
5. **Spells** (caster-only — omit group entirely for non-casters). See spell model below.
6. **Inventory, Currency & Treasure** (full-width): coins (no "spendable gold" line),
   gems & jewellery (in inventory; stowable in containers), magic items, spell books &
   scrolls (type tags), ammo. **Attacks section removed** — equipped weapons show
   `+hit · dmg · range` inline. Encumbrance carried/max + band in the bar; thresholds in a
   modal.
7. **Languages, Notes & Secondary Skills** (one group; notes editable).

## Behaviour requirements

### Per-weapon to-hit (bug fix)
Current sheet shows a per-weapon **adjusted THAC0**, which is wrong UX. Show a **bonus to
the roll** instead: render `AttackProfile.to_hit_ascending` (the +N-to-d20 value, mode-
independent) as `+N` per weapon. The single base THAC0/attack value stays in Combat.

### AC armoured + unarmoured
Combat shows the armoured AC (current behaviour) and an **unarmoured** AC = AC computed
with worn armour & shield ignored but DEX + magic AC mods (e.g. Ring of Protection) kept.
In descending-AC mode show descending values; in ascending mode show ascending. No
"other notation" line.

### Movement EX / EN / OV
- Exploration = `movement_base` (per turn).
- Encounter = `movement_base // 3` (per round) — already exists.
- Overland = `movement_base // 5` (miles/day) — new.

### Spells
Every spell is click-to-view (description) with prep controls in the detail modal.
- **Arcane**: show the spellbook **partitioned by level**; NO separate memorised list;
  memorise directly on a book entry; the **same spell may be memorised multiple times**.
  Three display states via cast-pips: known (no pips) / memorised-cast-ready (filled pip)
  / memorised-spent (hollow pip). When all of a spell's pips are spent, dim the name.
- **Divine**: no book — show only memorised spells (ready/spent pips); the Manage drawer
  lists the full memorizable spell list.

The current data model already supports this: `ClassEntry.slots` (each a `SpellSlot` with
`spell_id`, `reversed`, `spent`) gives the memorised copies; `known_spells` gives the book
(arcane) / full accessible list (divine). The cast-pip view groups `slots` by `spell_id`
within each level. No engine change required beyond a view shaping helper.

### Everything-with-info is clickable
Spells, class/race features, magic items, and inventory items that carry a `description`
open the shared detail modal (templated via `data-title` / `data-text`).

## Interaction model

One unified vanilla-JS overlay controller (ported from prototype-3), **one surface open
at a time**, Esc / scrim / close-button dismiss, anchored popovers:
- **Drawer**: unified equipment (tabs Carried / Magic / Documents / Treasure / Shop);
  spells management.
- **Modal**: feature/item/spell detail; advancement; to-hit matrix; encumbrance
  thresholds; notes; rest.
- **Popover**: HP (damage/heal/set); ability temp-mod; coins/convert.
  (Identity-edit popover dropped — no backend route; identity is display-only.)

No JS framework (project constraint). Lives in `aose/web/static/sheet_overlays.js`.

## Constraints / invariants (MUST preserve)

- Every existing route and form action keeps working. Routes are unchanged; only the
  templates/markup that POST to them are reorganised. Inventory: a complete list is in
  CLAUDE.md and `_equipment_ui.html`.
- `_equipment_ui.html` is **shared with the wizard equipment step** (mundane-only:
  `magic_acquisition=False`, no `coins`/gems/spell-sources). New tabs/sections must be
  **gated on context presence** so the wizard renders only Carried + Shop.
- Print: `sheet_print.html` (separate route) keeps working; the new on-screen sheet should
  degrade gracefully under `@media print` (groups expand, overflow visible).
- All 1020+ tests pass. Text-assertion tests in `tests/test_web.py` are updated to the new
  markup; add caster/non-caster spell-group coverage.

## Acceptance criteria

1. `GET /character/<id>` renders the new grouped zine sheet; full test suite green.
2. A non-caster (e.g. Thorin the dwarf fighter) shows **no Spells group**; a caster shows
   the arcane-by-level (or divine) spells group.
3. Every feature reachable on the old sheet is reachable on the new one (equip/unequip,
   stash/stow, buy/add/sell/refund, containers, ammo load, magic equip/charges, enchanted,
   spell learn/memorise/cast/clear/forget, spell-source cast/copy/add/remove, gems &
   jewellery add/adjust/sell/sell-all/remove/damaged, coins add/convert, hp damage/heal/set,
   temp ability mods, level-up, grant XP, energy drain, rest night/full-day, notes,
   possessions, carrying-treasure toggle).
4. Per-weapon shows `+N` roll bonus, not adjusted THAC0. THAC0 matrix only on click.
5. AC shows armoured + unarmoured. Move shows EX/EN/OV.
6. Wizard equipment step still renders and works (shared partial intact).
7. One overlay open at a time; Esc/scrim/close dismiss; no console errors.
