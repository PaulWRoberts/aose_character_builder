# Interactive Wizard Rolls & Class-Setup Consolidation — Design

**Date:** 2026-06-10
**Branch:** `feat/interactive-wizard-rolls`
**Status:** Approved (brainstorming) — ready to plan

## Problem

Two of the wizard's random outcomes populate themselves silently instead of
being rolled by the player:

* **Feature choices** (CC3 roll tables: mutoid mutations, draconic bloodline,
  fiendish gifts/appearance) auto-roll on the first GET of Class Setup when
  Strict Mode is on.
* **Secondary skill** auto-rolls on the first GET of Identity, in every mode.

Gold, HP, and ability scores already require a deliberate "Roll" press (even in
Strict Mode). The player wants the rolled features and secondary skill to behave
the same way — *the dice are theirs to throw*.

Two adjacent friction points came up while scoping and are folded in:

* The Class Setup page is several independent `<form>`s, so the player must click
  **Save proficiencies**, **Save spells**, and **Save features** *before* the
  separate **Next** button will advance. Four clicks where one should do.
* Spells, proficiencies, and languages each have exactly one valid number of
  selections, and the front end knows it — yet the player can over-click and only
  finds out when the server rejects the submit.

## Goals

1. Rolled features and the secondary skill require a **Roll** button press before
   they exist — even in Strict Mode — mirroring HP/gold/abilities exactly.
2. Class Setup becomes a **single save-and-advance**: the "Next" button saves
   every selection section at once; the per-section Save buttons disappear.
3. Selection sections **cap client-side** so the player physically cannot
   over-select.

## Non-goals

* No data-shape change. The draft still stores `feature_choices`
  (`dict[group_id, list[option_id]]`) and `secondary_skill` (`list[str]`); the
  saved `CharacterSpec` is untouched. Review/finalize/sheet need no changes.
* No change to the abilities/HP/gold roll flows themselves.
* No new optional rule. This is creation-flow UX, governed by the existing
  `strict_mode` flag.

## Behaviour model — mirror HP/gold

A rolled value is **absent until the player presses its Roll button**. After the
roll:

* **Strict Mode** → locked. No re-roll, no manual edit.
* **Non-strict** → re-roll allowed, *plus* the existing manual override (pick
  mutations via checkboxes / choose a specific secondary skill from the selector).

The player cannot advance past the step until every applicable roll is made.

## Part 1 — Secondary skill (Identity step)

### Routes & handlers

* `get_identity` **stops auto-rolling**. It no longer writes `secondary_skill` on
  first visit. New context flag `skill_rolled = "secondary_skill" in draft`.
* New route **`POST /{id}/identity/skill-roll`** (replaces `skill-reroll`):
  * Rolls the skill via `_roll_skill`.
  * Preserves any `name` / `alignment` / `language` fields already submitted on
    the page, so a half-filled Identity form is not lost (the current
    `skill-reroll` handler already does this — carry it over).
  * **Strict:** refuse if `secondary_skill` already present (first roll only).
  * **Non-strict:** always allowed (first roll *and* re-roll).
* `post_identity` now **requires** a rolled skill when the rule is on, in *both*
  modes — raise `HTTPException(400, "Roll your secondary skill first.")` if
  absent. Drop the Strict `setdefault("secondary_skill", [])` shortcut that
  currently lets an un-rolled draft through.

### Template (`identity.html`)

* **Unrolled** → prompt + a **Roll skill** button (its own sub-form posting to
  `skill-roll`, `formnovalidate` so the empty name field doesn't block it).
* **Rolled + Strict** → locked display (today's look).
* **Rolled + non-strict** → rolled value + **Re-roll** button + "or choose a
  skill" selector (today's look).

`_identity_complete` already requires `secondary_skill`; with auto-roll gone it
now correctly reflects that a roll must have happened.

## Part 2 — Feature choices (Class Setup) — per-table rolls

### Routes & handlers

* Remove the Strict auto-roll block from `_feature_choices_context` and the
  follow-up `save_draft` in `get_class_setup`.
* New route **`POST /{id}/feature-choices/roll`** with a `group_id` field:
  * Rolls just that one group via `roll_choice`, merges the result into
    `draft["feature_choices"]`, saves.
  * **Strict:** refuse a `group_id` already present (locked once rolled).
  * **Non-strict:** re-roll allowed.
  * Validate `group_id` is an active group for this draft.
* `post_feature_choices` (manual override, **non-strict only** — keep its Strict
  rejection) changes from *require-all-groups* to **merge**: validate and update
  only the groups present in the submitted form, leaving un-submitted groups'
  entries intact. (Under consolidation this logic is invoked by the unified
  advance handler — see Part 3 — rather than a standalone Save button.)

### Completion

Retire the `feature_choices_done` boolean entirely. Completion is computed:

```python
def _feature_choices_complete(draft, data) -> bool:
    groups = _active_choice_groups(draft, data)
    chosen = draft.get("feature_choices", {})
    return all(g.id in chosen for g in groups)
```

`_class_setup_complete` uses this in place of the
`_has_feature_choices`/`feature_choices_done` check. Remove `feature_choices_done`
from the `_clear_after_*` helpers (the key no longer exists; `feature_choices` and
`_has_feature_choices` are still cleared).

### Template (`class_setup.html`, Features section)

Each group renders independently:

* **Strict:** **Roll `<die>`** button when unrolled → locked result display when
  rolled.
* **Non-strict:** **Roll / Re-roll** button always; once rolled, *also* render the
  editable, pre-checked override checkboxes inside the consolidated form
  (Part 3).

## Part 3 — Class Setup: single save-and-advance

### The consolidation

The selection sections — **proficiencies**, **spells**, and (non-strict)
**feature overrides** — merge into one `<form>` whose submit *is* the
**Next: Identity →** button. The per-section **Save proficiencies / Save spells /
Save features / Confirm <class> spells** buttons are removed.

A new consolidated handler (extend `post_hp`, the existing class-setup advance
route, or add `POST /{id}/class_setup`) does, in order:

1. If `weapon_proficiency` rule on: validate & save proficiencies (reuse the
   `post_proficiencies` body).
2. If a caster casts at L1: validate & save spellbooks; set the books and mark
   spells resolved (reuse the `post_spells` body, including the divine
   "knows everything, empty book" path — no button needed now).
3. If non-strict and feature groups exist: merge-validate & save the feature
   overrides (reuse the merged `post_feature_choices` body).
4. On **any** validation failure: re-render `class_setup.html` with an inline
   error message for the offending section, **preserving the other sections'**
   submitted input (and all immediate-saved rolls). Do not advance.
5. On success: `save_draft` and redirect via `_next_incomplete_step`.

Roll buttons (HP, per-feature-table) remain their own little forms that POST and
re-render Class Setup — a roll is a mutate-and-re-render action.

### Revised completion / advance gating

Because selections are now saved *by* the Next click, "ready to advance" can no
longer depend on already-saved selection state. The gate splits:

* **Server-side** (renders **Next** with `disabled` until met): HP rolled **and**
  every feature table rolled — the immediate-save roll actions. Captured by an
  updated `rolls_ready` flag (HP done + `_feature_choices_complete`).
* **Client-side** (JS keeps **Next** disabled until met): spell counts exact,
  proficiency slots exact, languages within cap.
* **Server re-validates** all sections in the consolidated handler as the
  backstop, so a bypassed client gate produces an inline error rather than bad
  data.

`spells_done` as a *gate flag* is retired in favour of validating-on-advance;
`_class_setup_complete` is recast around `rolls_ready` + (server-side) the
selection validation that the advance handler performs.

## Part 4 — Client-side selection caps

The front end enforces the known valid count so over-clicking is impossible:

* **Spells** — already disables unchecked boxes at exactly N per caster, and
  disables submit until N. Behaviour preserved; the submit-disable now feeds the
  unified Next-enable logic instead of a per-form button.
* **Proficiencies** — disable further selection once spent slots reach `required`,
  accounting for **specialisation costing 2** (a specialise box implies its
  weapon box; disable an unchecked specialise box when it would push spent over
  `required`). Today it only shows a counter and permits over-click.
* **Languages** (Identity) — disable additional boxes once the
  `language_slots` allowance is reached. Fewer is still allowed (max, not exact),
  so no minimum gate.

All caps are progressive-enhancement on top of authoritative server validation.

## Files touched

| File | Change |
|---|---|
| `aose/web/wizard.py` | New `skill-roll` + `feature-choices/roll` routes; consolidated class-setup advance handler; `_feature_choices_complete`; remove auto-rolls, `feature_choices_done`, per-section save semantics; revised gating |
| `aose/web/templates/wizard/identity.html` | Roll-skill button + states; language cap JS |
| `aose/web/templates/wizard/class_setup.html` | Per-table feature Roll buttons; single consolidated form / Next; remove per-section Save buttons; proficiency cap JS; wire Next-enable JS |
| `tests/test_wizard_feature_choices.py` | Rewrite to roll-first + per-table routes + lock/override |
| `tests/test_wizard_identity.py`, `tests/test_secondary_skills.py` | Rewrite wizard portions to roll-first skill; advance gate |
| `tests/` (new/extended) | Consolidated advance: success + per-section validation error preserving other input; caps where testable server-side |
| `docs/ARCHITECTURE.md` | Update Wizard / Class Setup / feature-choices / secondary-skill notes |
| `docs/CHANGELOG.md` | One-line row |

## Risks

* **The consolidated handler is the invasive part.** Merging three validators with
  partial-input-preserving re-render is where regressions will hide — cover the
  success path and each section's failure path explicitly.
* **Gate split correctness.** If `rolls_ready` is too lax, Next is clickable before
  HP/features are rolled and the player hits a server error; if too strict, they
  can't advance. Test both immediate-save rolls gate the button.
* **Existing tests encode the old auto-roll contract** (e.g.
  `test_wizard_feature_choices` asserts `feature_choices_done is True`,
  `test_wizard_identity` asserts a skill on first GET). These are rewritten, not
  patched around.
