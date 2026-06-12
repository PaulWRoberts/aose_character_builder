"""Environment loader for auth config (GCIP web SDK + emulator detection)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AuthConfig:
    """Immutable Firebase/GCIP auth configuration loaded from environment variables."""

    session_secret: str
    whitelist_path: Path
    users_root: Path
    firebase_project_id: str
    firebase_api_key: str
    firebase_auth_domain: str
    use_emulator: bool
    emulator_host: str
    cookie_secure: bool

    @staticmethod
    def from_env(project_root: Path) -> "AuthConfig | None":
        """Return a config when ``AOSE_AUTH`` is truthy, else ``None`` (auth off).

        Args:
            project_root: Root directory for relative paths (whitelist_path, users_root).

        Returns:
            AuthConfig if AOSE_AUTH is "1", "true", or "yes"; None otherwise.
        """
        if os.environ.get("AOSE_AUTH", "").lower() not in ("1", "true", "yes"):
            return None
        session_secret = os.environ.get("AOSE_SESSION_SECRET", "")
        if not session_secret:
            raise ValueError(
                "AOSE_SESSION_SECRET must be set when AOSE_AUTH is enabled. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        emulator_host = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "")
        return AuthConfig(
            session_secret=session_secret,
            whitelist_path=project_root / os.environ.get("AOSE_WHITELIST", "whitelist.txt"),
            users_root=project_root / os.environ.get("AOSE_USERS_DIR", "users"),
            firebase_project_id=os.environ.get("AOSE_FIREBASE_PROJECT_ID", ""),
            firebase_api_key=os.environ.get("AOSE_FIREBASE_API_KEY", ""),
            firebase_auth_domain=os.environ.get("AOSE_FIREBASE_AUTH_DOMAIN", ""),
            use_emulator=bool(emulator_host),
            emulator_host=emulator_host,
            cookie_secure=os.environ.get("AOSE_COOKIE_INSECURE", "").lower()
            not in ("1", "true", "yes"),
        )
