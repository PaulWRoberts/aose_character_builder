"""Source-filter helper.  Cycle-free: imports only models.

A character's :class:`RuleSet` may disable content sources; this module decides
whether a given source id is currently active.  Classic Fantasy is the baseline
and can never be disabled.
"""
from aose.models import RuleSet

CLASSIC_SOURCE_ID = "ose_classic_fantasy"


def source_enabled(source_id: str, ruleset: RuleSet) -> bool:
    """Whether content from ``source_id`` is available under ``ruleset``."""
    if source_id == CLASSIC_SOURCE_ID:
        return True
    return source_id not in ruleset.disabled_sources
