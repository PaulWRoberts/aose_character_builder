import random

import pytest

from aose.engine import valuables as v
from aose.models import GemStack


def test_add_gem_creates_stack():
    gems = v.add_gem([], 100, count=2, label="ruby")
    assert len(gems) == 1
    assert gems[0].value == 100
    assert gems[0].count == 2
    assert gems[0].label == "ruby"
    assert len(gems[0].instance_id) == 32  # uuid4 hex


def test_add_gem_stacks_on_value_and_label():
    gems = v.add_gem([], 100, count=1, label="ruby")
    gems = v.add_gem(gems, 100, count=3, label="ruby")
    assert len(gems) == 1
    assert gems[0].count == 4


def test_add_gem_does_not_stack_when_label_differs():
    gems = v.add_gem([], 100, label="ruby")
    gems = v.add_gem(gems, 100, label="emerald")
    assert len(gems) == 2


def test_add_gem_accepts_custom_value():
    gems = v.add_gem([], 250)
    assert gems[0].value == 250


def test_add_gem_rejects_nonpositive_value_or_count():
    with pytest.raises(v.ValuableError):
        v.add_gem([], 0)
    with pytest.raises(v.ValuableError):
        v.add_gem([], 100, count=0)


def test_adjust_gem_count_clamps_and_removes_at_zero():
    gems = v.add_gem([], 50, count=2)
    iid = gems[0].instance_id
    gems2 = v.adjust_gem_count(gems, iid, +3)
    assert gems2[0].count == 5
    gems3 = v.adjust_gem_count(gems, iid, -5)
    assert gems3 == []


def test_remove_gem_drops_whole_stack():
    gems = v.add_gem([], 50, count=9)
    iid = gems[0].instance_id
    assert v.remove_gem(gems, iid) == []


def test_remove_gem_unknown_id_raises():
    with pytest.raises(v.ValuableError):
        v.remove_gem([], "nope")


def test_sell_gem_decrements_and_adds_value():
    gems = v.add_gem([], 100, count=3)
    iid = gems[0].instance_id
    gems2, gold = v.sell_gem(gems, 5, iid)
    assert gold == 105
    assert gems2[0].count == 2


def test_sell_gem_empties_row_when_last():
    gems = v.add_gem([], 100, count=1)
    iid = gems[0].instance_id
    gems2, gold = v.sell_gem(gems, 0, iid)
    assert gems2 == []
    assert gold == 100


def test_sell_gem_all_sells_whole_stack():
    gems = v.add_gem([], 100, count=4)
    iid = gems[0].instance_id
    gems2, gold = v.sell_gem_all(gems, 10, iid)
    assert gems2 == []
    assert gold == 410


def test_gem_stack_value():
    assert v.gem_stack_value(GemStack(instance_id="x", value=100, count=3)) == 300


def test_roll_jewellery_value_range():
    rng = random.Random(1)
    for _ in range(50):
        val = v.roll_jewellery_value(rng)
        assert 300 <= val <= 1800
        assert val % 100 == 0


def test_add_jewellery_appends_piece():
    jw = v.add_jewellery([], 700, damaged=False, label="necklace")
    assert len(jw) == 1
    assert jw[0].value == 700
    assert jw[0].damaged is False
    assert jw[0].label == "necklace"
    assert len(jw[0].instance_id) == 32


def test_add_jewellery_rejects_nonpositive_value():
    with pytest.raises(v.ValuableError):
        v.add_jewellery([], 0)


def test_set_jewellery_damaged_toggles():
    jw = v.add_jewellery([], 700)
    iid = jw[0].instance_id
    jw = v.set_jewellery_damaged(jw, iid, True)
    assert jw[0].damaged is True
    jw = v.set_jewellery_damaged(jw, iid, False)
    assert jw[0].damaged is False


def test_jewellery_value_halves_when_damaged_with_floor():
    from aose.models import JewelleryPiece
    assert v.jewellery_value(JewelleryPiece(instance_id="x", value=700)) == 700
    assert v.jewellery_value(
        JewelleryPiece(instance_id="x", value=125, damaged=True)) == 62


def test_remove_jewellery_drops_piece():
    jw = v.add_jewellery([], 700)
    iid = jw[0].instance_id
    assert v.remove_jewellery(jw, iid) == []


def test_remove_jewellery_unknown_id_raises():
    with pytest.raises(v.ValuableError):
        v.remove_jewellery([], "nope")


def test_sell_jewellery_adds_effective_value():
    jw = v.add_jewellery([], 700)
    iid = jw[0].instance_id
    jw2, gold = v.sell_jewellery(jw, 5, iid)
    assert jw2 == []
    assert gold == 705


def test_sell_jewellery_damaged_adds_halved_value():
    jw = v.add_jewellery([], 700, damaged=True)
    iid = jw[0].instance_id
    jw2, gold = v.sell_jewellery(jw, 0, iid)
    assert gold == 350


def test_total_value_mixes_gems_and_jewellery():
    from aose.models import CharacterSpec
    spec = CharacterSpec(
        name="T",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[{"class_id": "fighter", "level": 1, "hp_rolls": [8]}],
        alignment="neutral",
    )
    spec.gems = v.add_gem([], 100, count=3)            # 300
    spec.jewellery = v.add_jewellery([], 700)          # 700
    spec.jewellery = v.add_jewellery(spec.jewellery, 200, damaged=True)  # 100
    assert v.total_value(spec) == 1100


def test_valuables_weight_gems_one_each_jewellery_ten_each():
    from aose.engine.valuables import valuables_weight_cn
    from aose.models import CharacterSpec, GemStack, JewelleryPiece
    spec = CharacterSpec(
        name="T",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[{"class_id": "fighter", "level": 1, "hp_rolls": [8]}],
        alignment="neutral",
        gems=[GemStack(instance_id="g1", value=100, count=3)],
        jewellery=[
            JewelleryPiece(instance_id="j1", value=800),
            JewelleryPiece(instance_id="j2", value=400, damaged=True),
        ],
    )
    # 3 gems * 1 + 2 pieces * 10 = 23 (damaged does not change weight)
    assert valuables_weight_cn(spec) == 23
