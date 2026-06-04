# Optional Staves for spellcasters — design

**Date:** 2026-06-03
**Status:** Approved

## Problem

In AOSE, magic-users and illusionists may *not* wield a staff in combat under
the core rules. The book offers two optional rules — "Magic-Users and Staves"
and "Illusionists and Staves" — that permit it.

Today the builder gets this wrong: both `data/classes/magic_user.yaml` and
`data/classes/illusionist.yaml` list `staff` directly in `weapons_allowed` (with
a `# TODO: confirm optional staff rule` comment), so a staff is **always**
equippable for them. There is no toggle to gate it.

We want a **single** settings/rules toggle that lets any class which marks a
weapon as combat-optional (today: staff, on magic-user and illusionist) use that
weapon in combat (i.e. equip it). This is purely about the mundane `staff`
weapon's combat/equip gating — magic staves, rods, and wands are separate
`MagicItem` catalog entries and are already usable; they are untouched.

## Approach

Data-driven, mirroring the existing `weapons_allowed` resolution. A class flags
combat-optional weapons in a dedicated field; a single `RuleSet` flag unions
those weapons into the allowed set when on.

### Data model

- **`CharClass.optional_weapons_allowed: list[str]`** — new field,
  `default_factory=list`. Weapons usable in combat only when the optional-staves
  rule is on. Resolved through the same `_resolve_entries` path as
  `weapons_allowed` (a `list[str]`; no `"all"` form needed).
- **Data edits:**
  - `magic_user.yaml`, `illusionist.yaml`: remove `staff` (and the `# TODO`
    comment) from `weapons_allowed`; add `optional_weapons_allowed:\n  - staff`.
  - Net effect: a staff is **not** equippable for these classes by default —
    correcting today's always-allowed behavior — and becomes equippable only
    when the rule is on.
- **`RuleSet.optional_staves: bool = False`** — new flag.

### Engine

- `proficiency.allowed_weapon_ids(classes, data, ruleset=None)` gains an optional
  `ruleset` parameter. When `ruleset is not None and ruleset.optional_staves`, it
  unions each class's resolved `optional_weapons_allowed` into the result.
  - `ruleset=None`, or the flag off ⇒ today's behavior exactly (backward
    compatible).
  - Existing `"all"` fail-open and `_union` semantics are unchanged: a class
    whose `weapons_allowed == "all"` (e.g. fighter) stays `"all"`; an empty
    `optional_weapons_allowed` resolves to the empty set and adds nothing.
- This is the **only** engine change. Because both `equip()` enforcement and the
  `class_allowed` inventory-view flag (which drives the Equip button) consume the
  result of `allowed_weapon_ids`, gating flows to both automatically.

### Wiring

- Thread the per-character ruleset into the 6 `allowed_weapon_ids(classes, data)`
  call sites:
  - `aose/web/routes.py` (sheet view + equipment): pass `spec.ruleset`.
  - `aose/web/wizard.py` (equipment step + equip routes): pass the draft's
    snapshot ruleset.
- Register the rule as fully implemented (so the settings page renders no
  "pending" badge) in `aose/web/settings_routes.py`:
  - `RULE_LABELS["optional_staves"] = "Spellcasters and Staves"`
  - add `"optional_staves"` to `IMPLEMENTED_RULES`
  - add to `RULE_GROUPS` under **Combat**:
    `("optional_staves", "Magic-users and illusionists may wield a staff in combat.")`
  - `parse_ruleset_from_form` derives its boolean field set from `RULE_GROUPS`,
    so the settings page **and** the wizard `/rules` step are both wired with no
    form-parsing changes.

## Out of scope

- **Toggle-off / cascading clears.** Per the user: there is no workflow to toggle
  this after equipment (rules are chosen before the equipment step), and the app
  is not deployed, so no `_apply_rule_changes` clear and no migration handling for
  existing characters. If the rule is off while a staff happens to be equipped,
  the inventory view simply flags it as not class-allowed; equip state is left
  untouched.
- **Magic staves / rods / wands** — separate `MagicItem` entries, already usable.
- The descriptive `magic_users_and_staves_optional_rule` /
  `illusionists_and_staves_optional_rule` class **features** stay as-is (accurate
  sheet flavor text describing the optional rule).

## Testing

New tests:
- A magic-user (and illusionist) **cannot** equip a staff when
  `optional_staves` is off; **can** when it is on (via `equip()` and/or
  `allowed_weapon_ids`).
- `optional_weapons_allowed: [staff]` resolves to `{"staff"}` and is unioned in
  only when the rule is on.
- `staff` is absent from `allowed_weapon_ids` for these classes with the rule off.
- A class with no `optional_weapons_allowed` (e.g. cleric, fighter) is unaffected
  by the flag in either state.
- `allowed_weapon_ids(..., ruleset=None)` is byte-for-byte the old behavior.

Kept green:
- `tests/test_settings.py::test_no_pending_badges_when_all_rules_implemented`
  (new rule registered as implemented).
- Existing equip-enforcement (`tests/test_equip_enforcement.py`) and settings
  round-trip tests.
