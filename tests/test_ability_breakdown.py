"""AbilityRow breakdown: base/computed display fields, modifier lines, the
per-ability reference-table row, and the conditional-modifier flag."""
import copy
from pathlib import Path

from aose.data.loader import GameData
from aose.models import CharacterSpec, ClassEntry, MagicItem
from aose.sheet.view import build_sheet

DATA_DIR = Path(__file__).parent.parent / "data"
DATA = GameData.load(DATA_DIR)


def _spec(**overrides):
    base = dict(
        name="A",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 16, "CHA": 10},
        race_id="human", alignment="neutral",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
    )
    base.update(overrides)
    return CharacterSpec(**base)


def _row(sheet, ability):
    return next(r for r in sheet.abilities if r.ability == ability)


def test_plain_ability_has_table_row_and_no_lines():
    sheet = build_sheet(_spec(), DATA)
    con = _row(sheet, "CON")
    assert con.score == 16
    assert con.base_score == 16
    assert con.has_conditional is False
    assert con.lines == []
    cells = {c.label: c.value for c in con.table}
    assert cells["Hit Points"] == "+2"


def test_table_row_uses_computed_score():
    # Temp +2 takes CON 16 -> 18; the table row must reflect the computed 18.
    sheet = build_sheet(_spec(temp_ability_modifiers={"CON": 2}), DATA)
    con = _row(sheet, "CON")
    assert con.score == 18
    cells = {c.label: c.value for c in con.table}
    assert cells["Hit Points"] == "+3"


def test_temp_modifier_appears_as_line():
    sheet = build_sheet(_spec(temp_ability_modifiers={"STR": -1}), DATA)
    strr = _row(sheet, "STR")
    assert strr.score == 11
    assert strr.base_score == 12
    sources = {ln.source: ln for ln in strr.lines}
    assert "Temporary" in sources
    assert sources["Temporary"].effect == "−1"
    assert sources["Temporary"].conditional is False


def test_prime_requisite_gets_xp_modifier_cell():
    # Fighter's prime requisite is STR -> XP Modifier row appears.
    sheet = build_sheet(_spec(), DATA)
    strr = _row(sheet, "STR")
    cells = {c.label: c.value for c in strr.table}
    assert "XP Modifier" in cells
    # Non-prime ability has no XP modifier cell.
    cha = _row(sheet, "CHA")
    assert "XP Modifier" not in {c.label for c in cha.table}


def _with_gauntlets(data):
    d = copy.deepcopy(data)
    d.items["gauntlets_of_ogre_power"] = MagicItem(
        id="gauntlets_of_ogre_power", name="Gauntlets of Ogre Power",
        category="miscellaneous_magic_items", item_type="magic", cost_gp=0,
        weight_cn=0, magic=True, equippable=True,
        modifiers=[{"target": "ability:STR", "op": "set", "value": 18}],
    )
    return d


def test_magic_item_modifier_line_names_the_item():
    from aose.engine.magic import add_free_magic_item, equip_magic
    d = _with_gauntlets(DATA)
    spec = _spec(abilities={"STR": 9, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10})
    spec.magic_items = add_free_magic_item([], "gauntlets_of_ogre_power", d)
    spec.magic_items = equip_magic(spec.magic_items, spec.magic_items[0].instance_id, d)
    sheet = build_sheet(spec, d)
    strr = _row(sheet, "STR")
    assert strr.score == 18
    line = next(ln for ln in strr.lines if ln.source == "Gauntlets of Ogre Power")
    assert line.effect == "set to 18"
    assert line.conditional is False


def test_conditional_ability_modifier_sets_flag():
    d = copy.deepcopy(DATA)
    d.items["amulet_of_might"] = MagicItem(
        id="amulet_of_might", name="Amulet of Might",
        category="miscellaneous_magic_items", item_type="magic", cost_gp=0,
        weight_cn=0, magic=True, equippable=True,
        modifiers=[{"target": "ability:STR", "op": "add", "value": 2,
                    "condition": "in_combat"}],
    )
    from aose.engine.magic import add_free_magic_item, equip_magic
    spec = _spec()
    spec.magic_items = add_free_magic_item([], "amulet_of_might", d)
    spec.magic_items = equip_magic(spec.magic_items, spec.magic_items[0].instance_id, d)
    sheet = build_sheet(spec, d)
    strr = _row(sheet, "STR")
    assert strr.has_conditional is True
    cond_line = next(ln for ln in strr.lines if ln.conditional)
    assert cond_line.source == "Amulet of Might"
