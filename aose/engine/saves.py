from aose.data.loader import GameData
from aose.models import CharacterSpec


def _level_data(cls, level: int):
    if level in cls.progression:
        return cls.progression[level]
    available = [lv for lv in cls.progression.keys() if lv <= level]
    if not available:
        raise ValueError(f"No progression data for class {cls.id} at level {level}")
    return cls.progression[max(available)]


def saving_throws(spec: CharacterSpec, data: GameData) -> dict[str, int]:
    """Best (lowest) save in each category across all of the character's classes."""
    best: dict[str, int] = {}
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        ld = _level_data(cls, entry.level)
        for name, value in ld.saves.items():
            if name not in best or value < best[name]:
                best[name] = value
    return best
