# Crib: magic item

Two encodings, by kind. `extra="forbid"`. One book's magic items go in ONE list
file: `data/equipment/<book>_magic_items.yaml`. All entries set `magic: true`.

## A. Magic weapons / armour — use the NATIVE weapon/armor type
Keep `item_type: weapon` or `item_type: armor` and add a `magic_bonus`.
- Weapon: optional `conditional_bonus: {vs, bonus}` for "+X vs Y".
- Armour: `weight_multiplier: 0.5` for half-weight enchanted armour.

```yaml
- id: sword_plus_1
  name: Sword +1
  category: magic_swords
  item_type: weapon
  magic: true
  cost_gp: 0
  weight_cn: 60
  damage: { default: "1d6", variable: "1d8" }
  melee: true
  proficiency_group: sword
  magic_bonus: 1
- id: chain_mail_plus_1
  name: Chain Mail +1
  category: magic_armour
  item_type: armor
  magic: true
  cost_gp: 0
  weight_cn: 400
  ac_descending: 5
  movement_impact: metal
  magic_bonus: 1
  weight_multiplier: 0.5
```

## B. Everything else — use `item_type: magic` with modifiers
Fields: `equippable` (bool), `modifiers` (list[Modifier]),
`max_charges` (int | null) OR `charge_dice` (str | null, rolled at acquisition),
`description`.

`Modifier`: `{target: str, op: add|set|set_min|set_max, value: int}`.
Valid targets: `ability:STR…CHA`, `ac`, `save:all`,
`save:death|wands|paralysis|breath|spells`, `attack`, `damage`,
`carry_capacity`, `thac0`. `op` order applied per target: set → add → set_min
→ set_max. `add` always means "better for the character".

```yaml
- id: gauntlets_of_ogre_power
  name: Gauntlets of Ogre Power
  category: miscellaneous_magic_items
  item_type: magic
  magic: true
  cost_gp: 0
  weight_cn: 0
  equippable: true
  description: "Wearer has Strength 18; carrying capacity +1000 cn."
  modifiers:
    - { target: "ability:STR", op: set, value: 18 }
    - { target: carry_capacity, op: add, value: 1000 }
- id: ring_of_protection
  name: Ring of Protection
  category: magic_rings
  item_type: magic
  magic: true
  cost_gp: 0
  weight_cn: 0
  equippable: true
  description: "+1 to Armour Class and all saving throws."
  modifiers:
    - { target: ac, op: add, value: 1 }
    - { target: "save:all", op: add, value: 1 }
- id: potion_of_healing
  name: Potion of Healing
  category: magic_potions
  item_type: gear        # pure-text consumable, no instance/modifiers
  magic: true
  cost_gp: 0
  weight_cn: 10
  description: "Quaffing restores lost hit points (per the referee's table)."
```

## Rules
- Decision: is it a weapon/armour bonus? -> use A (native type + magic_bonus).
  A worn/wielded item with numeric effects? -> B (`item_type: magic` +
  modifiers). A pure-text consumable with no auto-applied numbers? -> `item_type: gear`.
- Only encode effects expressible as a `Modifier`. Anything else goes in
  `description` with a `# TODO:` if it needs manual play.
- `cost_gp: 0` (magic items are Add-only / GM-granted, not bought).
- ids unique across ALL of data/equipment/.
