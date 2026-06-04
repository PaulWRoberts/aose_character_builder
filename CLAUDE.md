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

## Current state (2026-06-03)

Faithful encumbrance, treasure weight & multi-coin currency just landed (13-task plan, on `main`). All 1020 tests pass.

- **Multi-coin purse** — `CharacterSpec` gains `platinum/electrum/silver/copper: int` alongside the existing `gold` (gp, stays the shop-spendable balance). New `aose/engine/currency.py` (cycle-free): `DENOMINATIONS`/`RATES`/`_ATTR`, `total_value_gp`, `coin_count` (weight), `convert` (make-change, whole-coin enforced, raises `CurrencyError`). Routes: `/coins/add` (denom + signed amount, clamped ≥ 0) and `/coins/convert` (from→to, count → 400).
- **Treasure weight** — gems 1 cn each, jewellery 10 cn each (`valuables_weight_cn`). Coins 1 cn each (via `coin_count`). Carried treasure magic items: potions 10, wands 10, rods 20, staves 40, scrolls 1 — derived in `treasure_item_weight` by category + id-prefix (no YAML edits needed). Spell-source scrolls also 1 cn each.
- **Encumbrance rewrite** — old `(armour × band)` table + dead demihuman scaling removed. Two AOSE-faithful modes: **basic** = `_BASIC_TABLE{(armour_cls, carrying_treasure)} → move`; over-1600 treasure → immobile; new `CharacterSpec.carrying_treasure: bool = False` toggle + `/carrying-treasure` route. **Detailed** = single-axis by total weight (bands 400/600/800/1600 → 120/90/60/30/0'); total = `treasure_weight_cn` + `equipment_weight_cn` (weapons + armour by weight; `AdventuringGear` items trigger flat **80 cn** misc-gear abstraction; carried containers contribute own weight + `int(multiplier × raw_contents)` — preserves Bag of Holding mechanic; non-treasure magic items by own weight).
- **EncumbranceTable** reshaped: basic = 3 armour rows × 2 treasure columns; detailed = 4 mobile bands × 1 movement column. Sheet exposes `coins`, `treasure_value_gp`, `treasure_weight_cn`, `carrying_treasure`, `max_load`.
- **Sheet UI**: coin purse in `_equipment_ui.html` (add/convert per denomination); encumbrance table in `sheet.html` uses new shape with current-cell highlighting; carrying-treasure toggle (basic mode only); treasure/cap line; gem+jewellery weight display. Spec/plan: `docs/superpowers/{specs,plans}/2026-06-03-encumbrance-treasure-currency*`.

Gems & jewellery just landed (7-task plan, on `feature/gems-and-jewellery`). All 959 tests pass.

- **Gems & jewellery** — free-acquired, weightless, sheet-only treasure. Two
  per-instance models on `CharacterSpec`: `GemStack` (value + count + label,
  stacks by value+label) and `JewelleryPiece` (full value + `damaged` toggle +
  label; damaged halves value with floor at display/sell). Cycle-free
  `aose/engine/valuables.py` owns add/adjust/remove/sell/sell-all (gems),
  add/toggle-damaged/remove/sell (jewellery), `roll_jewellery_value` (3d6×100),
  and the value helpers (`gem_stack_value`/`jewellery_value`/`total_value`).
  `GEM_INCREMENTS` is a dropdown affordance, not a constraint (custom values
  allowed). Selling adds value to `gold`; dropping refunds nothing (free
  acquisition). Sheet gains a "Gems & Jewellery" section (`valuables_view`) +
  `/gems/{add,adjust,sell,sell-all,remove}` and `/jewellery/{add,toggle-damaged,
  sell,remove}` (sheet-only). Never touches `encumbrance.py`. Spec/plan:
  `docs/superpowers/{specs,plans}/2026-06-03-gems-and-jewellery*`.

Spell books & scrolls just landed (11-task plan, on `feature/spell-books-scrolls`). All 924 tests pass.

- **Spell books & scrolls** — owned documents with custom contents, modelled as a
  per-instance `SpellSource` (`kind` spellbook|scroll, `caster_type`, `entries`
  each with a `copy_failed` flag) on `CharacterSpec.spell_sources`. Cycle-free
  `aose/engine/spell_sources.py` owns create/add/remove, `cast_from_scroll`
  (expends one spell; empties → document dropped; gated by caster-type match via
  `can_cast_scroll`), and `copy_spell` (Advanced-rule only; rolls 1d100 vs
  `spells.copy_chance_for_int(effective INT)`; **failure is recorded on the source
  entry, never on the character**, so the same spell stays copyable from another
  source). `spells.learn()` now refuses free adds under `advanced_spell_books`
  (copy-only); standard rule keeps free learn-on-level-up. Sheet gains a
  "Spell Books & Scrolls" section + `/spell-sources/{add,remove,cast,copy}`
  (sheet-only, Add-only). Protection scrolls (4) added as `MagicItem` catalog data
  in `data/equipment/scrolls.yaml` (`category: scrolls`, no Use action — matches
  potions). Cursed scrolls / treasure maps out of scope. Spec/plan:
  `docs/superpowers/{specs,plans}/2026-06-03-spell-books-and-scrolls*`.

Magic-item compendium bulk import (Phase 2) just landed (10-task plan, on `main`). All 882 tests pass.

- **Phase 2 bulk import** — every item from the AOSE Advanced magic-item markdown
  sources translated into book-faithful YAML game data with full descriptions.
  One code addition: `RolledModifier` value type (`aose/models/modifier.py`) + a
  `MagicItem.rolled_modifiers` field; `new_magic_instance` rolls the dice at
  acquisition time and populates `extra_modifiers` — used by **Bracers of Armour**
  (AC `8 − 1d4`, rolled when the GM grants the item). Files added/extended:
  `data/enchantments.yaml` (all sword/weapon/armour/shield enchantments +
  already-merged ammo enchantments); `data/equipment/magic_items.yaml` (26
  potions, 19 rings, 35 rods/staves/wands, ~130 miscellaneous items);
  `data/equipment/adventuring_gear.yaml` (re-imported with descriptions);
  `data/equipment/containers.yaml` (descriptions + Bag of Holding `magic: true`).
  Gloves of Dexterity and Periapt of Proof Against Poison carry `# TODO:` data
  comments (effects not yet modelled). Sword +3, Defender encoded with
  `magic_bonus: 3` only; AC-transfer option is description-only per user
  confirmation. Spec/plan: `docs/superpowers/{specs,plans}/2026-06-02-magic-item-import*`.

Ammunition just landed (9-task plan, on `feature/ammunition`).

- **Ammunition** — ammo is **not** a weapon. A new `Ammunition` item variant
  (`item_type: ammunition`, `groups`, `bundle_count`, `weight_cn: 0` always —
  the listed missile-weapon weight already includes its ammo + container, so
  ammo never touches `encumbrance.py`) holds the buyable mundane table
  (`data/equipment/ammunition.yaml`: arrows quiver-of-20, bolts case-of-30,
  silver-tipped arrow, free sling stones). Launchers gained `Weapon.accepts_ammo`
  (non-empty ⇔ "needs ammo"; bows `[arrow]`, crossbow `[crossbow_bolt]`, sling
  `[sling_stone]`; thrown weapons incl. javelin stay empty). Per-character
  `CharacterSpec.ammo: list[AmmoStack]` ({instance_id, base_id, enchantment_id,
  count}; stacks combine on `(base_id, enchantment_id)`; counts adjusted manually
  — no auto "shooting") + `loaded_ammo: dict[weapon_key, instance_id]` (weapon_key
  = the resolved weapon `.id`, i.e. catalog id or `ench:<instance_id>`). **Magic
  ammo is enchantment composition**: `Enchantment.kind` now includes
  `ammunition` (+ `any_ammunition` wildcard), so `arrows_plus_1/2`,
  `arrow_slaying`, `crossbow_bolts_plus_1/2`, `sling_bullet_impact` compose onto
  any matching base (e.g. `silver_arrow` takes `arrow_slaying`). Cycle-free
  `aose/engine/ammo.py` owns stacks/loading/bonus (`buy_ammo`/`add_free_ammo`/
  `adjust_count`/`remove_ammo`/`load`/`unload`/`loaded_stack`/`loaded_bonus`/
  `is_unloaded`/`resolve_ammo`). `aose/engine/attacks.py` adds the loaded ammo's
  `magic_bonus` to a launcher's to-hit/damage **additively** with the weapon's
  own bonus (a +1 arrow in a +1 bow = +2) and flags an empty launcher
  `unloaded`. Sheet + wizard share routes (`/ammo/{add,adjust,remove,load,
  unload}`; mundane buy via the existing `/equipment/buy`, special-cased; magic
  ammo is sheet-only Add). Spec/plan:
  `docs/superpowers/{specs,plans}/2026-06-02-ammunition*`.

Magic item enchantment composition previously landed (19-task plan, on `main`). All 834 tests pass.

- **Enchantment composition model** — magic weapons/armour are no longer stored as
  hand-authored catalog entries. A `Enchantment` registry (`data/enchantments.yaml` →
  `GameData.enchantments`) is independent of any base item; per-character
  `EnchantedInstance` pairs a `base_id` + `enchantment_id`. The cycle-free engine module
  `aose/engine/enchant.py` resolves the pair to a synthetic `Weapon`/`Armor` on the fly.
  Tag-based matching (`Weapon.groups`, `Armor.groups`, `Armor.ac_bonus` + kind wildcards
  `any_weapon`/`any_armour`/`any_shield`) means a new base is adopted by every compatible
  enchantment with no YAML changes. Acquisition is **sheet-only, Add-only** (GM grant, no
  gold); the wizard equipment step is mundane-only. The placeholder `magic_items.yaml` is
  deleted — misc magic items (gauntlets, rings, etc.) remain plain `MagicItem` catalog
  entries; only native magic weapons/armour moved to the composition model. Shield `ac_bonus`
  was refactored from a hardcoded constant to a data field. Phase 2 = bulk YAML import.
  Spec/plan: `docs/superpowers/{specs,plans}/2026-06-02-magic-item-enchantments*`.

Manual rolls + Strict Mode just landed (8-task plan, on `main`). All 788 tests pass.

- **Manual rolls + Strict Mode** — abilities, HP, and starting gold all require
  a deliberate Roll button press (like HP already did). A new `RuleSet.strict_mode`
  flag (default `True`) locks each roll after one press; off = free re-rolls.
  A hopeless ability set (`subpar` OR any score is 3) re-enables the Roll button
  under Strict Mode. Two back-navigation gates: rolling abilities locks the rules
  step; rolling HP locks every step before the HP page (`class_setup`) — prevents
  laundering rolls by navigating back. Gates show a `locked` breadcrumb state (🔒).
  Strict off → today's free back-navigation. `draft["hp_blessed_sets"]` (draft-only,
  never persisted to `CharacterSpec`) stores both Blessed HP sets so the Class Setup
  page can bold the higher. Spec/plan:
  `docs/superpowers/{specs,plans}/2026-06-02-manual-rolls-strict-mode*`.

On-sheet play state previously landed (9-task plan). All 788 tests pass.

- **On-sheet play state** — current HP via `CharacterSpec.damage_taken`
  (current = `max(0, max_hp − damage_taken)`, dead derived from current 0;
  `aose/engine/hp.py` gains `current_hp`/`is_dead`/`apply_damage`/`apply_healing`/
  `set_current_hp`). Prepared spells are now `ClassEntry.slots: list[SpellSlot]`
  (spell + reversed + spent), replacing the flat `prepared`; slot ops live in
  `aose/engine/spells.py` (`assign_slot`/`cast_slot`/`restore_slot`/`clear_slot`/
  `restore_all_slots`/`clear_all_slots`). Sheet routes: `/hp/{damage,heal,set}`,
  `/spells/{assign,cast,restore,clear}`, `/rest/{night,full-day}` (full-day adds
  1d3 healing; rest blocked when dead). Arcane reversed is fixed at memorize
  time; divine reversed is a cast-time button only (not stored). Spec/plan:
  `docs/superpowers/{specs,plans}/2026-06-02-on-sheet-character-state*`.

Previous: Spell selection (11-task plan) on `feature/spell-selection`.
Magic items (18-task plan) on `main`.

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
  `/unstash-container`, `/remove-container`). UI: inline collapsible container
  rows; moves are button/dropdown-only (`inventory.js` handles collapse only —
  drag-and-drop was removed 2026-06-02).
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
- **Multi-classing** — the Multiple Classes optional rule, free-form (no combo
  allowlist; `Race.allowed_multiclass_combos` was removed). The wizard class
  step offers up to 3 classes when `multiclassing` + `separate_race_class` are
  on; each pick is gated individually by ability requirements + the
  `demihuman_class_restrictions` rule. **XP is per class** — `ClassEntry.xp`
  replaces the old global `CharacterSpec.xp` (a `model_validator` migrates old
  saves). `aose/engine/leveling.py`: `grant_xp(spec, data, amount)` splits an
  award evenly, scales each share by that class's prime-requisite multiplier
  (lowest score among multi-prime classes), floors, and clamps ≥ 0; clawbacks
  (negative) split evenly without the multiplier. This wires the prime-req XP
  adjustment in for single-class characters too. **HP** (`aose/engine/hp.py`)
  recomputes from raw rolls + *effective* CON at display: per gain-event
  `max(1, event_roll_sum / N + CON_mod)` summed as exact `Fraction`s, floored
  once (order-independent; N=1 reduces to the old single-class formula).
  Creation = one event summing all N first rolls; each later level-up = its own
  event. `hp_remainder` exposes the leftover fraction. Saves/THAC0 already take
  the best across classes. Spec/plan:
  `docs/superpowers/{specs,plans}/2026-05-29-spell-selection*` (this work shares
  the multi-class plan file `quiet-soaring-hedgehog`).

See `project_aose_builder.md` for the longer architectural narrative.
