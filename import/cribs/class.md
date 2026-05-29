# Crib: class (and race-as-class)

Target model: `CharClass` (`aose/models/character_class.py`). `extra="forbid"`
— no fields beyond those listed. Progression/spell-slot level keys are integers.

## Fields
| Field | Type | Req | Notes |
|---|---|---|---|
| id | str | yes | snake_case, unique within data/classes/ |
| name | str | yes | display name |
| prime_requisites | list[Ability] | yes | subset of STR INT WIS DEX CON CHA |
| ability_requirements | map Ability->int | no | minimum scores to take the class |
| max_level | int | no | default 14 |
| hit_die | str | yes | e.g. "1d8", "1d4" |
| weapons_allowed | list[str] \| "all" | yes | |
| armor_allowed | list[str] \| "all" | yes | `[]` = none |
| shields_allowed | bool | yes | |
| proficiency | {starting_slots:int, new_slot_every_levels:int} | no | omit if not using weapon proficiencies |
| progression | map int->ClassLevelData | no | one entry per character level |
| features | list[ClassFeature] | no | |
| race_locked | str \| null | no | race id, for race-as-class entries |
| spell_lists | list[str] | no | which pool(s) this class casts from; `[]` = non-caster |

`ClassLevelData`: `{xp_required:int, thac0:int, hit_dice:str,
saves:{death,wands,paralysis,breath,spells (ints)}, spell_slots: map int->int | null}`
`ClassFeature`: `{id:str, name:str, text:str, gained_at_level:int=1, mechanical: map | null}`

## Example (non-caster)
```yaml
id: fighter
name: Fighter
prime_requisites: [STR]
max_level: 14
hit_die: 1d8
weapons_allowed: all
armor_allowed: all
shields_allowed: true
proficiency: { starting_slots: 4, new_slot_every_levels: 3 }
progression:
  1:
    xp_required: 0
    thac0: 19
    hit_dice: 1d8
    saves: { death: 12, wands: 13, paralysis: 14, breath: 15, spells: 16 }
features:
  - id: combat_focus
    name: Combat Focus
    text: "Fighters have unrestricted use of weapons, armor, and shields."
    gained_at_level: 1
```

## Caster progression rows
Read the SEPARATE spell-progression grid (character level x spell level) into
each row's `spell_slots`, and set the class's `spell_lists`:
```yaml
spell_lists: [magic_user]
progression:
  1:
    xp_required: 0
    thac0: 19
    hit_dice: 1d4
    saves: { death: 13, wands: 14, paralysis: 13, breath: 16, spells: 15 }
    spell_slots: { 1: 1 }          # one 1st-level spell at level 1
  3:
    xp_required: 5000
    thac0: 19
    hit_dice: 3d4
    saves: { death: 13, wands: 14, paralysis: 13, breath: 16, spells: 15 }
    spell_slots: { 1: 2, 2: 1 }
```
- Casting that begins later (e.g. cleric at level 2) means the level-1 row has
  NO `spell_slots`; the level-2 row is the first with one.
- Non-casters: omit `spell_lists` and every `spell_slots`.

## Race-as-class rules
- Set `race_locked` to the race id (e.g. `dwarf`).
- Mirror the race's ability requirements into `ability_requirements`.
- If the race casts via a borrowed list, set `spell_lists` to that list
  (elf -> `[magic_user]`, gnome -> `[illusionist]`), NOT to its own id.

## General rules
- Omit optional fields you can't source rather than guessing.
- If a value is unclear, emit it with a trailing `# TODO: confirm` comment.
