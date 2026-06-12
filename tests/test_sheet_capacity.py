from pathlib import Path

from aose.data.loader import GameData
from aose.sheet.view import build_sheet
from aose.models import CharacterSpec, ClassEntry, RuleSet

DATA = GameData.load(Path(__file__).parent.parent / "data")


def _fighter(level, **kw):
    return CharacterSpec(
        name="Cap", abilities={"STR": 13, "INT": 9, "WIS": 9, "DEX": 12, "CON": 12, "CHA": 9},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=level)],
        alignment="neutral", **kw,
    )


def test_sheet_exposes_remaining_proficiency_slots():
    spec = _fighter(4, ruleset=RuleSet(weapon_proficiency=True),
                    weapon_proficiencies=["sword", "dagger", "spear", "mace"])
    sheet = build_sheet(spec, DATA)
    cap = next(c for c in sheet.level_choices if c.kind == "proficiency")
    assert cap.remaining == 1


def test_sheet_no_capacity_when_all_spent():
    spec = _fighter(1, ruleset=RuleSet(weapon_proficiency=True),
                    weapon_proficiencies=["sword", "dagger", "spear", "mace"])
    sheet = build_sheet(spec, DATA)
    assert all(c.kind != "proficiency" for c in sheet.level_choices)
