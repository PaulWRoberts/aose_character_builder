# Wield capacity & two-weapon fighting — design

**Date:** 2026-06-10
**Status:** approved (design); plan pending
**Branch:** TBD

## Goal

Make "equipped" mean *what is physically in hand*, governed by a two-hand
budget. Today `equipped_weapons` is a flat list capped only by ownership — a
character can ready a sword, a bow, and two daggers at once. After this change:

- one suit of body armour (unchanged: single `armor` slot),
- two literal hand slots — `main_hand` and `off_hand`,
- a shield is simply a thing held in the off hand,
- the baseline rule (always on): **at most one weapon**, plus a shield only if a
  hand is free → `1H weapon + shield`, `2H weapon alone`, `shield alone`, or
  empty,
- a new optional rule — **Attacking with Two Weapons** — lets an *eligible*
  character put a qualifying small weapon in the off hand instead of a shield,
  with the −2 / −4 penalties applied automatically,
- the **gargantua** wields a two-handed *melee* weapon one-handed, freeing the
  off hand for a shield or off-hand weapon.

## Rules encoded

### Baseline wield limit (always enforced)

Pure **2-hand budget**. Each in-hand item has a hand cost:

| Item | Hand cost |
|---|---|
| Shield | 1 |
| Weapon | `weapon.hands` → 2 if it has `two_handed`, else 1 |
| Two-handed **melee** weapon, **gargantua wielder** | 1 (the special rule) |

A `two_handed` weapon in `main_hand` occupies the off hand too (cost 2), so
`off_hand` must be empty — *unless* the gargantua reduction applies, which frees
the off hand. The "a shield may not be employed" clause on `two_handed` /
`versatile` (two-handed mode) thus falls out of the budget rather than being a
special case. Baseline allows **at most one weapon**; a second weapon is legal
only under the optional rule below.

### Attacking with Two Weapons (optional rule)

Quoted from the supplied rule text:

> Characters with DEX or STR as a prime requisite may choose to wield two
> one-handed weapons, as follows:
> - The secondary weapon must be of small size (e.g. a dagger or hand axe).
> - Attacks with the primary weapon suffer a −2 penalty.
> - The character may make one extra attack per round with the secondary weapon,
>   at a −4 attack penalty.

Encoded as:

- **Gated** behind a new `RuleSet.two_weapon_fighting` flag (default off).
- **Character eligibility:** any of the character's classes lists `STR` or `DEX`
  in `prime_requisites` (the field already exists on `CharClass`). Multi-class:
  eligible if *any* class qualifies.
- **Off-hand weapon eligibility** (house rule — there is no "off-hand" weapon
  quality in AOSE, so this is synthesized to approximate "small size"):
  `weight_cn ≤ 30` **and** the weapon has the `melee` quality **and** it has
  **none** of `two_handed`, `versatile`, `slow`, `brace`, `charge`. (Qualifying
  catalog weapons today: dagger, hand axe, short sword, mace, war hammer,
  blackjack, silver dagger. Thrown-capable melee weapons such as the hand axe
  qualify — the rule text names the hand axe explicitly.)
- **Penalties (automated):** when both hands hold weapons, the `main_hand`
  profile takes **−2** to-hit and the `off_hand` profile takes **−4** to-hit.
  Each remains its own attack profile (which already represents the extra
  off-hand attack); attack *counts* are not otherwise modelled.

### Gargantua exception

From the gargantua `combat` feature: *"A gargantua can wield any two-handed melee
weapon, such as a battle axe, with only one hand."* Encoded as a new mechanical
flag on that feature:

```yaml
mechanical:
  armour_requires_tailoring: true
  one_handed_two_handed_melee: true     # NEW
```

Read via the existing `_reached_features` pattern in `engine/features.py`
(`one_handed_two_handed_weapons(spec, data) -> bool`), mirroring
`open_doors_category_bonus`. The race-as-class guard already prevents the
linked race and the race-locked class from both contributing. Effect: a
`two_handed` **melee** weapon costs 1 hand for this character; bows/crossbows
(two-handed *ranged*) are unaffected. This automatically enables `2H melee +
shield` and (optional rule) `2H melee + off-hand weapon`. A gargantua still
cannot dual-wield two two-handed weapons: a `two_handed` weapon fails the
off-hand eligibility check.

## Architecture: chosen approach (A — clean replacement)

`equipped_weapons` is **removed**. The existing `equipped: dict[str, str]`
becomes the single source of truth for worn/held gear with three slots:

| Slot key | Holds |
|---|---|
| `armor` | body-armour catalog id (unchanged) |
| `main_hand` | a weapon — catalog id **or** enchanted instance id |
| `off_hand` | a shield **or** an off-hand weapon — catalog id **or** enchanted instance id |

Enchanted weapons and shields become **slot-resident** (slot value = the
`EnchantedInstance.instance_id`) and are governed by exactly the same wield
rules as mundane gear — an enchanted longsword occupies a hand, an enchanted
shield fills the off hand, a magic dagger can be an off-hand weapon. Their
per-instance `equipped` bool is retired for `kind in {weapon, shield}` (still
used for body `armor`). This keeps a single place that answers "what is in each
hand," avoiding the two-source synchronisation problem that approach B would
have had. Catalog ids
(e.g. `"dagger"`) never collide with instance ids (uuid4 hex) and never with the
synthetic `ench:{instance_id}` weapon id, so slot values disambiguate by lookup.

### Slot value resolution

New helper (in `engine/equip.py`):

```python
def resolve_slot(spec, data, value) -> Weapon | Armor | None:
    """Resolve a slot's stored id to its concrete item.
    - catalog id           -> data.items[value]
    - enchanted instance id -> resolve_instance(that instance, data)
    - missing/stale         -> None
    """
```

Duplicate semantics: two identical catalog weapons → `main_hand` and `off_hand`
both hold the same catalog id; the ownership check counts slot occupancy against
`inventory.count(id)` across both slots. Enchanted instances are unique, so each
instance id appears in at most one slot.

## Data-model changes (`aose/models`)

- `CharacterSpec`: drop `equipped_weapons`; `equipped` now carries
  `armor` / `main_hand` / `off_hand`. **No migration/coercion validator** — the
  app is in development mode, so existing saved characters needn't load against
  the new shape (re-equip from scratch is fine). This keeps the model lean.
- `RuleSet`: add `two_weapon_fighting: bool = False`.
- `EnchantedInstance.equipped` semantics narrow to body armour only; no field
  change required, but weapon/shield equip flips slot occupancy instead of the
  bool. (The bool stays False for slot-resident enchanted weapons/shields; their
  "equipped-ness" is derived from being in a slot.)

## Engine changes

### `engine/equip.py` (the gatekeeper)

- New pure `validate_wield(slots, data, *, ruleset, eligible, gargantua_1h_2h,
  allowed_weapons, allowed_armor, allow_shields) -> None` that raises a clear
  `ValueError` on any illegal configuration (over budget, second weapon without
  the rule / eligibility, ineligible off-hand weapon, shield with no free hand,
  class restriction). Single source of legality, reused by the wizard and the
  sheet.
- `equip(...)` gains a `slot` parameter (`"main_hand" | "off_hand"` for hand
  items; armour always → `armor`). For weapons: when `slot` is omitted, default
  to `main_hand`; off-hand is chosen explicitly by the UI. Validates via
  `validate_wield` after tentatively placing the item, rolling back on error.
- `unequip(...)`: clear whichever slot holds the id (slots are now the only
  weapon store).
- Hand-cost / budget helpers live here:
  `hand_cost(item, *, gargantua_1h_2h) -> int`, `hands_used(slots, ...)`.

### `engine/features.py`

- `one_handed_two_handed_weapons(spec, data) -> bool` — reads the new
  `mechanical['one_handed_two_handed_melee']` flag from reached features.

### `engine/attacks.py`

- Iterate `main_hand` then `off_hand` (resolving each via `resolve_slot`)
  instead of `Counter(equipped_weapons)` + the separate `equipped_enchanted(
  "weapon")` loop. A slot resolving to a shield yields no profile.
- Dual-wield detection: both slots resolve to weapons → apply **−2** to the
  main-hand profile and **−4** to the off-hand profile, and label them
  ("primary" / "off-hand"). Add fields to `AttackProfile`
  (e.g. `hand: Literal["main","off",None]`) so the template can mark them.
- `_two_handed_variant` (versatile two-handed damage) is suppressed when the
  off hand is occupied (shield or weapon) — using the two-handed die is
  physically impossible then. Under the gargantua reduction a versatile weapon
  is still only `versatile` (1 hand), so this is purely about a free off hand.
- Unarmed and feature weapons (gargantua rock) are unchanged — synthetic,
  always available, not slot-resident.

### `engine/armor_class.py`

- Read the shield from `off_hand` (resolve via `resolve_slot`; apply bonus only
  when it resolves to an `Armor` with `is_shield`) instead of
  `equipped["shield"]` + `equipped_enchanted("shield")`. `_has_worn_armor`
  unchanged (body armour only).

### `engine/shop.py`, `engine/encumbrance.py`

- Replace every `equipped_weapons` reference with slot reads. Stash/remove must
  clear a slot when the underlying item leaves inventory. Encumbrance already
  counts equipped items once via `inventory`; ensure the "is this equipped"
  check consults slots.

## Web changes

### Routes (`aose/web/routes.py`)

- `/equipment/equip` accepts an optional `slot` form field; passes it through to
  `engine.equip.equip`. Surface `ValueError` messages to the user (existing
  pattern).
- Enchanted weapon/shield equip routes (`/equip-enchanted`,
  `/unequip-enchanted`) write/clear the relevant **slot** rather than calling
  `enchant.equip/unequip` for weapon/shield kinds (armour keeps the bool path).
- `/rules` per-character override: turning `two_weapon_fighting` **off**
  triggers a cascading clear (`_apply_rule_changes` in `wizard.py`) that
  un-equips a now-illegal off-hand weapon (moves it back to inventory; the slot
  is emptied).

### UI — equip control (sheet drawer + wizard equipment step)

- The **off-hand equip** control is shown only when a valid off-hand option
  exists: `two_weapon_fighting` on **and** the character is eligible **and** the
  weapon passes off-hand eligibility. When all three hold but the off hand is
  already occupied, the control is **shown but disabled**, with a hint to drop
  the current off-hand item first — so the player understands why they can't
  add it. When no off-hand option exists at all, the weapon equips to
  `main_hand` with no choice surfaced. Shields always target `off_hand`.
- Illegal attempts show the `validate_wield` error inline (e.g. "Both hands are
  full", "This class cannot use a shield", "Not eligible to fight with two
  weapons").
- Attack rows render the "primary −2" / "off-hand −4" labels from the new
  `AttackProfile.hand` field. (Templates: `sheet.html`,
  `sheet_overlays.js`, wizard equipment template.)

### Rule integration

- `/settings` default + wizard `/rules` per-character override for
  `two_weapon_fighting`, integrated end-to-end. The existing regression test
  that asserts every `RuleSet` flag is wired (no "pending" badge on settings)
  must pass for the new flag.

## Touch-point inventory

`equipped_weapons` appears in 8 files (~53 sites); all are rewritten to the slot
model: `models/character.py`, `engine/equip.py`, `engine/attacks.py`,
`engine/shop.py`, `engine/encumbrance.py`, `sheet/view.py`, `web/routes.py`,
`web/wizard.py`. Plus `engine/armor_class.py` (shield source) and
`engine/features.py` (gargantua flag), `data/races/gargantua.yaml` +
`data/classes/gargantua.yaml` (the flag), `models/ruleset.py` (new flag),
templates (`sheet.html`, `sheet_overlays.js`, wizard equipment), and `settings`
wiring.

## Testing

- **Engine (pure, TDD-first):** `validate_wield` truth table — 1H+shield, 2H
  alone, 2H+shield rejected (non-gargantua), 2H+shield allowed (gargantua),
  two weapons rejected when rule off / character ineligible / off-hand weapon
  too heavy or wrong qualities, two valid weapons accepted; hand-cost incl.
  gargantua reduction; off-hand eligibility predicate over every catalog weapon.
- **Attacks:** −2/−4 applied only when both hands hold weapons; off-hand labels;
  versatile two-handed variant suppressed with an occupied off hand.
- **AC:** shield bonus resolves from `off_hand` (mundane and enchanted shield).
- **Enchanted parity:** an enchanted weapon/shield equips, occupies a hand, and
  obeys the same wield rules as its mundane counterpart.
- **Rule wiring:** settings/regression test passes for `two_weapon_fighting`;
  cascading clear empties an illegal off-hand weapon when the rule is disabled.

## Non-goals

- Modelling number of attacks per round beyond showing both profiles.
- Quick-swap / "sheathed but ready" weapons — strict 2-hand means swapping.
- Encumbrance changes beyond keeping equipped-once accounting correct.
- Any new "off-hand" or "small" weapon *quality* in data — eligibility is
  computed from existing `weight_cn` + qualities.

## Open questions

None outstanding. The off-hand eligibility criteria are an explicit house rule
(no AOSE "off-hand" quality exists); recorded here as such.
