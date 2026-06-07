"""Tests for aose/engine/languages.py — pure unit + integration against real data."""
from pathlib import Path

import pytest

from aose.engine.languages import (
    LanguageError,
    additional_language_count,
    alignment_language,
    available_additional,
    broken_speech,
    display_name,
    known_languages,
    native_languages,
    validate_languages,
)

DATA_DIR = Path(__file__).parent.parent / "data"


def _data():
    from aose.data.loader import GameData
    return GameData.load(DATA_DIR)


@pytest.mark.parametrize("score,expected", [
    (3, 0), (8, 0), (12, 0), (13, 1), (15, 1), (16, 2), (17, 2), (18, 3),
])
def test_additional_language_count(score, expected):
    assert additional_language_count(score) == expected


def test_broken_speech_only_at_three():
    assert broken_speech(3) is True
    assert broken_speech(4) is False
    assert broken_speech(12) is False


def test_language_error_is_valueerror():
    assert issubclass(LanguageError, ValueError)


# ── Task 3: native / alignment / available / known ──────────────────────────

def test_native_languages_from_race():
    data = _data()
    elf = data.races["elf"]
    assert native_languages(elf) == elf.languages
    assert "elvish" in native_languages(elf)


def test_alignment_language_lookup():
    data = _data()
    assert alignment_language("law", data.languages) == "Lawful"
    assert alignment_language("chaos", data.languages) == "Chaotic"


def test_available_additional_excludes_known_case_insensitively():
    data = _data()
    elf = data.races["elf"]  # native incl. elvish, gnoll, hobgoblin, orcish
    avail = available_additional(data.languages, set(native_languages(elf)))
    assert "elvish" not in avail
    assert "gnoll" not in avail
    assert "orcish" not in avail
    assert "dragon" in avail            # something the elf doesn't speak
    assert len(avail) == len(set(avail))


def test_known_languages_composes_and_dedupes_in_order():
    data = _data()
    human = data.races["human"]  # native: ["common"]
    known = known_languages(["dragon"], human, "law", data.languages)
    assert known == ["common", "Lawful", "dragon"]


def test_known_languages_dedupes_case_insensitively():
    data = _data()
    elf = data.races["elf"]
    # Even if a chosen value duplicates a native tongue by case, it appears once.
    known = known_languages(["elvish"], elf, "neutral", data.languages)
    lowered = [k.casefold() for k in known]
    assert len(lowered) == len(set(lowered))


# ── Task 4: validate_languages ───────────────────────────────────────────────

def test_validate_languages_within_limit_passes():
    data = _data()
    human = data.races["human"]  # INT 16 -> 2 additional allowed
    validate_languages(["Dragon", "Ogre"], human, "law", 16, data.languages)


def test_validate_languages_empty_always_passes():
    data = _data()
    human = data.races["human"]
    validate_languages([], human, "law", 9, data.languages)


def test_validate_languages_too_many_fails():
    data = _data()
    human = data.races["human"]  # INT 13 -> only 1 allowed
    with pytest.raises(LanguageError):
        validate_languages(["Dragon", "Ogre"], human, "law", 13, data.languages)


def test_validate_languages_rejects_native_tongue():
    data = _data()
    elf = data.races["elf"]  # natively speaks elvish
    with pytest.raises(LanguageError):
        validate_languages(["Elvish"], elf, "neutral", 18, data.languages)


def test_validate_languages_rejects_alignment_tongue():
    data = _data()
    human = data.races["human"]
    with pytest.raises(LanguageError):
        validate_languages(["Lawful"], human, "law", 18, data.languages)


def test_validate_languages_rejects_duplicates():
    data = _data()
    human = data.races["human"]
    with pytest.raises(LanguageError):
        validate_languages(["Dragon", "Dragon"], human, "law", 18, data.languages)


def test_validate_languages_rejects_unknown():
    data = _data()
    human = data.races["human"]
    with pytest.raises(LanguageError):
        validate_languages(["Klingon"], human, "law", 18, data.languages)


def test_display_name_uses_registry():
    data = _data()
    assert display_name("common", data.languages) == "Common"
    assert display_name("deepcommon", data.languages) == "Deepcommon"
    assert display_name("lizard_man", data.languages) == "Lizard man"


def test_display_name_fallback_titlecases_unregistered_id():
    data = _data()
    assert display_name("language_of_earth_elementals", data.languages) == \
        "Language of earth elementals"
