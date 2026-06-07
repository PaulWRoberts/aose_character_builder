"""Languages subsystem — pure / cycle-free.

Imports only models (no engine, no web).  Native languages come from the race;
the alignment tongue is auto-determined by alignment; additional languages are
INT-gated player picks.  All ids are lowercase; the ``names`` registry maps
them to proper display names.
"""
from __future__ import annotations

from aose.models import Ability


class LanguageError(ValueError):
    """Raised when a language selection is invalid."""


def display_name(lang_id: str, lang_data) -> str:
    """Proper display name for a language id. Registry first; otherwise a
    readable fallback (underscores -> spaces, first letter capitalised) so any
    data-discovered language still renders with a proper name."""
    registered = lang_data.names.get(lang_id)
    if registered:
        return registered
    return lang_id.replace("_", " ").capitalize()


def additional_language_count(int_score: int) -> int:
    """Number of additional languages granted by *final* INT (OSE table)."""
    if int_score >= 18:
        return 3
    if int_score >= 16:
        return 2
    if int_score >= 13:
        return 1
    return 0


def broken_speech(int_score: int) -> bool:
    """INT 3 speaks in broken sentences — a display note, grants 0 additional."""
    return int_score == 3


def granted_languages(spec, data) -> list[str]:
    """Special languages a character's race/class *features* grant — order-stable,
    deduped case-insensitively. Read from ``feature.mechanical['languages']``.
    Race features always count; class features are gated by ``gained_at_level``."""
    out: list[str] = []
    seen: set[str] = set()

    def _add(ids):
        for lang_id in ids or []:
            key = lang_id.casefold()
            if key not in seen:
                seen.add(key)
                out.append(lang_id)

    race = data.races.get(spec.race_id)
    if race is not None:
        for feat in race.features:
            if feat.mechanical:
                _add(feat.mechanical.get("languages"))
    for entry in spec.classes:
        cls = data.classes.get(entry.class_id)
        if cls is None:
            continue
        for feat in cls.features:
            if feat.gained_at_level <= entry.level and feat.mechanical:
                _add(feat.mechanical.get("languages"))
    return out


def native_languages(race) -> list[str]:
    """The character's racial native tongues (already includes Common)."""
    return list(race.languages)


def alignment_language(alignment: str, lang_data) -> str:
    """The tongue for an alignment id (law / neutral / chaos)."""
    return lang_data.alignment[alignment]


def available_additional(lang_data, already_known: set[str]) -> list[str]:
    """The additional list minus any language already known, compared
    case-insensitively.  Order-stable, no duplicates."""
    known = {k.casefold() for k in already_known}
    out: list[str] = []
    seen: set[str] = set()
    for lang in lang_data.additional:
        key = lang.casefold()
        if key in known or key in seen:
            continue
        seen.add(key)
        out.append(lang)
    return out


def known_languages(chosen, race, alignment, lang_data) -> list[str]:
    """Native + alignment tongue + chosen additional, order-stable + deduped
    (case-insensitive)."""
    ordered = list(native_languages(race))
    ordered.append(alignment_language(alignment, lang_data))
    ordered.extend(chosen)
    out: list[str] = []
    seen: set[str] = set()
    for lang in ordered:
        key = lang.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(lang)
    return out


def validate_languages(chosen, race, alignment, final_int, lang_data) -> None:
    """Raise ``LanguageError`` unless the chosen additional languages are valid:

    * at most ``additional_language_count(final_int)`` of them,
    * no case-insensitive duplicates within the choices,
    * each is in ``available_additional`` (i.e. in the data list AND not already
      native or the alignment tongue).
    """
    limit = additional_language_count(final_int)
    if len(chosen) > limit:
        raise LanguageError(
            f"At most {limit} additional language(s) at INT {final_int}; "
            f"got {len(chosen)}."
        )

    seen: set[str] = set()
    for lang in chosen:
        key = lang.casefold()
        if key in seen:
            raise LanguageError(f"Duplicate language: {lang!r}")
        seen.add(key)

    already = set(native_languages(race)) | {alignment_language(alignment, lang_data)}
    allowed = {a.casefold() for a in available_additional(lang_data, already)}
    for lang in chosen:
        if lang.casefold() not in allowed:
            raise LanguageError(f"{lang!r} is not a selectable additional language.")


def literacy(spec, data) -> str:
    """Literacy state: ``"illiterate"`` (INT <= 5), ``"basic"`` (6-8), or
    ``"literate"`` (>= 9). A class feature may force illiteracy below a level via
    ``mechanical['illiterate_below_level']`` (barbarian: illiterate at level 1)."""
    int_score = spec.abilities[Ability.INT]
    if int_score <= 5:
        tier = "illiterate"
    elif int_score <= 8:
        tier = "basic"
    else:
        tier = "literate"

    for entry in spec.classes:
        cls = data.classes.get(entry.class_id)
        if cls is None:
            continue
        for feat in cls.features:
            if not feat.mechanical:
                continue
            floor = feat.mechanical.get("illiterate_below_level")
            if floor is not None and entry.level < floor:
                return "illiterate"
    return tier
