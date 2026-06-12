from __future__ import annotations

import re

_UID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def normalise_email(email: str) -> str:
    """Lowercase + strip (no plus/dot trickery — friends scale)."""
    return email.strip().lower()


def safe_uid(uid: str) -> str:
    """Return ``uid`` if it is a path-safe token, else raise ``ValueError``."""
    if not _UID_RE.match(uid or ""):
        raise ValueError(f"unsafe uid: {uid!r}")
    return uid
