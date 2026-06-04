from pydantic import BaseModel, ConfigDict


class GemStack(BaseModel):
    """A stack of identical gems the character owns.  Gems with the same
    (value, label) combine into one stack; counts are adjusted manually.
    ``value`` is gp per gem — one of the table increments or a custom amount.
    Weighs 1 cn per gem; never stored in ``inventory``."""
    model_config = ConfigDict(extra="forbid")

    instance_id: str          # uuid4 hex
    value: int                # gp per gem; > 0
    count: int = 1            # number of identical gems in this stack
    label: str = ""           # optional free-text name


class JewelleryPiece(BaseModel):
    """A single piece of jewellery.  ``value`` is the full (un-halved) gp worth;
    ``damaged`` halves the effective value at display/sell time (reversible
    toggle).  Weighs 10 cn per piece; never stored in ``inventory``."""
    model_config = ConfigDict(extra="forbid")

    instance_id: str          # uuid4 hex
    value: int                # full gp value; > 0
    damaged: bool = False
    label: str = ""           # optional free-text name
