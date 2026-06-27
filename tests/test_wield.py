"""Pure wield-capacity helpers."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine.equip import (
    hand_cost, off_hand_eligible, resolve_slot, validate_wield, WieldError,
)
from aose.models.character import CharacterSpec, ClassEntry, ItemInstance

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


def W(data, wid):
    return data.items[wid]


def _spec(slots):
    """A CharacterSpec whose items carry the given equip slots
    (e.g. {"main_hand": "sword", "off_hand": "shield"})."""
    items = [
        ItemInstance(instance_id=f"t_{slot}", catalog_id=cid, equip=slot)
        for slot, cid in slots.items()
    ]
    return CharacterSpec(
        name="T", abilities={}, race_id="human",
        classes=[ClassEntry(class_id="fighter")], alignment="neutral",
        items=items,
    )


def test_hand_cost_basic(data):
    assert hand_cost(W(data, "sword"), gargantua_1h_2h=False) == 1          # 1H melee
    assert hand_cost(W(data, "two_handed_sword"), gargantua_1h_2h=False) == 2
    assert hand_cost(W(data, "shield"), gargantua_1h_2h=False) == 1
    assert hand_cost(W(data, "long_bow"), gargantua_1h_2h=False) == 2       # 2H ranged


def test_hand_cost_gargantua_reduces_two_handed_melee_only(data):
    # Battle axe is two_handed + melee -> 1 hand for a gargantua.
    assert hand_cost(W(data, "battle_axe"), gargantua_1h_2h=True) == 1
    # Long bow is two_handed but ranged -> stays 2 even for a gargantua.
    assert hand_cost(W(data, "long_bow"), gargantua_1h_2h=True) == 2


def test_off_hand_eligible(data):
    assert off_hand_eligible(W(data, "dagger")) is True
    assert off_hand_eligible(W(data, "hand_axe")) is True       # thrown melee, 30cn
    assert off_hand_eligible(W(data, "short_sword")) is True
    assert off_hand_eligible(W(data, "club")) is False          # 50cn, too heavy
    assert off_hand_eligible(W(data, "two_handed_sword")) is False  # two_handed
    assert off_hand_eligible(W(data, "spear")) is False         # brace
    assert off_hand_eligible(W(data, "bastard_sword")) is False  # versatile
    assert off_hand_eligible(W(data, "long_bow")) is False      # no melee quality


def test_resolve_slot_catalog_and_missing(data):
    assert resolve_slot("sword", data, []) is W(data, "sword")
    assert resolve_slot(None, data, []) is None
    assert resolve_slot("nonsense", data, []) is None


def test_validate_wield_baseline_legal(data):
    # 1H weapon + shield, rule off.
    validate_wield(_spec({"main_hand": "sword", "off_hand": "shield"}), data,
                   two_weapon=False, eligible=False, gargantua_1h_2h=False)


def test_validate_wield_two_handed_blocks_shield(data):
    with pytest.raises(WieldError):
        validate_wield(_spec({"main_hand": "two_handed_sword", "off_hand": "shield"}),
                       data, two_weapon=False, eligible=False,
                       gargantua_1h_2h=False)


def test_validate_wield_gargantua_two_handed_plus_shield(data):
    validate_wield(_spec({"main_hand": "battle_axe", "off_hand": "shield"}), data,
                   two_weapon=False, eligible=False, gargantua_1h_2h=True)


def test_validate_wield_two_weapons_requires_rule_and_eligibility(data):
    slots = {"main_hand": "sword", "off_hand": "dagger"}
    with pytest.raises(WieldError):  # rule off
        validate_wield(_spec(slots), data, two_weapon=False, eligible=True,
                       gargantua_1h_2h=False)
    with pytest.raises(WieldError):  # ineligible
        validate_wield(_spec(slots), data, two_weapon=True, eligible=False,
                       gargantua_1h_2h=False)
    # rule on + eligible + eligible off-hand -> OK
    validate_wield(_spec(slots), data, two_weapon=True, eligible=True,
                   gargantua_1h_2h=False)


def test_validate_wield_off_hand_must_be_eligible_weapon(data):
    with pytest.raises(WieldError):
        validate_wield(_spec({"main_hand": "sword", "off_hand": "club"}), data,
                       two_weapon=True, eligible=True, gargantua_1h_2h=False)


def test_validate_wield_off_hand_weapon_needs_main(data):
    with pytest.raises(WieldError):
        validate_wield(_spec({"off_hand": "dagger"}), data,
                       two_weapon=True, eligible=True, gargantua_1h_2h=False)
