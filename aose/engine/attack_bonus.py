from aose.data.loader import GameData
from aose.models import CharacterSpec

from .saves import _level_data


def thac0(spec: CharacterSpec, data: GameData) -> int:
    best = 20
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        ld = _level_data(cls, entry.level)
        if ld.thac0 < best:
            best = ld.thac0
    return best


def attack_bonus(spec: CharacterSpec, data: GameData) -> int:
    return 19 - thac0(spec, data)
