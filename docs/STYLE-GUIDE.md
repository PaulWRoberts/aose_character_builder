# AOSE Character Builder — UI Style Guide

> For any session adding or changing UI. The **character sheet** uses the
> **OSR-zine** design system documented here. Read this before touching
> `aose/web/templates/sheet.html`, `_equipment_ui.html`, or `sheet.css`.
>
> Canonical visual reference (frozen, do not edit): `docs/redesign/character-sheet-prototype-3.html`.
> Design spec: `docs/superpowers/specs/2026-06-04-character-sheet-redesign-design.md`.

---

## 0. Two design languages — know which page you're on

The app has **two** visual systems living in the same `sheet.css`:

| Surface | Design language | Palette | Notes |
|---|---|---|---|
| **Character sheet** (`sheet.html`, `_equipment_ui.html`) | **Zine (this guide)** | `--ink`/`--paper`/etc. tokens | Oswald + Bitter, inked bars |
| **Wizard / settings / index** | **Legacy site chrome** | brown `#4a3728` on white | Bottom of `sheet.css`, marked `LEGACY / SITE-WIDE` |

When you build sheet UI, use the **zine** system below. Do **not** bleed the
legacy brown into the sheet, and do **not** restyle the legacy pages to zine
unless that's the explicit task. The legacy block starts at the
`/* LEGACY / SITE-WIDE styles ... */` banner in `sheet.css` — keep new zine
rules **above** it.

`_equipment_ui.html` is **shared** by both the sheet (full zine drawer) and the
wizard (plain). See §7.

---

## 1. Design tokens (`:root` in `sheet.css`)

```css
--ink:#18160f;  --ink-2:#3a362c;                          /* near-black text / bars  */
--paper:#efece2; --sheet:#f7f5ed; --box:#fdfcf6; --box-sunk:#ebe8dc;  /* newsprint surfaces */
--gray:#6c685b; --faint:#a39e8c; --hair:#cdc8b6;          /* muted text / hairlines  */
--stamp:#b32a1e; --stamp-dk:#8c2016;                      /* red rubber-stamp accent */
--display:'Oswald','Arial Narrow',sans-serif;             /* labels, bars, numbers   */
--body:'Bitter',Georgia,serif;                            /* prose, item names       */
--gap:12px;                                               /* the one spacing unit    */
```

Rules:
- **Always reference tokens**, never raw hex. The one common literal is `#f7f5ed`
  (= `--sheet`) used as the *reversed* text colour on inked (`--ink`) backgrounds.
- Red (`--stamp`) is an **accent only** — magic/treasure markers, danger buttons,
  hover. Never body text or large fills.
- `--gap` (12px) is the layout rhythm. Internal padding is hand-tuned per
  component (small, 4–10px); don't invent new spacing variables.

---

## 2. Typography

- **Two families only.** `--display` (Oswald) for labels, group bars, buttons,
  tags, stat numbers, drop-caps. `--body` (Bitter) for item names, descriptions,
  notes, prose.
- **Display = UPPERCASE + tracked.** Bars/labels: `text-transform:uppercase`,
  `letter-spacing:.06em–.12em`, `font-weight:600`. Body stays sentence case,
  no tracking.
- **Numbers** (AC, saves, HP, coins, weights): `--display` with
  `font-variant-numeric:lining-nums tabular-nums` for alignment.
- **Oswald is a variable font** (wght 400–700) served as a **single file**
  `oswald-variable.woff2` via one weight-range `@font-face`
  (`font-weight:400 700`). Use any weight 400–700; it interpolates. Do **not**
  re-add per-weight Oswald files. See §8 for the trap that bit us.

---

## 3. Layout — bounded "groups"

The sheet is a grid of **groups**. A group keeps the sheet ~one screen as
content grows and maps to a future mobile swipe-card.

```html
<section class="group">                  <!-- add .prominent for thicker frame (Combat) -->
  <div class="bar">Title
    <span class="tools"><button class="btn tool" data-modal="...">Action</button></span>
  </div>
  <div class="gbody scroll" style="max-height:320px">…</div>  <!-- internal scroll -->
</section>
```

- `.bar` = inked header, reversed white caps, with a faint CSS
  `repeating-linear-gradient` texture via `::after`. **Never** use
  `feTurbulence` / `mix-blend-mode` (hangs rendering + screenshot pipeline).
- `.gbody.scroll` + a `max-height` keeps long lists contained; the zine
  scrollbar is styled. Bar-right actions go in `<span class="tools">`.
- The page grid is `.layout` (`grid-template-columns:300px 1fr 1fr`); columns
  are `.col` (flex, `gap:var(--gap)`). Full-width groups use `.full`.
- A **caster-only** group (Spells) must be wrapped so non-casters render nothing
  — gate on the view model (e.g. `{% if sheet.spellbook %}`), never an empty bar.

---

## 4. Core components (use these, don't reinvent)

| Pattern | Class | Use |
|---|---|---|
| Group header | `.bar` (+ `.tools`, `.meta`) | section title + right-aligned actions / meta |
| Label-tab field | `.field` → `.tab` + `.box` | a labelled value; `.editable` + `data-pop` makes it click-to-edit |
| Big stat | `.box.big` | HP, prominent numbers |
| Identity pill | `.pill` | race/class/alignment chips in the identity band (display-only) |
| Feature/spell chip | `.chip` (+ `.src`) | clickable → detail modal (`data-modal="modal-feature"` + `data-title`/`data-text`) |
| Inline tag | `.tag` (+ `.faint`) | type markers (gem/scroll/magic); `--stamp` variants for magic/treasure |
| Button | `.btn` (+ `.solid`/`.tool`/`.link`/`.danger`/`.dark`) | actions; `.tool` is the small bar button |
| Saving throw | `.save` → `.cap` (drop-cap) + `.nm` + `.tg` | the drop-cap saves row |
| Cast pip | `.pip` (+ `.spent`) | memorised-spell state (filled = ready, hollow = spent) |
| Coin cell | `.coin` → `.d` + value | currency row |

Conventions baked into the components:
- **Everything with info is clickable** → opens a detail/management modal. Spell rows
  and plain inventory rows (Equipped / Carried / Stashed) open a **per-row management
  modal** (server-rendered, one per row) carrying cast/restore/clear or equip/stash/
  drop/sell forms. Race/class feature chips use the shared `modal-feature` pattern
  (`data-modal="modal-feature"` + `data-title`/`data-text`). The "Manage" drawers are
  retained for bulk/creation work (memorise/forget/learn, shop, grants).
- **Per-weapon to-hit shows `+N` roll bonus** (`atk.to_hit_ascending`), **never**
  an adjusted THAC0. The single base THAC0/attack lives in Combat; the full
  matrix is the `modal-matrix` click-through only.
- **Identity (name/alignment) is display-only** — there is no edit route. Do not
  add edit triggers/popovers for it.

---

## 5. Overlays & interaction model

One vanilla-JS controller: `aose/web/static/sheet_overlays.js`. **One surface
open at a time.** Dismiss = scrim click, `[data-close]` (the × in `.ov-head`),
or `Esc`.

Three surface types, all children of the same model:

| Type | Class | Trigger attr | When |
|---|---|---|---|
| **Drawer** (right slide) | `.overlay.drawer` | `data-drawer="id"` | big tabbed panels: equipment, spells management |
| **Modal** (centred) | `.overlay.modal` | `data-modal="id"` | detail (feature/spell), advancement, matrix, encumbrance, notes, rest |
| **Popover** (anchored) | `.overlay.popover` | `data-pop="id"` | small inline edits: HP, ability temp-mod, coins |

To add an overlay:
1. Add the trigger: `<button class="btn tool" data-modal="modal-foo">…</button>`.
2. Add the panel markup at the overlay block near the bottom of `sheet.html`:
   `<div class="overlay modal" id="modal-foo" role="dialog" aria-label="Foo">`
   with an `.ov-head` (title + `<button class="x" data-close>×</button>`) and
   `.ov-body`. No JS wiring needed — the controller is event-delegated.
3. Real `<form action="/character/{{ character_id }}/…">` inside; never leave an
   empty `action`.

**Templated detail modal:** `modal-feature` is filled from the trigger's `data-title` /
`data-text` by the controller (`[data-role="title"]`, `[data-role="text"]`).

**Per-spell and per-item modals** are rendered server-side (one per row) and carry their
own cast/restore/clear or equip/stash/drop forms. The "Manage" drawers keep the bulk
operations (memorise/forget/learn, shop, grants). To add a per-item modal: render it in
the overlay block of `sheet.html` using the `item_modal` macro; for spells the loop in
the `{% if sheet.spellbook %}` block already handles new rows automatically.

**Roll → Confirm at level-up.** Sub-name-level advancement is a deliberate two-step:
a `POST …/level-up/{class_id}/roll` stores the HP in `CharacterSpec.pending_level_up`,
then `POST …/confirm` commits it and bumps the level. Under Strict Mode the pending roll
locks after one press; Strict off allows re-roll before confirm. At/beyond name level the
roll step is skipped entirely — only `/confirm` is shown. Mirrors the wizard's L1 HP step.
Per-class `modal-levelup-{class_id}` modals are rendered in the overlay block of
`sheet.html` via `{% for m in sheet.level_up_modals %}`; `LevelUpModal` is built in
`aose/sheet/view.py`.

---

## 6. ⚠️ Invariants & gotchas (learned the hard way)

These caused real bugs. Don't regress them.

1. **Closed overlays must not capture clicks.** `.overlay.modal` is kept in the
   layout while closed (for the fade/scale transition) but **must** carry
   `pointer-events:none`, flipped to `auto` only on `.overlay.modal.on`.
   Without this, invisible centred modals (`opacity:0`, `z-index:50`) blanket
   the screen and swallow every click — dead buttons, un-dismissable popovers.
   Any new always-present overlay needs the same pointer-events discipline.
2. **Variable Oswald, single file.** One `oswald-variable.woff2` + one
   weight-range `@font-face`. If you ever re-self-host a font, **verify glyph
   coverage** (see §8) — a broken subset renders a few glyphs and silently
   falls back for the rest.
3. **Static files are served `no-cache`** (`NoCacheStaticFiles` in `app.py`) so
   CSS/JS edits show up on a normal refresh under `--reload`. Keep it.
4. **No `feTurbulence` / `mix-blend-mode`.** Use cheap CSS
   `repeating-linear-gradient` for the inked texture.
5. **`@media print` must degrade gracefully:** groups expand
   (`overflow:visible; max-height:none`), overlays/chrome hidden, `.print-only`
   shown. The separate `sheet_print.html` route is untouched by sheet changes.
6. **Don't break the legacy block.** Keep new zine rules above the
   `LEGACY / SITE-WIDE` banner; the wizard/settings/index depend on what's below.

---

## 7. The shared equipment partial (`_equipment_ui.html`)

Used by **both** the sheet drawer and the wizard equipment step. New
tabs/sections are **gated on context presence** so the wizard (which passes none
of that context) shows only **Carried + Shop**:

| Tab | Gate |
|---|---|
| Carried | always |
| Magic | `{% if magic_acquisition %}` |
| Documents (spell books/scrolls) | `{% if spell_sources is defined %}` |
| Treasure (gems/jewellery) | `{% if valuables is defined %}` |
| Shop | always |

If you add a sheet-only section here, gate it the same way and confirm
`tests/test_wizard.py` still passes (the wizard must render Carried + Shop only).

---

## 8. Self-hosting / replacing a font (the trap)

The original Oswald files were a corrupt subset (only space + "A"); every other
letter fell back to Arial Narrow and the lone real "A" stood out. To avoid this:

1. Prefer the **variable** woff2 (Google Fonts CSS2, `latin` subset, modern UA →
   woff2). Save as `aose/web/static/fonts/<name>-variable.woff2`.
2. **Verify coverage before committing** (`fonttools` is in the venv):
   ```python
   from fontTools.ttLib import TTFont
   f = TTFont("aose/web/static/fonts/oswald-variable.woff2")
   cmap = f.getBestCmap()
   print(sum(1 for c in cmap if 32 <= c < 127))   # expect ~95 for full Latin ASCII
   print("fvar" in f)                               # True ⇒ variable
   ```
   A healthy Latin face has ~95 ASCII glyphs. Single digits ⇒ broken subset.
3. One weight-range `@font-face` for a variable font; per-weight `@font-face`
   only for genuinely distinct static files (different sizes/MD5s).

---

## 9. Checklist for new sheet UI

- [ ] Tokens only (no raw hex except `#f7f5ed` reversed-on-ink).
- [ ] Display font UPPERCASE+tracked for labels; Bitter for prose; lining/tabular nums for numbers.
- [ ] Wrapped in a `.group` with a `.bar`; long content in `.gbody.scroll` + `max-height`.
- [ ] Info-bearing rows are clickable → detail modal via `data-modal`/`data-title`/`data-text`.
- [ ] New overlay: `data-*` trigger + `.ov-head`(with `data-close`) + `.ov-body`; real form `action`; closed-state `pointer-events:none` if always-present.
- [ ] Caster/optional content gated on the view model (no empty bars).
- [ ] Shared partial additions gated so the wizard still shows Carried + Shop.
- [ ] `@media print` still degrades; `GET /character/<id>` is 200; web tests updated.
- [ ] One overlay open at a time; Esc/scrim/× all dismiss; no console errors.
```
