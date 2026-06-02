"""Unit tests for the spell-slot engine (memorize/cast/restore/clear/rest)."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine import spells
from aose.engine.spells import SpellError
from aose.models import ClassEntry, SpellSlot

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def _mu(spellbook, slots=None):
    return ClassEntry(class_id="magic_user", level=1, hp_rolls=[3],
                      spellbook=spellbook, slots=slots or [])


def test_assign_slot_known_and_level(data):
    cls = data.classes["magic_user"]
    e = _mu(["magic_user_magic_missile"])
    e2 = spells.assign_slot(e, cls, data, 1, "magic_user_magic_missile")
    assert len(e2.slots) == 1
    assert e2.slots[0].spell_id == "magic_user_magic_missile"
    assert e2.slots[0].spent is False
    assert e2.slots[0].reversed is False


def test_assign_slot_rejects_unknown(data):
    cls = data.classes["magic_user"]
    e = _mu(["magic_user_magic_missile"])
    with pytest.raises(SpellError):
        spells.assign_slot(e, cls, data, 1, "magic_user_sleep")  # not in book


def test_assign_slot_rejects_wrong_level(data):
    cls = data.classes["magic_user"]
    e = _mu(["magic_user_magic_missile"])
    with pytest.raises(SpellError):
        spells.assign_slot(e, cls, data, 2, "magic_user_magic_missile")


def test_assign_slot_respects_cap(data):
    cls = data.classes["magic_user"]  # L1 magic-user: one level-1 slot
    e = _mu(["magic_user_magic_missile", "magic_user_sleep"])
    e = spells.assign_slot(e, cls, data, 1, "magic_user_magic_missile")
    with pytest.raises(SpellError):
        spells.assign_slot(e, cls, data, 1, "magic_user_sleep")


def test_assign_slot_reversed_arcane_reversible_ok(data):
    cls = data.classes["magic_user"]
    e = _mu(["magic_user_light"])  # Light is reversible (→ Darkness)
    e2 = spells.assign_slot(e, cls, data, 1, "magic_user_light", reversed=True)
    assert e2.slots[0].reversed is True


def test_assign_slot_reversed_rejected_for_non_reversible(data):
    cls = data.classes["magic_user"]
    e = _mu(["magic_user_magic_missile"])
    with pytest.raises(SpellError):
        spells.assign_slot(e, cls, data, 1, "magic_user_magic_missile", reversed=True)


def test_assign_slot_reversed_rejected_for_divine(data):
    cls = data.classes["druid"]
    e = ClassEntry(class_id="druid", level=1, hp_rolls=[5])
    with pytest.raises(SpellError):
        spells.assign_slot(e, cls, data, 1, "faerie_fire", reversed=True)


def test_cast_slot_spends_only_one_duplicate(data):
    e = ClassEntry(class_id="magic_user", level=1, slots=[
        SpellSlot(level=1, spell_id="magic_user_sleep"),
        SpellSlot(level=1, spell_id="magic_user_sleep"),
    ])
    e2 = spells.cast_slot(e, 0)
    assert e2.slots[0].spent is True
    assert e2.slots[1].spent is False


def test_cast_slot_double_cast_raises(data):
    e = ClassEntry(class_id="magic_user", level=1,
                   slots=[SpellSlot(level=1, spell_id="magic_user_sleep")])
    e = spells.cast_slot(e, 0)
    with pytest.raises(SpellError):
        spells.cast_slot(e, 0)


def test_restore_slot_unspends(data):
    e = ClassEntry(class_id="magic_user", level=1,
                   slots=[SpellSlot(level=1, spell_id="magic_user_sleep", spent=True)])
    e2 = spells.restore_slot(e, 0)
    assert e2.slots[0].spent is False


def test_clear_slot_removes_one_row(data):
    e = ClassEntry(class_id="magic_user", level=1, slots=[
        SpellSlot(level=1, spell_id="magic_user_sleep"),
        SpellSlot(level=1, spell_id="magic_user_magic_missile"),
    ])
    e2 = spells.clear_slot(e, 0)
    assert [s.spell_id for s in e2.slots] == ["magic_user_magic_missile"]


def test_bad_index_raises(data):
    e = ClassEntry(class_id="magic_user", level=1, slots=[])
    for fn in (spells.cast_slot, spells.restore_slot, spells.clear_slot):
        with pytest.raises(SpellError):
            fn(e, 0)


def test_restore_all_and_clear_all(data):
    e = ClassEntry(class_id="magic_user", level=1, slots=[
        SpellSlot(level=1, spell_id="magic_user_sleep", spent=True),
        SpellSlot(level=1, spell_id="magic_user_magic_missile", spent=True),
    ])
    restored = spells.restore_all_slots(e)
    assert all(s.spent is False for s in restored.slots)
    cleared = spells.clear_all_slots(e)
    assert cleared.slots == []
