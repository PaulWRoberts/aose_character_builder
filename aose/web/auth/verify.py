from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class VerifiedUser:
    uid: str
    email: str
    email_verified: bool


class TokenError(Exception):
    """Raised when an ID token cannot be verified."""


class Verifier(ABC):
    @abstractmethod
    def verify(self, id_token: str) -> VerifiedUser: ...


class FirebaseVerifier(Verifier):
    """Production verifier — wraps firebase-admin (imported lazily).

    Honours ``FIREBASE_AUTH_EMULATOR_HOST`` automatically (set by the local
    Firebase emulator), so the same code path works offline in dev.
    """

    def __init__(self, project_id: str) -> None:
        import firebase_admin
        from firebase_admin import credentials

        self._project_id = project_id
        if not firebase_admin._apps:
            try:
                firebase_admin.initialize_app(
                    credentials.ApplicationDefault(), {"projectId": project_id}
                )
            except Exception:
                # Emulator / verify-only: no service-account creds available.
                firebase_admin.initialize_app(options={"projectId": project_id})

    def verify(self, id_token: str) -> VerifiedUser:
        from firebase_admin import auth

        try:
            decoded = auth.verify_id_token(id_token)
        except Exception as exc:  # firebase-admin raises several subclasses
            raise TokenError(str(exc)) from exc
        return VerifiedUser(
            uid=decoded["uid"],
            email=decoded.get("email", ""),
            email_verified=bool(decoded.get("email_verified", False)),
        )


class FakeVerifier(Verifier):
    """Test verifier — maps known token strings to users, no network."""

    def __init__(self, tokens: dict[str, VerifiedUser]) -> None:
        self._tokens = tokens

    def verify(self, id_token: str) -> VerifiedUser:
        try:
            return self._tokens[id_token]
        except KeyError as exc:
            raise TokenError("unknown token") from exc


def build_verifier(config) -> Verifier:
    """Build the production verifier from an :class:`AuthConfig`."""
    return FirebaseVerifier(config.firebase_project_id)
