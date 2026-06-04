"""Other-possessions + notes: model defaults and engine mutators."""
import pytest

from aose.models import CharacterSpec, ClassEntry


def _fighter(**kw):
    return CharacterSpec(
        name="Bran",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral", **kw,
    )


def test_new_fields_default_empty():
    spec = _fighter()
    assert spec.other_possessions == []
    assert spec.notes == ""


def test_fields_round_trip():
    spec = _fighter(other_possessions=["a bronze key"], notes="hello")
    reloaded = CharacterSpec.model_validate(spec.model_dump())
    assert reloaded.other_possessions == ["a bronze key"]
    assert reloaded.notes == "hello"


from aose.engine import possessions
from aose.engine.possessions import PossessionError


def test_add_possession_appends_trimmed():
    assert possessions.add_possession([], "  a bronze key  ") == ["a bronze key"]


def test_add_possession_skips_empty():
    assert possessions.add_possession(["x"], "   ") == ["x"]


def test_add_possession_allows_duplicates():
    assert possessions.add_possession(["key"], "key") == ["key", "key"]


def test_add_possession_returns_new_list():
    original = ["x"]
    result = possessions.add_possession(original, "y")
    assert original == ["x"]            # not mutated in place
    assert result == ["x", "y"]


def test_remove_possession_by_index():
    assert possessions.remove_possession(["a", "b", "c"], 1) == ["a", "c"]


def test_remove_possession_bad_index_raises():
    with pytest.raises(PossessionError):
        possessions.remove_possession(["a"], 5)
    with pytest.raises(PossessionError):
        possessions.remove_possession(["a"], -1)
