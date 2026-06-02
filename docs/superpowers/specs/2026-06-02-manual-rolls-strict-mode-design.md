# Manual Rolls + Strict Mode — Design

**Date:** 2026-06-02
**Status:** Approved (pending spec review)

## Problem

Ability scores and starting gold are rolled *automatically* the moment the
player reaches their wizard step, then silently locked. HP, by contrast, is a
deliberate button press ("Roll HP") that locks after one roll. The player never
*chooses* to roll abilities or gold — it just happens.

We want all three creation rolls to feel like deliberate, player-driven
actions, so the player feels in control even though the outcome is functionally
identical. We also want an optional rule that relaxes the one-roll lock into
free re-rolls, and we want the Human "Blessed" double-roll to actually *show*
both results instead of silently discarding the loser.

## Goals

1. **Abilities** require pressing a Roll button for the first roll; locked
   afterwards — exactly like HP today. A *hopeless* result re-enables the
   button (see Hopeless rule below).
2. **Starting gold** requires pressing a Roll button for the first roll; locked
   afterwards.
3. **Strict Mode** — a new optional rule, **default on**. When off, abilities,
   HP, and gold may be freely re-rolled.
4. **Blessed HP** shows *both* rolled sets with their totals and **bolds the
   higher**, instead of keeping only the winner.

Non-goals: the secondary-skill roll is untouched (keeps its existing always-on
reroll button, unaffected by Strict Mode). No changes to how any rolled value
is *computed*.

## Hopeless rule (abilities re-roll under Strict Mode)

Even with Strict Mode on, an unplayable ability set may be re-rolled. The
trigger is the existing `ability_warnings` output:

- `subpar` — all six scores ≤ 8 (the "may start over" warning), **or**
- `rock_bottom` — any single score is exactly 3.

When **either** is present, the abilities Roll button stays active. Both
warnings already render on the page; the `rock_bottom` note's wording is updated
to say a re-roll is allowed (today it only says "extremely low"). Outside Strict
Mode the button is always active, so the hopeless rule is moot there.

## Design

### 1. `RuleSet.strict_mode`

Add `strict_mode: bool = True` to `aose/models/ruleset.py`. Wire it like every
other optional rule:

- `RULE_LABELS["strict_mode"] = "Strict Mode"`
- Add to `IMPLEMENTED_RULES` (so the settings page never shows a "pending"
  badge — guarded by a regression test).
- Add to a `RULE_GROUPS` section (Character Options) with the description:
  *"Ability scores, hit points, and starting gold are locked after a single
  roll (a hopeless ability set may always be re-rolled). Turn off to allow free
  re-rolls."*

`parse_ruleset_from_form` already derives bools as `field in form`, which is
correct checkbox semantics: rendered checked by default (because the model
default is `True`), unchecked-and-submitted → `False`. No special handling and
no gating against other rules.

`_apply_rule_changes` needs **no** cascade for `strict_mode` — toggling it only
changes button availability, never invalidates a chosen value.

### 2. Abilities — manual roll

**Draft lifecycle change.** `/wizard/new` no longer pre-rolls abilities; it
seeds only the ruleset. No new "rules done" flag is needed — the only change is
to route an abilities-less draft to the abilities step:

- `_next_incomplete_step`: the first check becomes
  `if "abilities" not in draft or not draft.get("abilities_confirmed"): return "abilities"`
  (was: abilities-missing → `"rules"`). `/wizard/new` still redirects to
  `/rules`, and `post_rules` still redirects forward via `_next_incomplete_step`,
  so the user starts on rules and advances to abilities to roll.
- `_apply_rule_changes`: drop the "abilities missing → re-seed + clear" safety
  block; replace with an early `return` when abilities aren't rolled yet (no
  downstream exists to clear). The remaining rule-change cascades are unchanged.
- `_seed_draft_abilities` is no longer called at creation; it is invoked by the
  new roll route.

No draft migration is provided (single-user dev app — see memory
"No migrations needed"). In-flight drafts created before this change may need to
be restarted.

**Abilities page (`get_abilities` + `wizard/abilities.html`).**

- New context flags: `abilities_rolled` (`"abilities" in draft`) and
  `can_reroll`.
- `can_reroll = (not strict_mode) or subpar or bool(rock_bottom)`.
- Not rolled → render a Roll button (`POST .../abilities/roll`) and explanatory
  text; hide the score table and Continue.
- Rolled → render the score table + warnings + Continue, plus the Roll button
  again **iff** `can_reroll` (labelled "Roll again").

**New route `POST /{draft_id}/abilities/roll`.**

- If `"abilities" in draft` and not `can_reroll` → `HTTPException(400, ...)`
  ("Ability scores are already rolled and locked."), mirroring `post_hp_roll`.
- Otherwise: `_clear_after_abilities(draft)` (clears race/class/etc. for the
  back-nav-and-reroll case), `_seed_draft_abilities(draft)`, and clear
  `abilities_confirmed`. Save, redirect to `/abilities`.

**`post_abilities` (Continue).** Guard: if abilities missing, redirect back to
`/abilities`; otherwise set `abilities_confirmed = True` as today.

### 3. Gold — manual roll

**`get_equipment`.** Remove the auto-roll block (`if "gold" not in draft: …`).
The page renders the shop only once gold exists; before that it shows a Roll
button.

- `wizard/equipment.html`: `{% if gold_rolled %}{% include "_equipment_ui.html"
  %}{% else %}<roll button + blurb>{% endif %}`, where `gold_rolled = "gold" in
  draft`. The "Next: Review" button only shows after gold is rolled (review is
  already gated by `_next_incomplete_step` requiring `gold`).
- A **Reroll gold** button shows when `gold_rolled and not gold_locked`
  (non-strict, pre-purchase).

**New route `POST /{draft_id}/equipment/roll-gold`.**

- If `gold_locked` → `HTTPException(400, ...)`.
- Roll `roll_starting_gold()`, `draft.setdefault("inventory", [])`, set
  `draft["gold"]`. Strict → `gold_locked = True` (locked immediately).
  Non-strict → `gold_locked = False` (first purchase locks it via existing
  buy logic). Save, redirect to `/equipment`.

`_equipment_context` already surfaces `gold` and `gold_locked`; the shared
`_equipment_ui.html` partial is unchanged (the roll/reroll buttons live in the
wizard-only `equipment.html`).

### 4. Blessed HP — show both sets

**Engine.** Add a helper to `aose/engine/dice.py` that returns *both* blessed
sets, e.g. `roll_blessed_hp_sets(hit_dice, *, min_die, rng) -> tuple[list[int],
list[int]]` (two complete sets, one die per class each). The existing
`roll_first_level_hp` keeps its current contract for the non-blessed path; the
HP route uses the new helper when blessed and picks the better set
(`sum(a) >= sum(b)` keeps `a`, matching today's tie behaviour).

**Draft state (draft-only, never persisted).** When blessed, the roll route
stores `draft["hp_blessed_sets"] = [set_a, set_b]` *in addition to* the existing
kept `hp_roll` / `hp_rolls`. This key is **display state on the draft only** —
`CharacterSpec` has no such field, so it is dropped when the character is
finalized and never reaches a saved character. Non-blessed rolls do not set it;
a re-roll overwrites it.

**`post_hp_roll`.** Honour Strict Mode: if `_has_hp(draft)` and
`strict_mode` → 400 (locked); otherwise roll (overwriting on re-roll). When
blessed, populate `hp_blessed_sets`; when not, leave it unset / pop it.

**`_hp_context` + `class_setup.html`.** When `hp_blessed_sets` is present, build
a `blessed_sets` structure: for each set, its per-class rolls and total, plus a
`kept` / `higher` flag. The template renders both sets and bolds the higher
total (ties bold the kept set). The HP section also gains a **Reroll HP** button
shown when `not strict_mode` (replacing the "locked" message in that case).

## Data shapes touched

- `RuleSet`: `+ strict_mode: bool = True`.
- Draft dict: `+ hp_blessed_sets: list[list[int]]` (draft-only display state).
  Abilities/gold keys unchanged in shape — only *when* they are written changes.
- `CharacterSpec`: **unchanged** (blessed sets never persist).

## Testing

- **Rule:** `strict_mode` defaults `True`; settings POST round-trips on/off;
  settings page shows no "pending" badge for it.
- **Abilities:** `/wizard/new` leaves abilities unset; roll route stores six
  scores; second roll under Strict (non-hopeless) → 400; reroll allowed when
  Strict-off, when `subpar`, and when any score is 3; reroll clears downstream
  + `abilities_confirmed`; Continue blocked until rolled.
- **Gold:** equipment GET no longer auto-rolls; roll route stores gold; Strict
  locks immediately; non-strict allows reroll until first purchase.
- **HP:** non-strict reroll allowed; Strict still locks (existing behaviour).
- **Blessed:** roll stores both sets; `_hp_context` exposes both totals with the
  higher flagged; tie keeps/bolds the first set; finalized character has no
  `hp_blessed_sets`.
- Update existing end-to-end wizard tests that assume auto-rolled abilities/gold
  (the main blast radius of this change).
