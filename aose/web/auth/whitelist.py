from __future__ import annotations

from pathlib import Path

from aose.web.auth.identity import normalise_email


class Whitelist:
    """Invite list read fresh from a flat file (one email per line).

    Blank lines and ``#`` comments are ignored.  Read per-call so editing the
    file takes effect without a restart.  Missing file admits nobody.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def _entries(self) -> set[str]:
        if not self._path.exists():
            return set()
        out: set[str] = set()
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            out.add(normalise_email(line))
        return out

    def allows(self, email: str) -> bool:
        return normalise_email(email) in self._entries()
