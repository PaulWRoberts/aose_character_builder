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

## Current state (2026-05-29)

Spell selection just landed (11-task plan) on `feature/spell-selection`.
All 577 tests pass. Magic items landed before it (18-task plan, on `main`).

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
- **Container items** — `Container` catalog variant (`item_type: container`,
  `capacity_cn`, `weight_multiplier`) + per-instance `ContainerInstance`
  (`instance_id`, `catalog_id`, `state`, `contents`) on
  `CharacterSpec.containers`. Items inside a container aren't in `inventory`
  /`stashed`; they follow the container's carried/stashed state for weight.
  Carried containers contribute `own_weight + int(multiplier * raw_contents)`;
  a Bag of Holding (×0.06) at 10 000 cn weighs 600 cn. Capacity uses raw
  weight. No nesting. Engine helpers in `shop.py`: `stow` / `take_out` /
  `stash_container` / `unstash_container` / `remove_container` /
  `buy_container` / `inventory_view` (returns a `containers` list).
  Sheet + wizard share routes (`/stow`, `/take-out`, `/stash-container`,
  `/unstash-container`, `/remove-container`, and a unified `/move`
  drag-and-drop dispatcher in `aose/web/move_dispatch.py`). UI: inline
  collapsible container rows + `inventory_dnd.js` (vanilla HTML5 DnD).
  Spec/plan: `docs/superpowers/{specs,plans}/2026-05-27-container-items*`.
- **Magic items** — data-driven. A `Modifier` value type
  (`aose/models/modifier.py`: `target` / `op` add|set|set_min|set_max / `value`)
  is shared by catalog `MagicItem.modifiers` and per-instance
  `MagicItemInstance.extra_modifiers`. `MagicItem` is an `Item` union variant
  (`item_type: magic`, `equippable`, `modifiers`, `max_charges` / `charge_dice`);
  `ItemBase` gained `description` + a cross-cutting `magic` flag. Magic
  weapons/armour stay native `Weapon`/`Armor` with a `magic_bonus` field
  (Armor also gained `weight_multiplier` for half-weight enchanted armour;
  Weapon gained `conditional_bonus` → a `{vs, bonus}` second attack line).
  Per-instance state lives on `CharacterSpec.magic_items` (mirrors
  `ContainerInstance`); modifiers apply only when `equipped`.
  `aose/engine/magic.py` is the **cycle-free core** (imports only models +
  loader + dice): `apply_modifiers` (literal set→add→set_min→set_max),
  `active_modifiers`, `effective_abilities`, `carry_capacity_bonus`,
  `needs_instance`, plus the instance/charge helpers (`new_magic_instance`,
  `add_free_magic_item`, `equip_magic`/`unequip_magic`, `use_charge`/
  `reset_charges`, `remove_magic`, `set_magic_note`). The derivation modules
  import *from* it: AC adds `magic_bonus` + `ac` mods over effective DEX;
  saves apply `save:*` mods with a floor of 2; THAC0 applies `thac0` mods
  (Girdle `set_max`); attacks use effective abilities, `magic_bonus`, global
  `attack`/`damage` mods, the conditional variant, and a synthetic always-first
  **Unarmed** profile (1d2, STR); encumbrance halves enchanted-armour weight,
  counts instance weight, and bands on `banding_weight_cn` (raw −
  `carry_capacity_bonus`) while displaying raw carried weight. Acquisition is
  **Add-only** (GM grant, no Buy/gold): `/add` routes a `needs_instance` item to
  `add_free_magic_item`. Sheet + wizard share routes (`/equip-magic`,
  `/unequip-magic`, `/use-charge`, `/reset-charges`, `/remove-magic`,
  `/magic-note`). Sheet shows a Magic Items section (collapsible descriptions +
  `modifier_summary` chips), a `*` marker on modified abilities, and the Unarmed
  + conditional attack rows. Seed data: `data/equipment/magic_items.yaml`
  (auto-loaded by the equipment glob — there is no `ITEM_FILES` list).
  No magic-item drag-and-drop in V1 (buttons/forms only; magic weapons/armour
  still DnD as plain inventory ids). Escape hatch: free-text `note` +
  homebrew `extra_modifiers`. Spec/plan:
  `docs/superpowers/{specs,plans}/2026-05-28-magic-items*`.
- **Spells** — data-driven, faithful known-vs-prepared. A `SpellList` registry
  (`aose/models/spell_list.py`, seed `data/spell_lists.yaml`: id → `caster_type`
  arcane|divine) is the single home for the known-vs-prepared distinction; a
  class derives its behaviour from the list(s) in `CharClass.spell_lists` (no
  per-class flag). `ClassEntry` carries `spellbook` (known; arcane) + `prepared`
  (daily, slot-capped; replaces the old unused `chosen_spells`).
  `aose/engine/spells.py` is the cycle-free core (imports only models + loader):
  `caster_type_of` (raises on mixed/unknown lists), `accessible_levels`,
  `memorizable_slots`, `known_spells` (arcane=spellbook, divine=full accessible
  list), `learnable_spells`, `beginning_spell_count` (standard=memorizable total,
  advanced=INT table), and the `learn`/`forget`/`prepare`/`unprepare` mutators
  (return a new `ClassEntry`, raise `SpellError`). The standard-vs-advanced
  spell-book rules are the `advanced_spell_books` optional rule (off=standard:
  book capped at memorizable; on=INT beginning spells + uncapped book). **There is
  no special Read Magic rule** — it's an ordinary magic-user spell. Wizard
  `spells` step (after HP, before Equipment; gated by a cached
  `draft["spellcasting"]` flag set in `post_class`, cleared by the `_clear_after_*`
  helpers) selects the arcane starting book (exact-count, field `spell_<class_id>`)
  / shows the divine list read-only. Sheet `spells_view` + Spells section + routes
  (`/spells/learn|forget|prepare|unprepare`, keyed by `class_id`) manage both
  layers. Seed spells in `data/spells/*.yaml` (verified against the PDF). No
  spell DnD in V1. Spec/plan:
  `docs/superpowers/{specs,plans}/2026-05-29-spell-selection*`.

See `project_aose_builder.md` for the longer architectural narrative.
