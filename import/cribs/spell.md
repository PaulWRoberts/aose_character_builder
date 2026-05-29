# Crib: spell

Target model: `Spell` (`aose/models/spell.py`). `extra="forbid"`.
One book's spells go in ONE list file: `data/spells/<book>_spells.yaml`.

## Fields
| Field | Type | Req | Notes |
|---|---|---|---|
| id | str | yes | snake_case, unique across ALL spell files |
| name | str | yes | |
| level | int | yes | spell level |
| spell_lists | list[str] | no | pool IDs: magic_user, cleric, druid, illusionist, kineticist… |
| source | str | no | book of origin, e.g. ose-advanced, carcass-crawler-1 |
| range | str | yes | e.g. "150'", "Touch", "0 (caster)" |
| duration | str | yes | e.g. "instant", "6 turns", "1 turn/level" |
| description | str | yes | full rules text |
| reversible | bool | no | default false |
| reverse_name | str \| null | no | name of the reversed form if any |

## Example
```yaml
- id: magic_missile
  name: Magic Missile
  level: 1
  spell_lists: [magic_user]
  source: ose-advanced
  range: "150'"
  duration: instant
  description: >-
    A glowing dart speeds toward a target and strikes unerringly for 1d6+1
    damage. +1 missile at levels 6, 11, and 16.
- id: cure_light_wounds
  name: Cure Light Wounds
  level: 1
  spell_lists: [cleric]
  source: ose-advanced
  range: Touch
  duration: instant
  description: "Heals 1d6+1 hit points, or cures paralysis."
  reversible: true
  reverse_name: Cause Light Wounds
```

## Rules
- A spell on two lists gets both: `spell_lists: [cleric, druid]`.
- For a race-as-class that reuses a list, do NOT tag the spell with the race;
  tag it with the list (the class references the list via its own `spell_lists`).
- Set `source` to the book id; keep it consistent with the manifest unit.
- Keep ids unique across every spell file (the validator enforces this).
