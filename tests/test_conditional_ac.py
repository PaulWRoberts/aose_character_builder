from pathlib import Path

from aose.data.loader import GameData
from aose.engine import armor_class as ac
from aose.engine.armor_class import ACBreakdown, ACModLine, armor_class, armor_class_detail
from aose.models import CharacterSpec, ClassEntry, Modifier
from tests._itemhelp import coerce_equipment

_DATA_DIR = Path(__file__).parent.parent / "data"
DATA = GameData.load(_DATA_DIR)


def _spec(race_id="human", class_id="fighter", level=1, **kw):
    defaults = dict(
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id=race_id,
        alignment="neutral",
    )
    defaults.update(kw)
    coerce_equipment(defaults)
    return CharacterSpec(
        name="T", classes=[ClassEntry(class_id=class_id, level=level, hp_rolls=[8])],
        **defaults,
    )


def test_conditional_ac_modifier_does_not_change_headline(monkeypatch):
    # A bright_light -1 AC modifier must NOT change the headline number.
    def fake_all(spec, data):
        return [Modifier(target="ac", op="add", value=-1,
                         condition="bright_light", source="Light Sensitivity")]
    monkeypatch.setattr(ac, "all_modifiers", fake_all)
    spec = _spec()
    # DEX 10 -> +0; unarmoured descending = 9.
    assert armor_class(spec, DATA) == (9, 10)


def test_breakdown_lists_conditional_line(monkeypatch):
    def fake_all(spec, data):
        return [Modifier(target="ac", op="add", value=2,
                         condition="large_attacker", source="Defensive Bonus")]
    monkeypatch.setattr(ac, "all_modifiers", fake_all)
    bd = armor_class_detail(_spec(), DATA)
    assert isinstance(bd, ACBreakdown)
    assert bd.descending == 9          # situational, excluded from headline
    cond = [ln for ln in bd.lines if ln.conditional]
    assert len(cond) == 1
    assert cond[0].source == "Defensive Bonus"
    assert cond[0].effect == "+2"
    assert cond[0].note == "vs attackers larger than human-sized"
    assert bd.has_conditional is True


def test_breakdown_penalty_uses_unicode_minus(monkeypatch):
    def fake_all(spec, data):
        return [Modifier(target="ac", op="add", value=-1,
                         condition="bright_light", source="Light Sensitivity")]
    monkeypatch.setattr(ac, "all_modifiers", fake_all)
    bd = armor_class_detail(_spec(), DATA)
    cond = [ln for ln in bd.lines if ln.conditional]
    assert cond[0].effect == "−1"   # "−1"
    assert cond[0].note == "in bright light"


def test_unknown_condition_falls_back_to_underscore_replace(monkeypatch):
    def fake_all(spec, data):
        return [Modifier(target="ac", op="add", value=1,
                         condition="prone_target", source="Homebrew")]
    monkeypatch.setattr(ac, "all_modifiers", fake_all)
    bd = armor_class_detail(_spec(), DATA)
    cond = [ln for ln in bd.lines if ln.conditional]
    assert cond[0].note == "prone target"


def test_unarmored_conditioned_bonus_excluded_from_conditional_lines(monkeypatch):
    # `unarmored` is headline-evaluated, NOT a situational/conditional line.
    def fake_all(spec, data):
        return [Modifier(target="ac", op="add", value=1,
                         condition="unarmored", source="Agile Fighting")]
    monkeypatch.setattr(ac, "all_modifiers", fake_all)
    bd = armor_class_detail(_spec(), DATA)
    assert all(not ln.conditional for ln in bd.lines)
    assert bd.has_conditional is False
    # And it DOES apply to the (unarmoured) headline: 9 - 1 = 8.
    assert bd.descending == 8


def test_breakdown_has_base_and_dex_lines():
    # DEX 13 -> +1; one armour/base line + one Dexterity line, no conditional.
    spec = _spec(abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 13, "CON": 10, "CHA": 10})
    bd = armor_class_detail(spec, DATA)
    sources = [ln.source for ln in bd.lines]
    assert "Unarmoured" in sources
    assert "Dexterity" in sources
    dex_line = next(ln for ln in bd.lines if ln.source == "Dexterity")
    assert dex_line.effect == "+1"
    assert bd.descending == 8


def test_breakdown_reconciles_with_armor_class():
    spec = _spec(equipped={"armor": "chain_mail"})
    bd = armor_class_detail(spec, DATA)
    assert (bd.descending, bd.ascending) == armor_class(spec, DATA)


# ── view-model tests ──────────────────────────────────────────────────────────

from aose.sheet.view import build_sheet, SheetACLine


def test_build_sheet_flags_conditional_ac_for_drow():
    spec = _spec(race_id="drow")
    sheet = build_sheet(spec, DATA)
    assert sheet.ac_has_conditional is True
    cond = [ln for ln in sheet.ac_lines if ln.conditional]
    assert any(ln.source == "Light Sensitivity" for ln in cond)
    assert all(isinstance(ln, SheetACLine) for ln in sheet.ac_lines)


def test_build_sheet_no_conditional_ac_for_human():
    sheet = build_sheet(_spec(race_id="human"), DATA)
    assert sheet.ac_has_conditional is False
    assert all(not ln.conditional for ln in sheet.ac_lines)
