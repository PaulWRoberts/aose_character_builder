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
  `ac`, `thac0`, `attack`, `damage`, `save:<cat>`, `save:vs:<thing>`, `initiative`
  (inert — consumed only by `engine/initiative.py`), and ability targets.
- **`apply_modifiers`** (`aose/engine/magic.py`) applies ops in the fixed order
  `set → add → set_min → set_max`. This is the literal evaluation core.
- **`active_modifiers`** (magic.py) collects modifiers from equipped magic items;
  **`feature_modifiers`** (`aose/engine/features.py`) collects them from class
  features (gated by `gained_at_level`) and race features (all) — **except for a
  race-as-class character** (`is_race_as_class`: single class whose `race_locked`
  equals `race_id`), whose linked race is skipped entirely. Their union is
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
scaled), halfling Missile Attack Bonus (`attack +1 ranged`), dwarf/halfling/
duergar/gnome CON-scaled save resilience, Kineticist level-AC (a level-scaled
`ac set` granted modifier — the old `ClassLevelData.armor_class` column was
retired onto this path).

**`mechanical.requires_rule` — per-feature visibility gating:** a feature whose
`mechanical` dict carries `requires_rule: <flag>` is hidden from the sheet
when the named `RuleSet` flag is `False`. This is enforced in
`_feature_visible()` (view.py), called by both `_race_features` and
`_class_features`. Used for halfling's "Initiative Bonus (Optional Rule)" — shown
only when `individual_initiative` is on — while human's "Decisiveness" (no
`requires_rule`) always appears.

**`engine/initiative.py` — display-only breakdown:** `initiative_detail(spec,
data)` assembles `InitiativeDetail{base, total, lines, has_conditional}` from
the DEX initiative modifier (`ability_mods.initiative_modifier`) plus any
`initiative`-target grants in `all_modifiers`. It is only rendered when
`RuleSet.individual_initiative` is set; none of the core derivations (AC, saves,
attacks) import it. The `CharacterSheet` carries `initiative_modifier`,
`initiative_lines`, and `initiative_has_conditional` for the Combat box INIT
field and its breakdown modal.

**Generic `mechanical` keys beyond `granted_modifiers`:** `features.py` also
exposes collectors that read arbitrary `mechanical` dict keys off reached
features via `iter_reached` (the canonical "which features apply" generator —
class features gated by `gained_at_level`, chosen options, and race features /
chosen race options suppressed for race-as-class): `feature_weapons` reads
`mechanical["weapon"]` descriptors to produce synthetic always-on
`AttackProfile`s (the gargantua's thrown rock, Mutoid claws, Mycelian fists —
declared as `name`/`damage`/`melee`/`ranged`/etc. in the feature YAML; a
`damage_per_level_die` key resolves to `"{level}{die}"` at render time);
`open_doors_category_bonus` sums `mechanical["str_category_bonus"]` for the STR
ability table bump (gargantua Open Doors). Both follow the same race-as-class
guard, so a character who is race *and* class never double-counts.

**Feature choices (`FeatureChoice` / `ChoiceOption`):** A Race or CharClass can
declare `feature_choices: list[FeatureChoice]`, each being a "pick N (or roll)"
group. Selections live on `CharacterSpec.feature_choices: dict[str, list[str]]`
(group id → chosen option ids). Chosen `ChoiceOption`s are feature-shaped
(`mechanical`, `granted_modifiers`, `daily_uses`, `spell_id`), so they flow
through `iter_reached` / `feature_modifiers` / `feature_weapons` with no
per-option engine code. Engine: `aose/engine/feature_choices.py`
`roll_choice`/`validate_choice`/`effective_pick`. Selected features render on the sheet alongside
normal class/race features.

*Level-banded pick count:* `FeatureChoice.pick_by_level: dict[int, int]` gives
the number of picks at each level band (e.g. `{1:1, 5:2, 10:3}`). `effective_pick(group,
level)` returns the right count; at creation (wizard) level is always 1.
Groups with `pick_by_level` feed the **unspent-capacity** mechanism below.

*Rule gating:* `FeatureChoice.requires_rule: str` hides a group unless
`spec.ruleset.<field>` is True. `ChoiceOption.excluded_when_rule: str` hides a
single option (Weapon specialist hides when `weapon_proficiency` is on).
All gating flows through the single chokepoint `_active_choice_groups` (wizard)
and the equivalent filter in `_level_choice_extras` (sheet).

*Parameterised options:* `ChoiceOption.param: OptionParam` declares a player-chosen
free value. `kind="text"` stores the value in `CharacterSpec.choice_params: dict[str,str]`
keyed by option id; `feature_modifiers` substitutes it into any `{param}` in a
modifier's `condition` (Slayer: `"vs {param}"` → `"vs dragons"`).
`kind="weapon"` writes the value directly into `spec.weapon_specialisations`
(Weapon specialist).

**Wizard feature-choices flow:** `class_setup` step shows a picker (roll-first
for groups with `roll_dice`; manual checkbox grid for groups without, like Combat
Talents). `POST /{id}/feature-choices/roll?group_id=X` rolls one table; Strict Mode
locks after the first roll; non-strict allows re-roll and manual override via
`POST /{id}/feature-choices` which calls `_apply_feature_overrides` (reads
`param_<option_id>` fields for parameterised options). Strict Mode only locks
*rolls*: pick-only groups (no `roll_dice`, e.g. Combat Talents) are a deliberate
selection and stay editable in every mode — `_apply_feature_overrides` skips only
rolled groups under Strict, and the picker always renders their checkbox grid
(submitted via the consolidated `POST /{id}/hp` `section=features`). Cascading clear in
`_apply_rule_changes` removes `feature_choices["combat_talents"]`,
`choice_params`, and any talent-granted `weapon_specialisations` when
`combat_talents` is toggled off.

**Unspent-capacity mechanism (`aose/engine/level_choices.py`):** A subsystem-agnostic
`Capacity(kind, group_id, label, earned, spent)` model tracks how many selections
a character has earned vs. spent for any pick-granting subsystem. Two providers:
`proficiency_capacity(spec, data)` (weapon-proficiency slots from THAC0 progression)
and `talent_capacities(spec, data)` (one entry per level-banded group whose rule is
active). `all_capacities` aggregates both and returns only those with `remaining > 0`.
The sheet exposes these as `level_choices`, with matching pickers rendered by
`_levelup_choices.html` (proficiency: `POST /character/{id}/proficiency/add`;
talent: `POST /character/{id}/talent/add`). The level-up modal shows a reminder
note when any capacity is outstanding. `CharacterSheet.proficiency_weapon_options`
and `talent_options` carry the selectable choices for the pickers.

**Weapon specialisation gate:** `attacks.py:_profile_for` checks `spec.ruleset.weapon_proficiency OR spec.ruleset.combat_talents` for `is_specialised`. Under proficiency the weapon must also appear in `weapon_proficiencies`; under combat talents (Weapon specialist) it need not — the two subsystems are mutually exclusive via the `excluded_when_rule` gate.

**Race vs race-as-class are distinct stat blocks that share only a name.** A
race-as-class character is defined wholly by its `race_locked` `CharClass`; the
linked `Race` contributes *nothing* (no features, no feature-grants, no ability
modifiers — see `is_race_as_class` in features.py / `_race_features` in view.py).
The `Race` is read only in split mode. Consequently a grant a demihuman has in
*both* modes (Light Sensitivity, Defensive Bonus, Missile Bonus, …) is authored
on **both** the race file (split mode) *and* the race-locked class file
(race-as-class) — duplication is intentional, and the class's own `features:`
list is the source of truth for which grants a race-as-class receives. A feature
the class omits (e.g. Resilience / Magic Resistance, which are race-only Advanced
abilities) therefore does **not** apply to the race-as-class.

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
  descending AC. Data: Light Sensitivity (`attack -2 bright_light`, on **both** the
  race file and the race-locked class file — race and race-as-class are separate
  self-contained stat blocks; see the `GrantedModifier` section), Knight Mounted
  Combat
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

Equipping an enchanted item enforces the **same class weapon/armour allowances**
as mundane gear: the `equip-enchanted` route resolves the synthetic
`Weapon`/`Armor` and checks its `base_weapon_id`/`base_armor_id` against the
class's allowed sets. Weapons/shields go through `equip()` (slot-resident);
body armour is flag-resident (`EnchantedInstance.equipped`) so the route applies
the `allowed_armor_ids` gate itself before flipping the flag.

The **UI** equip-eligibility decision has a single source of truth so the two
rendering paths can't diverge: `shop.class_allows(item, allowed_weapons,
allowed_armor, allow_shields)` is consumed by both `_build_row` (mundane
`InventoryRow.class_allowed`) and `enchanted_items_view`
(`MagicItemView.class_allowed`). The enchanted/magic modal hides the Equip
button (→ "Not usable") whenever `class_allowed` is false, mirroring the mundane
row and preventing a server error on submit. `equip()` remains the server-side
backstop. (Retainer gear is DM-controlled, so its enchanted view keeps the
`"all"` default — unrestricted, matching `OwnerCaps.class_filter_equip=False`.)

---

## Attacks & ammunition

- **Weapon qualities are the source of truth for weapon mechanics.** `Weapon.qualities: list[QualityRef]` — authored in YAML as bare ids (`melee`, `two_handed`) or one-key parametric dicts (`{missile: [s,m,l]}`, `{versatile: "die"}`). Computed properties (`melee`, `ranged`, `hands`, `versatile`, `range_*`, `two_handed_damage`, `deals_damage`) are derived from qualities; nothing is stored. The loader validates every quality ref against the `WeaponQuality` registry (`_validate_weapon_qualities`). No-damage weapons (`net`, `blowgun`) have `damage.default == ""`. Under the variable-damage rule, a `{versatile: "die"}` weapon emits a second `(Two-handed)` attack profile in `attacks.py`.
- **`aose/engine/attacks.py`** uses effective abilities, `magic_bonus`, global
  `attack`/`damage` mods, the conditional variant, and the synthetic Unarmed
  profile. A second synthetic profile category — **feature weapons** — is emitted
  by `_feature_weapon_profile` for each descriptor in `feature_weapons(spec,
  data)`: always proficient, no manage link, no catalog entry; ranged ⇒ DEX to
  hit + flat damage, melee ⇒ STR to hit and damage. The gargantua's thrown rock
  is the first example (range 50/100/150 ft, 1d6, ranged/blunt).
- **Ammo is *not* a weapon.** `Ammunition` item variant (`item_type:
  ammunition`, `groups`, `bundle_count`, **`weight_cn: 0` always** — the missile
  weapon's listed weight already includes ammo, so ammo never touches
  `encumbrance.py`). Buyable table in `data/equipment/ammunition.yaml`.
- Launchers carry `Weapon.accepts_ammo` (non-empty ⇔ needs ammo; bows `[arrow]`,
  crossbow `[crossbow_bolt]`, sling `[sling_stone]`, blowgun `[blowgun_dart]`;
  thrown weapons stay empty).
- Per-character `CharacterSpec.ammo: list[AmmoStack]` (`{instance_id, base_id,
  enchantment_id, count}`, stacks combine on `(base_id, enchantment_id)`; counts
  adjusted manually — no auto-shooting) + `loaded_ammo: dict[weapon_key,
  instance_id]` (weapon_key = resolved weapon `.id`, i.e. catalog id or
  `ench:<instance_id>`).
- Magic ammo is enchantment composition (`arrows_plus_1/2`, `arrow_slaying`,
  etc.). `aose/engine/ammo.py` owns stacks/loading/bonus. Loaded ammo's
  `magic_bonus` adds **additively** with the weapon's own bonus (+1 arrow in +1
  bow = +2); an empty launcher is flagged `unloaded`.
- **Quality-based weapon allowance** — `CharClass.weapon_qualities_allowed: list[str]`
  grants a class permission to use any weapon that carries a matching quality id.
  `aose/engine/proficiency.py` expands `allowed_weapon_ids` to include every
  catalog weapon whose qualities include any listed id. Cleric and Acolyte carry
  `weapon_qualities_allowed: [blunt]`, which automatically covers all current and
  future blunt weapons (club, mace, flail, blackjack, etc.) without enumerating
  individual ids.

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
  uncapped book, copy-only (no free adds).
- **Cantrips (CC5, `cantrips` rule)** are level-0 arcane spells for *dedicated
  arcane casters* (`spells.is_dedicated_arcane`: arcane caster type + a L1 spell
  slot at level 1). They ride the normal spellbook/slots — `memorizable_slots` /
  `accessible_levels` inject `{0: cantrip_count(level)}` (2/3/4 by level) when
  passed `data`+`ruleset`, so the sheet renders a "Cantrips" group and
  prepare/cast reuse the spell path. Cantrips obey the active book rule: standard
  = free learn, book cap = memorise cap = the cantrip table; advanced = copy-only
  from books/scrolls, uncapped book; the memorise cap stays 2/3/4 in both. The
  dependent `read_magic_cantrip` rule hides the L1 read magic
  (`DEMOTED_READ_MAGIC_IDS`) and auto-grants a level-0 `read_magic_cantrip`
  (beyond the cap) to dedicated arcane casters. Spells:
  `data/spells/carcass_crawler_5_cantrips.yaml`. Source rules wired in
  `SOURCE_RULES["carcass_crawler_5"]`.
- **Arcane reversed** is fixed at memorize time; **divine reversed** is a cast-
  time button only (not stored).
- **Spell books & scrolls** — owned documents as a per-instance `SpellSource`
  (`kind` spellbook|scroll, `caster_type`, `language`, `unlocked`, `entries` each
  with a `copy_failed` flag, `location: StorageLocation` default Carried) on
  `CharacterSpec.spell_sources`. `aose/engine/spell_sources.py`: create/add/remove,
  `cast_from_scroll` (expends one charge; empties → dropped; gated by
  `scroll_cast_block_reason`), `copy_spell` (Advanced rule; rolls 1d100 vs
  `copy_chance_for_int(effective INT)`; **failure is recorded on the source entry,
  never the character** — same spell stays copyable from another source).
  **Copying requires the arcane source to be deciphered** (`unlocked`) — both an
  arcane scroll's magical script and a captured spell book are unreadable until
  Read Magic is used (`copyable_spell_ids` returns ∅ for a sealed source).
  **Cast/decipher/copy are all gated on the document being Carried** by the PC
  (`location.kind == "carried"`); a stashed or carrier-stored scroll shows the
  block reason and cannot be used. Movement uses `move_thing(spec, "source", ...)`.
  Spell sources bucket by location in `inventory_groups` (`group.spell_sources`);
  container-stowed sources appear in `ContainerView.stowed_spell_sources`. Modals
  show Move ▾ + Drop for every source. Sheet-only, Add-only. Protection scrolls live
  as `MagicItem` catalog data in `data/equipment/scrolls.yaml`.
  - **Scribe Add form** — `spell_source_add_options(data, ruleset)` is
    ruleset-filtered: only spell lists whose source content is enabled appear,
    level-0 cantrips show only under the Cantrips rule, and the `advanced` flag
    (Advanced Spell Book rule) gates the Spell Book document type (hidden in the
    template otherwise, since books are useless without copying). The JS hides the
    per-charge quantity stepper for books.
  - **Arcane documents** (scrolls and spell books) carry `unlocked: bool`
    (default False). Must be deciphered by casting Read Magic —
    `ready_read_magic_slot` finds a memorized unspent slot, `decipher_source`
    burns it and sets `unlocked=True` (works on any arcane source, not just
    scrolls). Casting from a sealed arcane scroll is blocked
    (`scroll_cast_block_reason` → "needs Read Magic"); copying from a sealed
    arcane scroll *or* spell book is blocked too.
  - **Divine scrolls** carry `language: str` (default "Common"). Casting requires
    the character to know the scroll's language (case-insensitive, via
    `known_languages`). `scroll_cast_block_reason` returns "unknown language: X".
  - **Duplicate charges** — scrolls may list the same `spell_id` more than once
    (each entry = one charge); spellbooks still reject duplicates.
  - **Scroll rows in the unified spell list** — `spell_lists_view` folds scrolls
    via `_scroll_spell_rows` into the same `SpellRow` model used for class spells
    and innate abilities. `ready` = charge count, `castable`/`block_reason` from
    `scroll_cast_block_reason`. Locked pips + block reason render for non-castable rows.
- **Rest** (`/rest/night`, `/rest/full-day`) calls `reset_powers` + slot restore;
  full-day adds 1d3 healing; rest blocked when dead.

### Mental powers caster type

`mental` is a third caster type. No slot levels — a daily-use pool counter.
`spells_view`/`spell_lists_view` skip mental; a separate `mental_powers_view` →
`MentalPowersBlock` drives the Mental Powers section (pool pips, Use/Restore/
Reset, known-power list). Routes `/powers/{learn,forget,spend,restore,reset}`.
Kineticist is the only mental class (`data/classes/kineticist.yaml`, source
`carcass_crawler_1`, all on `data/spells/carcass_crawler_kineticist_powers.yaml`).

### Innate daily-use abilities (`aose/engine/innate.py`)

Non-caster analogue of the mental-power pool. A `ClassFeature` or `RaceFeature`
(or chosen `ChoiceOption`) carries `daily_uses: DailyUses` (`per_day: int` and/or
`scales_with_level: bool`). `innate_abilities(spec, data)` iterates `iter_reached`
and collects every feature with `daily_uses`, resolving the max against the
granting class's level. `CharacterSpec.innate_uses: dict[str, int]` tracks
uses-spent; `spend_innate`/`restore_innate`/`reset_innate` mutate it.
Routes `/character/{id}/innate/{spend,restore,reset}` mirror the powers routes.
`rest_night` and `rest_full_day` call `reset_innate`. Innate abilities that carry
a `spell_id` pointing to an arcane or divine spell are **routed into the unified
spell list** (`_routed_innate` → `spell_lists_view`) as `SpellRow` entries with
`source_kind="innate"`, labelled by their source (class/race). Non-spell innate
and mental-only spells remain in the "Innate Abilities" block. The sheet renders
each innate row as a pip row (ready/spent) that opens a `modal-innate-{id}`
overlay carrying Use/Restore forms. The actions **must** live in that standalone
modal, not inline in the row — the global overlay click handler intercepts any
click inside a `[data-modal]` trigger with `preventDefault`, so an inline Use
button would never submit.

### Carcass Crawler 2 / 4 / 5 content (`source: carcass_crawler_{2,4,5}`)

Pure-data import (no new mechanics — same shape as the CC1 duals). **Classes:**
Wood Elf (CC2, 10-level race-as-class, `spell_lists: [druid]` from L1, missile
`attack +1 ranged`, detect-secret-doors / ghoul-immunity / hiding text), Halfling
Hearthsinger (CC4, 8-level, `race_locked: halfling`, no caster, Foster-Friendship /
Lore / Read-Languages skill tables as feature text, Defensive Bonus `ac +2
large_attacker`), Halfling Reeve (CC4, 8-level, `race_locked: halfling`,
`allowed_alignments: [law]`, `spell_lists: [druid]` from L4, Goblin Slayer /
Wolf Hunter as conditional `attack`/`damage +1` grants — surfaced in the
conditional-attack breakdown), Arcane Bard (CC4, 14-level, **not** race-locked,
`spell_lists: [magic_user]` from L2, CS/HN/PP/RL skill tables), Ratling (CC5,
8-level race-as-class, semi-martial, skill tables, Prehensile Tail / Rat Affinity
text), Changeling (CC5, 10-level race-as-class, Back-Stab + Shape-Stealing text,
BE/HN/HS/MS skill tables). **Races:** Wood Elf (–1 CHA +1 WIS), Ratling (–1 CHA
+1 DEX), Changeling (–1 CON +1 CHA) — split-mode duals carrying their own grants.
New language: `dryad` (Wood Elf). The percentage/d6 skill tables are **feature
text only** (no skills engine), matching the acrobat/thief precedent.

### Carcass Crawler 3 content (`source: carcass_crawler_3`)

**Classes:** Beast Master (14-level, no race-lock, animal companion / speak-with-
animals), Dragonborn (10-level, breath weapon ×3/day, Scales +1 AC, `feature_choices:
draconic_bloodline` — pick/roll 1 from 5 colour options, each granting a
`save:vs:<type>` bonus), Mutoid (8-level race-as-class, `feature_choices: mutations`
— pick/roll 2 from 8, some granting synthetic weapons, one granting +2 AC),
Mycelian (6-level race-as-class, no armour, natural AC table via level-scaled `ac
set`, `fists` with `damage_per_level_die: d4`, `fungal_spores` with
`scales_with_level: true`), Tiefling (10-level race-as-class, `feature_choices:
fiendish_gifts` — pick/roll 2 from 10 innate spell-grants with `daily_uses`,
`feature_choices: fiendish_appearance` — 2 cosmetic-only flavour traits). **Races:**
Dragonborn, Mutoid, Mycelian, Tiefling — mirrors of the race-as-class content for
`separate_race_class` mode; no new languages beyond `deepcommon` (already present).

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

- **Inventory shapes** — `CharacterSpec.items: list[ItemInstance]` is the single
  flat list for all owned gear (plain, enchanted, and ammo). Each `ItemInstance`
  carries: `instance_id: str` (uuid4 hex), `catalog_id: str`, `location:
  StorageLocation` (default `carried`), `equip: str | None` (`"armor"`,
  `"main_hand"`, `"off_hand"`), `count: int`, `enchantment_id: str | None` (non-None
  → enchanted item), `loaded_ammo_id: str | None` (ranged weapon with loaded ammo).
  The old `inventory: list[str]` / `stashed: list[str]` / `equipped: dict[str, str]`
  / `loaded_ammo: dict` / `armor_tailored: bool` / `spec.enchanted` / `spec.ammo`
  side-tables are gone — equip-state, stack count, and location are fields on the
  instance. `armor_tailored` is now `ItemInstance.tailored: bool = True` on the
  body-armour instance. A weapon is equippable into `main_hand` when an instance with
  that `catalog_id` exists at `carried` and the slot is empty (or into `off_hand` with
  the `two_weapon_fighting` rule + `two_weapon_eligible` + `off_hand_eligible`). Hand
  budget: each item costs 1 or 2 hands (`hand_cost`); total cannot exceed 2. Gargantua's
  `one_handed_two_handed_melee` feature flag reduces two-handed melee weapons to 1 hand.
  Equip/unequip/validation go through `aose/engine/equip.py` (`equip()`, `unequip()`,
  `validate_wield()`). Slot accessors: `equipped_instance(spec, slot)`, `slot_item(spec,
  slot, data)`, `equipped_ref(spec)`. Sheet renders Equipped / Carried / Stashed by location.
- **StorageLocation** — `aose/models/storage.py` defines `StorageLocation(kind, id)`
  (`LocationKind = Literal["carried","stashed","animal","vehicle","container"]`) as a
  frozen pointer to where a value-stack (coins/gems/jewellery) or a container lives.
  `id` is the carrier/container `instance_id`; None for person-level buckets. Moving
  the container moves its contents for free — no per-item bookkeeping.
- **Containers** — `Container` catalog variant (`item_type: container`,
  `capacity_cn`, `weight_multiplier`) + per-instance `ContainerInstance`
  (`instance_id`, `catalog_id`, `location: StorageLocation`) on
  `CharacterSpec.containers`. Container's location may be carried/stashed/animal/vehicle —
  never "container" (no nesting). Carried containers contribute `own_weight +
  int(multiplier × raw_contents)` — a Bag of Holding (×0.06) at 10 000 cn weighs
  600 cn. Container contents now include coins/gems/jewellery stowed inside (counted
  via container, not as top-level treasure). Capacity uses raw item weight.
  `move_container(spec, id, dest)` in `storage.py`. UI: inline collapsible rows,
  button/dropdown-only.
- **Movement engine** — `aose/engine/storage.py` is the single movement vocabulary
  and the single front door for all owned-thing movement. Public API:
  `move_thing(spec, category, ref_id, dest, *, count=None, src=None, data=None)` —
  dispatches on `category` (`item`, `container`, `coin`, `gem`, `jewellery`, `magic`,
  `enchanted`, `ammo`, `source`). Also: `add_item` (the single stackable-aware add
  front door — `add_item(spec, catalog_id, count, loc, data)` appends or merges into
  an existing same-`catalog_id` stack at `loc`, used by buy/grant/kit so the merge rule
  lives in one place), `consume_item(spec, instance_id)` (removes exactly one unit from
  a stacking item and prunes the stack at zero, clearing any weapon's `loaded_ammo_id`
  when its last ammo is spent — searches the PC world then every retainer world),
  `move_container`, `move_coins`, `add_coins`, `convert_coins`, `move_valuable`. All
  mutate `spec` in place. `StorageError(ValueError)` routes to HTTP 400.
- **World-aware container resolution** — a container's contents and capacity are read
  in the *world that owns the container*, not always the PC's. `_container_owner(spec,
  container_id, data)` finds whether a `StorageLocation(kind="container")` target lives
  in `spec` or in some `retainer.spec`, and returns that owning spec; capacity checks
  and content listing run against it, and a cross-world move (PC item → a
  retainer-owned backpack, or back) lands the item in the destination's owning world.
  This is what fixed bug 3 (`no container with id` / over-fill counted against the wrong
  world). `_check_capacity(spec, dest, added_cn, data)` is the single
  capacity gate: validates container/animal/vehicle load against the resolved owner;
  skips when `dest.kind` is `carried`/`stashed`/`retainer` or when `data is None`.
  `location_load_cn(spec, loc, data)` is the shared carrier-load helper used by both
  `_check_capacity` and the encumbrance container loop. The old per-category helpers in `shop.py`
  (`stash`/`unstash`/`stow`/`take_out`/`stash_container`/`unstash_container`) and
  the companions load/unload helpers (`load_onto_animal` etc.) are deleted; every
  move goes through `move_thing`. HTTP front door: `POST /inventory/move` (character
  sheet) and `POST /wizard/{id}/inventory/move` (wizard). Imports only models +
  currency — no cycle risk. `encumbrance` ↔ `storage` cross-imports stay
  function-local to avoid cycles.
- **Stackable gear** — `AdventuringGear.bundle_count: int = 1`. `buy_item()` grants
  `bundle_count` units for one price (auto-merges into an existing carried stack);
  `add_free_item()` grants one bundle free. Sell removes 1 unit, returns
  `int((cost_gp / bundle_count) / 2)`; refund removes a full bundle, returns
  `cost_gp`. Gear data is book-faithful; the encumbrance engine uses a flat **80 cn**
  for any `AdventuringGear` item, so per-item `weight_cn` is dead data and is not
  fabricated.
- **Encumbrance** (`aose/engine/encumbrance.py`) — two AOSE-faithful modes.
  **Basic** = `_BASIC_TABLE{(armour_cls, carrying_treasure)} → move` (over-1600
  treasure → immobile; `CharacterSpec.carrying_treasure` toggle). **Detailed** =
  single-axis by total weight (bands 400/600/800/1600 → 120/90/60/30/0'); total =
  `treasure_weight_cn` + `equipment_weight_cn`. Encumbrance counts only **Carried**
  coins and valuables (not stashed, not on carriers). Container weight calculated via
  `location_load_cn(spec, carried_loc, data)` from `storage.py` — same helper used
  by `_check_capacity`, so container load is a single definition. Magic items band on
  `banding_weight_cn` (raw − `carry_capacity_bonus`) while displaying raw carried
  weight; enchanted armour weighs half. `EncumbranceTable` reshaped accordingly.

---

## Currency, treasure & valuables

- **Located coin stacks** — `CharacterSpec.coins: list[CoinStack]`. Each
  `CoinStack(denom, count, location: StorageLocation)` is at most one stack per
  `(denom, location)` — empty stacks are pruned by the movement engine.
  `aose/engine/currency.py`: `DENOMINATIONS`/`RATES`,
  `carried_coins`, `total_value_cp`, `total_value_gp` (all locations, for wealth
  readout), `coin_count(carried_only=True)` (encumbrance weight — Carried bucket
  only), `convert_amount` (pure: raises `CurrencyError` on non-whole result). Routes:
  `/coins/add` (grants into a location), `/coins/convert` (per-stack conversion),
  `/inventory/move-coins` (transfer between locations).
- **Shop spend** — `shop.spend(spec, cost_gp)` debits **Carried** coins only,
  lowest-denomination-first. Tries exact payment first; if unavailable, pays the
  smallest whole-gp overshoot and returns change in gp. Raises `InsufficientFunds`
  (HTTP 400) when total carried value < cost. `buy_item`/`add_free_item`/`sell_instance`/
  `sell_container` are spec-mutating helpers that operate on `spec.items` (and
  `spec.containers` for containers). `sell_instance` is instance-keyed; the old
  catalog-keyed `sell_item`/`sell_from_stash` have been deleted.
- **Treasure weight** — gems 1 cn, jewellery 10 cn (**Carried only** — stashed /
  on-carrier treasure adds zero to PC encumbrance). Carried treasure magic items:
  potions 10 / wands 10 / rods 20 / staves 40 / scrolls 1, derived by category +
  id-prefix in `treasure_item_weight`. Magic items, enchanted gear, and ammo are also
  **Carried-only** for encumbrance: only instances at `StorageLocation(kind="carried")`
  or stowed inside a carried container count toward PC load.
- **Gems & jewellery** — `GemStack` + `JewelleryPiece` each carry a
  `location: StorageLocation` (default Carried). `add_gem`/`add_jewellery` accept an
  optional `location` param. `valuables_weight_cn` counts only Carried gems/jewellery.
  `total_value` sums all locations (for the wealth readout). `total_wealth_gp` (in
  `valuables.py`) = `total_value_gp(spec)` + `total_value(spec)`, excluding retainers
  (they own their own purse). Route `/inventory/move` re-homes gem stacks
  (merging same-value/label stacks at destination) or jewellery pieces via `move_thing`.
- **Top-level inventory groups** — `sheet.inventory_groups: list[TopLevelGroup]`
  (Carried, Stashed, one per animal, one per vehicle, one per retainer) with
  `loose`, `coins`, `treasure_gems`, `treasure_jewellery`, `containers`, `magic_items`,
  `enchanted`, `spell_sources`, `ammo` sub-lists, plus rich display lists
  `equipped_attacks` (AttackProfile), `equipped_worn` (EquippedRow), `equipped_magic`
  (MagicItemView). `magic_items`/`enchanted`/`ammo` are **location-bucketed**: each
  group contains only the instances whose `StorageLocation` matches that group's owner.
  Container views (`ContainerView`) additionally carry `stowed_magic`, `stowed_enchanted`,
  `stowed_ammo`, `stowed_coins`, `stowed_gems`, `stowed_jewellery`, `stowed_spell_sources`
  sub-lists for pointer types stored inside that container. Each group carries an `OwnerCaps` descriptor
  (`has_equipped`, `can_wield`, `can_stash`, `class_filter_equip`, `bucket_label`) that
  drives the three-section pane layout (Equipped · Coins · Carried/Stowed) without any
  per-owner template branches. `build_inventory_groups(spec, data)` in
  `aose/sheet/view.py` builds this. `sheet.total_wealth_gp: int` for the wealth
  readout. The inventory box is the single interaction hub: every owned-item action
  (equip/unequip, stash/unstash, move, use-as-container) is performed from here;
  `use_as_container(spec, owner, item_id, data)` in `aose/engine/storage.py` promotes
  a loose Container string to a `ContainerInstance`. The box renders as a collapsible
  accordion (one `<details class="inv-pane">` per group, Carried open by default).
  Spells / Mental Powers / Innate Abilities in a full-width `.spells-fullwidth` grid
  below. Companions cards no longer hold storage UI — all carrier/retainer inventory
  is visible in the accordion. All container/item/pointer-type moves go through the
  single route `POST /inventory/move`. Retainer containers are handled via
  `_find_container_anywhere` (searches `spec.containers` then all
  `retainer.spec.containers`). Per-item modals (`item_modal` in `_inv_modals.html`)
  expose **Sell ▾ + Drop** for the person buckets (carried/stashed) on top of the
  gated equip/move actions; carrier & retainer loose rows keep Move + their gated
  equip only.
- **Coin / gem / jewellery modals** — coin stacks, gem stacks, and jewellery pieces
  in the box are **clickable → per-stack modals** (`coin_modal` / `gem_modal` /
  `jewellery_modal` in `_inv_modals.html`), rendered per non-retainer group in
  `sheet.html`. Coin modal: Convert ▾ (`/coins/convert`), Move ▾ (`/inventory/move`),
  Adjust / Drop-all (`/coins/add`, signed). Gem modal: Sell one / Sell all
  (`/gems/sell`, `/gems/sell-all`), ±1 (`/gems/adjust`), Move ▾ (`/inventory/move`),
  Drop (`/gems/remove`). Jewellery modal: Mark damaged/intact
  (`/jewellery/toggle-damaged`), Sell (`/jewellery/sell`), Move ▾, Drop
  (`/jewellery/remove`). All Move controls use the unified `act_move` macro from
  `_actions.html`; destination list comes from `move_targets(spec, data)` (a flat
  `[{kind, id, label}]` covering all carriers + containers + stash). Magic item modals
  also gain Move ▾ for unequipped/stowed items. Coin weight still appears only for
  Carried; the pane summary bar shows a `count denom` inline tally. The wizard box
  passes `manage_treasure=False` to `inv_pane` (no draft-scoped treasure routes), so
  its treasure rows stay non-clickable. Retainer treasure stays display-only (lives in
  `retainer.spec`, no PC-scoped route).
- **Action dispatcher** — `aose/engine/inventory_actions.py` is the single code path
  for equip/unequip/sell/charge/note across all three item substrates (`item` plain,
  `enchanted`, `magic`). The five POST routes `/inventory/{equip,unequip,sell,charge,note}`
  (plus `/inventory/move`) are registered on both the character-sheet router and the
  wizard router; the old `/equipment/equip|unequip|equip-magic|…|equip-enchanted|…`
  routes have been deleted. Templates post `category` + `instance_id` (+ `mode`/`op`/`note`);
  the dispatcher branches on `category`. `consume_item` has its own `POST
  /inventory/consume` route (remove one unit of a stacking item). A contract test
  (`tests/test_inventory_box_contract.py`) guards the template↔route field contract so
  the silent-404 class of bug cannot recur; it also asserts that every per-instance
  action form rendered for container/animal/retainer contents carries a **non-empty**
  `instance_id`/`item_id`/`denom` (the regression guard for the bug where a contents row
  submitted `no item instance ''`).
- **Single per-instance row + `stack_actions` macro** — `_instance_row(inst, data, …)`
  in `aose/sheet/view.py` is the *one* function that builds a per-instance row view; the
  same source feeds loose rows, carrier/retainer rows, and container contents, so equip
  eligibility and action wiring are defined once. On the template side, `stack_actions`
  (in `_actions.html`) is the canonical stackable UI: one qty number-box that JS copies
  into the hidden `count` of the chosen action, then a Move dropdown (auto-submits) plus
  optional Sell / Drop / Consume forms. Items, ammo, coins, and gems all render through
  it — there is no per-substrate stack UI. **Known boundary:** gems support move-by-count
  through `stack_actions`, but `/gems/sell` still sells the whole stack (the route takes
  no `count`), so gem sell-by-count is not yet wired.
- **Move-route robustness** — `_loc(kind, id)` in `routes.py` builds the
  `StorageLocation` for `POST /inventory/move` (and `/coins/add`, `/coins/convert`),
  mapping a bad/empty kind to HTTP 400 (Pydantic `ValidationError` would otherwise
  surface as 500). The single `move_thing(spec, category, …)` dispatcher in
  `aose/engine/storage.py` handles all owned-thing categories (`item`, `container`,
  `coin`, `gem`, `jewellery`, `magic`, `enchanted`, `ammo`).
- **Shared action controls** — `aose/web/templates/_actions.html` provides three
  macros imported `with context` by every modal template: `act_button` (one-shot form
  button with `.btn` size/variant classes), `act_move` (move-form using the flat
  `move_targets` list from context), `act_stepper` (±1 stepper, two submit buttons on
  one form). Button sizes follow a CSS scale: `.btn` (modal default 10px), `.btn-inline`
  (row/inline-form 9px), `.btn-tool` (toolbar 9px, light-on-dark), `.btn-cta` (wizard
  CTA 11px); `.btn.tool` is aliased to `.btn-tool` for call-site compatibility.

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
  list[str]`. Roll-first: `GET /identity` never auto-rolls; `POST
  /identity/skill-roll` performs the roll (strict locks after one press; non-strict
  allows re-roll). `POST /identity` requires the skill to be present before
  advancing; non-strict accepts a manual dropdown override.

---

## Characters, leveling & play state

- **Multi-classing** — free-form (Multiple Classes optional rule; no combo
  allowlist). Wizard offers up to 3 classes when `multiclassing` +
  `separate_race_class` are on, each gated by ability requirements +
  `demihuman_class_restrictions`. **XP is per class** (`ClassEntry.xp`, not a
  global). `grant_xp(spec, data, amount)` (`leveling.py`) splits evenly, scales
  each share by that class's prime-requisite multiplier, floors, clamps ≥ 0;
  clawbacks split evenly without the multiplier.
- **Prime-requisite XP bonus** — `prime_req_bonus_pct(cls, abilities)`
  (`leveling.py`) is the single source of the +5%/+10% experience adjustment
  (`_prime_req_multiplier` = `1 + pct/100`; `ClassAdvancement.xp_bonus_pct`
  surfaces it on the sheet's XP track). AOSE states this rule *per class*, and
  multi-prime classes vary (one ≥13 vs both ≥13 vs a specific ability ≥16, …),
  so it is **data-driven**: each multi-prime `CharClass` carries
  `xp_bonus_tiers: list[XpBonusTier]`, an ordered list of `{bonus_pct, any_of}`
  tiers where `any_of` is OR-of-AND requirement sets (`{AB: min, …}`). The
  highest satisfied tier wins; no match → no adjustment (tiered classes carry
  **no** low-score penalty — the book states only bonuses for them). Classes
  with no tiers (single-prime, or none) fall back to the standard single-ability
  XP table on the lowest prime score — the only path that still applies the
  −10%/−20% low-score penalty. **HP** recomputes from raw rolls + effective CON: per gain-event
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
  Advanced Fantasy + Carcass Crawler 1–5, Necrotic Gnome). A
  `source` field on `ItemBase`/`Race`/`CharClass`/`SpellList`/`Enchantment`/
  `Spell` defaults to `ose_classic_fantasy`; only non-Classic entries carry their
  own id. `CONTENT_CATEGORIES = ("classes", "equipment", "magic_items")` in
  `aose/models/ruleset.py`. `RuleSet.disabled_content: list[str]` stores
  `"{source_id}:{category}"` keys for disabled content; Classic is never added.
  `aose/engine/sources.py`:
  `CLASSIC_SOURCE_ID`, `content_enabled(source_id, category, ruleset)`,
  `source_content_categories(data)` (derives categories from loaded data — no
  per-item tagging). Gated in wizard race/class steps, spell candidates,
  `shop_categories`, `_enchant_choices`. Mid-wizard, changing `disabled_content`
  clears orphaned race/class picks via `_apply_rule_changes`.
- **Optional rules** — every flag in `RuleSet` is integrated end-to-end. The
  settings page never renders a "pending" badge (a regression test guards this).
- **Manual rolls + Strict Mode** — abilities, HP, starting gold, per-table feature
  choices, and the secondary skill each require a deliberate Roll press. Strict Mode
  (default `True`) locks each roll after one press; off = free re-rolls. A hopeless
  ability set (`subpar` or any score 3) re-enables the Roll button under strict.
  Back-nav gates: rolling abilities locks the rules step; rolling HP locks every
  step before HP (`class_setup`) — gates show a 🔒 breadcrumb state.
  `draft["hp_blessed_sets"]` (draft-only, never persisted) stores both Blessed HP
  sets so Class Setup can bold the higher.
- **Class Setup — consolidated advance** — `POST /{id}/hp` is the single "Next"
  handler. Sections present in the consolidated form declare themselves via hidden
  `<input name="section" value="...">` markers (values: `proficiencies`, `spells`,
  `features`); the handler runs `_apply_proficiencies` / `_apply_spells` /
  `_apply_feature_overrides` for each declared section, then saves and advances via
  `_next_incomplete_step`. The per-section routes (`/proficiencies`, `/spells`,
  `/feature-choices`) remain for backward-compat. Client-side `csValidate` enables
  the Next button only when all selection counts match their server-declared
  requirements (`data-required` attributes on `.prof-table` and `.card-grid`).
  `draft["_feature_choice_group_ids"]` (set at class-pick time) lets
  `_feature_choices_complete` determine completeness without threading `data` into
  `_next_incomplete_step`. `feature_choices_done` is retired.

---

## Sheet & UI

- **Zine sheet** — `aose/web/templates/sheet.html`: identity band, 3-column grid
  (combat+abilities, features+notes, spells/powers — column 3 opens for
  `sheet.spell_lists or sheet.mental_powers`), full-width inventory/currency/treasure
  group, footer. Groups have inked bars + internal scroll.
- **Design system** — `aose/web/static/sheet.css` (Oswald + Bitter, self-hosted
  woff2 under `aose/web/static/fonts/`). **Read `docs/STYLE-GUIDE.md` before any
  sheet/UI work** — tokens, components, the overlay model, and hard-won invariants
  (closed-overlay `pointer-events`, variable-font self-hosting, `no-cache` static).
- **Overlay controller** — `aose/web/static/sheet_overlays.js`: single-open
  drawer/modal/popover, dismissed by Esc/scrim/close.
- **Acquisition drawer** — `_equipment_ui.html` is acquisition-only: Shop (always,
  default open), Enchant (gated `magic_acquisition`), Scribe (gated `spell_sources`),
  Treasure (gated `valuables`; **acquisition only** — Add-coins / Add-gem / Add-jewellery
  forms; management of existing stacks moved to the box's per-stack modals).
  An "Other Possessions" add-form in the Shop footer adds custom text items to Carried.
  All owned-item management (equip/stash/move/sell) is in the inventory box, not the
  drawer. The wizard equipment step renders the inventory box above the drawer and a
  "Next: Review" continue button below (only the Shop tab is available in the wizard).
- **Print sheet** — `sheet_print.html` mirrors the live sheet; conditional AC/
  attack/save lines and situational `vs:*` bonuses appear as footnotes.
- **`build_sheet(spec, data) -> CharacterSheet`** (`aose/sheet/view.py`) assembles
  every derivation. Block models (`SpellListBlock`, `SpellListLevel`, `SpellRow`,
  `MentalPowersBlock`, `ACBreakdown`, `AttackBreakdown`, `SaveBreakdown`,
  `EncumbranceTable`, etc.) live alongside it / in their engine modules.
  `spell_lists_view` returns one `SpellListBlock` per caster type (arcane/divine),
  merging class spells, scrolls, and spell-backed innate abilities into a single
  `SpellRow` list per level. Source labels show only when a block has 2+ distinct
  sources (`show_labels`). The macros `spell_row`/`spell_modal` in
  `aose/web/templates/_spells.html` render every row uniformly.
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
- **Wizard card detail surfaces** — race/class cards open a shared zine
  `#wizard-detail` overlay (`wizard.html`) whose body is built by `aose/web/book.py`
  (`class_entry`/`race_entry`/`spell_entry`) and rendered by the `book_entry` macro
  (`_book_entry.html`). Modal Select drives client-side selection (radio/checkbox
  check + grid collapse); Clear restores the grid; multiclass grid collapses at the
  cap (`data-multi`/`data-cap`). The spells step renders the same `book_entry` inline
  as per-card expanders with a Learn/Forget toggle and slot cap. Controller:
  `aose/web/static/wizard_cards.js`; styles: `wizard_cards.css` (reuses zine tokens,
  wizard-only).

---

## Hosting & auth

All auth behaviour is **off by default**. When `AOSE_AUTH` is not set (or `0`)
the app is identical to the local-only single-user build — zero behaviour
change. Auth is enabled by setting `AOSE_AUTH=1`.

- **`AuthConfig.from_env()`** (`aose/web/auth/`) returns `None` (auth off) or an
  `AuthConfig` instance (auth on). The `create_app()` factory accepts an optional
  `auth_verifier` keyword for testing; production uses `FirebaseVerifier`.
- **`WorkspaceAuthMiddleware`** is the single integration point. It resolves
  `request.state.{characters_dir, drafts_dir, settings_path}` from
  `resolve_workspace(request)`. Auth-off: mirrors the global root dirs
  (`characters/`, `drafts/`, `settings.json`). Auth-on: derives
  `users/<uid>/characters/`, `users/<uid>/drafts/`, `users/<uid>/settings.json`
  from the session cookie. All route handlers read these three state attrs and
  never touch the raw filesystem paths directly.
- **Per-user workspace** — `users/<uid>/` at the project root mirrors the root
  layout (characters/, drafts/, settings.json). Keyed by GCIP uid;
  `safe_uid(uid)` strips any path-traversal characters before the directory is
  created. First login is seeded with example characters via
  `seed_user_workspace(uid)`.
- **GCIP Google-only sign-in** — the `/login` page loads the Firebase JS SDK
  from CDN (the one exception to the server-rendered-only ethos) and triggers a
  Google OAuth pop-up. The resulting ID token is POSTed to `/auth/verify`, which
  calls `FirebaseVerifier` (wraps firebase-admin, lazy-imported to keep the
  auth-off path import-free) → `Whitelist` check → sets a signed
  `SessionMiddleware` cookie (itsdangerous).
- **Whitelist** — `whitelist.txt` at the project root (gitignored). Read fresh
  per request. Lines starting with `#` and blank lines are ignored. Every
  Google-authenticated user whose email is not listed receives a 403. This is
  the sole invite gate — no email is sent at any point, no SMTP/DNS dependency.
- **`FakeVerifier` test seam** — inject via `create_app(auth_verifier=FakeVerifier({email: uid, ...}))`.
  Tests never need firebase-admin installed; the real verifier is only imported
  when `AOSE_AUTH=1` in production.
- **Firebase emulator for offline dev** — set
  `FIREBASE_AUTH_EMULATOR_HOST=localhost:9099` and both the Firebase JS SDK
  (frontend) and firebase-admin (backend verifier) route to the local emulator.
- **Export / import** — `GET /character/{id}/export` returns a JSON download of
  the full `CharacterSpec`. `POST /import` accepts a JSON file upload, validates
  it as a `CharacterSpec`, saves it under a new id, and redirects to the sheet.
  These routes work in both auth-on and auth-off modes and provide a self-serve
  backup / escape hatch.

---

## Companions & Holdings

Animals and vehicles are first-class storage locations owned by a character,
each with its own capacity that never contributes to the PC's encumbrance.

**Item variants** (`aose/models/item.py`): three new discriminated-union members —
`Animal` (hd, hp, ac, attacks, morale, load limits), `Vehicle` (hull_points,
cargo_capacity_cn, vehicle_category), and `AnimalArmor` (sets_ac, fits list).
All three are catalog items purchasable through the existing shop machinery.

**Roster instances** (`aose/models/character.py`): `AnimalInstance` and
`VehicleInstance` mirror `ContainerInstance`. Each has `instance_id`,
`catalog_id`, a mutable `name`, damage/hull fields, and a `contents: list[str]`
of loaded item ids. `ContainerInstance` gains `location` + `location_id` so a
container can be placed *on* an animal or vehicle (excluded from PC encumbrance).
`CharacterSpec` carries `animals: list[AnimalInstance]` and
`vehicles: list[VehicleInstance]`.

**Monster-stats engine** (`aose/engine/monster_stats.py`): HD string → THAC0,
attack bonus, and all five save scores. Two YAML lookup tables are loaded by
`GameData`: `data/monster_attack_matrix.yaml` (16 HD bands) and
`data/monster_saves.yaml` (9 HD bands). The engine imports only `models` and
`loader` — no cycle risk.

**Catalog data**: `data/equipment/animals.yaml` (7 animals: camel, draft/riding/
war horse, mule, hunting/war dog), `data/equipment/vehicles.yaml` (16 land and
water vehicles), `data/equipment/tack.yaml` (dog armour, horse barding,
saddle & bridle, saddle bags container).

**Companions engine** (`aose/engine/companions.py`): buy/remove animals &
vehicles (deducting/refunding gold), assign/clear animal armour, load/unload
loose gear onto a carrier (capacity-checked), move a container between person
and carrier. `encumbrance.py` and `shop.py` skip containers whose `location !=
"person"`.

**Sheet view** (`aose/sheet/companions_view.py`): `companions_block(spec, data)`
assembles `AnimalCard` and `VehicleCard` view models — derives ascending AC
(overridden by equipped armour), THAC0/attack bonus, and saves from catalog stats
— and attaches resolved `InventoryRow` contents. Returns `None` when the
character has no companions. `CharacterSheet.companions` carries this block.

**Acquisition**: animals/vehicles share the normal shop catalog (grouped by their
`category`), so the generic `POST /character/{id}/equipment/buy` route is the buy
path. `equipment_buy` dispatches on item type — `Animal` → `buy_animal`,
`Vehicle` → `buy_vehicle` — creating a roster instance instead of an inventory id
(alongside the existing `Ammunition`/`Container` branches). Without that dispatch
a purchased carrier would fall through to `shop_buy` and land in carried
inventory. Dedicated `POST /character/{id}/animal/{buy,remove,rename,hp,armor,load,unload}`
routes and the parallel vehicle set (hull, extra-animals toggle) handle play-state
mutation. All follow the standard `_load_spec_or_404` → mutate → `save_character`
→ 303 pattern.

**Sheet UI** (`aose/web/templates/_companions.html`, included from `sheet.html`):
a zine `group full` ("Companions & Holdings" inked bar) rendered as a **collapsed
ledger** — one `<details class="crow">` row per retainer/animal/vehicle, ordered
Retainers → Animals → Vehicles (most-consulted first). The whole collapsed
`<summary>` shows only at-a-glance fields (name, descriptor/species/kind, loyalty
[red ≤ 4 via `.crow-loy-v.low`], and an HP/Hull stepper); the full stat block
(AC, THAC0, all five saves, movement, morale, traits/gear, controls) lives in the
`.crow-body` revealed on expand. The stepper `<form>` carries
`onclick="event.stopPropagation()"` so +/− submits without toggling the
disclosure. `static/companions.js` persists which rows are open across the
full-page POST reloads via `localStorage`. Ledger CSS (`.crow*`, `.cstat*`,
`.csave*`, `.csubbar`) lives above the `LEGACY` banner in `sheet.css`; the old
`.companion-*` card rules were removed. Print sheet includes a static text block
in `sheet_print.html`.

### Phase B — Retainers

Hired classed NPCs (and 0-level normal humans) stored as embedded `CharacterSpec`s
inside the hiring PC's `CharacterSpec.retainers: list[Retainer]`. Each `Retainer`
carries a `spec`, `loyalty: int`, `role: str`, and a uuid4 `id`.

**`Retainer` model** (`aose/models/character.py`): defined after `CharacterSpec`
with `CharacterSpec.model_rebuild()` to resolve the forward reference.

**`RetainerHiringRule`** (`aose/models/character_class.py`): `{min_level, allows}`
entries on `CharClass.retainer_hiring`. `allows` is `"any"`, `"none"`, or a list
of class ids. Only `assassin.yaml` carries non-default rules; all other classes
default to unrestricted hiring.

**`normal_human` class** (`data/classes/normal_human.yaml`): max_level 1, 1d4 HP,
THAC0 20, weakest saves. Excluded from the wizard class list. Used as the starting
class for 0-level retainer hirelings; `promote_normal_human` replaces it with a
real class at L1 (keeping accumulated XP).

**Retainers engine** (`aose/engine/retainers.py`):
- `allowed_retainer_classes(hiring_spec, data)` — returns `"any"` or a `set` of
  class ids (empty = may not hire) derived from `retainer_hiring` rules on the PC's
  class. This is the AOSE per-class hiring tier, orthogonal to content/edition gates.
- `retainer_class_ids(hiring_spec, data)` — the single source of truth for what a
  retainer may be hired as: `normal_human` always, plus every class that is
  content/edition-available (`class_available` from `engine/sources`) AND permitted
  by `allowed_retainer_classes`. Used by the sheet option builder and the hire route.
- `initial_loyalty(hiring_spec, retainer_race_id, data)` — CHA base + racial
  modifiers (`retainer_loyalty_modifier` in race/class features; `except_same_race`
  flag for half-orc). Race-as-class double-counting is prevented in `_features_with`.
- `generate_retainer(...)` — rolls baseline-10 abilities, applies racial mods (in
  Advanced/split mode only; optional human benefits applied when `human_racial_abilities`
  is on), bumps to class minimums, rolls HP per level, assigns quick-equipment kit.
  Retainers are always single-class regardless of the `multiclassing` rule.
- `grant_retainer_xp(retainer, data, amount)` — halves positive XP (−50% rule)
  then delegates to `leveling.grant_xp`.
- `promote_normal_human(retainer, new_class_id, data)` — replaces the normal_human
  ClassEntry in-place, re-rolls HP, reassigns kit.
- `transfer_to_retainer` / `transfer_to_pc` — move a single item id between the
  PC's `inventory` and the retainer's `spec.inventory`.

**Hiring follows the PC's edition and content rules:**
- **Basic** (`separate_race_class` off): all classes offered including race-as-class
  demihuman entries; no separate race is chosen (race-as-class entries carry their own
  race via `race_locked`; standard classes are human).
- **Advanced** (`separate_race_class` on): class and race are chosen separately;
  race-as-class entries are excluded; demihuman `allowed_classes` and `class_level_caps`
  are enforced at the route (governed by `lift_demihuman_restrictions`); optional human
  benefits apply to human retainers when `human_racial_abilities` is on.
- **Content gate**: classes and races from a `disabled_content` source are excluded.
  Shared predicates in `engine/sources.py` (`class_available`, `race_available`,
  `class_allowed_for_race`, `class_level_cap`) are consumed by both the wizard and
  the retainer layer — one source of truth.

**CHA accessors** (`aose/engine/ability_mods.py`): `max_retainers(cha)` and
`base_loyalty(cha)` read from the existing `_CHA_RETAINERS_MAX` and
`_CHA_RETAINERS_LOYALTY` tables.

**Sheet view**: `_retainer_cards(spec, data)` recursively calls `build_sheet` on
each retainer spec (safe because `retainer.spec.retainers` is always empty).
`_with_retainers` attaches cards and `max_retainers` to `CompanionsBlock`; it
also returns a non-None block when `retainer_class_options` exist (so the add
form is visible even for PCs with no existing companions). `CharacterSheet`
gains `race_id`, `retainer_class_options: list[dict]`, and
`retainer_race_options: list[dict]` (non-empty in Advanced only; drives the
race `<select>` in the hire form).

**Routes**: 12 POST routes under `/character/{id}/retainer/` — `add`, `{rid}/remove`,
`{rid}/hp`, `{rid}/loyalty`, `{rid}/role`, `{rid}/xp`, `{rid}/levelup`, `{rid}/promote`,
`{rid}/give`, `{rid}/take`, `{rid}/equip`, `{rid}/unequip`. `{rid}/hp` adjusts the
retainer spec's `damage_taken` via the `hp` engine (the ledger HP stepper); `delta`
is signed (−1 damage, +1 heal), clamped to `[0, max_hp]`.

`{rid}/equip` reuses `equip.equip` (same engine as the PC), omitting
`allowed_weapons`/`allowed_armor` (NPCs — DM controls gear). `{rid}/unequip`
reuses `equip.unequip`. Both redirect to the character sheet on success.

**Animal barding unequip**: `POST /character/{id}/animal/{inst_id}/unequip`
wraps `companions_engine.clear_armor`, returning the barding to the PC's
carried inventory (same as setting `armor_id=""` via the armor select form).

**Live-sheet click-to-modal**: equipped rows in retainer and animal inventory
panes are now clickable (was only the PC's carried pane). `_inv_pane.html`
computes `eq_modal_prefix` per group kind (`"equipped"` for carried,
`"retainer-{id}-eq"` / `"animal-{id}-eq"` otherwise). Modals are emitted in
`sheet.html`; retainer loose-item modals use a per-retainer URL prefix so the
Equip action in `_inv_row_actions.html` targets the retainer's equip route.
