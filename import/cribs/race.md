# Crib: race

Target model: `Race` (`aose/models/race.py`). `extra="forbid"`.

## Fields
| Field | Type | Req | Notes |
|---|---|---|---|
| id | str | yes | snake_case |
| name | str | yes | |
| ability_requirements | map Ability->int | no | minimum scores |
| ability_maxima | map Ability->int | no | caps |
| ability_minima | map Ability->int | no | floors |
| infravision | int | no | feet; default 0 |
| base_movement | int | no | default 120 |
| languages | list[str] | no | |
| allowed_classes | list[str] | no | `[]` = ANY class (the human case) |
| class_level_caps | map str->int | no | per-class level cap; missing = no cap |
| allowed_multiclass_combos | list[list[str]] | no | only under the Multiclassing rule |
| features | list[RaceFeature] | no | |

`RaceFeature`: `{id:str, name:str, text:str, mechanical: map | null}`

## Example
```yaml
id: elf
name: Elf
ability_requirements:
  INT: 9
infravision: 60
base_movement: 120
languages: [common, elvish, gnoll, hobgoblin, orcish]
allowed_classes: [fighter, magic_user]
class_level_caps: { fighter: 10, magic_user: 10 }
allowed_multiclass_combos:
  - [fighter, magic_user]
features:
  - id: detect_secret_doors
    name: Detect Secret Doors
    text: "When actively searching, elves find secret doors on 1-2 on 1d6."
```

## Rules
- `allowed_classes: []` means "any class" — use it only for human-like races.
- Omit optional fields you can't source. Mark unclear values `# TODO: confirm`.
