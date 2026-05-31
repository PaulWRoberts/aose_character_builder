from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .ability import Ability


class RaceFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    text: str
    mechanical: dict[str, Any] | None = None


class Race(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    ability_requirements: dict[Ability, int] = Field(default_factory=dict)
    ability_maxima: dict[Ability, int] = Field(default_factory=dict)
    ability_minima: dict[Ability, int] = Field(default_factory=dict)
    infravision: int = 0
    base_movement: int = 120
    languages: list[str] = Field(default_factory=list)
    # Empty allowed_classes means "any class allowed" (the Human case).
    # Listed entries restrict to only those classes.
    allowed_classes: list[str] = Field(default_factory=list)
    # Per-class level caps. Missing entry = no cap.
    class_level_caps: dict[str, int] = Field(default_factory=dict)
    features: list[RaceFeature] = Field(default_factory=list)
