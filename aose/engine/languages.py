"""Languages subsystem — pure / cycle-free.

Imports only models (no engine, no web).  Native languages come from the race;
the alignment tongue is auto-determined by alignment; additional languages are
INT-gated player picks.  All exclusion/dedup comparisons are case-insensitive
(race langs are lowercase ids like ``elvish``; the additional list is
title-case display names like ``Elvish``).
"""
from __future__ import annotations


class LanguageError(ValueError):
    """Raised when a language selection is invalid."""


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
