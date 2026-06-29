from pathlib import Path

from aose.data.loader import GameData
from aose.engine import spells as se
from aose.models import CharacterSpec, ClassEntry
from aose.sheet.view import spell_lists_view

DATA = GameData.load(Path(__file__).parent.parent / "data")

MM = "magic_user_magic_missile"
SLEEP = "magic_user_sleep"
SHIELD = "magic_user_shield"


def _abilities():
    return {"STR": 9, "INT": 16, "WIS": 13, "DEX": 12, "CON": 10, "CHA": 9}


def _solo_mu():
    e = ClassEntry(class_id="magic_user", level=3, hp_rolls=[4, 3, 2],
                   spellbook=[MM, SLEEP, SHIELD])
    cls = DATA.classes["magic_user"]
    e = se.assign_slot(e, cls, DATA, level=1, spell_id=MM)
    e = se.assign_slot(e, cls, DATA, level=1, spell_id=MM)
    e = se.cast_slot(e, 0)
    return CharacterSpec(name="M", abilities=_abilities(), race_id="human",
                         classes=[e], alignment="neutral")


def test_solo_arcane_single_block_no_labels():
    blocks = spell_lists_view(_solo_mu(), DATA)
    assert [b.caster_type for b in blocks] == ["arcane"]
    block = blocks[0]
    assert block.show_labels is False               # single source → no tags
    lvl1 = next(g for g in block.levels if g.level == 1)
    mm = next(r for r in lvl1.rows if r.spell_id == MM)
    assert (mm.ready, mm.spent) == (1, 1)
    assert mm.source_kind == "class" and mm.source_label == "Magic-User"
    assert mm.modal_id == f"modal-spell-magic_user-{MM}-n"


def test_multiclass_same_type_merges_with_labels():
    mu = ClassEntry(class_id="magic_user", level=3, hp_rolls=[4, 3, 2],
                    spellbook=[MM])
    ill = ClassEntry(class_id="illusionist", level=3, hp_rolls=[4, 3, 2],
                     spellbook=["illusionist_light"])
    spec = CharacterSpec(name="X", abilities=_abilities(), race_id="human",
                         classes=[mu, ill], alignment="neutral")
    blocks = spell_lists_view(spec, DATA)
    arcane = [b for b in blocks if b.caster_type == "arcane"]
    assert len(arcane) == 1                          # merged into one block
    block = arcane[0]
    assert block.show_labels is True
    labels = {r.source_label for lvl in block.levels for r in lvl.rows}
    assert {"Magic-User", "Illusionist"} <= labels


from aose.engine import spell_sources as ss

CURE = "cleric_cure_light_wounds"


def test_scroll_rows_join_caster_type_block_with_labels():
    e = ClassEntry(class_id="cleric", level=1, hp_rolls=[6])
    spec = CharacterSpec(
        name="C", abilities={"STR": 9, "INT": 10, "WIS": 16, "DEX": 12,
                             "CON": 10, "CHA": 9},
        race_id="human", classes=[e], alignment="neutral")
    spec.spell_sources = [
        ss.new_spell_source("scroll", "divine", [CURE, CURE, CURE], DATA,
                            language="Common"),
        ss.new_spell_source("scroll", "divine", [CURE], DATA, language="Common"),
    ]
    blocks = spell_lists_view(spec, DATA)
    divine = next(b for b in blocks if b.caster_type == "divine")
    assert divine.show_labels is True               # class + 2 scrolls = 3 labels
    lvl1 = next(g for g in divine.levels if g.level == 1)
    scrolls = [r for r in lvl1.rows if r.source_kind == "scroll"]
    assert sorted(r.ready for r in scrolls) == [1, 3]   # charges → ready pips
    assert all(r.castable for r in scrolls)
    assert {r.source_label for r in scrolls} == {"scroll 1", "scroll 2"}
    assert all(r.modal_id.startswith("modal-scroll-") for r in scrolls)


def test_arcane_scroll_row_locked_until_read():
    e = ClassEntry(class_id="magic_user", level=1, spellbook=[])
    spec = CharacterSpec(
        name="M", abilities={"STR": 9, "INT": 13, "WIS": 9, "DEX": 12,
                             "CON": 10, "CHA": 9},
        race_id="human", classes=[e], alignment="neutral")
    spec.spell_sources = [
        ss.new_spell_source("scroll", "arcane", ["magic_user_fire_ball"], DATA)]
    blocks = spell_lists_view(spec, DATA)
    arcane = next(b for b in blocks if b.caster_type == "arcane")
    lvl3 = next(g for g in arcane.levels if g.level == 3)
    row = next(r for r in lvl3.rows if r.spell_id == "magic_user_fire_ball")
    assert row.castable is False
    assert row.block_reason == "needs Read Magic"
    assert row.source_kind == "scroll"


from aose.models import Ability, CharClass, ClassFeature, DailyUses


def _data_with_innate():
    data = GameData.load(Path(__file__).parent.parent / "data")
    data.classes["zinn"] = CharClass(
        id="zinn", name="ZInn", prime_requisites=[Ability.STR], hit_die="1d8",
        weapons_allowed="all", armor_allowed="all", shields_allowed=True,
        progression=data.classes["fighter"].progression,
        features=[ClassFeature(id="breath", name="Breath", text="3/day",
                  daily_uses=DailyUses(per_day=3),
                  spell_id="magic_user_magic_missile")],
    )
    return data


def test_spell_backed_innate_routes_into_arcane_list():
    data = _data_with_innate()
    spec = CharacterSpec(name="T", abilities={a: 10 for a in Ability},
                         race_id="human", alignment="neutral",
                         classes=[ClassEntry(class_id="zinn", level=1)],
                         innate_uses={"breath": 1})
    blocks = spell_lists_view(spec, data)
    arcane = next(b for b in blocks if b.caster_type == "arcane")
    rows = [r for lvl in arcane.levels for r in lvl.rows
            if r.source_kind == "innate"]
    assert len(rows) == 1
    row = rows[0]
    assert row.spell_id == "magic_user_magic_missile"
    assert row.ability_id == "breath"
    assert (row.ready, row.spent) == (2, 1)         # 3/day, 1 used → 2 ready
    assert row.modal_id == "modal-innate-breath"
    assert row.source_label == "ZInn"


def test_non_spell_innate_stays_out_of_spell_lists():
    data = GameData.load(Path(__file__).parent.parent / "data")
    data.classes["zinn2"] = CharClass(
        id="zinn2", name="ZInn2", prime_requisites=[Ability.STR], hit_die="1d8",
        weapons_allowed="all", armor_allowed="all", shields_allowed=True,
        progression=data.classes["fighter"].progression,
        features=[ClassFeature(id="spores", name="Spores", text="1/day",
                  daily_uses=DailyUses(per_day=1))],   # no spell_id
    )
    spec = CharacterSpec(name="T", abilities={a: 10 for a in Ability},
                         race_id="human", alignment="neutral",
                         classes=[ClassEntry(class_id="zinn2", level=1)])
    assert spell_lists_view(spec, data) == []         # no spell-backed source
