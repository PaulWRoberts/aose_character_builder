# Item Identity Unification — Design

**Date:** 2026-06-24
**Status:** Approved (design)
**Branch:** feat/item-identity-unification

## Problem

Equipping a weapon/armour on a retainer, then moving the carried item to another
inventory, leaves the item **both** equipped on the retainer **and** present at
the destination — a dupe (the retainer's AC/attacks still count the gone item).

The proximate cause is in `move_item` ([storage.py:196](../../../aose/engine/storage.py)):
the equipped-slot cleanup is hardcoded to the PC world — it only fires when
`src.kind == "carried"` and only touches `spec.equipped`/`spec.inventory`. A
retainer's own inventory is exposed as a single `kind="retainer"` location, so
the branch never runs, and even if it did it would patch the wrong spec.

But that is a symptom. The **root cause is an identity gap**: loose catalog items
are bare `str` ids in positional lists (`inventory`, `stashed`, every container/
animal/vehicle `contents`), so they have no per-instance identity. "Equipped" and
"loaded ammo" therefore live in **side tables** (`equipped: dict[str,str]`,
`loaded_ammo: dict[str,str]`) keyed by catalog id, and *every* removal/move path
must remember to patch those tables in lockstep. They drift. The
2026-06-23 unified-movement spec explicitly listed *"No flat-pointer rewrite of
catalog-item storage … loose catalog items stay identity-less strings"* as a
**non-goal** — this design closes that deferral.

The engine mints an instance only when forced to (scrolls, magic items,
enchanted gear, ammo, gems). That lazy boundary is the recurring source of
item bugs: two representations, two mental models, side tables that fall out of
sync.

## North-star invariant

**Every owned thing is an instance with identity.** It carries an `instance_id`
and a `location`; stackables additionally carry a `count`; equippables carry
their equip-state *as a field on the instance*. There are no side tables keyed by
catalog id, and no positional lists. One move path and one equip path operate on
instances regardless of owner (PC or retainer) or kind.

## Goals

- Give **loose catalog items** real instance identity (`ItemInstance`): id +
  location (+ count for stackables, + equip-state for equippables).
- Make **equipped** and **loaded-ammo** and **armour-tailored** *instance state*,
  deleting the `equipped` / `loaded_ammo` side tables and the `armor_tailored`
  spec field.
- Give **coin stacks** an `instance_id` so every stack moves by id through one
  vocabulary.
- Collapse loose storage to **one flat `items` list with location-as-field**,
  retiring the positional `inventory`/`stashed` lists and the `contents`
  sub-lists on containers/animals/vehicles.
- Define **stackable** formally (durable vs consumable) and make **move / sell /
  drop / use** uniform across every stackable.
- Route **PC↔retainer transfer** through the one move vocabulary, deleting the
  bespoke `transfer_to_retainer` / `transfer_to_pc`.
- Fix the reported dupe **structurally** (it falls out of the invariants), with a
  regression test that reproduces it.

## Non-goals

- **No single polymorphic collection.** We keep the existing typed lists
  (`magic_items`, `enchanted`, `ammo`, `gems`, `jewellery`, `spell_sources`,
  `coins`, `containers`, `animals`, `vehicles`); they already satisfy the
  instance contract. Unification is a *shared contract*, not one physical list.
  (Approach A from brainstorming; the "one collection" Approach B was rejected as
  a big-bang rewrite.)
- **No change to the two real equip mechanics.** Slotted (weapons/armour/shields
  → `armor`/`main_hand`/`off_hand`) and toggled (magic items → worn bool) are
  both genuine game concepts; we make both *instance state*, we do not merge them
  into one.
- **No nesting.** A container still cannot live inside a container.
- **No new per-shot ammo consumption.** "Use" on a consumable is an explicit
  drop-1 button, not automatic.
- **No migration tooling.** App is not deployed (project convention). A
  best-effort load-time coercion of old saves is provided as a courtesy only.

## Decisions (from brainstorming)

1. **Shared contract, keep typed lists** (Approach A). Every owned thing shares
   `instance_id + location (+ count) (+ equip-state)`.
2. **Stackable vs equippable.** Stackables (coins, gems, ammo, bulk consumables)
   are one instance with `count`. Equippables (weapons, armour, shields) are
   always per-instance, `count == 1`, and **never** stack. Stackability and
   equippability derive from the **catalog item type**, not an instance flag
   (data-not-code).
3. **Two stackable categories.** *Durable* = exactly {coins, gems}. *Consumable*
   = ammo + all bulk gear (torches, rations, spikes, oil, …). The only
   behavioural difference is the **"use"** button (consumables only).
4. **Equip is instance state.** Slotted things carry `equip = slot | None`;
   magic items keep `equipped: bool`. `CharacterSpec.equipped` is **deleted**.
5. **Quantity vocabulary.** Every quantity-removing action on a stackable — move,
   sell, drop — takes a `count`, rendered as a number box defaulting to the full
   current count and clamped to `1..count`. Consumables also get **use** (= drop
   1). The box appears per action only where that action exists for the type.
6. **Auto-merge.** At most **one stack per (merge-key, location)**. Any operation
   that lands a stackable into a location with a matching stack has the resident
   absorb the incoming count; the incoming instance is discarded. Splitting is
   only by moving a partial count to a *different* location. Merge-keys: coins →
   `denom`; gems → `value + label`; ammo → `base_id + enchantment_id`; consumable
   gear → `catalog_id`.
7. **One move path, retainers included.** `move_thing` is the single front door;
   `transfer_to_retainer`/`transfer_to_pc` are deleted; give/take is a move with
   `kind="retainer"` as src/dest, identical to container/carrier moves.

## Architecture

### Models (`aose/models/character.py`, `storage.py`)

**New `ItemInstance`** — the loose catalog item, finally an instance:

```
instance_id: str            # uuid4 hex
catalog_id: str             # references a Weapon / Armor / gear item
location: StorageLocation   # carried/stashed/container/animal/vehicle/retainer
count: int = 1              # >1 only for stackables; equippables always 1
equip: Literal["armor","main_hand","off_hand"] | None = None  # equippables only
tailored: bool = True       # inert unless tailorable body armour
loaded_ammo_id: str | None = None   # launcher weapons only; an AmmoStack id
```

- `CharacterSpec.inventory: list[str]` and `stashed: list[str]` → **one**
  `items: list[ItemInstance]`. Carried-vs-stashed is `location.kind`.
- `ContainerInstance.contents` / `AnimalInstance.contents` /
  `VehicleInstance.contents` (`list[str]`) → **removed**. An item in a container
  is an `ItemInstance` with `location = container:<id>` — exactly how a magic
  item in a container already works.
- `CharacterSpec.equipped: dict[str,str]` → **removed**; the slot is read from
  each `ItemInstance.equip` / `EnchantedInstance.equip`.
- `CharacterSpec.loaded_ammo: dict[str,str]` → **removed**; loaded ammo is
  `ItemInstance.loaded_ammo_id` on the launcher.
- `CharacterSpec.armor_tailored: bool` → **removed**; `ItemInstance.tailored` /
  `EnchantedInstance.tailored` on the worn armour.
- `EnchantedInstance.equipped: bool` → `equip: slot | None` (so an enchanted
  weapon/armour is slotted exactly like a loose one). It also gains `tailored`.
- `MagicItemInstance.equipped: bool` — **unchanged** (toggle mechanic).
- `CoinStack` gains `instance_id: str`. The `(denom, location)` uniqueness
  invariant stays (it is just the coin merge-key).

Models stay "dumb": invariants that need a catalog lookup (equippable ⇒ count 1;
equip only on equippables; stackable ⇒ no equip) are enforced in the engine, not
the model.

### Engine — one equip path (`equip.py`)

- `equip(spec, instance_id, slot, *, data, ruleset_flags...)` and
  `unequip(spec, instance_id)` operate on **instances** of whichever spec owns
  them — a loose `ItemInstance` or an `EnchantedInstance`. They set/clear the
  instance's `equip` field. No `equipped` dict is threaded through.
- Wield-budget validation (`validate_wield`) iterates the owner spec's instances
  whose `equip in {main_hand, off_hand}` — identical code for PC and retainer.
- **Invariant: `equip is not None ⇒ location.kind == "carried"`.** Enforced at
  the single equip/move chokepoint. Equipping requires the instance be carried;
  moving an equipped instance off `carried` clears its `equip` first.
- Loaded-ammo and tailoring follow the instance: moving/unequipping the launcher
  clears `loaded_ammo_id`; the armour's `tailored` rides with the instance across
  re-equips for free (it is the instance's own field now).

### Engine — one move path (`storage.py`)

`move_thing(spec, category, ref_id, dest, *, count=None, src=None, data=None)`
remains the front door; every category reduces to the same primitives:

1. **locate** the instance by id (in the PC world or any retainer world);
2. **capacity-check** the destination (`_check_capacity`, unchanged);
3. **place-or-merge** at the destination — for stackables, find the resident
   stack by `(merge-key, dest)` and absorb `count`, else create/re-point a stack
   carrying the remaining/whole count; for equippables, re-point `location`;
4. **leaving-carried cleanup** — if the instance leaves `carried`, clear `equip`
   and `loaded_ammo_id`; if a launcher leaves, unload it; if a full ammo stack
   moves, unload any launcher pointing at it.

- **Cross-world moves (PC↔retainer)** move the instance between the two specs'
  `items` (or typed) lists, resetting `location` to carried in the destination
  world. Same-world moves re-point `location`. This is exactly today's
  `move_instance` pattern, now used for loose items too.
- **`split_stack(spec, instance_id, n, dest)`** is the shared primitive behind
  move/sell/drop of a partial count: it removes `n` from the source (pruning an
  emptied stack) and applies the place-or-merge at `dest` (or, for sell/drop, to
  the sink). One implementation replaces the divergent coin/gem/ammo splitters.
- **`transfer_to_retainer` / `transfer_to_pc` deleted**; the give/take routes
  become thin wrappers over `move_thing` (or are dropped in favour of the
  existing move UI).
- `move_targets` and `loose_list`/`containers_collection`/`_carrier`/`_retainer`
  resolvers stay, adjusted for the flat `items` list (location-filtered instead
  of positional).

### Engine — sell / drop / use (`shop.py`, `storage.py`)

- **Sell** a stackable: `split_stack` off `count` (default full, clamp
  `1..count`), credit half-price (or refund) to the PC's carried coins, prune an
  emptied source. One path for coins-can't-be-sold aside; gems and consumable
  gear share it.
- **Drop** a stackable: `split_stack` off `count` to a discard sink (the
  instance/quantity is removed from the world). Equippables drop whole.
- **Use** (consumables only): `drop(count=1)` — a dedicated shortcut, no number
  entry.

### Derivations (encumbrance, attacks, AC, ammo, quick_equipment, retainers)

- **Encumbrance** (`encumbrance.py`, `location_load_cn`): sum `items` by
  `location` and `count` (catalog `weight_cn × count`) instead of iterating a
  positional list; equipped items still weigh (they are carried). Magic/enchanted/
  coins/gems already filter by location — unchanged.
- **Attacks / AC / equip queries** read the equipped instance via
  `equip == slot` instead of `spec.equipped[slot]`. A small helper
  `equipped_in(spec, slot) -> instance | None` centralises the lookup.
- **Ammo** loaded-launcher reads `ItemInstance.loaded_ammo_id` instead of the
  `loaded_ammo` dict.
- **quick_equipment** / kit application builds `ItemInstance`s (with ids)
  directly.
- **retainers**: transfer helpers removed (use `move_thing`); generation/kit
  already routes through `quick_equipment`, so retainer items are instances with
  ids like the PC's — same equip/move code throughout.

### View + templates (`sheet/view.py`, inventory templates)

- Inventory grouping buckets the flat `items` list by `location` (as it already
  does for magic/enchanted/coins/gems). Equipped items render in the equipped
  block via `equip`; everything else under its location group/container.
- The shared action macros (`_actions.html`, from the 2026-06-23 work) gain the
  **count box** on move/sell/drop for stackables (default full, clamp `1..count`)
  and the **use** button for consumables. One affordance, every stackable.

### Routes (`routes.py`)

- `POST /inventory/move` (single front door) unchanged in shape; now also the
  path for give/take (dest/src `kind="retainer"`).
- Sell/drop routes take an optional `count`; a new use action posts drop-1.
- `retainer/give` + `retainer/take` become wrappers over `move_thing` (or are
  removed if the move UI fully covers them — decided at plan time by grepping
  call sites).
- Equip/unequip routes (PC, retainer, enchanted) collapse onto the single
  instance-based `equip`/`unequip`.

### Load-time coercion (courtesy, no migration tooling)

A `model_validator(mode="before")` on `CharacterSpec`:

- wraps `inventory`/`stashed` strings into `ItemInstance`s
  (`location = carried/stashed`, `count` by collapsing duplicates for stackables,
  per-instance for equippables);
- drains each container/animal/vehicle `contents` into `items` with the matching
  `location`;
- converts the `equipped` dict into `equip` on the matching instances (and the
  enchanted `equipped` bool likewise);
- converts `loaded_ammo` → `loaded_ammo_id`; `armor_tailored` → `tailored` on the
  worn armour;
- assigns `instance_id` to coin stacks.

Old saves load unchanged; no separate migration step.

## Data flow

```
spec ─► build_inventory_groups(spec, data)
          items + coins/gems/jewellery/magic/enchanted/ammo
          all bucketed by StorageLocation (top-level + per container)
          equipped block ← instances where .equip is set / magic .equipped
                    ▼
       sheet templates → per-item modal → _actions.html macros
          Move ▾ (count box for stackables) · Sell ▾ (count) · Drop (count)
          · Use (consumables) · Equip/Unequip (equippables)
                    ▼
       POST /inventory/move | /sell | /drop | /use | /equip | /unequip
          → storage.move_thing / shop / equip  (all instance-based, owner-agnostic)
          → invariants enforced once: equipped⇒carried; ≤1 stack per key+location
```

## Phasing (cohesive spec → phased plan)

Each phase keeps the suite green before the next.

1. **Model + coercion + primitives.** Add `ItemInstance`, flat `items`,
   `equip`/`tailored`/`loaded_ammo_id`; `instance_id` on coins; enchanted `equip`.
   Add the before-validator coercion. Reshape `storage.py` resolvers + `equip.py`
   onto instances; add `split_stack`; enforce the two invariants. Green:
   `test_storage*`, `test_equip`, `test_retainer_transfer`.
2. **Derivations.** encumbrance, attacks, AC, ammo, quick_equipment, retainers
   read instances. Delete `transfer_to_*`. Green: engine suite.
3. **View + templates + UI.** bucket `items` by location; count box + use button
   in the shared macros; equip block via `equip`. Green: web/view tests.
4. **Delete dead side tables.** Remove `spec.equipped`, `loaded_ammo`,
   `armor_tailored`, the `contents` sub-lists, and the transfer routes; sweep call
   sites by grep. Update `ARCHITECTURE.md` (storage shapes, equip, encumbrance)
   in place + a `CHANGELOG.md` row.

## Testing

- **Reported dupe (regression):** equip a weapon on a retainer → move it to the
  PC → assert the retainer slot is clear, the instance is unequipped, and exactly
  one copy exists in the world.
- **Equip-as-state:** equipping sets `equip`; moving an equipped instance off
  carried clears `equip`; equipping a stashed/in-container instance is rejected;
  PC and retainer use the same path.
- **Auto-merge:** moving a stackable into a location with a matching stack yields
  exactly one stack (resident absorbs; incoming id gone); equippables never merge.
- **Split-by-move:** partial move leaves a remainder at source and one stack at
  dest; full move prunes the source.
- **Quantity actions:** sell/drop clamp `count` to `1..count` and default to
  full; "use" drops exactly 1 and only exists for consumables; durables (coins,
  gems) expose no "use".
- **Loaded ammo / tailoring follow the instance:** moving/unequipping a launcher
  clears its load; tailoring survives re-equip on the same armour instance.
- **Coercion:** an old save (string inventory, `equipped` dict, `loaded_ammo`,
  `armor_tailored`, `contents`) loads into the new shape with weights, equip, and
  load preserved.
- **Regression:** full suite green; encumbrance totals unchanged for an
  unmodified character; print sheet lists all groups; settings page shows no
  "pending" badge.

## Risks / open implementation notes

- **Blast radius.** This touches models, loader, ~10 engine modules, the sheet
  view, and many templates. Phasing keeps each step green, but the model change is
  inherently atomic (the flat `items` list breaks every positional reader at
  once); Phase 1 must land model + all `storage`/`equip` readers together.
- **Coercion fidelity.** Collapsing duplicate strings into counted stacks must use
  the same stackable/equippable classification the runtime uses, or weights/counts
  drift on load. Share one `is_stackable(catalog_item)` helper between coercion and
  engine.
- **Merge-key correctness.** Each stackable type's merge-key must match its
  existing behaviour (coins `denom`, gems `value+label`, ammo
  `base_id+enchantment_id`) and the new consumable-gear key (`catalog_id`); a wrong
  key either fragments or wrongly fuses stacks.
- **Enchanted equip migration.** Enchanted weapons were doubly tracked (an
  `equipped` bool *and* a `spec.equipped` slot id). The coercion must reconcile
  both into the single `equip` slot without losing which hand.
- **Call-site sweep on deletion.** Removing `spec.equipped`/`loaded_ammo`/
  `contents`/`transfer_*` 404s or AttributeErrors any missed reader; grep
  exhaustively before deleting (Phase 4).
