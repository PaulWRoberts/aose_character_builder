from pathlib import Path

from aose.data.loader import GameData
from aose.engine import spells as se
from aose.models import CharacterSpec, ClassEntry
from aose.sheet.view import spellbook_view

DATA = GameData.load(Path(__file__).parent.parent / "data")


MM = "magic_user_magic_missile"
SHIELD = "magic_user_shield"
SLEEP = "magic_user_sleep"
LIGHT = "magic_user_light"   # level 1, reversible → "Darkness"


def _mu():
    e = ClassEntry(class_id="magic_user", level=3, hp_rolls=[4, 3, 2],
                   spellbook=[MM, SLEEP, SHIELD])
    spec = CharacterSpec(
        name="M", abilities={"STR": 9, "INT": 16, "WIS": 9, "DEX": 12, "CON": 10, "CHA": 9},
        race_id="human", classes=[e], alignment="neutral",
    )
    cls = DATA.classes["magic_user"]
    # assign_slot is the real API (plan called it prepare)
    e2 = se.assign_slot(e, cls, DATA, level=1, spell_id=MM)
    e2 = se.assign_slot(e2, cls, DATA, level=1, spell_id=MM)   # memorise twice
    e2 = se.cast_slot(e2, 0)                                    # spend one copy
    spec.classes = [e2]
    return spec


def _mu_reversed():
    e = ClassEntry(class_id="magic_user", level=3, hp_rolls=[4, 3, 2],
                   spellbook=[MM, LIGHT])
    spec = CharacterSpec(
        name="M", abilities={"STR": 9, "INT": 16, "WIS": 9, "DEX": 12, "CON": 10, "CHA": 9},
        race_id="human", classes=[e], alignment="neutral",
    )
    cls = DATA.classes["magic_user"]
    e2 = se.assign_slot(e, cls, DATA, level=1, spell_id=LIGHT)                    # normal
    e2 = se.assign_slot(e2, cls, DATA, level=1, spell_id=LIGHT, reversed=True)    # reversed
    spec.classes = [e2]
    return spec


def test_reversed_memorisation_is_distinct_row():
    blocks = spellbook_view(_mu_reversed(), DATA)
    lvl1 = next(g for g in blocks[0].levels if g.level == 1)
    light_rows = [r for r in lvl1.rows if r.spell_id == LIGHT]
    assert len(light_rows) == 2
    normal = next(r for r in light_rows if not r.reversed)
    rev = next(r for r in light_rows if r.reversed)
    assert normal.display_name == "Light"
    assert rev.display_name == "Darkness"
    assert normal.ready == 1 and rev.ready == 1
    assert len(normal.ready_slots) == 1 and len(rev.ready_slots) == 1
    assert set(normal.ready_slots).isdisjoint(rev.ready_slots)


def test_spellbook_view_groups_by_level_with_cast_counts():
    spec = _mu()
    blocks = spellbook_view(spec, DATA)
    assert len(blocks) == 1
    block = blocks[0]
    assert block.caster_type == "arcane"
    lvl1 = next(g for g in block.levels if g.level == 1)
    mm = next(r for r in lvl1.rows if r.spell_id == MM)
    assert (mm.ready, mm.spent) == (1, 1)      # 2 memorised, 1 cast
    assert mm.known is True
    sh = next(r for r in lvl1.rows if r.spell_id == SHIELD)
    assert (sh.ready, sh.spent) == (0, 0) and sh.known is True   # known, not memorised
