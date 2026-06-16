from pathlib import Path

from aose.data.loader import GameData
from aose.web.book import class_entry, race_entry, spell_entry

DATA_DIR = Path(__file__).parent.parent / "data"


def _data():
    return GameData.load(DATA_DIR)


def _stat(entry, label):
    for s in entry["stats"]:
        if s["label"] == label:
            return s["value"]
    raise AssertionError(f"no stat {label!r} in {[s['label'] for s in entry['stats']]}")


def test_class_entry_has_header_and_features():
    cls = _data().classes["assassin"]
    e = class_entry(cls)
    assert e["kind"] == "class"
    assert e["name"] == "Assassin"
    assert _stat(e, "Prime requisite") == "DEX"
    assert _stat(e, "Hit Dice") == "1d4"
    assert _stat(e, "Maximum level") == "14"
    assert "Leather" in _stat(e, "Armour")
    assert _stat(e, "Weapons") == "Any"
    # Features carry their markdown text verbatim for the macro to render.
    names = [f["name"] for f in e["features"]]
    assert "Combat" in names
    assert any("master of the art" in f["text"].lower() or "masters of the art" in f["text"].lower()
               for f in e["features"])
    assert e["body"] is None


def test_race_entry_trims_to_deltas_and_languages():
    race = _data().races["drow"]
    e = race_entry(race)
    assert e["kind"] == "race"
    assert _stat(e, "Requirements") == "INT 9"
    mods = _stat(e, "Ability modifiers")
    assert "DEX +1" in mods and "CON -1" in mods
    assert "Elvish" in _stat(e, "Languages")
    feat_names = [f["name"] for f in e["features"]]
    assert "Innate Magic" in feat_names


def test_spell_entry_carries_meta_and_body():
    spell = _data().spells["cleric_light"]
    e = spell_entry(spell)
    assert e["kind"] == "spell"
    assert _stat(e, "Range") == spell.range
    assert _stat(e, "Duration") == spell.duration
    assert e["features"] == []
    assert e["body"] == spell.description
