"""Pure alignment derivation (cycle-free; imports models only).

A class with an empty ``allowed_alignments`` list is unrestricted (any of the
three). The legal alignment set for a character is the intersection across all
their classes — which may be empty for an incompatible combination.
"""
from aose.models import CharClass

ALL: set[str] = {"law", "neutral", "chaos"}


def allowed_alignments(classes: list[CharClass]) -> set[str]:
    """Intersection of each class's allowed alignments; an empty
    ``allowed_alignments`` on a class means 'all three'. Result may be empty
    (an alignment-incompatible class combination)."""
    result = set(ALL)
    for cls in classes:
        result &= set(cls.allowed_alignments) if cls.allowed_alignments else set(ALL)
    return result
