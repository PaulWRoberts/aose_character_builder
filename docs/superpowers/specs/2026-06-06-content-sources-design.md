# Content Sources — design

**Date:** 2026-06-06
**Status:** Approved

## Problem

Game data (races, classes, spell lists, items, enchantments, spells) comes from
different published books. Today there is no structured notion of *which book*
a piece of content is from — only a free-text, inconsistent `source` field on
`Spell` (all 212 spells are tagged `"ose-advanced-fantasy"`, even the Classic
cleric/magic-user spells).

We want:

1. A first-class **Source** concept (name, publisher, core flag).
2. Every piece of filterable content tagged with its source.
3. A **filter** on the rules and settings pages to enable/disable sources, which
   hides disabled content everywhere (wizard pickers, shop, spell selection,
   enchantment acquisition).

## Sources defined

| id | name | publisher | core |
|---|---|---|---|
| `ose_classic_fantasy` | Old School Essentials Classic Fantasy | Necrotic Gnome | yes |
| `ose_advanced_fantasy` | Old School Essentials Advanced Fantasy | Necrotic Gnome | yes |

Classic Fantasy is the **default** for all existing/untagged content and is
**locked on** (never offered as a toggle — it holds the baseline). Advanced
Fantasy and any future source are freely toggleable.

`core` is an informational flag (shown in the UI), **not** a lock — locking is a
separate, Classic-only rule (see UI section).

## Data model

### New: `Source` (`aose/models/source.py`)

```python
class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    publisher: str
    core: bool = False
```

### New registry: `data/sources.yaml`

A YAML list of mappings, loaded like `spell_lists.yaml` into
`GameData.sources: dict[str, Source]` (id-keyed). A `_load_sources` helper in
`loader.py` returns `{}` when the file is absent (minimal test fixtures).

### `source` field on content models

Add `source: str = "ose_classic_fantasy"` to:

- `ItemBase` (covers **all** item variants: weapon, armor, gear, poison,
  container, magic, ammunition)
- `Race`
- `CharClass`
- `SpellList`
- `Enchantment`
- `Spell` — repurpose the existing `source` field; change its default to
  `"ose_classic_fantasy"` and normalize values (see below)

Default = Classic, so **mundane equipment and all existing Classic content need
no YAML changes**. Only Advanced entries get an explicit
`source: ose_advanced_fantasy`.

## Tagging the Advanced content

Tag every entry from the user-provided Advanced Fantasy lists with
`source: ose_advanced_fantasy`. This applies to **existing data only** — entries
in the lists that don't yet exist in the data are not authored here.

- **Races** (`data/races/`): drow, duergar, dwarf, elf, gnome, half_elf,
  halfling, half_orc, svirfneblin
- **Classes** (`data/classes/`): acrobat, assassin, barbarian, bard, drow,
  druid, duergar, gnome, half_elf, half_orc, illusionist, knight, paladin,
  ranger, svirfneblin
- **Spell lists** (`data/spell_lists.yaml`): druid, illusionist
- **Magic items** (`data/equipment/magic_items.yaml`): the misc items and
  rods/staves/wands from the lists that exist in the catalog
- **Enchantments** (`data/enchantments.yaml`): the swords and weapons from the
  lists that exist in the registry (these back the magic weapons via the
  composition model)

Note: which Classic race/class entries (e.g. `human`, `cleric`, `fighter`,
`magic_user`, `thief`, `dwarf`/`elf`/`halfling` *race-as-class*) stay Classic is
handled automatically by the default — no edits. Where the same id appears in
both Classic and Advanced (e.g. `dwarf` exists as both a Classic race-as-class
file and an Advanced race), tag the file that corresponds to the Advanced
version. Mapping ambiguities resolved during implementation by inspecting each
file's content against the book.

### Spell tag normalization

Retag every spell's `source` to match its spell list(s):

- A spell is **Classic** if it belongs to any Classic list (`magic_user`,
  `cleric`).
- Otherwise (only `druid` and/or `illusionist`) it is **Advanced**.

This makes the per-spell field accurate. Filtering, however, is driven by
**spell-list** source, not the per-spell tag (see below) — the per-spell tag is
informational and a hook for any future per-spell filtering.

## Enabled state: `RuleSet.disabled_sources`

Add `disabled_sources: list[str] = []` to `RuleSet`. A source is enabled iff its
id is **not** in this list.

- Empty default ⇒ everything enabled ⇒ **no migration** (existing
  `settings.json` and in-progress drafts load unchanged).
- Classic is never offered as a toggle, so it can never enter the list (locked
  on).

(Rejected alternative: an `enabled_sources` list — an empty default would mean
"nothing enabled", silently breaking every existing draft and the global
default.)

## Filtering / gating

A pure helper, e.g. `source_enabled(source_id: str, ruleset: RuleSet) -> bool`
(`return source_id not in ruleset.disabled_sources`), used at every point where
selectable content is built:

- **Wizard race options** (`wizard.py` ~559) — filter `data.races.values()`.
- **Wizard class options** (`wizard.py` ~645) — filter `data.classes.values()`.
- **Spell lists & spells** — a spell list is gated by its own source; a spell is
  available if **at least one** of its `spell_lists` belongs to an enabled
  source.
- **Shop / item catalog** (sheet + wizard equipment) — filter `data.items`.
- **Enchantment acquisition** (sheet `/add`) — filter `data.enchantments`.

Disabled content is omitted from the lists exactly as if it weren't in the data.

## Filter UI (rules + settings pages)

Both `/settings` (global default for new characters) and the wizard `/rules`
step (per-character override) get an identical **Sources** section, since they
share `parse_ruleset_from_form` and the rule-rendering structure.

- One row per source: name, publisher, and a "Core" marker when `core` is true.
- Each source is a checkbox reflecting enabled state.
- **Classic renders checked and disabled** (locked on).
- `parse_ruleset_from_form` gains a `source_ids: list[str]` argument (passed by
  both routes, which have `GameData` via `request.app.state`). It computes
  `disabled_sources = [id for id in source_ids if id not checked and id != classic_id]`.
- Routes pass `sources` (the registry, sorted core-first then name) into the
  template context.

## Mid-wizard cascade

`_apply_rule_changes` (in `wizard.py`) gains source-aware downstream clears,
mirroring the existing rule-change cascade: when a source is disabled and the
draft's picked race / class(es) / spells / inventory items / enchantments are no
longer from an enabled source, those selections are cleared (and any now-invalid
later steps reset), so the wizard never carries an orphaned pick.

## Out of scope

- Authoring new content for Advanced entries not already in the data.
- Per-spell *filtering* (the per-spell tag is normalized for accuracy but the
  filter operates at spell-list granularity).
- Retroactively re-filtering **saved characters** or **existing drafts** when the
  global source set changes — consistent with how every other rule works: the
  global setting is the default for *new* characters; drafts snapshot their
  ruleset; the per-character `/rules` step is the override.
- Backward-compat migrations (app is local single-user, not deployed; empty
  `disabled_sources` default makes old data load as-is).

## Testing

- Loader: `data/sources.yaml` parses into `GameData.sources`; absent file ⇒ `{}`.
- Model defaults: untagged content reports `ose_classic_fantasy`.
- `source_enabled` truth table; Classic always enabled even if injected into
  `disabled_sources`.
- Wizard race/class/spell/shop/enchantment lists exclude content from a disabled
  source and include it when enabled.
- `parse_ruleset_from_form` builds the correct `disabled_sources` from checkbox
  state and never disables Classic.
- Cascade: disabling a source mid-wizard clears an orphaned race/class pick.
- Spell normalization: cleric/magic-user spells ⇒ Classic, druid/illusionist-only
  spells ⇒ Advanced.
- Regression: a default `RuleSet` (empty `disabled_sources`) shows all content.
