# Individual Initiative (optional rule) — design

**Date:** 2026-06-10
**Status:** approved (brainstorming)

## Summary

Implement AOSE's optional **individual initiative** rule. The app does not
simulate combat, so the sole behaviour is: when the rule is active, the
character sheet's Combat box shows the player's **initiative modifier** — the
DEX-derived modifier plus any racial/class bonuses — with a clickable breakdown
consistent with the AC / THAC0 boxes.

### Rule text (AOSE p222)

> Instead of an initiative roll per side, a roll may be made for each individual
> involved in a battle, modified by DEX. The referee may determine an initiative
> modifier for monsters that are very fast or slow, instead of applying a DEX
> modifier.

### DEX → initiative modifier table

| DEX | Modifier |
|---|---|
| 3 | −2 |
| 4–8 | −1 |
| 9–12 | 0 |
| 13–17 | +1 |
| 18 | +2 |

This is the same data already encoded (as display strings) in `_DEX_INIT` in
`aose/engine/ability_mods.py`.

### Racial / class bonuses (the complete set)

- **Halfling (race):** +1 to initiative rolls — *only* under individual
  initiative.
- **Halfling (race-as-class):** +1 — *only* under individual initiative.
- **Human (race):** Decisiveness. +1 to initiative rolls under individual
  initiative, **and** wins tied initiative even without the optional rule.

There are no others.

## Design

### 1. Rule flag

Add `individual_initiative: bool = False` to `RuleSet`
(`aose/models/ruleset.py`).

Surface it as a **Combat**-group toggle in the settings/wizard rules form:
- `RULE_GROUPS` (Combat group), `RULE_LABELS`, and `IMPLEMENTED_RULES` in
  `aose/web/settings_routes.py`.
- `OPTIONAL_RULE_LABELS` in `aose/sheet/view.py`, so it lists in the sheet's
  "enabled optional rules" display.

No cascading clear is needed in `_apply_rule_changes` (`wizard.py`): toggling the
rule touches no stored draft data — it only gates a display. It does not gate a
wizard step.

### 2. The number — single-source DEX table + engine

**One table, one place.** The DEX→initiative values are the single source of
truth; the display strings are derived from them, not stored separately.

In `aose/engine/ability_mods.py`:
- Replace the hand-authored display map `_DEX_INIT = {3: "−2", …}` with a numeric
  source `_DEX_INIT_VALUES = {3: -2, 4: -1, 9: 0, 13: 1, 18: 2}`.
- Derive the display strings from it once (negative → `−n` with U+2212, zero →
  `None`, positive → `+n`) so `ability_table_row`'s Initiative column is
  unchanged in output.
- Add `initiative_modifier(score: int) -> int` — banded lookup over
  `_DEX_INIT_VALUES` (greatest key ≤ score; clamps below 3 and above 18, same
  banding semantics as the existing reference-table logic).

New module **`aose/engine/initiative.py`** (cycle-free: imports `ability_mods`,
`magic` for `effective_abilities`, and `features` for the modifier list — none of
those import `initiative`):

```python
class InitiativeLine(BaseModel):
    source: str
    bonus: int
    conditional: bool
    note: str

class InitiativeDetail(BaseModel):
    base: int                  # DEX initiative modifier
    total: int
    lines: list[InitiativeLine]
    has_conditional: bool

def initiative_detail(spec, data) -> InitiativeDetail: ...
```

`base` = `initiative_modifier(effective DEX)`. The lines list starts with the
DEX line, then one line per modifier targeting `initiative` (see §3). `total` =
base + sum of those bonuses. This mirrors `armor_class_detail` /
`attack_modifiers_detail`.

### 3. Feature bonuses — data, not code

Per the project rule that class/race bonuses are `GrantedModifier` data (no
engine module references a class/race id), introduce a new modifier **target
`initiative`**:
- Document it in the `target` grammar in `aose/models/modifier.py`.
- It is inert for every existing derivation (AC, saves, attacks, etc. ignore
  unknown targets), so adding it changes nothing elsewhere.

Add `granted_modifiers: [{target: initiative, op: add, value: 1}]` to:
- `data/races/halfling.yaml` → `initiative_bonus_optional_rule`
- `data/classes/halfling.yaml` → `initiative_bonus_optional_rule`
- `data/races/human.yaml` → `decisiveness`

The initiative engine sums all `initiative`-targeted modifiers, but
`initiative_detail` is only ever read when the rule is active (the box is hidden
otherwise). So the human +1 correctly counts only under individual initiative,
even though the modifier carries no special condition.

### 4. Feature visibility gating

Add `mechanical.requires_rule: individual_initiative` to the **two halfling**
initiative features (race + race-as-class). Introduce a generic, reusable rule:
a feature whose `mechanical.requires_rule` names a `RuleSet` flag is hidden from
the sheet's feature lists when that flag is off.

- `_race_features` / `_class_features` in `view.py` share a small
  `_feature_visible(feat, ruleset)` filter.
- Human's **Decisiveness** has *no* `requires_rule` — it keeps the tie-break
  benefit regardless of the optional rule, so it always shows; its +1 simply
  goes dark when the rule is off (the box isn't rendered).

### 5. Sheet UI

`CharacterSheet` (`view.py`) gains:
- `individual_initiative: bool`
- `initiative_modifier: int`
- `initiative_lines: list[SheetAttackLine]` (reuse the existing
  source/bonus/conditional/note line shape rather than adding a new model)
- `initiative_has_conditional: bool`

`build_sheet` populates these from `initiative_detail` (DEX line + feature
lines), gated so the values are computed regardless but rendered only when the
rule is on.

In `aose/web/templates/sheet.html`, the `combat-top` block gains an **INIT**
field, wrapped in `{% if sheet.individual_initiative %}`. Per the approved
mockup: HP and INIT sit together top-left, THAC0 below them, AC remains the
large box on the right. The INIT field is clickable → a new `modal-init`
breakdown listing the DEX line, each feature line, and the total (same star
treatment for conditional lines as AC/attack). Mirror the field + modal in
`sheet_print.html`.

Lay out `combat-top` to match the mockup; consult `docs/STYLE-GUIDE.md` and
`aose/web/static/sheet.css` for the OSR-zine tokens/components before touching
CSS.

## Testing

- `ability_mods.initiative_modifier` — full table incl. below-3 and above-18
  clamping; and that the derived `_DEX_INIT` display strings are unchanged
  (`ability_table_row` Initiative column regression).
- `initiative_detail` — DEX-only character; +1 halfling race; +1 human;
  halfling race-as-class +1; correct `total` and line sources.
- Feature visibility — halfling initiative feature hidden when rule off, shown
  when on; human Decisiveness shown in both states.
- Sheet — INIT box absent when rule off, present (with breakdown) when on.
- Settings — `individual_initiative` in `RULE_GROUPS` + `IMPLEMENTED_RULES` (no
  `pending` badge regression); form round-trips the flag.

## Out of scope

- Any combat simulation / initiative rolling. Display only.
- Monster initiative modifiers (referee-side, not a PC concern).
