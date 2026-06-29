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
