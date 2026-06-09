"""Sheet assembly (build_sheet) end-to-end checks."""
from pathlib import Path

from aose.data.loader import GameData
from aose.models import CharacterSpec, ClassEntry

DATA = GameData.load(Path(__file__).parent.parent / "data")


def _sheet(race_id, class_id, *, str_score=12, hp=8):
    from aose.sheet.view import build_sheet
    spec = CharacterSpec(
        name="G",
        abilities={"STR": str_score, "INT": 10, "WIS": 10, "DEX": 10, "CON": 12, "CHA": 10},
        race_id=race_id, alignment="neutral",
        classes=[ClassEntry(class_id=class_id, level=1, hp_rolls=[hp])],
    )
    return build_sheet(spec, DATA)


def _open_doors_cell(sheet):
    str_row = next(r for r in sheet.abilities if r.ability == "STR")
    return next(c for c in str_row.table if c.label == "Open Doors")


def test_gargantua_open_doors_cell_bumped_with_note():
    cell = _open_doors_cell(_sheet("gargantua", "fighter", str_score=12))
    assert cell.value == "3-in-6"
    assert cell.note == "+1 category (Gargantua)"


def test_non_gargantua_open_doors_cell_plain():
    cell = _open_doors_cell(_sheet("human", "fighter", str_score=12))
    assert cell.value == "2-in-6"
    assert cell.note == ""
