# Wizard detail modals + trimmed cards — design

**Date:** 2026-06-16
**Status:** Approved (design); implementation pending
**Scope:** Presentation of spells, classes, and races on the character-creation
wizard. No engine or storage changes.

## Problem

The wizard's selection cards over- and under-present:

- **Spell cards** jam the entire spell description (rendered markdown) into the
  card body — unreadable and visually broken.
- **Class cards** are good as-is.
- **Race cards** show too much: a static *Movement* line (identical for nearly
  every race), a languages **count** that conveys nothing, and ability changes
  spelled out as `rolled → effective` when the delta alone (`DEX +1`) is what
  matters.

There is also no way to read a class/race/spell's full rules text the way the
printed book presents it. Selection happens by clicking a card, with no chance
to review the entry first.

## Goals

1. Trim the cards to the minimum useful at-a-glance info.
2. Let the player read the **full book entry** — requirements block + every
   feature/rules section — rendered in the app's **zine** styling.
3. Make selection deliberate: review, then commit.

## Non-goals

- No level-progression / saves grid in the class modal (decided: "prose +
  features only"). Races have no such table anyway.
- No engine, model, or persistence changes. Selection still posts the same
  form fields on **Next** as today.
- No changes to the shared equipment partial or its "Carried + Shop only"
  wizard behaviour.

## Design language

The wizard runs on the **legacy site chrome**, but these new surfaces use the
**zine** design language (per the user's request "as if from the book … in our
zine styling"). The zine *tokens* (`--ink`/`--paper`/`--display`/`--body`/…)
are already global because `base.html` loads `sheet.css` on every page. The new
modal/expander/collapse rules and the selection controller live in dedicated,
**wizard-only** files so neither design language bleeds into the other:

- `aose/web/static/wizard_cards.css`
- `aose/web/static/wizard_cards.js`

`base.html` gains `{% block head %}` and `{% block scripts %}`; `wizard.html`
fills them. (Chosen over extending `sheet.css`, which the style guide keeps
strictly partitioned between the two design languages.)

## Component 1 — card trimming

| Card | Change |
|---|---|
| **Spell** | Remove the jammed `description`. Show: name, a small `L{level}` tag, and a `range / duration` micro-line. Full text moves to the expander (Component 5). |
| **Class** | No change (HD, Prime requisite, race max-level, unmet-requirement warnings). |
| **Race** | Remove the *Movement* line and the languages-count line. Render ability changes as deltas only — `DEX +1, CON −1` — dropping `rolled → effective`. Keep Requires + Infravision. |

Race view-model note: the `ability_changes` entries already carry `name` and
`delta`; the template simply stops rendering `rolled`/`effective`. No backend
change required for the race trim. `base_movement` and `languages` stay in the
view model (harmless) but are no longer rendered.

## Component 2 — shared book renderer (`_book_entry.html`)

A single Jinja macro `book_entry(kind, header_stats, features, body_markdown)`
renders content "as from the book", reused by the race/class modal body **and**
the spell expander so all three are visually identical:

1. **Header stat block** — the green-box data from the book page:
   - *Class:* Requirements, Prime requisite, Hit Dice, Maximum level, Armour,
     Weapons, Alignment (allowed alignments / restriction).
   - *Race:* Requirements, Ability modifiers, Languages, Allowed classes (with
     per-class max levels where capped).
   - *Spell:* Level, Range, Duration, Reversible (+ reverse name).
2. **Feature sections** — each `feature` (off `CharClass.features` /
   `Race.features`) as a titled section: a zine `.bar`-style heading + the
   feature's markdown `text` rendered through the existing `| markdown` filter.
   Skill/chance tables already live inside that markdown, so they render for
   free.
3. **Spell body** — for spells there are no `features`; the macro renders the
   spell's `description` markdown (which includes the reversed-form prose, as in
   the *Light/Darkness* example).

Styling uses zine tokens only (`--ink` bars, `--body` prose, `.scroll` for
overflow). No raw hex beyond the documented `#f7f5ed` reversed-on-ink literal.

## Component 3 — race / single-class interaction

- **Card click → modal.** One shared `.overlay.modal` shell (zine) with
  `.ov-head` (title + `data-close` ×) and `.ov-body`. The JS controller injects
  the clicked card's inline-hidden `book_entry` body and the card name as title.
  Dismiss via ×, scrim, or `Esc`. The shell carries the closed-state
  `pointer-events:none` discipline from the style guide §6.1.
- **Select.** A **Select** button in the modal sets the card's hidden `radio`
  and closes the modal. The grid then **collapses to the chosen card only**,
  which gains a **Clear** button. **Clear** restores the full grid (unsets the
  radio). Selection is client-side; the step's existing form still POSTs the
  radio value on **Next**.
- **Disabled cards.** Cards greyed for unmet ability requirements or race
  disallowance still open the modal **read-only**: the Select button is disabled
  and labelled with the reason (`Requires INT 9`, `Not available to Dwarf`).

### Modal body delivery — inline-hidden

Each card renders its `book_entry` body in a hidden container inside the card.
The controller moves/clones it into the shared shell on open. No fetch route,
no async/loading state; mirrors the sheet's server-rendered per-row modals. The
extra page weight is text-only markdown for ~40 classes / ~20 races and is
acceptable.

## Component 4 — multi-classing

Same modal + Select flow, but the grid does **not** collapse on each pick. Cards
stay visible (so more can be added) until the cap (`MAX_CLASSES` = 3) is
reached, at which point unpicked cards hide. Each picked card carries its own
**Clear**. The underlying inputs remain checkboxes; the existing
"picked X of N" counter / disable-at-cap logic is reused, now driven through the
modal's Select instead of a raw card-click.

## Component 5 — spells & cantrips

No modal. Each spell/cantrip card gains:

- An inline **expander**: clicking the card body toggles an in-card panel that
  renders the spell via `book_entry` (Component 2). **Multiple expanders may be
  open at once.**
- An embedded **Learn** button that performs selection. **Learn** toggles to
  **Forget** (learned state on the card). Once `required` spells are learned,
  the remaining unlearned cards' Learn buttons **disable** until one is
  forgotten — preserving the existing `data-required` counter and `csValidate`
  gating of the Next button.
- **Divine ("know-all") casters** render read-only expanders with **no Learn
  button** (nothing to choose), replacing today's plain `<li>` list.

Cantrips use the identical pattern with their own `cantrip_{class_id}` inputs
and `cantrip_required` cap.

## Component 6 — plumbing & view-model touch-ups

- `base.html`: add `{% block head %}` (after the `sheet.css` link) and
  `{% block scripts %}` (before `</body>`).
- `wizard.html`: load `wizard_cards.css` / `wizard_cards.js`; add the shared
  `.overlay.modal` shell once.
- `wizard.py` `_caster_entries`: enrich each candidate/cantrip dict with
  `range`, `duration`, `reversible`, `reverse_name` (off the `Spell` model) so
  the spell `book_entry` matches the book.
- Race/class view models already expose `features` indirectly — the templates
  read the model's features via the macro; if the current context only passes a
  thin dict, extend it to include `features` and the header-stat fields. (The
  class/race getters build plain dicts today; add the fields the macro needs.)
- `wizard_cards.js` — one controller handling: overlay open/close, Select/Clear
  (single + collapse), multiclass cap, spell expand toggle, and Learn toggle.

## Testing

- `tests/test_wizard.py`: update assertions for the new markup — trimmed race
  card (no Movement / languages-count, delta-only ability changes), spell cards
  without inline description, presence of modal shell + `book_entry` bodies,
  Learn buttons on spell cards.
- Confirm the wizard equipment step still renders **Carried + Shop only**
  (unchanged; this design doesn't touch the shared partial).
- `GET` for the race, class, and class_setup (spells) steps returns 200 with the
  new templates.

## Invariants honoured

- Zine tokens only; closed-overlay `pointer-events:none`; one overlay open at a
  time; ×/scrim/Esc all dismiss (style guide §5, §6).
- No `feTurbulence` / `mix-blend-mode`.
- Legacy site chrome untouched; new zine rules isolated to wizard-only files.
- No migrations / model changes; selection still posts the same fields on Next.
