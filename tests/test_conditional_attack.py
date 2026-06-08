from pathlib import Path

from aose.data.loader import GameData
from aose.engine import attacks as atk
from aose.engine.attacks import (
    AttackBreakdown,
    AttackModLine,
    attack_modifiers_detail,
    attack_profiles,
)
from aose.models import CharacterSpec, ClassEntry, Modifier

_DATA_DIR = Path(__file__).parent.parent / "data"
DATA = GameData.load(_DATA_DIR)


def _spec(race_id="human", class_id="fighter", level=1, **kw):
    defaults = dict(
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id=race_id,
        alignment="neutral",
    )
    defaults.update(kw)
    return CharacterSpec(
        name="T", classes=[ClassEntry(class_id=class_id, level=level, hp_rolls=[8])],
        **defaults,
    )


def test_conditional_attack_mod_not_in_weapon_to_hit(monkeypatch):
    # A bright_light -2 attack modifier must NOT change any weapon's to-hit.
    def fake_all(spec, data):
        return [Modifier(target="attack", op="add", value=-2,
                         condition="bright_light", source="Light Sensitivity")]
    monkeypatch.setattr(atk, "all_modifiers", fake_all)
    spec = _spec()
    profiles = attack_profiles(spec, DATA)
    unarmed = next(p for p in profiles if p.unarmed)
    # STR 10 -> +0, base fighter THAC0 19 -> attack bonus 0, no conditional applied.
    assert unarmed.to_hit_ascending == 0
    assert unarmed.to_hit_thac0 == 19


def test_breakdown_lists_conditional_line(monkeypatch):
    def fake_all(spec, data):
        return [Modifier(target="attack", op="add", value=-2,
                         condition="bright_light", source="Light Sensitivity")]
    monkeypatch.setattr(atk, "all_modifiers", fake_all)
    bd = attack_modifiers_detail(_spec(), DATA)
    assert isinstance(bd, AttackBreakdown)
    assert bd.thac0 == 19
    assert bd.attack_bonus == 0
    cond = [ln for ln in bd.lines if ln.conditional]
    assert len(cond) == 1
    assert cond[0].source == "Light Sensitivity"
    assert cond[0].bonus == -2
    assert cond[0].note == "in bright light"
    assert bd.has_conditional is True


def test_breakdown_mounted_note(monkeypatch):
    def fake_all(spec, data):
        return [Modifier(target="attack", op="add", value=1,
                         condition="mounted", source="Mounted Combat")]
    monkeypatch.setattr(atk, "all_modifiers", fake_all)
    bd = attack_modifiers_detail(_spec(), DATA)
    cond = [ln for ln in bd.lines if ln.conditional]
    assert cond[0].bonus == 1
    assert cond[0].note == "while mounted"


def test_unconditional_global_attack_mod_is_non_conditional_line(monkeypatch):
    def fake_all(spec, data):
        return [Modifier(target="attack", op="add", value=1, source="Ring of Aiming")]
    monkeypatch.setattr(atk, "all_modifiers", fake_all)
    bd = attack_modifiers_detail(_spec(), DATA)
    assert bd.has_conditional is False
    assert any(ln.source == "Ring of Aiming" and ln.bonus == 1
               and not ln.conditional for ln in bd.lines)


def test_ranged_melee_mods_excluded_from_breakdown(monkeypatch):
    # ranged/melee are weapon-type-automatic; they belong on per-weapon rows,
    # not the character-level breakdown, and must not light up has_conditional.
    def fake_all(spec, data):
        return [
            Modifier(target="attack", op="add", value=1, condition="ranged",
                     source="Missile Attack Bonus"),
            Modifier(target="attack", op="add", value=1, condition="melee",
                     source="Melee Thing"),
        ]
    monkeypatch.setattr(atk, "all_modifiers", fake_all)
    bd = attack_modifiers_detail(_spec(), DATA)
    assert bd.lines == []
    assert bd.has_conditional is False


def test_unknown_condition_falls_back_to_underscore_replace(monkeypatch):
    def fake_all(spec, data):
        return [Modifier(target="attack", op="add", value=2,
                         condition="prone_target", source="Homebrew")]
    monkeypatch.setattr(atk, "all_modifiers", fake_all)
    bd = attack_modifiers_detail(_spec(), DATA)
    cond = [ln for ln in bd.lines if ln.conditional]
    assert cond[0].note == "prone target"


def test_no_attack_mods_empty_breakdown(monkeypatch):
    def fake_all(spec, data):
        return []
    monkeypatch.setattr(atk, "all_modifiers", fake_all)
    bd = attack_modifiers_detail(_spec(), DATA)
    assert bd.lines == []
    assert bd.has_conditional is False
    assert bd.thac0 == 19


# ── view-model tests ──────────────────────────────────────────────────────────

from aose.sheet.view import build_sheet, SheetAttackLine


def test_build_sheet_flags_conditional_attack_for_drow():
    sheet = build_sheet(_spec(race_id="drow"), DATA)
    assert sheet.attack_has_conditional is True
    cond = [ln for ln in sheet.attack_lines if ln.conditional]
    assert any(ln.source == "Light Sensitivity" and ln.bonus == -2
               and ln.note == "in bright light" for ln in cond)
    assert all(isinstance(ln, SheetAttackLine) for ln in sheet.attack_lines)


def test_build_sheet_flags_conditional_attack_for_knight():
    sheet = build_sheet(_spec(class_id="knight"), DATA)
    cond = [ln for ln in sheet.attack_lines if ln.conditional]
    assert any(ln.source == "Mounted Combat" and ln.bonus == 1
               and ln.note == "while mounted" for ln in cond)


def test_build_sheet_no_conditional_attack_for_human_fighter():
    sheet = build_sheet(_spec(race_id="human", class_id="fighter"), DATA)
    assert sheet.attack_has_conditional is False
    assert all(not ln.conditional for ln in sheet.attack_lines)
