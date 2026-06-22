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
from aose.engine import languages as lang_engine
from aose.engine import spells as spell_engine
from aose.engine.spells import DEMOTED_READ_MAGIC_IDS, READ_MAGIC_CANTRIP_ID

READ_MAGIC_IDS = DEMOTED_READ_MAGIC_IDS | {READ_MAGIC_CANTRIP_ID}
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
                     list_id: str | None = None,
                     language: str = "Common") -> SpellSource:
    """Build a validated SpellSource.

    Spellbooks are coerced to ``arcane``.  Every spell must exist and match
    ``caster_type`` (or, when ``list_id`` is given, be on that exact list).
    Scrolls may list the same spell more than once (each entry is one charge);
    spell books may not.  ``language`` is stored for divine scrolls (default
    Common).  No spell-level filter — a document may hold spells of any level."""
    if kind == "spellbook":
        caster_type = "arcane"
    if not spell_ids:
        raise SpellSourceError("a spell book / scroll must contain at least one spell")
    if kind == "scroll" and len(spell_ids) > MAX_SCROLL_SPELLS:
        raise SpellSourceError(f"a scroll holds at most {MAX_SCROLL_SPELLS} spells")
    if kind == "spellbook" and len(set(spell_ids)) != len(spell_ids):
        raise SpellSourceError("a spell book cannot list the same spell twice")
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
        language=language.strip() or "Common",
        entries=[SpellSourceEntry(spell_id=sid) for sid in spell_ids],
    )


def add_spell_source(sources: list[SpellSource], kind: Kind, caster_type: CasterType,
                     spell_ids: list[str], data: GameData, name: str = "",
                     list_id: str | None = None,
                     language: str = "Common") -> list[SpellSource]:
    """Add-only append (GM grant / loot); no gold."""
    return [*sources,
            new_spell_source(kind, caster_type, spell_ids, data, name, list_id, language)]


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


def _character_known_languages(spec: CharacterSpec, data: GameData) -> set[str]:
    """Case-folded set of the character's known language tokens."""
    race = data.races.get(spec.race_id)
    if race is None:
        langs = [lang_engine.alignment_language(spec.alignment, data.languages),
                 *spec.languages]
    else:
        langs = lang_engine.known_languages(
            spec.languages, race, spec.alignment, data.languages,
            granted=lang_engine.granted_languages(spec, data),
        )
    return {l.casefold() for l in langs}


def scroll_cast_block_reason(source: SpellSource, spec: CharacterSpec,
                             data: GameData) -> str | None:
    """None when the scroll spell is castable now; otherwise a short reason.

    Arcane scrolls need a matching caster AND to have been deciphered
    (``unlocked``).  Divine scrolls need a matching caster AND knowledge of the
    scroll's ``language``.  Spell books are never castable."""
    if source.kind != "scroll":
        return "not a scroll"
    if source.caster_type not in character_caster_types(spec, data):
        return f"not a {source.caster_type} caster"
    if source.caster_type == "arcane":
        return None if source.unlocked else "needs Read Magic"
    if source.language.casefold() not in _character_known_languages(spec, data):
        return f"can't read {source.language}"
    return None


def can_cast_scroll(source: SpellSource, spec: CharacterSpec, data: GameData) -> bool:
    """True when the scroll spell is castable now (see ``scroll_cast_block_reason``)."""
    return scroll_cast_block_reason(source, spec, data) is None


def ready_read_magic_slot(spec: CharacterSpec, data: GameData) -> tuple[int, int] | None:
    """(class index, slot index) of a memorized, not-yet-spent Read Magic slot in
    any arcane class, or None. Used to decipher an arcane scroll."""
    for ci, entry in enumerate(spec.classes):
        cls = data.classes.get(entry.class_id)
        if cls is None or spell_engine.caster_type_of(cls, data) != "arcane":
            continue
        for si, slot in enumerate(entry.slots):
            if not slot.spent and slot.spell_id in READ_MAGIC_IDS:
                return ci, si
    return None


def read_scroll(spec: CharacterSpec, data: GameData, instance_id: str
                ) -> tuple[list[ClassEntry], list[SpellSource]]:
    """Decipher an arcane scroll: spend a memorized Read Magic cast and mark the
    scroll ``unlocked``.  Returns updated (classes, spell_sources); inputs are not
    mutated.  Raises if the document is not an un-deciphered arcane scroll, or no
    Read Magic is memorized."""
    idx = _index(spec.spell_sources, instance_id)
    src = spec.spell_sources[idx]
    if src.kind != "scroll" or src.caster_type != "arcane":
        raise SpellSourceError("only arcane scrolls are deciphered with Read Magic")
    if src.unlocked:
        raise SpellSourceError("this scroll is already deciphered")
    found = ready_read_magic_slot(spec, data)
    if found is None:
        raise SpellSourceError("no memorized Read Magic available to read the scroll")
    ci, si = found
    classes = list(spec.classes)
    classes[ci] = spell_engine.cast_slot(classes[ci], si)
    new_src = src.model_copy(update={"unlocked": True})
    sources = [*spec.spell_sources[:idx], new_src, *spec.spell_sources[idx + 1:]]
    return classes, sources


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
