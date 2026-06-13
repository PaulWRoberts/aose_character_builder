from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


EncumbranceMode = Literal["none", "basic", "detailed"]

# The content categories a source can offer. Derived from loaded data at
# runtime (see engine/sources.source_content_categories); listed here so the
# model's legacy-coercion validator can expand an old whole-source disable.
CONTENT_CATEGORIES = ("classes", "equipment", "magic_items")

_CLASSIC_SOURCE_ID = "ose_classic_fantasy"  # mirrors engine.sources.CLASSIC_SOURCE_ID


class RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ascending_ac: bool = False
    secondary_skills: bool = False
    weapon_proficiency: bool = False
    multiclassing: bool = False
    reroll_1s_2s_hp_l1: bool = False
    separate_race_class: bool = True
    lift_demihuman_restrictions: bool = False
    variable_weapon_damage: bool = False
    advanced_spell_books: bool = False
    human_racial_abilities: bool = False
    strict_mode: bool = True
    optional_staves: bool = False
    two_weapon_fighting: bool = False
    individual_initiative: bool = False
    combat_talents: bool = False
    cantrips: bool = False
    read_magic_cantrip: bool = False

    encumbrance: EncumbranceMode = "basic"

    # Content the user has switched off, as "{source_id}:{category}" keys. A
    # category is enabled unless its key is listed here. Classic Fantasy
    # categories are never added (its content is locked on).
    disabled_content: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_disabled_sources(cls, data):
        """Fold a legacy whole-source `disabled_sources` value into
        `disabled_content` by expanding each disabled source to all three
        category keys. The validator has no GameData, so it emits all three —
        harmless, since content_enabled is only queried for categories a
        source actually provides."""
        if isinstance(data, dict) and "disabled_sources" in data:
            legacy = data.pop("disabled_sources") or []
            expanded = [
                f"{sid}:{cat}"
                for sid in legacy
                if sid != _CLASSIC_SOURCE_ID
                for cat in CONTENT_CATEGORIES
            ]
            existing = list(data.get("disabled_content") or [])
            data["disabled_content"] = existing + [
                k for k in expanded if k not in existing
            ]
        return data
