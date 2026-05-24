from pathlib import Path

import pytest

from aose.characters.storage import (
    delete_character,
    list_character_ids,
    load_character,
    save_character,
)
from aose.models import CharacterSpec, ClassEntry, RuleSet


def make_spec(name="Test"):
    return CharacterSpec(
        name=name,
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[5])],
        alignment="neutral",
    )


def test_save_and_load_roundtrip(tmp_path):
    spec = make_spec(name="Bilbo")
    save_character("bilbo", spec, tmp_path)
    loaded = load_character("bilbo", tmp_path)
    assert loaded.name == "Bilbo"
    assert loaded.classes[0].class_id == "fighter"
    assert loaded.ruleset.separate_race_class is True


def test_list_ids(tmp_path):
    save_character("a", make_spec("A"), tmp_path)
    save_character("b", make_spec("B"), tmp_path)
    assert list_character_ids(tmp_path) == ["a", "b"]


def test_list_empty_when_dir_missing(tmp_path):
    nonexistent = tmp_path / "nope"
    assert list_character_ids(nonexistent) == []


def test_load_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_character("ghost", tmp_path)


def test_delete(tmp_path):
    save_character("x", make_spec("X"), tmp_path)
    delete_character("x", tmp_path)
    assert list_character_ids(tmp_path) == []


def test_example_character_loads():
    examples_dir = Path(__file__).parent.parent / "examples"
    spec = load_character("thorin", examples_dir)
    assert spec.name == "Thorin"
    assert spec.race_id == "dwarf"
