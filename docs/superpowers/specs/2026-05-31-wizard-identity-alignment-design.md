# Wizard Overhaul — Slice 6a: Identity Page & Alignment Filtering

**Date:** 2026-05-31
**Status:** Design approved, pending written-spec review

## Context

Slice 6 of the wizard overhaul was split into **6a (Identity page + alignment
filtering)** and **6b (languages subsystem)**. This is 6a. It implements the
non-language parts of the target spec's **P7 — Identity & Background**:
consolidate name + alignment + secondary skill onto one page (placed after
Class Setup), and build the alignment filtering the spec calls for.

## Goal

1. Add typed class alignment restrictions and filter/validate alignment against
   the selected class(es).
2. Consolidate **name + alignment + secondary skill** onto one "Identity &
   Background" page, moving `name` off the abilities step.
3. Reorder the flow so Identity comes after Class Setup (matching P7-after-P6).

(Languages — native, alignment language, INT-based additional — are **Slice
6b**. The Identity page built here is where 6b will later add the language
section.)

## Findings

- Alignment restrictions exist today only as **feature prose**: paladin "must be
  lawful", druid "must be neutral", ranger "lawful or neutral", assassin "may
  not be lawful". Cleric/bard/drow ("faithful to their alignment"), knight
  ("same as liege"), and thief carry **no hard creation-time restriction**.
- `CharacterSpec` already has `alignment` and `secondary_skill`; **no model
  change** is needed for those.
- `name` is currently collected on the abilities step and is also that step's
  completion marker in `_next_incomplete_step`.

## Design

### 1. Class alignment data

**`aose/models/character_class.py`** — add:

```python
allowed_alignments: list[Literal["law", "neutral", "chaos"]] = Field(default_factory=list)
```

Empty = no restriction (any of the three). Populate:

| Class | allowed_alignments |
|---|---|
| paladin | `[law]` |
| druid | `[neutral]` |
| ranger | `[law, neutral]` |
| assassin | `[neutral, chaos]` |
| all others | `[]` (unrestricted) |

Keep each class's descriptive `alignment` feature text for the sheet; only the
enforcement moves to the typed field.

### 2. Engine helper (pure)

New `aose/engine/alignment.py` (cycle-free; imports models only):

```python
ALL = {"law", "neutral", "chaos"}

def allowed_alignments(classes) -> set[str]:
    """Intersection of each class's allowed alignments; an empty
    allowed_alignments list on a class means 'all three'. Result may be empty
    (an alignment-incompatible class combination)."""
```

### 3. Alignment filtering at the class step

Per the resolved decision, **reject incompatible combos proactively**.
`post_class` (multi-class path): after validating the picked class set, compute
`allowed_alignments(classes)`; if it is **empty**, reject with 400
("These classes have incompatible alignment requirements"). This prevents the
player ever reaching an unsatisfiable Identity page. (Single-class can never be
empty.)

### 4. The `identity` step (consolidation + reorder)

Replace the standalone `alignment` and `skill` steps with one **`identity`**
step (label "Identity & Background"), and move `name` collection into it.

- **`_wizard_steps`:** remove `alignment` and `skill`; add `identity` **after
  `class_setup`, before `equipment`**. Net flow:
  `rules → abilities → [race] → class → adjust → class_setup → identity →
  equipment → review` (matches P1–P9 ordering).
- **Abilities step:** `name` field removed from `abilities.html`; `post_abilities`
  no longer requires name. The step's completion marker becomes a new
  `draft["abilities_confirmed"] = True` set when the player clicks Continue.
  `_next_incomplete_step` checks `abilities_confirmed` instead of `name`.
- **Identity page** (`GET/POST /{draft_id}/identity`): a single form with
  - **Name** (text, required),
  - **Alignment** (radio, options filtered to `allowed_alignments(classes)`;
    selecting one outside the set → 400),
  - **Secondary skill** section, shown only when the `secondary_skills` rule is
    on — re-homing the existing auto-roll + reroll + dropdown behavior unchanged
    (reroll via a sub-action `POST /{draft_id}/identity/skill-reroll`).
  - A **Continue** that validates and advances to `equipment`.
- **Completion:** `identity` is incomplete until `name` and `alignment` are set
  (and `secondary_skill`, when the rule is on).

### 5. Downstream clears

`_clear_after_class`: also clear `alignment` (a class change can invalidate the
previously-chosen alignment). **Keep `name` and `secondary_skill`** (neither
depends on class). Race/abilities clears already cascade through class.

### 6. Tests

- `CharClass.allowed_alignments` loads with the table above; others empty.
- `allowed_alignments`: paladin → {law}; fighter → {law,neutral,chaos};
  paladin+fighter → {law}; ranger+assassin → {neutral}; paladin+assassin → {} .
- Class step rejects adding assassin to a paladin pick (and vice versa).
- Identity page filters alignment options to the intersection; posting an
  out-of-set alignment → 400; name required; skill section gated by the rule.
- Flow: abilities step completes without a name (`abilities_confirmed`); the
  standalone `alignment`/`skill` steps are gone; `identity` sits after
  `class_setup`; breadcrumb reflects the new order.
- Class change clears `alignment` but preserves `name` and `secondary_skill`.

## Risks / notes

- Moving `name` changes the abilities-step completion contract; update any test
  that asserted name on the abilities POST.
- Knight's "same alignment as liege" is a roleplay constraint, not a creation
  filter — modelled as unrestricted (empty list), intentionally.
- No migration (nothing deployed).
