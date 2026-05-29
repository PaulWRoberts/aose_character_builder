# Crib: item (mundane)

Target: the `Item` discriminated union (`aose/models/item.py`), keyed by
`item_type`. `extra="forbid"`. One book's mundane items go in ONE list file:
`data/equipment/<book>_items.yaml` (mixed item_types allowed).

## Common (ItemBase) fields
`id` (str), `name` (str), `category` (str), `cost_gp` (float), `weight_cn`
(int, default 0), `description` (str | null), `magic` (bool, default false).

## Variants
- **weapon** (`item_type: weapon`): `damage: {default, variable, variable_two_handed?}`,
  `hands` (int=1), `versatile` (bool), `melee` (bool=true), `ranged` (bool=false),
  `range_short/medium/long` (int | null), `qualities` (list[str]),
  `proficiency_group` (str | null), `magic_bonus` (int=0),
  `conditional_bonus: {vs:str, bonus:int} | null`.
- **armor** (`item_type: armor`): `ac_descending` (int), `movement_impact`
  (none|leather|metal), `is_shield` (bool), `magic_bonus` (int=0),
  `weight_multiplier` (float=1.0).
- **gear** (`item_type: gear`): common fields only.
- **poison** (`item_type: poison`): `save_modifier` (int=0), `onset` (str|null),
  `effect` (str|null).
- **container** (`item_type: container`): `capacity_cn` (int|null),
  `weight_multiplier` (float=1.0).

## Example
```yaml
- id: club
  item_type: weapon
  name: Club
  category: weapons
  cost_gp: 3
  weight_cn: 50
  damage: { default: "1d6", variable: "1d4" }
  hands: 1
  proficiency_group: bludgeon
- id: leather_armor
  item_type: armor
  name: Leather Armor
  category: armor
  cost_gp: 20
  weight_cn: 200
  ac_descending: 7
  movement_impact: leather
- id: torch
  item_type: gear
  name: Torch
  category: adventuring_gear
  cost_gp: 1
  weight_cn: 20
```

## Rules
- Pick the right `item_type` per entry; one file may mix types.
- `damage.default` is the standard 1d6; `damage.variable` is the Variable Weapon
  Damage value. Set both.
- Leave `magic_bonus` at 0 / omit for mundane items (magic items: see magic-item crib).
- ids unique across ALL of data/equipment/ (validator enforces).
