from pydantic import BaseModel, ConfigDict, Field


class LanguageData(BaseModel):
    """Campaign language registry.  ``alignment`` maps an alignment id
    (law / neutral / chaos) to its tongue's display name; ``additional`` is the
    selectable list of extra languages an intelligent character may learn.

    Defaults are empty so the loader stays usable with minimal test data dirs.
    """
    model_config = ConfigDict(extra="forbid")

    alignment: dict[str, str] = Field(default_factory=dict)
    additional: list[str] = Field(default_factory=list)
