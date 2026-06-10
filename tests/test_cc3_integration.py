from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine.armor_class import armor_class
from aose.engine.attacks import attack_profiles
from aose.engine.saves import situational_save_bonuses
from aose.sheet.view import build_sheet
from aose.models import Ability, CharacterSpec, ClassEntry

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


def _spec(class_id, level=1, choices=None):
    return CharacterSpec(
        name="T", abilities={a: 12 for a in Ability}, race_id=class_id,
        alignment="neutral", classes=[ClassEntry(class_id=class_id, level=level)],
        feature_choices=choices or {},
    )


def test_mutoid_scales_grant_ac(data):
    spec = _spec("mutoid", choices={"mutations": ["scales", "clawed_hand"]})
    desc, _asc = armor_class(spec, data)
    base, _ = armor_class(_spec("mutoid", choices={"mutations": ["beast_ears", "gills"]}), data)
    assert desc == base - 2  # +2 AC = 2 lower descending


def test_mutoid_clawed_hand_attack(data):
    spec = _spec("mutoid", choices={"mutations": ["clawed_hand", "gills"]})
    names = [p.name for p in attack_profiles(spec, data)]
    assert "Clawed Hand" in names


def test_mycelian_natural_ac_scales(data):
    l1 = armor_class(_spec("mycelian", level=1), data)[0]
    l4 = armor_class(_spec("mycelian", level=4), data)[0]
    assert l1 == 6 and l4 == 3


def test_mycelian_fist_scales(data):
    spec = _spec("mycelian", level=3)
    fist = next(p for p in attack_profiles(spec, data) if p.name == "Fists")
    assert fist.damage.startswith("3d4")


def test_dragonborn_bloodline_resistance(data):
    spec = _spec("dragonborn", choices={"draconic_bloodline": ["red"]})
    bonuses = situational_save_bonuses(spec, data)
    things = {t.lower() for b in bonuses for t in b.things}
    assert "fire" in things


def test_tiefling_gift_innate_on_sheet(data):
    spec = _spec("tiefling", choices={
        "fiendish_gifts": ["magic_missile", "save_poison"],
        "fiendish_appearance": ["horns", "tail"],
    })
    sheet = build_sheet(spec, data)
    innate_names = [a.name for a in sheet.innate_abilities]
    assert "Magic Missile" in innate_names
    feat_names = [f.name for f in sheet.class_features]
    assert "Resist Poison" in feat_names
    assert "Horns" in feat_names  # cosmetic still shown as a feature
