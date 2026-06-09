# AOSE Character Builder — architecture reference

The living design of each subsystem: where it lives, the key models, and the
hard-won invariants. This is the deep reference; [CLAUDE.md](../CLAUDE.md) is the
quick orientation and [CHANGELOG.md](CHANGELOG.md) is the dated landing ledger.
Full per-feature designs live in `docs/superpowers/{specs,plans}/`.

The engine modules are **pure derivations** and deliberately **cycle-free**. The
import DAG is roughly: `models → loader → magic → features → {armor_class,
saves, attacks}`, with `currency`, `valuables`, `encumbrance`, `ammo`,
`enchant`, `spells`, `spell_sources`, `secondary_skills`, `sources` hanging off
models/loader only.

---

## The modifier pipeline (the core abstraction)

Almost every numeric bonus in the app — magic items, class/race features, WIS
saves — flows through one shared pipeline.

- **`Modifier`** (`aose/models/modifier.py`) — `target` / `op`
  (`add`|`set`|`set_min`|`set_max`) / `value`, plus `condition: str | None` and
  `source: str` (feature/item name, for hover). Target families seen so far:
  `ac`, `thac0`, `attack`, `damage`, `save:<cat>`, `save:vs:<thing>`, and ability
  targets.
- **`apply_modifiers`** (`aose/engine/magic.py`) applies ops in the fixed order
  `set → add → set_min → set_max`. This is the literal evaluation core.
- **`active_modifiers`** (magic.py) collects modifiers from equipped magic items;
  **`feature_modifiers`** (`aose/engine/features.py`) collects them from class
  features (gated by `gained_at_level`) and race features (all). Their union is
  **`all_modifiers`**, the single thing every consumer reads.
- **Consumers** (`armor_class`, `saves`, `attacks`) read `all_modifiers`. Saves
  apply `save:*` with a floor of 2; THAC0 applies `thac0` mods.
- **Conditions are inert-but-carried**: a modifier with a condition a consumer
  can't evaluate is *kept* in the data but *excluded* from the headline number,
  never inflating it. Known conditions are evaluated; unknown ones surface as
  breakdown lines (see next section). `unarmored` AC bonuses drop when armour is
  worn; `ranged`/`melee` attack/damage mods filter per weapon.

### `GrantedModifier` + `Scaling` (data-driven feature bonuses)

`GrantedModifier` (modifier.py) declares a modifier a class/race feature grants:
same `target`/`op`/`condition` grammar, plus exactly one of `value` (flat) or
`scale` (a `Scaling` with `by: level | ability:X` and a banded
`table: dict[int, int]`). `ClassFeature` and `RaceFeature` each carry
`granted_modifiers: list[GrantedModifier]`. `features.py` resolves them
(`_band_lookup` = greatest key ≤ input, 0 below the lowest band; level-scaling is
class-only). **No engine code references any class or race id** — all of it is
data. Examples encoded: barbarian Agile Fighting (`ac add unarmored`, level-
scaled), halfling Missile Attack Bonus (`attack +1 ranged`, race file only),
dwarf/halfling/duergar/gnome CON-scaled save resilience, Kineticist level-AC
(a level-scaled `ac set` granted modifier — the old `ClassLevelData.armor_class`
column was retired onto this path).

### Conditional / situational breakdowns

When a conditioned modifier can't fold into a headline, it surfaces as a
breakdown line. Three parallel implementations, all the same shape (registry of
condition → display note, with underscore fallback):

- **AC** — `armor_class.py`: shared `_compute_ac` helper feeds both
  `armor_class()` and `armor_class_detail() -> ACBreakdown` (`ACModLine`s).
  Headline excludes anything not `unarmored`. `_AC_CONDITION_NOTES`
  (`bright_light`, `large_attacker`). Sheet: `ac_lines` + `ac_has_conditional`,
  `★` opens `modal-ac`. Data: Light Sensitivity (`ac -1 bright_light`, drow/
  duergar/svirfneblin), Defensive Bonus (`ac +2 large_attacker`, gnome/
  svirfneblin/halfling).
- **Attack** — `attacks.py`: `attack_modifiers_detail() -> AttackBreakdown`
  (`AttackModLine`s; unconditional global mods first, then situational;
  `ranged`/`melee` excluded as those are per-weapon). `_ATTACK_CONDITION_NOTES`
  (`bright_light`, `mounted`). Sheet: `attack_lines` + `attack_has_conditional`,
  `★` opens the retitled `modal-matrix` ("Attack"), to-hit matrix gated to
  descending AC. Data: Light Sensitivity (`attack -2 bright_light`, **race files
  only** — race-as-class is covered via `race_locked`, so class files stay
  grant-free to avoid double-application), Knight Mounted Combat
  (`attack +1 mounted`). Per-weapon conditional bonuses (Sword +1, Giant Slayer)
  are separate: `Weapon.conditional_bonus` → `ConditionalAttack`, own row.
- **Saves** — `saves.py`: `saving_throws_detail() -> dict[str, SaveBreakdown]`
  (each carries `base` from class progression, `modified` headline = unconditional
  mods only floored at 2, and `lines: list[SaveModLine]`). `saving_throws()`
  delegates to it. Condition notes: `magical` → "magical effects only", `poison`
  → "poison only (not death magic)", `paralysis` → "paralysis only (not
  petrification)". Sheet `SheetSave` carries `base`/`modified`/`lines`; rows are
  clickable per-save modals.

### Situational "vs X" save bonuses (`save:vs:*`)

A distinct target family `save:vs:<thing>` (e.g. `save:vs:fire`). Collected via
the same `all_modifiers` pipeline but handled separately:
`situational_save_bonuses() -> list[SituationalSaveBonus]` (groups by
source+value, collects `things`; display registry `_VS_DISPLAY` with underscore
fallback). **Never** folded into a headline or a per-category modal — shown only
as smaller-font footnotes under the saving throws (`SheetSituationalSave`,
`.save-note`), also on the print sheet. Data: druid Energy Resistance
(`fire`/`lightning` +2), svirfneblin Illusion Resistance (`illusion` +2),
kineticist Mental Defence (`mental_powers` +2), knight Strength of Will
(`charm`/`hold` +4, `illusion` +2, at level 3).

---

## Abilities, magic items & charges

- **Magic items are data-driven.** `MagicItem` is an `Item` union variant
  (`item_type: magic`, `equippable`, `modifiers`, `max_charges`/`charge_dice`);
  `ItemBase` carries `description` + a cross-cutting `magic` flag. Per-instance
  state on `CharacterSpec.magic_items` (mirrors `ContainerInstance`); modifiers
  apply only when `equipped`.
- **`aose/engine/magic.py`** is the cycle-free core (imports only models + loader
  + dice): `apply_modifiers`, `active_modifiers`, `effective_abilities`,
  `carry_capacity_bonus`, `needs_instance`, plus instance/charge helpers
  (`new_magic_instance`, `add_free_magic_item`, `equip_magic`/`unequip_magic`,
  `use_charge`/`reset_charges`, `remove_magic`, `set_magic_note`).
- **Effective abilities** flow everywhere: AC over effective DEX, attacks use
  effective abilities, HP recomputes from effective CON. A `*` marks modified
  abilities on the sheet.
- **`RolledModifier`** (modifier.py) + `MagicItem.rolled_modifiers`: dice rolled
  at acquisition time and baked into `extra_modifiers` — e.g. Bracers of Armour
  (AC `8 − 1d4`).
- **Native magic weapons/armour** stay `Weapon`/`Armor` with a `magic_bonus`
  field (Armor also `weight_multiplier` for half-weight enchanted armour). A
  synthetic always-first **Unarmed** profile (1d2, STR) leads the attack list.
- Acquisition is **Add-only** (GM grant, no Buy/gold). Escape hatch: free-text
  `note` + homebrew `extra_modifiers`. No magic-item drag-and-drop.
- Seed: `data/equipment/magic_items.yaml` (auto-loaded by the equipment glob —
  there is no `ITEM_FILES` list).

### Enchantment composition

Magic weapons/armour/ammo are **composed**, not hand-authored. An `Enchantment`
registry (`data/enchantments.yaml` → `GameData.enchantments`) is independent of
any base; a per-character `EnchantedInstance` pairs `base_id` + `enchantment_id`.
`aose/engine/enchant.py` resolves the pair to a synthetic `Weapon`/`Armor` on the
fly. Tag-based matching (`groups`, `Armor.ac_bonus`, kind wildcards
`any_weapon`/`any_armour`/`any_shield`/`any_ammunition`) means a new base is
adopted by every compatible enchantment with no YAML changes. Shield `ac_bonus`
is a data field, not a constant.

---

## Attacks & ammunition

- **`aose/engine/attacks.py`** uses effective abilities, `magic_bonus`, global
  `attack`/`damage` mods, the conditional variant, and the synthetic Unarmed
  profile.
- **Ammo is *not* a weapon.** `Ammunition` item variant (`item_type:
  ammunition`, `groups`, `bundle_count`, **`weight_cn: 0` always** — the missile
  weapon's listed weight already includes ammo, so ammo never touches
  `encumbrance.py`). Buyable table in `data/equipment/ammunition.yaml`.
- Launchers carry `Weapon.accepts_ammo` (non-empty ⇔ needs ammo; bows `[arrow]`,
  crossbow `[crossbow_bolt]`, sling `[sling_stone]`; thrown weapons stay empty).
- Per-character `CharacterSpec.ammo: list[AmmoStack]` (`{instance_id, base_id,
  enchantment_id, count}`, stacks combine on `(base_id, enchantment_id)`; counts
  adjusted manually — no auto-shooting) + `loaded_ammo: dict[weapon_key,
  instance_id]` (weapon_key = resolved weapon `.id`, i.e. catalog id or
  `ench:<instance_id>`).
- Magic ammo is enchantment composition (`arrows_plus_1/2`, `arrow_slaying`,
  etc.). `aose/engine/ammo.py` owns stacks/loading/bonus. Loaded ammo's
  `magic_bonus` adds **additively** with the weapon's own bonus (+1 arrow in +1
  bow = +2); an empty launcher is flagged `unloaded`.

---

## Spells, spell books & mental powers

- **`SpellList` registry** (`aose/models/spell_list.py`, `data/spell_lists.yaml`:
  id → `caster_type` arcane|divine|mental) is the single home for the
  known-vs-prepared distinction. A class derives behaviour from the list(s) in
  `CharClass.spell_lists` — no per-class flag.
- **`ClassEntry`** carries `spellbook` (known; arcane *and* mental reuse it as the
  "chosen subset"), `slots: list[SpellSlot]` (prepared daily — spell + reversed +
  spent), and `powers_used` (mental daily-use counter; pool = `2 × level`).
- **`aose/engine/spells.py`** (cycle-free): `caster_type_of` (raises on mixed/
  unknown lists), `accessible_levels`, `memorizable_slots`, `known_spells`
  (arcane=spellbook, divine=full accessible list, mental=all on-list not yet
  known), `learnable_spells`, `beginning_spell_count`, the `learn`/`forget`/
  `prepare`/`unprepare` mutators, slot ops (`assign_slot`/`cast_slot`/etc.), and
  the power-pool ops (`power_pool`/`spend_power`/`restore_power`/`reset_powers`).
- **Standard vs advanced books** = the `advanced_spell_books` rule. Off: book
  capped at memorizable, free learn-on-level-up. On: INT beginning spells,
  uncapped book, copy-only (no free adds). There is **no special Read Magic
  rule** — it's an ordinary magic-user spell.
- **Arcane reversed** is fixed at memorize time; **divine reversed** is a cast-
  time button only (not stored).
- **Spell books & scrolls** — owned documents as a per-instance `SpellSource`
  (`kind` spellbook|scroll, `caster_type`, `entries` each with a `copy_failed`
  flag) on `CharacterSpec.spell_sources`. `aose/engine/spell_sources.py`:
  create/add/remove, `cast_from_scroll` (expends one; empties → dropped; gated by
  caster-type match), `copy_spell` (Advanced rule; rolls 1d100 vs
  `copy_chance_for_int(effective INT)`; **failure is recorded on the source
  entry, never the character** — same spell stays copyable from another source).
  Sheet-only, Add-only. Protection scrolls live as `MagicItem` catalog data in
  `data/equipment/scrolls.yaml`.
- **Rest** (`/rest/night`, `/rest/full-day`) calls `reset_powers` + slot restore;
  full-day adds 1d3 healing; rest blocked when dead.

### Mental powers caster type

`mental` is a third caster type. No slot levels — a daily-use pool counter.
`spells_view`/`spellbook_view` skip mental; a separate `mental_powers_view` →
`MentalPowersBlock` drives the Mental Powers section (pool pips, Use/Restore/
Reset, known-power list). Routes `/powers/{learn,forget,spend,restore,reset}`.
Kineticist is the only mental class (`data/classes/kineticist.yaml`, source
`carcass_crawler_1`, all on `data/spells/carcass_crawler_kineticist_powers.yaml`).

### Carcass Crawler 1 content (`source: carcass_crawler_1`)

**Classes:** Acolyte (scroll-only divine, `spell_lists: [cleric]`, no slots),
Mage (scroll-only arcane, `spell_lists: [magic_user]`, no slots, +2 AC
`granted_modifier`), Gargantua / Goblin / Hephaestan (race-as-class via
`race_locked`). **Races (Advanced):** Gargantua (–1 INT +1 STR, Resilience,
classes Assassin/Barbarian/Cleric*/Fighter/Thief), Goblin (+1 DEX –1 STR,
infravision 60', Resilience, Defensive Bonus, classes Acrobat/Assassin/
Cleric*/Fighter/Magic-user/Thief), Hephaestan (–1 STR +1 CHA, Listening /
Neuropressure only per races.md, classes Acrobat/Assassin/Cleric*/Fighter/
Illusionist/Magic-user/Thief). New languages: `hephaestan`, `language_of_wolves`.

---

## Inventory, containers & encumbrance

- **Inventory shapes** — `inventory: list[str]` (duplicates count toward size);
  `equipped: dict[str, str]` (armor/shield slots); `equipped_weapons: list[str]`
  (duplicates allowed). A weapon is equippable when
  `equipped_weapons.count(id) < inventory.count(id)`. Equipped items live *inside*
  `inventory` already — weight is counted once. `stashed: list[str]` is off-person
  (no weight). Sheet renders Equipped / Carried / Stashed.
- **Containers** — `Container` catalog variant (`item_type: container`,
  `capacity_cn`, `weight_multiplier`) + per-instance `ContainerInstance`
  (`instance_id`, `catalog_id`, `state`, `contents`) on `CharacterSpec.containers`.
  Items inside aren't in `inventory`/`stashed`; they follow the container's
  carried/stashed state. Carried containers contribute `own_weight +
  int(multiplier × raw_contents)` — a Bag of Holding (×0.06) at 10 000 cn weighs
  600 cn. Capacity uses raw weight. No nesting. Helpers in `shop.py` (`stow`/
  `take_out`/`stash_container`/etc.). Dispatch is by `isinstance(item, Container)`,
  so the file location of a container item is transparent to routes. UI: inline
  collapsible rows, button/dropdown-only (drag-and-drop was removed 2026-06-02).
- **Stackable gear** — `AdventuringGear.bundle_count: int = 1`. `buy()` grants
  `bundle_count` units for one price; `add_free()` always grants one. Sell removes
  1 unit, returns `int((cost_gp / bundle_count) / 2)`; refund removes a full stack,
  returns `cost_gp`. Gear data is book-faithful; the encumbrance engine uses a flat
  **80 cn** for any `AdventuringGear` item, so per-item `weight_cn` is dead data
  and is not fabricated.
- **Encumbrance** (`aose/engine/encumbrance.py`) — two AOSE-faithful modes.
  **Basic** = `_BASIC_TABLE{(armour_cls, carrying_treasure)} → move` (over-1600
  treasure → immobile; `CharacterSpec.carrying_treasure` toggle). **Detailed** =
  single-axis by total weight (bands 400/600/800/1600 → 120/90/60/30/0'); total =
  `treasure_weight_cn` + `equipment_weight_cn`. Magic items band on
  `banding_weight_cn` (raw − `carry_capacity_bonus`) while displaying raw carried
  weight; enchanted armour weighs half. `EncumbranceTable` reshaped accordingly.

---

## Currency, treasure & valuables

- **Multi-coin purse** — `CharacterSpec.platinum/electrum/gold/silver/copper`
  (gp stays the shop-spendable balance). `aose/engine/currency.py` (cycle-free):
  `DENOMINATIONS`/`RATES`/`_ATTR`, `total_value_gp`, `coin_count` (weight, 1 cn
  each), `convert` (make-change, whole-coin enforced, raises `CurrencyError`).
  Routes `/coins/add`, `/coins/convert`.
- **Treasure weight** — gems 1 cn, jewellery 10 cn; carried treasure magic items
  potions 10 / wands 10 / rods 20 / staves 40 / scrolls 1, derived by category +
  id-prefix in `treasure_item_weight` (no YAML edits).
- **Gems & jewellery** — free-acquired, weightless for movement-mode purposes,
  sheet-only treasure. `GemStack` (value + count + label, stacks by value+label)
  and `JewelleryPiece` (full value + `damaged` toggle + label; damaged halves
  value, floor). `aose/engine/valuables.py` owns add/adjust/remove/sell plus
  `roll_jewellery_value` (3d6×100); `GEM_INCREMENTS` is a dropdown affordance, not
  a constraint. Selling adds to `gold`; dropping refunds nothing. Never touches
  `encumbrance.py` directly (weight comes via `treasure_weight_cn`).

---

## Identity: languages, literacy, secondary skills

- **Language registry** — `LanguageData.names: dict[str, str]` maps every id to
  its book-authoritative display name; `display_name(id, lang_data)` does registry
  lookup with a title-case fallback. `data/languages.yaml` `additional:` is a list
  of ids.
- **Granted languages** — `granted_languages(spec, data)` walks race features (all)
  and class features (level-gated) collecting `feature.mechanical["languages"]`
  ids (gnome burrowing-mammals tongue, druid's `druidic`). Granted tongues appear
  in the known list but never in the INT-pick learnable list; the wizard shows them
  under "Granted:".
- **Literacy** — `literacy(spec, data)` → `illiterate` (INT ≤ 5) / `basic`
  (6–8) / `literate` (≥ 9). `mechanical.illiterate_below_level` forces illiterate
  until that level (barbarian: `2` → illiterate at level 1 only).
- **WIS magic-save modifiers** — `wisdom_save_modifiers(spec, data)` builds
  synthetic `Modifier`s from effective WIS: unconditional on `save:spells`/
  `save:wands`; conditional (`magical`) on `save:death`/`save:paralysis`; never on
  `save:breath`.
- **Secondary skills** — `SecondarySkillEntry` (`{name, weight≥1, roll_twice}`),
  `data/secondary_skills.yaml` is the exact d100 table (loader validates the sum =
  100 and exactly one roll-twice). `aose/engine/secondary_skills.py`:
  `selectable_names` (excludes roll-twice), `roll(entries, rng)` (weighted; roll-
  twice expands to two distinct trades, never nests). `CharacterSpec.secondary_skills:
  list[str]`. Strict mode rolls once on first `GET /identity` and locks; non-strict
  re-rolls freely.

---

## Characters, leveling & play state

- **Multi-classing** — free-form (Multiple Classes optional rule; no combo
  allowlist). Wizard offers up to 3 classes when `multiclassing` +
  `separate_race_class` are on, each gated by ability requirements +
  `demihuman_class_restrictions`. **XP is per class** (`ClassEntry.xp`, not a
  global). `grant_xp(spec, data, amount)` (`leveling.py`) splits evenly, scales
  each share by that class's prime-requisite multiplier (lowest score among
  multi-prime classes), floors, clamps ≥ 0; clawbacks split evenly without the
  multiplier. **HP** recomputes from raw rolls + effective CON: per gain-event
  `max(1, event_roll_sum / N + CON_mod)` summed as exact `Fraction`s, floored once
  (order-independent; N=1 = the old single-class formula). `hp_remainder` exposes
  the leftover. Saves/THAC0 take the best across classes.
- **Current HP** — `CharacterSpec.damage_taken` (current = `max(0, max_hp −
  damage_taken)`, dead derived from current 0). `aose/engine/hp.py`: `current_hp`/
  `is_dead`/`apply_damage`/`apply_healing`/`set_current_hp`. Routes `/hp/{damage,
  heal,set}`.

---

## Content sources & optional rules

- **Sources** — `Source` model + `data/sources.yaml` (OSE Classic Fantasy + OSE
  Advanced Fantasy, both Necrotic Gnome). A `source` field on `ItemBase`/`Race`/
  `CharClass`/`SpellList`/`Enchantment`/`Spell` defaults to
  `ose_classic_fantasy`; only Advanced-tagged entries carry the Advanced id.
  `RuleSet.disabled_sources: list[str]` (Classic is always enabled, never added).
  `aose/engine/sources.py`: `CLASSIC_SOURCE_ID` + `source_enabled(source_id,
  ruleset)`. Gated in wizard race/class steps, spell candidates, `shop_categories`,
  `_enchant_choices`. Mid-wizard, disabling a source clears orphaned race/class
  picks via `_apply_rule_changes`.
- **Optional rules** — every flag in `RuleSet` is integrated end-to-end. The
  settings page never renders a "pending" badge (a regression test guards this).
- **Manual rolls + Strict Mode** — abilities, HP, and starting gold each require a
  deliberate Roll press. `RuleSet.strict_mode` (default `True`) locks each roll
  after one press; off = free re-rolls. A hopeless ability set (`subpar` or any
  score 3) re-enables the Roll button under strict. Back-nav gates: rolling
  abilities locks the rules step; rolling HP locks every step before HP
  (`class_setup`) — gates show a 🔒 breadcrumb state. `draft["hp_blessed_sets"]`
  (draft-only, never persisted) stores both Blessed HP sets so Class Setup can bold
  the higher.

---

## Sheet & UI

- **Zine sheet** — `aose/web/templates/sheet.html`: identity band, 3-column grid
  (combat+abilities, features+notes, spells/powers — column 3 opens for
  `sheet.spellbook or sheet.mental_powers`), full-width inventory/currency/treasure
  group, footer. Groups have inked bars + internal scroll.
- **Design system** — `aose/web/static/sheet.css` (Oswald + Bitter, self-hosted
  woff2 under `aose/web/static/fonts/`). **Read `docs/STYLE-GUIDE.md` before any
  sheet/UI work** — tokens, components, the overlay model, and hard-won invariants
  (closed-overlay `pointer-events`, variable-font self-hosting, `no-cache` static).
- **Overlay controller** — `aose/web/static/sheet_overlays.js`: single-open
  drawer/modal/popover, dismissed by Esc/scrim/close.
- **Tabbed equipment drawer** — `_equipment_ui.html`: Carried (always), Magic
  (gated `magic_acquisition`), Documents (gated `spell_sources`), Treasure (gated
  `valuables`), Shop (always). The wizard shows only Carried + Shop.
- **Print sheet** — `sheet_print.html` mirrors the live sheet; conditional AC/
  attack/save lines and situational `vs:*` bonuses appear as footnotes.
- **`build_sheet(spec, data) -> CharacterSheet`** (`aose/sheet/view.py`) assembles
  every derivation. Block models (`SpellbookBlock`, `MentalPowersBlock`,
  `ACBreakdown`, `AttackBreakdown`, `SaveBreakdown`, `EncumbranceTable`, etc.) live
  alongside it / in their engine modules.
- **Per-item modals** — every clickable entry in the inventory section (carried/
  stashed/equipped gear, containers, ammo, worn magic items) opens a dedicated
  server-rendered `overlay modal` showing properties via `detail_card(row.detail)`
  (i.e. `item_card()` stats + markdown description) and safe management actions
  (equip/unequip, stow, stash/unstash, load/unload ammo, use-charge). Destructive
  actions (drop/sell/refund) are **drawer-only** — never in a sheet modal.
- **`show_remove` boundary** — `_inv_row_actions.html` accepts `show_remove=True`
  (default). Sheet modals pass `False`; the management drawer uses the default.
- **Launcher modals** — equipped weapons that accept ammo expose a Load
  `<select>` + Unload form in their modal, keyed by `manageable_item_id` /
  `ammo_load_options` (both use the plain catalog weapon id).
- **Shop expander** — `ShopItem.detail` (populated by `item_card(i)` in
  `shop_categories`) is rendered via `detail_card` in a `row-detail` expander row
  toggled by `inventory.js` (same pattern as drawer inventory rows). Buy/add
  controls are unaffected — the toggle ignores clicks inside forms/buttons.
