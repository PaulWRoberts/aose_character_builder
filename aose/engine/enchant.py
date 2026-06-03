"""Enchantment engine — the cycle-free core for magic-item composition.

Imports only models, the data loader, and dice (like ``magic.py``).  The
derivation modules import *from here*, never the other way round.

A magic weapon/armour is composed at runtime from a base catalog item + a
reusable ``Enchantment``.  ``resolve_weapon`` / ``resolve_armor`` return a
synthetic ``Weapon`` / ``Armor``; nothing composed is persisted.
"""
from __future__ import annotations

import random
import uuid

from aose.data.loader import GameData
from aose.engine.dice import roll
from aose.models import (
    Armor,
    Enchantment,
    EnchantedInstance,
    Weapon,
)


class UnknownEnchantment(ValueError):
    pass


class IncompatibleBase(ValueError):
    pass


class NoCharges(ValueError):
    pass


_WILDCARDS = {"any_weapon", "any_armour", "any_shield"}


def _is_weapon(base) -> bool:
    return isinstance(base, Weapon)


def _is_armour(base) -> bool:
    return isinstance(base, Armor) and not base.is_shield


def _is_shield(base) -> bool:
    return isinstance(base, Armor) and base.is_shield


def matches(base, token: str) -> bool:
    """A base item matches ``token`` if it is the kind wildcard for the base's
    nature, equals the base id, or appears in ``base.groups``."""
    if token == "any_weapon":
        return _is_weapon(base)
    if token == "any_armour":
        return _is_armour(base)
    if token == "any_shield":
        return _is_shield(base)
    if token == base.id:
        return True
    return token in getattr(base, "groups", [])


def _nature_matches_kind(base, kind: str) -> bool:
    return (
        (kind == "weapon" and _is_weapon(base))
        or (kind == "armor" and _is_armour(base))
        or (kind == "shield" and _is_shield(base))
    )


def is_compatible(base, ench: Enchantment) -> bool:
    """A base is compatible when its nature matches the enchantment kind, it
    matches at least one ``include`` token, and no ``exclude`` token (exclude
    wins)."""
    if not _nature_matches_kind(base, ench.kind):
        return False
    if any(matches(base, t) for t in ench.applies_to.exclude):
        return False
    return any(matches(base, t) for t in ench.applies_to.include)


def compatible_bases(ench: Enchantment, data: GameData) -> list:
    """Every catalog base item compatible with ``ench``, sorted by name."""
    out = [item for item in data.items.values()
           if isinstance(item, (Weapon, Armor)) and is_compatible(item, ench)]
    out.sort(key=lambda i: i.name)
    return out
