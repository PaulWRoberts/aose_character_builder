from pydantic import BaseModel, ConfigDict


class Source(BaseModel):
    """A published content source (rulebook).  Content models reference a
    source by id via their ``source`` field; the active ``RuleSet`` may disable
    non-core sources to hide their content."""
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    publisher: str
    core: bool = False
