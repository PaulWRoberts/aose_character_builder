from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine.innate import (
    InnateError, innate_abilities, reset_innate, restore_innate, spend_innate,
)
from aose.models import (
    Ability, CharacterSpec, CharClass, ClassEntry, ClassFeature, DailyUses,
)

DATA_DIR = Path(__file__).parent.parent / "data"


def _data():
    data = GameData.load(DATA_DIR)
    data.classes["zinnate"] = CharClass(
        id="zinnate", name="ZInnate", prime_requisites=[Ability.STR], hit_die="1d8",
        weapons_allowed="all", armor_allowed="all", shields_allowed=True,
        progression=data.classes["fighter"].progression,
        features=[
            ClassFeature(id="breath", name="Breath", text="3/day",
                         daily_uses=DailyUses(per_day=3)),
            ClassFeature(id="spores", name="Spores", text="per level",
                         daily_uses=DailyUses(scales_with_level=True),
                         spell_id="magic_user_magic_missile"),
        ],
    )
    return data


def _spec(level=2, used=None):
    return CharacterSpec(
        name="T", abilities={a: 10 for a in Ability}, race_id="human",
        alignment="neutral", classes=[ClassEntry(class_id="zinnate", level=level)],
        innate_uses=used or {},
    )


def test_collects_with_resolved_max():
    abilities = {a.id: a for a in innate_abilities(_spec(level=2), _data())}
    assert abilities["breath"].max_uses == 3
    assert abilities["spores"].max_uses == 2          # scales with level=2
    assert abilities["spores"].spell_id == "magic_user_magic_missile"
    assert abilities["breath"].remaining == 3


def test_spend_and_remaining():
    data = _data()
    spec = spend_innate(_spec(level=2), "breath", data)
    assert spec.innate_uses["breath"] == 1
    ab = {a.id: a for a in innate_abilities(spec, data)}["breath"]
    assert ab.used == 1 and ab.remaining == 2


def test_spend_beyond_max_raises():
    data = _data()
    spec = _spec(level=2, used={"breath": 3})
    with pytest.raises(InnateError):
        spend_innate(spec, "breath", data)


def test_restore_and_reset():
    spec = _spec(level=2, used={"breath": 2, "spores": 1})
    spec = restore_innate(spec, "breath")
    assert spec.innate_uses["breath"] == 1
    spec = reset_innate(spec)
    assert spec.innate_uses == {}


def test_spend_unknown_ability_raises():
    with pytest.raises(InnateError):
        spend_innate(_spec(), "nope", _data())
