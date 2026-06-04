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
