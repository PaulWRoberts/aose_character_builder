"""Carcass Crawler 2/4/5 content — Wood Elf, Halfling Hearthsinger, Halfling
Reeve, Arcane Bard, Ratling, Changeling. Pure-data import (no new mechanics):
these tests pin loading, source tagging, race-as-class linkage, spell-list
wiring, and the conditional combat grants."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.models import CharacterSpec, RuleSet
from aose.models.character import ClassEntry
from aose.engine.features import is_race_as_class, all_modifiers
from aose.engine.attacks import attack_modifiers_detail

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


CLASS_SOURCES = {
    "wood_elf": "carcass_crawler_2",
    "halfling_hearthsinger": "carcass_crawler_4",
    "halfling_reeve": "carcass_crawler_4",
    "arcane_bard": "carcass_crawler_4",
    "ratling": "carcass_crawler_5",
    "changeling": "carcass_crawler_5",
}
RACE_SOURCES = {
    "wood_elf": "carcass_crawler_2",
    "ratling": "carcass_crawler_5",
    "changeling": "carcass_crawler_5",
}


def test_classes_loaded_with_source(data):
    for cid, src in CLASS_SOURCES.items():
        assert cid in data.classes, cid
        assert data.classes[cid].source == src


def test_races_loaded_with_source(data):
    for rid, src in RACE_SOURCES.items():
        assert rid in data.races, rid
        assert data.races[rid].source == src


def test_race_as_class_linkage(data):
    # Demihuman classes lock to their own race…
    for cid in ["wood_elf", "ratling", "changeling"]:
        assert data.classes[cid].race_locked == cid
    # …the two halfling demihuman classes lock to the existing halfling race…
    assert data.classes["halfling_hearthsinger"].race_locked == "halfling"
    assert data.classes["halfling_reeve"].race_locked == "halfling"
    # …and the Arcane Bard is a human-playable class, not race-locked.
    assert data.classes["arcane_bard"].race_locked is None


def test_spell_list_wiring(data):
    assert data.classes["wood_elf"].spell_lists == ["druid"]
    assert data.classes["halfling_reeve"].spell_lists == ["druid"]
    assert data.classes["arcane_bard"].spell_lists == ["magic_user"]
    # Non-casters carry no spell list.
    for cid in ["halfling_hearthsinger", "ratling", "changeling"]:
        assert data.classes[cid].spell_lists == []


def test_delayed_casting_first_slot_row(data):
    # Reeve casts from 4th level; Arcane Bard from 2nd.
    reeve = data.classes["halfling_reeve"].progression
    assert reeve[3].spell_slots is None
    assert reeve[4].spell_slots == {1: 1}
    bard = data.classes["arcane_bard"].progression
    assert bard[1].spell_slots is None
    assert bard[2].spell_slots == {1: 1}
    # Wood Elf casts from 1st level.
    assert data.classes["wood_elf"].progression[1].spell_slots == {1: 1}


def test_reeve_is_lawful_only(data):
    assert data.classes["halfling_reeve"].allowed_alignments == ["law"]


def _rac_spec(cls_id: str, level: int, race_id: str, alignment: str = "neutral"):
    return CharacterSpec(
        name="T",
        abilities={"STR": 12, "INT": 12, "WIS": 13, "DEX": 14, "CON": 12, "CHA": 13},
        race_id=race_id,
        classes=[ClassEntry(class_id=cls_id, level=level, hp_rolls=[6] * level)],
        alignment=alignment,
        ruleset=RuleSet(separate_race_class=False),
    )


def test_wood_elf_missile_bonus_applies_once(data):
    """Race-as-class suppresses race features, so the +1 ranged missile bonus
    comes from the class alone — exactly one such modifier, never doubled."""
    spec = _rac_spec("wood_elf", 7, "wood_elf")
    assert is_race_as_class(spec, data)
    ranged = [
        m for m in all_modifiers(spec, data)
        if m.target == "attack" and m.condition == "ranged"
    ]
    assert len(ranged) == 1
    assert ranged[0].value == 1


def test_reeve_goblin_and_wolf_conditional_lines(data):
    """Goblin Slayer / Wolf Hunter surface as conditional attack lines."""
    spec = _rac_spec("halfling_reeve", 4, "halfling", alignment="law")
    detail = attack_modifiers_detail(spec, data)
    notes = {l.note: l.bonus for l in detail.lines if l.conditional}
    assert notes.get("vs goblins") == 1
    assert notes.get("vs wolves") == 1


def test_demihuman_caps_reference_real_classes(data):
    for rid in RACE_SOURCES:
        race = data.races[rid]
        for cid in race.allowed_classes:
            assert cid in data.classes, f"{rid} -> {cid}"
        for cid in race.class_level_caps:
            assert cid in race.allowed_classes, f"{rid} cap {cid} not allowed"
