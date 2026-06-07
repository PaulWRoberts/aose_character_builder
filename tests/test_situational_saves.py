from pathlib import Path

from aose.data.loader import GameData
from aose.engine import saves
from aose.engine.saves import SituationalSaveBonus
from aose.models import CharacterSpec, ClassEntry, Modifier

_DATA_DIR = Path(__file__).parent.parent / "data"
DATA = GameData.load(_DATA_DIR)


def _spec(class_id="fighter", level=1, **kw):
    defaults = dict(
        abilities={"STR": 9, "INT": 9, "WIS": 9, "DEX": 9, "CON": 9, "CHA": 9},
        race_id="human",
        alignment="law",
    )
    defaults.update(kw)
    return CharacterSpec(
        name="T", classes=[ClassEntry(class_id=class_id, level=level)],
        **defaults,
    )


def test_no_situational_bonuses_is_empty():
    spec = _spec()  # plain fighter, no vs:* grants
    assert saves.situational_save_bonuses(spec, DATA) == []


def test_groups_two_things_under_one_source(monkeypatch):
    # Two save:vs:* modifiers from the same source+value collapse to one group.
    def fake_all(spec, data):
        return [
            Modifier(target="save:vs:fire", op="add", value=2, source="Energy Resistance"),
            Modifier(target="save:vs:lightning", op="add", value=2, source="Energy Resistance"),
        ]
    monkeypatch.setattr(saves, "all_modifiers", fake_all)
    result = saves.situational_save_bonuses(_spec(), DATA)
    assert result == [
        SituationalSaveBonus(source="Energy Resistance", bonus=2, things=["fire", "lightning"])
    ]


def test_different_sources_stay_separate(monkeypatch):
    def fake_all(spec, data):
        return [
            Modifier(target="save:vs:fire", op="add", value=2, source="Energy Resistance"),
            Modifier(target="save:vs:fire", op="add", value=1, source="Ring of Warmth"),
        ]
    monkeypatch.setattr(saves, "all_modifiers", fake_all)
    result = saves.situational_save_bonuses(_spec(), DATA)
    assert result == [
        SituationalSaveBonus(source="Energy Resistance", bonus=2, things=["fire"]),
        SituationalSaveBonus(source="Ring of Warmth", bonus=1, things=["fire"]),
    ]


def test_display_name_registry_and_fallback(monkeypatch):
    def fake_all(spec, data):
        return [
            Modifier(target="save:vs:illusion", op="add", value=2, source="Illusion Resistance"),
            Modifier(target="save:vs:cold_iron", op="add", value=1, source="Charm"),
        ]
    monkeypatch.setattr(saves, "all_modifiers", fake_all)
    result = saves.situational_save_bonuses(_spec(), DATA)
    things = {r.source: r.things for r in result}
    assert things["Illusion Resistance"] == ["illusions"]   # registry override
    assert things["Charm"] == ["cold iron"]                 # underscore fallback


def test_picks_up_magic_item_modifiers(monkeypatch):
    # Real path: an equipped magic item emits a save:vs:* modifier via all_modifiers.
    # Use a homebrew extra_modifier on an instance so we don't depend on catalog data.
    def fake_all(spec, data):
        return [Modifier(target="save:vs:fire", op="add", value=2, source="Ring of Fire Resistance")]
    monkeypatch.setattr(saves, "all_modifiers", fake_all)
    result = saves.situational_save_bonuses(_spec(), DATA)
    assert result == [
        SituationalSaveBonus(source="Ring of Fire Resistance", bonus=2, things=["fire"])
    ]


def test_empty_source_falls_back_to_dash(monkeypatch):
    def fake_all(spec, data):
        return [Modifier(target="save:vs:fire", op="add", value=2, source="")]
    monkeypatch.setattr(saves, "all_modifiers", fake_all)
    result = saves.situational_save_bonuses(_spec(), DATA)
    assert result == [SituationalSaveBonus(source="—", bonus=2, things=["fire"])]


def test_ignores_non_add_ops(monkeypatch):
    def fake_all(spec, data):
        return [Modifier(target="save:vs:fire", op="set", value=2, source="Weird")]
    monkeypatch.setattr(saves, "all_modifiers", fake_all)
    assert saves.situational_save_bonuses(_spec(), DATA) == []


# ── Task 2: view model tests ──────────────────────────────────────────────────

from aose.sheet.view import build_sheet, SheetSituationalSave


def test_build_sheet_exposes_situational_saves_for_druid():
    spec = CharacterSpec(
        name="Druid", classes=[ClassEntry(class_id="druid", level=1)],
        abilities={"STR": 9, "INT": 9, "WIS": 13, "DEX": 9, "CON": 9, "CHA": 9},
        race_id="human", alignment="neutral",
    )
    sheet = build_sheet(spec, DATA)
    energy = [s for s in sheet.situational_saves if s.source == "Energy Resistance"]
    assert len(energy) == 1
    assert energy[0].bonus == 2
    assert energy[0].vs == "fire & lightning"


def test_sheet_situational_save_joins_three_things():
    s = SheetSituationalSave.from_bonus_things(2, ["a", "b", "c"], "Src")
    assert s.vs == "a, b & c"
    one = SheetSituationalSave.from_bonus_things(1, ["solo"], "Src")
    assert one.vs == "solo"
