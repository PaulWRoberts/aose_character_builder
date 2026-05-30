# Crib: spell-list

Target model: `SpellList` (`aose/models/spell_list.py`). `extra="forbid"`.
All lists live in ONE file: `data/spell_lists.yaml` (a YAML list of mappings).

## Fields
| Field | Type | Req | Notes |
|---|---|---|---|
| id | str | yes | snake_case pool id (e.g. magic_user, cleric, druid, illusionist) |
| name | str | yes | display name |
| caster_type | "arcane" \| "divine" | yes | see decision rule below |
| description | str \| null | no | one line |

## Deciding caster_type (the one judgment call)
- **arcane** — the tradition uses a *spell book*; casters "learn"/"study" spells
  and are limited to a known set (magic-user, illusionist, elf's borrowed list).
- **divine** — casters "pray"/"are granted" spells and know their *entire* class
  list (cleric, druid).

Make this decision ONCE per list. Classes and spells reference the list by id;
they never restate the caster type.

## Example
```yaml
- id: magic_user
  name: Magic-User
  caster_type: arcane
  description: Arcane spells learned through study and recorded in a spell book.
- id: druid
  name: Druid
  caster_type: divine
```
