# AOSE Character Builder — agent notes

Python + FastAPI + Jinja2 character builder for Advanced Old-School Essentials.
Pydantic v2 models, YAML data, no JS framework. Local-only single-user app
(no auth model anywhere — every route mutates by URL).

## Running

```powershell
.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload
```

`uvicorn` bare won't work — the venv isn't auto-activated.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

The trailing PermissionError on `pytest-current` is a known Windows-tempdir
quirk in pytest 9; ignore it.

## Layout

| Path | What it holds |
|---|---|
| `aose/models/` | Pydantic v2 models (CharacterSpec, RuleSet, Race, CharClass, Item discriminated union, ProficiencyConfig) |
| `aose/data/loader.py` | `GameData.load(data_dir)` — single side-effecting entry; `items` is a flat dict keyed by id |
| `aose/engine/` | Pure derivations: `ability_mods`, `armor_class`, `attack_bonus`, `saves`, `hp`, `dice`, `proficiency`, `leveling`, `attacks`, `equip`, `shop`, `encumbrance` |
| `aose/sheet/view.py` | `build_sheet(spec, data) -> CharacterSheet` — assembles every derivation for the live sheet |
| `aose/characters/` | Persistence: `storage.py` (saved characters), `drafts.py` (in-progress), `settings.py` (global default RuleSet) |
| `aose/web/` | FastAPI routes (`routes.py`, `wizard.py`, `settings_routes.py`) + Jinja templates |
| `data/` | YAML game data: `races/`, `classes/`, `equipment/` (weapons, armor, adventuring_gear), `secondary_skills.yaml` |

## Wizard flow

Per-character ruleset gates which steps run:
`rules → abilities → [race] → class → alignment → [skill] → [proficiencies] → hp → equipment → review`

Steps in `[brackets]` are gated by an optional rule. `_wizard_steps(draft)`
builds the list per-draft from the snapshot ruleset. The breadcrumb shows
completed steps as back-navigation links.

## Storage shapes

- `CharacterSpec.equipped`: `dict[str, str]` — `armor` / `shield` slots
- `CharacterSpec.equipped_weapons`: `list[str]` — duplicates allowed
- `inventory`: `list[str]` — duplicates count toward inventory size
- A weapon is equippable when `equipped_weapons.count(id) < inventory.count(id)`

## Settings vs per-character ruleset

`/settings` (global, in `settings.json` at project root, gitignored) is the
*default* for new drafts. The wizard's first step `/rules` is a per-character
override. Changing a rule mid-wizard applies targeted downstream clears
(`_apply_rule_changes` in `wizard.py`).

## Optional rules currently wired

Every flag in `RuleSet` is integrated end-to-end. The settings page never
renders a "pending" badge — a regression test guards this.

## Current state (2026-05-27)

Last commit: `6e486a2 Stashed inventory + table-lookup encumbrance`.
Tree is clean; all 380 tests pass.

Key concepts now live:

- **Stashed inventory** — `CharacterSpec.stashed: list[str]` for items left
  off-person (no weight contribution). Sheet renders three inventory
  subsections: Equipped / Carried / Stashed.
- **Table-lookup encumbrance** — movement is *set* by `(armor_class, weight_band)`
  per the OSE Advanced table; armour no longer subtracts from a base.
  Demihuman rates scale from the 120'-base human row by `base / 120`,
  rounded down to 5'. See `aose/engine/encumbrance.py` for the table.
- Equipped items live inside `inventory` already — weight is counted once
  via the inventory list, not twice via `equipped` / `equipped_weapons`.

See `project_aose_builder.md` for the longer architectural narrative.
