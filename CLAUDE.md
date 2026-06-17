# AOSE Character Builder — agent notes

Python + FastAPI + Jinja2 character builder for Advanced Old-School Essentials.
Pydantic v2 models, YAML data, no JS framework. Local-only single-user by
default; opt-in hosted multi-user via `AOSE_AUTH=1` (GCIP Google sign-in,
per-user workspaces). Every route still mutates by URL.

**Doing any sheet/UI work?** Read `docs/STYLE-GUIDE.md` first — the OSR-zine
design system (tokens, components, overlay model) plus hard-won invariants
(closed-overlay `pointer-events`, variable-font self-hosting, `no-cache` static).

**Working on a subsystem?** Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) —
the living design of every subsystem (the modifier pipeline, magic items, spells,
encumbrance, etc.), where each lives, and its invariants. This file is just the
quick orientation. [`docs/CHANGELOG.md`](docs/CHANGELOG.md) is the dated landing
ledger; full per-feature designs are in `docs/superpowers/{specs,plans}/`.

**Landing a feature?** Keep the docs current, and keep them lean:
- Add a one-line row to the top of `docs/CHANGELOG.md` (date, feature, branch,
  spec/plan slug). Full prose belongs in the spec/plan, not here.
- Update the relevant subsystem section in `docs/ARCHITECTURE.md` in place (edit
  the existing topic — don't append a dated entry). Add a section only for a
  genuinely new subsystem.
- Touch `CLAUDE.md` only if orientation changed (a new top-level dir, a wizard
  step, a storage shape). Do **not** add per-feature "Current state" notes here —
  that is what bloated this file before.

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
| `aose/engine/` | Pure, cycle-free derivations: `ability_mods`, `armor_class`, `attack_bonus`, `saves`, `hp`, `dice`, `proficiency`, `leveling`, `attacks`, `equip`, `shop`, `encumbrance`, `magic`, `features`, `currency`, `valuables`, `ammo`, `enchant`, `spells`, `spell_sources`, `secondary_skills`, `sources`, `monster_stats`, `companions`, `quick_equipment`, `retainers` |
| `aose/sheet/view.py` | `build_sheet(spec, data) -> CharacterSheet` — assembles every derivation for the live sheet |
| `aose/characters/` | Persistence: `storage.py` (saved characters), `drafts.py` (in-progress), `settings.py` (global default RuleSet) |
| `aose/web/` | FastAPI routes (`routes.py`, `wizard.py`, `settings_routes.py`) + Jinja templates |
| `aose/web/auth/` | Auth package: `AuthConfig`, `WorkspaceAuthMiddleware`, `Whitelist`, verifier (Firebase+fake), workspace resolver, login/logout routes |
| `data/` | YAML game data: `races/`, `classes/`, `equipment/` (weapons, armor, adventuring_gear, ...), `spells/`, `spell_lists.yaml`, `enchantments.yaml`, `sources.yaml`, `languages.yaml`, `secondary_skills.yaml` |

The engine import DAG is roughly `models → loader → magic → features →
{armor_class, saves, attacks}`. Keep it acyclic. See `docs/ARCHITECTURE.md` for
the full picture.

## Wizard flow

Per-character ruleset gates which steps run:
`rules → abilities → [race] → class → alignment → [skill] → [proficiencies] → hp → [spells] → equipment → review`

Steps in `[brackets]` are gated by an optional rule (or, for `spells`, a cached
`draft["spellcasting"]` flag). `_wizard_steps(draft)` builds the list per-draft
from the snapshot ruleset. The breadcrumb shows completed steps as
back-navigation links (or a 🔒 when a roll has locked an earlier step).

## Storage shapes

- `CharacterSpec.equipped`: `dict[str, str]` — slots `armor`, `main_hand`, `off_hand`
  (`equipped_weapons: list[str]` retired; all held items go through named slots)
- `inventory`: `list[str]` — duplicates count toward inventory size
- Off-hand weapon requires `two_weapon_fighting` rule + `two_weapon_eligible` + passes
  `off_hand_eligible`; total hand cost (via `hand_cost`) ≤ 2
- Equipped items live *inside* `inventory` — weight is counted once
- `stashed`, `containers`, `magic_items`, `ammo`, `spell_sources`, gems/jewellery
  each have their own shapes — see `docs/ARCHITECTURE.md`
- `animals`: `list[AnimalInstance]` / `vehicles`: `list[VehicleInstance]` — per-instance
  roster entries; each is a storage carrier with its own load capacity, never counted toward
  PC encumbrance; `ContainerInstance.location` (`"person"|"animal"|"vehicle"`) + `location_id`
  puts a container on a carrier instead of on the PC
- `retainers`: `list[Retainer]` — each wraps a full `CharacterSpec` (the NPC) plus
  `id` (uuid4 hex), `loyalty: int`, `role: str`; `Retainer` is defined after `CharacterSpec`
  with `model_rebuild()` to resolve the forward reference; retainer spec's own `retainers`
  is always empty (no nesting)
- `feature_choices`: `dict[str, list[str]]` — group id → chosen option ids (CC3 pick/roll)
- `innate_uses`: `dict[str, int]` — daily-use ability id → uses spent today (reset on rest)
- `RuleSet.disabled_content`: `list[str]` — `"{source_id}:{category}"` keys for disabled
  content categories (`classes`, `equipment`, `magic_items`); Classic source never added;
  legacy `disabled_sources` is coerced to `disabled_content` at load time
- Per-user workspaces (auth-on): `users/<uid>/` at project root mirrors root `characters/`, `drafts/`, `settings.json`; keyed by GCIP uid; seeded with examples on first login. Auth off → global dirs unchanged.

## Settings vs per-character ruleset

`/settings` (global, in `settings.json` at project root, gitignored) is the
*default* for new drafts. The wizard's first step `/rules` is a per-character
override. Changing a rule mid-wizard applies targeted downstream clears
(`_apply_rule_changes` in `wizard.py`). Every flag in `RuleSet` is integrated
end-to-end; the settings page never renders a "pending" badge (a regression
test guards this).

## Conventions

- **No migrations** — the app isn't deployed; data-shape changes don't need
  backward-compat (model validators that coerce legacy saves are a courtesy, not
  a requirement).
- **Verify rules against the Rules** before encoding AOSE mechanics (ensure you
  have the PDF or exerpts from the PDF in Markdown - if rules are being added
  without either prompt the user for this).
- **Data, not code** — class/race bonuses are `GrantedModifier` data; no engine
  module references any class or race id.

See `docs/ARCHITECTURE.md` for the longer architectural narrative.
