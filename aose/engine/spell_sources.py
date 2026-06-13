"""Spell books & scrolls — the cycle-free core for owned spell documents.

A ``SpellSource`` is a physical document (spell book or scroll) with custom
contents.  This module validates contents, adds/removes documents, expends a
scroll spell on cast, and runs the Advanced-rule copy-from-source attempt.

Imports only models + the data loader + the dice/spells/magic engines (like
``engine/ammo.py``); nothing imports it back.  Copy-failure state is written
ONLY onto the source document, never onto the character.
"""
from __future__ import annotations

import random
import uuid
from typing import Literal, Optional

from aose.data.loader import GameData
from aose.engine import spells as spell_engine
from aose.engine.dice import roll
from aose.models import (
    CharClass, CharacterSpec, ClassEntry, Spell, SpellSource, SpellSourceEntry,
)

Kind = Literal["spellbook", "scroll"]
CasterType = Literal["arcane", "divine"]

# The AOSE Magic Scrolls table tops out at 7 spells per scroll (spell books are
# uncapped).  See import/markdown/magic-items/advanced-fantasy_magic-scrolls-and-maps.md.
MAX_SCROLL_SPELLS = 7


class SpellSourceError(ValueError):
    """All spell-document validation / mutation errors (routes map to HTTP 400)."""


def _spell_caster_type(spell: Spell, data: GameData) -> CasterType | None:
    """The caster type a spell belongs to via its lists (arcane/divine).  None
    if it is on no known list."""
    for list_id in spell.spell_lists:
        sl = data.spell_lists.get(list_id)
        if sl is not None:
            return sl.caster_type
    return None


def new_spell_source(kind: Kind, caster_type: CasterType, spell_ids: list[str],
                     data: GameData, name: str = "",
                     list_id: str | None = None) -> SpellSource:
    """Build a validated SpellSource.

    Spellbooks are coerced to ``arcane``.  Every spell must exist and match
    ``caster_type`` (or, when ``list_id`` is given, be on that exact list).
    Duplicates within one document are rejected.  No spell-level filter — a
    document may hold spells of any level."""
    if kind == "spellbook":
        caster_type = "arcane"
    if not spell_ids:
        raise SpellSourceError("a spell book / scroll must contain at least one spell")
    if kind == "scroll" and len(spell_ids) > MAX_SCROLL_SPELLS:
        raise SpellSourceError(f"a scroll holds at most {MAX_SCROLL_SPELLS} spells")
    if len(set(spell_ids)) != len(spell_ids):
        raise SpellSourceError("a document cannot list the same spell twice")
    for sid in spell_ids:
        spell = data.spells.get(sid)
        if spell is None:
            raise SpellSourceError(f"Unknown spell {sid!r}")
        if list_id is not None:
            if list_id not in spell.spell_lists:
                raise SpellSourceError(f"{sid!r} is not on spell list {list_id!r}")
        elif _spell_caster_type(spell, data) != caster_type:
            raise SpellSourceError(f"{sid!r} is not a {caster_type} spell")
    return SpellSource(
        instance_id=uuid.uuid4().hex,
        kind=kind, caster_type=caster_type, name=name.strip(),
        entries=[SpellSourceEntry(spell_id=sid) for sid in spell_ids],
    )


def add_spell_source(sources: list[SpellSource], kind: Kind, caster_type: CasterType,
                     spell_ids: list[str], data: GameData, name: str = "",
                     list_id: str | None = None) -> list[SpellSource]:
    """Add-only append (GM grant / loot); no gold."""
    return [*sources, new_spell_source(kind, caster_type, spell_ids, data, name, list_id)]


def _index(sources: list[SpellSource], instance_id: str) -> int:
    for i, s in enumerate(sources):
        if s.instance_id == instance_id:
            return i
    raise SpellSourceError(f"No spell document with id {instance_id!r}")


def remove_spell_source(sources: list[SpellSource], instance_id: str) -> list[SpellSource]:
    idx = _index(sources, instance_id)
    return [*sources[:idx], *sources[idx + 1:]]


def cast_from_scroll(sources: list[SpellSource], instance_id: str,
                     spell_id: str) -> list[SpellSource]:
    """Expend one spell from a scroll: remove that entry.  If the scroll empties,
    drop the whole document (the parchment is now blank).  Validates document
    integrity only — caller checks caster-type usability via ``can_cast_scroll``."""
    idx = _index(sources, instance_id)
    src = sources[idx]
    if src.kind != "scroll":
        raise SpellSourceError("only scrolls can be cast from")
    pos = next((i for i, e in enumerate(src.entries) if e.spell_id == spell_id), None)
    if pos is None:
        raise SpellSourceError(f"{spell_id!r} is not on this scroll")
    remaining = [e for i, e in enumerate(src.entries) if i != pos]
    if not remaining:
        return [*sources[:idx], *sources[idx + 1:]]
    updated = src.model_copy(update={"entries": remaining})
    return [*sources[:idx], updated, *sources[idx + 1:]]


def character_caster_types(spec: CharacterSpec, data: GameData) -> set[str]:
    """The caster types the character can use (across all class entries)."""
    out: set[str] = set()
    for entry in spec.classes:
        cls = data.classes.get(entry.class_id)
        if cls is None:
            continue
        ctype = spell_engine.caster_type_of(cls, data)
        if ctype is not None:
            out.add(ctype)
    return out


def can_cast_scroll(source: SpellSource, spec: CharacterSpec, data: GameData) -> bool:
    """A scroll is castable if it is a scroll and the character has a class whose
    caster type matches the scroll's (arcane↔arcane, divine↔divine)."""
    if source.kind != "scroll":
        return False
    return source.caster_type in character_caster_types(spec, data)


def copyable_spell_ids(source: SpellSource, entry: ClassEntry, cls: CharClass,
                       data: GameData, ruleset=None) -> set[str]:
    """Spell ids in ``source`` an arcane caster may attempt to copy right now:
    arcane source, spell arcane-learnable for this class (on-list, accessible
    level — including level-0 cantrips when the rule is on — not already known),
    and not already marked ``copy_failed`` on this source."""
    if source.caster_type != "arcane":
        return set()
    learnable = {s.id for s in spell_engine.learnable_spells(entry, cls, data, ruleset)}
    return {
        e.spell_id for e in source.entries
        if not e.copy_failed and e.spell_id in learnable
    }


def copy_spell(entry: ClassEntry, cls: CharClass, data: GameData, ruleset,
               int_score: int, sources: list[SpellSource], instance_id: str,
               spell_id: str, rng: Optional[random.Random] = None
               ) -> tuple[ClassEntry, list[SpellSource], bool]:
    """Attempt to copy ``spell_id`` from the source into the arcane caster's
    spellbook (Advanced rule only).

    Validates: advanced rule on; spell is currently copyable from this source
    (``copyable_spell_ids``).  Rolls 1d100 vs ``spells.copy_chance_for_int``:
      success -> append to ``entry.spellbook``; source unchanged.
      failure -> set ``copy_failed`` on this source's entry; spellbook unchanged.
    Returns ``(entry, sources, success)`` — neither input is mutated."""
    if not ruleset.advanced_spell_books:
        raise SpellSourceError("copying from a source requires the Advanced Spell Book rule")
    idx = _index(sources, instance_id)
    src = sources[idx]
    if spell_id not in copyable_spell_ids(src, entry, cls, data, ruleset):
        raise SpellSourceError(
            f"{spell_id!r} cannot be copied from this source "
            "(wrong type, not castable yet, already known, or already failed here)"
        )
    chance = spell_engine.copy_chance_for_int(int_score)
    success = roll("1d100", rng) <= chance
    if success:
        new_entry = entry.model_copy(update={"spellbook": [*entry.spellbook, spell_id]})
        return new_entry, list(sources), True
    new_entries = [
        e.model_copy(update={"copy_failed": True}) if e.spell_id == spell_id else e
        for e in src.entries
    ]
    new_src = src.model_copy(update={"entries": new_entries})
    return entry, [*sources[:idx], new_src, *sources[idx + 1:]], False
