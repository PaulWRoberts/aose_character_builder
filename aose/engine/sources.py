"""Source / content-category filter.  Cycle-free: imports only models + the
GameData type.

A character's :class:`RuleSet` may disable individual content categories
(``classes`` / ``equipment`` / ``magic_items``) per source; this module decides
whether a given source+category is currently active, and derives which
categories each source actually offers from loaded data.  Classic Fantasy is
the baseline and can never be disabled.
"""
from aose.models import RuleSet, CONTENT_CATEGORIES

CLASSIC_SOURCE_ID = "ose_classic_fantasy"


def content_enabled(source_id: str, category: str, ruleset: RuleSet) -> bool:
    """Whether ``category`` content from ``source_id`` is available."""
    if source_id == CLASSIC_SOURCE_ID:
        return True
    return f"{source_id}:{category}" not in ruleset.disabled_content


def source_content_categories(data) -> dict[str, list[str]]:
    """Map each source id to the ordered content categories it provides,
    derived from loaded ``GameData`` (no per-item tagging needed).

    - ``classes``     — the source has any class or race (spell lists ride along)
    - ``equipment``   — the source has any non-magic item
    - ``magic_items`` — the source has any magic item or enchantment
    """
    cats: dict[str, set[str]] = {}

    def add(source_id: str, category: str) -> None:
        cats.setdefault(source_id, set()).add(category)

    for cls in data.classes.values():
        add(cls.source, "classes")
    for race in data.races.values():
        add(race.source, "classes")
    for item in data.items.values():
        is_magic = getattr(item, "item_type", None) == "magic" or getattr(
            item, "magic", False
        )
        add(item.source, "magic_items" if is_magic else "equipment")
    for ench in data.enchantments.values():
        add(ench.source, "magic_items")

    order = {c: n for n, c in enumerate(CONTENT_CATEGORIES)}
    return {sid: sorted(s, key=lambda c: order[c]) for sid, s in cats.items()}
