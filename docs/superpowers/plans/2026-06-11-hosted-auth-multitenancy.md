# Hosted Auth & Multi-Tenancy (GCIP / Google Sign-In) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in, invite-only authentication via **GCP Identity Platform with Google sign-in only**, namespacing each user's characters/drafts/settings into their own workspace — so the app can be hosted for friends without users stomping each other's data, while leaving the local single-user workflow and every existing test untouched when auth is off.

**Architecture:** Auth is a feature flag (`auth_enabled`, default `False`). A single HTTP middleware resolves a per-request *workspace* (the three storage paths) onto `request.state`: auth off → mirrors the existing global dirs (zero behaviour change); auth on → derives `users/<uid>/` from the session and gates unauthenticated requests to a login page. Login is a small client-side flow: the Firebase JS SDK runs Google sign-in, hands the backend a GCIP **ID token**, the backend verifies it (firebase-admin), checks the email against a hand-maintained **whitelist** (the sole invite gate), then mints its *own* signed session cookie. GCIP issues identity only; the per-user data isolation is ours. No email is ever sent; no SMTP/DNS. Export/import gives every character a self-serve backup.

**Tech Stack:** Python 3.11+, FastAPI/Starlette (`SessionMiddleware` + `itsdangerous`), `firebase-admin` (ID-token verification, lazily imported), Pydantic v2, Firebase JS SDK (login page only), pytest + `TestClient` with an injected fake verifier (fully offline).

---

## Phase 0 — GCP / GCIP prerequisites (no code)

Done **once, by hand** (operator: you). Nothing in Phases A–D requires these to be true — the code defaults to auth-off and the test suite uses an injected fake verifier — but the production login (`AOSE_AUTH=1`) needs them. **No email, no SPF/DKIM/DMARC** with Google-only sign-in.

- [ ] **Create / pick a GCP project** and enable **Identity Platform** (Console → Identity Platform → Enable). (Firebase Authentication on the same project works too; GCIP is the GCP-branded surface.)
- [ ] **Enable the Google sign-in provider** (Identity Platform → Providers → Add → Google).
- [ ] **Configure the OAuth consent screen** (APIs & Services → OAuth consent screen): User type *External*; add your friends' Google emails as *Test users* (or publish the app). This is what lets their Google accounts complete the popup.
- [ ] **Add authorized domains** (Identity Platform → Settings → Authorized domains): add `dungeoncrawl.quest` (and `localhost` is allowed by default for dev).
- [ ] **Grab the Firebase Web config** (Project settings → "Your apps" → Web app → SDK config): you need `apiKey`, `authDomain`, `projectId`. These are **public** (they go in the login page) — they identify, they don't authorize.
- [ ] **Create a service account for backend token verification** (IAM → Service Accounts → Create; no special roles needed for `verify_id_token`), download its JSON key, and place it on the EC2 box. Its path becomes `GOOGLE_APPLICATION_CREDENTIALS`. (Token verification needs only public certs + the project id, but firebase-admin initializes cleanly with Application Default Credentials.)
- [ ] **Confirm the app is served over HTTPS** (reverse proxy / cert on the EC2 box, same as Foundry). The session cookie is `Secure` in production, and Google sign-in popups require a secure origin.

Invite-only note: you do **not** need to block sign-up at GCIP. Anyone with a Google account can authenticate *at GCIP*, but the backend refuses to set a session or provision a workspace unless the verified email is on your whitelist — so non-invitees get "not invited" and zero access/data. (A GCIP "blocking function" could reject earlier, but it pulls in Cloud Functions and isn't needed.)

No commit for this phase.

---

## File Structure

New files:

- `aose/web/auth/__init__.py` — package docstring.
- `aose/web/auth/config.py` — `AuthConfig` dataclass + `AuthConfig.from_env()`.
- `aose/web/auth/identity.py` — `normalise_email`, `safe_uid`.
- `aose/web/auth/whitelist.py` — `Whitelist` (load + membership test).
- `aose/web/auth/verify.py` — `VerifiedUser`, `TokenError`, `Verifier` ABC, `FirebaseVerifier`, `FakeVerifier`, `build_verifier`.
- `aose/web/auth/workspace.py` — `Workspace`, `resolve_workspace(request)`.
- `aose/web/auth/middleware.py` — `WorkspaceAuthMiddleware`.
- `aose/web/auth/routes.py` — `/login`, `/login/session`, `/logout`.
- `aose/web/templates/auth/login.html` — Google sign-in page (Firebase JS).
- `tests/test_auth_identity.py`, `tests/test_auth_whitelist.py`, `tests/test_auth_verify.py`, `tests/test_auth_config.py`, `tests/test_auth_flow.py`, `tests/test_auth_disabled.py`, `tests/test_export_import.py`.

Modified files:

- `aose/web/app.py` — `create_app(..., auth_config=None, auth_verifier=None)`, register middleware + session + auth router, auth-aware seeding.
- `aose/web/routes.py`, `aose/web/wizard.py`, `aose/web/settings_routes.py` — mechanical `request.app.state.{characters_dir,drafts_dir,settings_path}` → `request.state.{…}`.
- `aose/web/routes.py` — export/import routes (Phase F).
- `pyproject.toml` — add `itsdangerous` and `firebase-admin` to the `web` extra.
- `.gitignore` — ignore `whitelist.txt`, `users/`, service-account JSON.
- Docs (Phase G).

---

## Phase A — Per-request workspace + auth-off passthrough

Introduces the indirection with **auth disabled**, so behaviour and all existing tests are unchanged. Safe to land on its own.

### Task A1: Workspace dataclass + resolver (auth-off path only)

**Files:**
- Create: `aose/web/auth/__init__.py`, `aose/web/auth/workspace.py`
- Test: `tests/test_auth_disabled.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_auth_disabled.py
from starlette.requests import Request

from aose.web.auth.workspace import Workspace, resolve_workspace


def _fake_request(app_state: dict, session: dict | None = None) -> Request:
    scope = {"type": "http", "headers": [], "method": "GET", "path": "/"}
    req = Request(scope)
    class _App:
        state = type("S", (), app_state)()
    req.scope["app"] = _App()
    if session is not None:
        req.scope["session"] = session
    return req


def test_resolve_workspace_auth_off_mirrors_global_dirs(tmp_path):
    state = {
        "auth_config": None,
        "characters_dir": tmp_path / "characters",
        "drafts_dir": tmp_path / "drafts",
        "settings_path": tmp_path / "settings.json",
    }
    ws = resolve_workspace(_fake_request(state))
    assert isinstance(ws, Workspace)
    assert ws.characters_dir == tmp_path / "characters"
    assert ws.drafts_dir == tmp_path / "drafts"
    assert ws.settings_path == tmp_path / "settings.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth_disabled.py -q`
Expected: FAIL — `ModuleNotFoundError: aose.web.auth.workspace`.

- [ ] **Step 3: Write minimal implementation**

```python
# aose/web/auth/__init__.py
"""Opt-in, invite-only Google (GCIP) auth + per-user workspace resolution.

Auth is off by default; when off the app behaves exactly as the original
local single-user tool.  See docs/ARCHITECTURE.md → "Hosting & auth".
"""
```

```python
# aose/web/auth/workspace.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from starlette.requests import Request


@dataclass(frozen=True)
class Workspace:
    """The three storage paths a request reads/writes through."""

    characters_dir: Path
    drafts_dir: Path
    settings_path: Path


def resolve_workspace(request: Request) -> Workspace:
    """Resolve the per-request workspace.

    Auth off (``app.state.auth_config is None``): mirror the global dirs.
    Auth on: derive ``users/<uid>/`` from the session (wired in Task D2).
    """
    state = request.app.state
    config = getattr(state, "auth_config", None)
    if config is None:
        return Workspace(
            characters_dir=state.characters_dir,
            drafts_dir=state.drafts_dir,
            settings_path=state.settings_path,
        )
    raise NotImplementedError("auth-on workspace resolution added in Task D2")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth_disabled.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/auth/__init__.py aose/web/auth/workspace.py tests/test_auth_disabled.py
git commit -m "feat(auth): Workspace + auth-off resolver"
```

### Task A2: Middleware that sets `request.state` dirs (auth-off no-op gate)

**Files:**
- Create: `aose/web/auth/middleware.py`
- Test: `tests/test_auth_disabled.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_auth_disabled.py  (append)
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from aose.web.auth.middleware import WorkspaceAuthMiddleware


def test_middleware_sets_request_state_when_auth_off(tmp_path):
    app = FastAPI()
    app.state.auth_config = None
    app.state.characters_dir = tmp_path / "characters"
    app.state.drafts_dir = tmp_path / "drafts"
    app.state.settings_path = tmp_path / "settings.json"
    app.add_middleware(WorkspaceAuthMiddleware)

    @app.get("/probe")
    def probe(request):  # type: ignore[no-untyped-def]
        return PlainTextResponse(str(request.state.characters_dir))

    client = TestClient(app)
    resp = client.get("/probe")
    assert resp.status_code == 200
    assert resp.text.endswith("characters")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth_disabled.py -q`
Expected: FAIL — `ModuleNotFoundError: aose.web.auth.middleware`.

- [ ] **Step 3: Write minimal implementation**

```python
# aose/web/auth/middleware.py
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from aose.web.auth.workspace import resolve_workspace

_PUBLIC_PREFIXES = ("/login", "/logout", "/static")


def _is_public(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") or path.startswith(p)
               for p in _PUBLIC_PREFIXES)


class WorkspaceAuthMiddleware(BaseHTTPMiddleware):
    """Resolve the per-request workspace and gate unauthenticated requests.

    Auth off: set ``request.state`` dirs from globals and pass through.
    Auth on: require a session ``uid`` for non-public paths (else redirect to
    ``/login``), then resolve the per-user workspace.
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        config = getattr(request.app.state, "auth_config", None)

        if config is not None and not _is_public(request.url.path):
            uid = request.session.get("uid") if "session" in request.scope else None
            if not uid:
                return RedirectResponse(url="/login", status_code=303)

        try:
            ws = resolve_workspace(request)
        except NotImplementedError:
            return RedirectResponse(url="/login", status_code=303)

        request.state.characters_dir = ws.characters_dir
        request.state.drafts_dir = ws.drafts_dir
        request.state.settings_path = ws.settings_path
        response: Response = await call_next(request)
        return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth_disabled.py -q`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add aose/web/auth/middleware.py tests/test_auth_disabled.py
git commit -m "feat(auth): workspace+gate middleware (auth-off no-op)"
```

### Task A3: Wire middleware into `create_app`; mechanical `request.state` rename

**Files:**
- Modify: `aose/web/app.py`, `aose/web/routes.py` (82 refs), `aose/web/wizard.py` (3), `aose/web/settings_routes.py` (1)
- Test: existing `tests/` suite is the regression guard.

- [ ] **Step 1: Add the middleware to `create_app`**

In `aose/web/app.py`, add the import:

```python
from aose.web.auth.middleware import WorkspaceAuthMiddleware
```

Inside `create_app`, after the existing `app.state.*` assignments, add:

```python
    app.state.auth_config = None  # auth disabled by default (Phase D wires it on)
```

And after `app.mount(...)`, before `app.include_router(router)`:

```python
    app.add_middleware(WorkspaceAuthMiddleware)
```

- [ ] **Step 2: Mechanically retarget the three storage attrs to `request.state`**

In **each** of `aose/web/routes.py`, `aose/web/wizard.py`, `aose/web/settings_routes.py`, replace every occurrence (leave `request.app.state.game_data` and `request.app.state.examples_dir` untouched):

- `request.app.state.characters_dir` → `request.state.characters_dir`
- `request.app.state.drafts_dir` → `request.state.drafts_dir`
- `request.app.state.settings_path` → `request.state.settings_path`

This includes `_character_summaries(request.app.state.characters_dir)` at `routes.py:143`.

- [ ] **Step 3: Verify no stragglers remain**

Run: `.venv\Scripts\python.exe -c "import pathlib,re; bad=[(f,i+1) for f in ['aose/web/routes.py','aose/web/wizard.py','aose/web/settings_routes.py'] for i,l in enumerate(pathlib.Path(f).read_text(encoding='utf-8').splitlines()) if re.search(r'app\.state\.(characters_dir|drafts_dir|settings_path)', l)]; print(bad)"`
Expected: `[]`

- [ ] **Step 4: Run the full suite (zero behaviour change)**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS as before (ignore the known trailing `pytest-current` PermissionError).

- [ ] **Step 5: Commit**

```bash
git add aose/web/app.py aose/web/routes.py aose/web/wizard.py aose/web/settings_routes.py
git commit -m "refactor(web): resolve storage dirs via request.state + middleware"
```

---

## Phase B — Identity helpers & whitelist

### Task B1: Email normalisation + safe-uid guard

**Files:**
- Create: `aose/web/auth/identity.py`
- Test: `tests/test_auth_identity.py`

`safe_uid` defends the filesystem: the workspace dir is named after the GCIP uid, so we reject anything that isn't a plain token (no `/`, `..`, etc.) before it touches a path.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_auth_identity.py
import pytest

from aose.web.auth.identity import normalise_email, safe_uid


def test_normalise_lowercases_and_strips():
    assert normalise_email("  Alice@Gmail.COM ") == "alice@gmail.com"


def test_safe_uid_accepts_firebase_style_ids():
    assert safe_uid("abc123XYZ_-") == "abc123XYZ_-"


@pytest.mark.parametrize("bad", ["../escape", "a/b", "", "has space", "."])
def test_safe_uid_rejects_path_unsafe(bad):
    with pytest.raises(ValueError):
        safe_uid(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth_identity.py -q`
Expected: FAIL — `ModuleNotFoundError: aose.web.auth.identity`.

- [ ] **Step 3: Write minimal implementation**

```python
# aose/web/auth/identity.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth_identity.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/auth/identity.py tests/test_auth_identity.py
git commit -m "feat(auth): email normalisation + path-safe uid guard"
```

### Task B2: Whitelist loader

**Files:**
- Create: `aose/web/auth/whitelist.py`
- Test: `tests/test_auth_whitelist.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_auth_whitelist.py
from aose.web.auth.whitelist import Whitelist


def test_membership_is_normalised(tmp_path):
    f = tmp_path / "whitelist.txt"
    f.write_text("Alice@Gmail.com\n# a comment\n\nbob@example.org\n", encoding="utf-8")
    wl = Whitelist(f)
    assert wl.allows("alice@gmail.com")
    assert wl.allows("  BOB@EXAMPLE.ORG ")
    assert not wl.allows("mallory@evil.test")


def test_missing_file_allows_nobody(tmp_path):
    wl = Whitelist(tmp_path / "nope.txt")
    assert not wl.allows("anyone@example.com")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth_whitelist.py -q`
Expected: FAIL — `ModuleNotFoundError: aose.web.auth.whitelist`.

- [ ] **Step 3: Write minimal implementation**

```python
# aose/web/auth/whitelist.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth_whitelist.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/auth/whitelist.py tests/test_auth_whitelist.py
git commit -m "feat(auth): invite whitelist loader"
```

---

## Phase C — GCIP token verification

### Task C1: Verifier (Firebase + fake) + factory

**Files:**
- Create: `aose/web/auth/verify.py`
- Test: `tests/test_auth_verify.py`

`firebase_admin` is imported **lazily inside `FirebaseVerifier`** so the test suite (which injects `FakeVerifier`) never needs the package installed.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_auth_verify.py
import pytest

from aose.web.auth.verify import FakeVerifier, TokenError, VerifiedUser


def test_fake_verifier_returns_mapped_user():
    v = FakeVerifier({"tok-a": VerifiedUser(uid="u-a", email="a@gmail.com", email_verified=True)})
    user = v.verify("tok-a")
    assert user.uid == "u-a" and user.email == "a@gmail.com" and user.email_verified


def test_fake_verifier_unknown_token_raises():
    v = FakeVerifier({})
    with pytest.raises(TokenError):
        v.verify("nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth_verify.py -q`
Expected: FAIL — `ModuleNotFoundError: aose.web.auth.verify`.

- [ ] **Step 3: Write minimal implementation**

```python
# aose/web/auth/verify.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth_verify.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/auth/verify.py tests/test_auth_verify.py
git commit -m "feat(auth): GCIP ID-token verifier (firebase + fake)"
```

---

## Phase D — Login flow, config, and auth-on wiring

### Task D1: AuthConfig (env loader)

**Files:**
- Create: `aose/web/auth/config.py`
- Test: `tests/test_auth_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_auth_config.py
from pathlib import Path

from aose.web.auth.config import AuthConfig


def test_from_env_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AOSE_AUTH", raising=False)
    assert AuthConfig.from_env(project_root=Path(".")) is None


def test_from_env_enabled_builds_config(monkeypatch, tmp_path):
    monkeypatch.setenv("AOSE_AUTH", "1")
    monkeypatch.setenv("AOSE_SESSION_SECRET", "sess")
    monkeypatch.setenv("AOSE_FIREBASE_PROJECT_ID", "demo-proj")
    monkeypatch.setenv("AOSE_FIREBASE_API_KEY", "web-key")
    monkeypatch.setenv("AOSE_FIREBASE_AUTH_DOMAIN", "demo-proj.firebaseapp.com")
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    cfg = AuthConfig.from_env(project_root=tmp_path)
    assert cfg is not None
    assert cfg.session_secret == "sess"
    assert cfg.firebase_project_id == "demo-proj"
    assert cfg.firebase_api_key == "web-key"
    assert cfg.firebase_auth_domain == "demo-proj.firebaseapp.com"
    assert cfg.whitelist_path == tmp_path / "whitelist.txt"
    assert cfg.users_root == tmp_path / "users"
    assert cfg.use_emulator is False


def test_from_env_detects_emulator(monkeypatch, tmp_path):
    monkeypatch.setenv("AOSE_AUTH", "1")
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099")
    cfg = AuthConfig.from_env(project_root=tmp_path)
    assert cfg.use_emulator is True
    assert cfg.emulator_host == "localhost:9099"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth_config.py -q`
Expected: FAIL — `ModuleNotFoundError: aose.web.auth.config`.

- [ ] **Step 3: Write minimal implementation**

```python
# aose/web/auth/config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AuthConfig:
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
        """Return a config when ``AOSE_AUTH`` is truthy, else ``None`` (auth off)."""
        if os.environ.get("AOSE_AUTH", "").lower() not in ("1", "true", "yes"):
            return None
        emulator_host = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "")
        return AuthConfig(
            session_secret=os.environ.get("AOSE_SESSION_SECRET", ""),
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/auth/config.py tests/test_auth_config.py
git commit -m "feat(auth): AuthConfig env loader (GCIP web config + emulator detect)"
```

### Task D2: Auth-on workspace resolution + per-user seeding

**Files:**
- Modify: `aose/web/auth/workspace.py`
- Test: `tests/test_auth_disabled.py` (append; the file covers both modes)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_auth_disabled.py  (append)
from aose.web.auth.config import AuthConfig


def _auth_state(tmp_path):
    cfg = AuthConfig(
        session_secret="s",
        whitelist_path=tmp_path / "whitelist.txt",
        users_root=tmp_path / "users",
        firebase_project_id="demo", firebase_api_key="k",
        firebase_auth_domain="demo.firebaseapp.com",
        use_emulator=True, emulator_host="localhost:9099", cookie_secure=False,
    )
    return {
        "auth_config": cfg,
        "characters_dir": tmp_path / "characters",
        "drafts_dir": tmp_path / "drafts",
        "settings_path": tmp_path / "settings.json",
        "examples_dir": tmp_path / "examples",
    }


def test_resolve_workspace_auth_on_is_per_user(tmp_path):
    state = _auth_state(tmp_path)
    ws_a = resolve_workspace(_fake_request(state, session={"uid": "uid-alice"}))
    ws_b = resolve_workspace(_fake_request(state, session={"uid": "uid-bob"}))
    assert ws_a.characters_dir.is_relative_to(tmp_path / "users")
    assert ws_a.settings_path.name == "settings.json"
    assert ws_a.characters_dir.parent != ws_b.characters_dir.parent


def test_resolve_workspace_rejects_unsafe_uid(tmp_path):
    import pytest
    state = _auth_state(tmp_path)
    with pytest.raises(ValueError):
        resolve_workspace(_fake_request(state, session={"uid": "../escape"}))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth_disabled.py -q`
Expected: FAIL — `NotImplementedError: auth-on workspace resolution added in Task D2`.

- [ ] **Step 3: Replace the `NotImplementedError` branch**

In `aose/web/auth/workspace.py`, add the import at top:

```python
from aose.web.auth.identity import safe_uid
```

Replace the final `raise NotImplementedError(...)` with:

```python
    uid = safe_uid(request.session["uid"])  # gate guarantees presence when auth on
    user_base = config.users_root / uid
    characters_dir = user_base / "characters"
    drafts_dir = user_base / "drafts"
    settings_path = user_base / "settings.json"
    _seed_new_user(user_base, characters_dir, getattr(state, "examples_dir", None))
    return Workspace(
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        settings_path=settings_path,
    )
```

Add this helper at module bottom:

```python
def _seed_new_user(user_base: Path, characters_dir: Path, examples_dir) -> None:
    """First time we see a user, create their dirs and seed example characters."""
    if user_base.exists():
        return
    characters_dir.mkdir(parents=True, exist_ok=True)
    (user_base / "drafts").mkdir(parents=True, exist_ok=True)
    if examples_dir is not None and Path(examples_dir).exists():
        for example in Path(examples_dir).glob("*.json"):
            (characters_dir / example.name).write_bytes(example.read_bytes())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth_disabled.py -q`
Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add aose/web/auth/workspace.py tests/test_auth_disabled.py
git commit -m "feat(auth): per-user workspace resolution + first-login seeding"
```

### Task D3: Login routes + Google sign-in template

**Files:**
- Create: `aose/web/auth/routes.py`, `aose/web/templates/auth/login.html`
- Test: deferred to Task D4 (full flow).

- [ ] **Step 1: Write the login template**

```html
<!-- aose/web/templates/auth/login.html -->
{% extends "base.html" %}
{% block content %}
<section class="auth-card">
  <h1>Sign in</h1>
  <p>This is an invite-only tool. Sign in with the Google account you were invited with.</p>
  <button id="google-signin" type="button">Sign in with Google</button>
  <p id="auth-error" class="auth-error" hidden></p>
</section>
<script type="module">
  import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
  import { getAuth, connectAuthEmulator, GoogleAuthProvider, signInWithPopup }
    from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";

  const app = initializeApp({
    apiKey: "{{ firebase_api_key }}",
    authDomain: "{{ firebase_auth_domain }}",
    projectId: "{{ firebase_project_id }}",
  });
  const auth = getAuth(app);
  {% if use_emulator %}
  connectAuthEmulator(auth, "http://{{ emulator_host }}", { disableWarnings: true });
  {% endif %}

  const errEl = document.getElementById("auth-error");
  function showError(msg) { errEl.textContent = msg; errEl.hidden = false; }

  document.getElementById("google-signin").addEventListener("click", async () => {
    errEl.hidden = true;
    try {
      const cred = await signInWithPopup(auth, new GoogleAuthProvider());
      const idToken = await cred.user.getIdToken();
      const resp = await fetch("/login/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idToken }),
      });
      if (resp.ok) { window.location.assign("/"); return; }
      const data = await resp.json().catch(() => ({}));
      showError(data.error === "not invited"
        ? "That Google account isn't on the invite list."
        : "Sign-in failed. Please try again.");
    } catch (e) {
      showError("Sign-in was cancelled or failed.");
    }
  });
</script>
{% endblock %}
```

Note: this assumes `base.html` defines a `content` block. Open `aose/web/templates/base.html` and use its actual content block name if different. Task D4's flow test (which renders `/` after login) plus a manual emulator check (Phase E) confirm the page works.

- [ ] **Step 2: Write the routes**

```python
# aose/web/auth/routes.py
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from aose.web.auth.identity import normalise_email
from aose.web.auth.verify import TokenError
from aose.web.templating import make_templates

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = make_templates(str(TEMPLATES_DIR))


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    cfg = request.app.state.auth_config
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {
            "firebase_api_key": cfg.firebase_api_key,
            "firebase_auth_domain": cfg.firebase_auth_domain,
            "firebase_project_id": cfg.firebase_project_id,
            "use_emulator": cfg.use_emulator,
            "emulator_host": cfg.emulator_host,
        },
    )


@router.post("/login/session")
async def login_session(request: Request):
    verifier = request.app.state.auth_verifier
    whitelist = request.app.state.auth_whitelist
    body = await request.json()
    id_token = body.get("idToken", "")
    try:
        user = verifier.verify(id_token)
    except TokenError:
        return JSONResponse({"error": "invalid token"}, status_code=401)
    if not user.email_verified or not whitelist.allows(user.email):
        return JSONResponse({"error": "not invited"}, status_code=403)
    request.session["uid"] = user.uid
    request.session["email"] = normalise_email(user.email)
    return JSONResponse({"ok": True})


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
```

- [ ] **Step 3: No standalone run yet** — depends on `app.state.auth_{config,verifier,whitelist}`, wired in D4.

- [ ] **Step 4: Commit**

```bash
git add aose/web/auth/routes.py aose/web/templates/auth/login.html
git commit -m "feat(auth): Google sign-in page + session endpoint"
```

### Task D4: Wire auth into `create_app` + end-to-end flow test

**Files:**
- Modify: `aose/web/app.py`, `pyproject.toml`, `.gitignore`
- Test: `tests/test_auth_flow.py`

- [ ] **Step 1: Write the failing flow test**

```python
# tests/test_auth_flow.py
from pathlib import Path

from fastapi.testclient import TestClient

from aose.web.app import create_app
from aose.web.auth.config import AuthConfig
from aose.web.auth.verify import FakeVerifier, VerifiedUser

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def _make(tmp_path, whitelist=("alice@gmail.com",), tokens=None):
    (tmp_path / "whitelist.txt").write_text("\n".join(whitelist), encoding="utf-8")
    cfg = AuthConfig(
        session_secret="test-session-secret",
        whitelist_path=tmp_path / "whitelist.txt",
        users_root=tmp_path / "users",
        firebase_project_id="demo", firebase_api_key="k",
        firebase_auth_domain="demo.firebaseapp.com",
        use_emulator=True, emulator_host="localhost:9099", cookie_secure=False,
    )
    tokens = tokens or {
        "tok-alice": VerifiedUser(uid="uid-alice", email="alice@gmail.com", email_verified=True),
        "tok-mallory": VerifiedUser(uid="uid-mallory", email="mallory@evil.test", email_verified=True),
        "tok-bob": VerifiedUser(uid="uid-bob", email="bob@example.org", email_verified=True),
    }
    app = create_app(data_dir=DATA_DIR, auth_config=cfg, auth_verifier=FakeVerifier(tokens))
    return app, TestClient(app)


def test_unauthenticated_is_redirected_to_login(tmp_path):
    _, client = _make(tmp_path)
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_full_login_flow_grants_access(tmp_path):
    _, client = _make(tmp_path)
    resp = client.post("/login/session", json={"idToken": "tok-alice"})
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    assert client.get("/").status_code == 200  # session cookie now lets us in


def test_non_whitelisted_email_is_forbidden(tmp_path):
    _, client = _make(tmp_path)
    resp = client.post("/login/session", json={"idToken": "tok-mallory"})
    assert resp.status_code == 403
    assert client.get("/", follow_redirects=False).status_code == 303  # still gated


def test_invalid_token_is_unauthorized(tmp_path):
    _, client = _make(tmp_path)
    assert client.post("/login/session", json={"idToken": "garbage"}).status_code == 401


def test_two_users_have_isolated_workspaces(tmp_path):
    app, client = _make(tmp_path, whitelist=("alice@gmail.com", "bob@example.org"))
    client.post("/login/session", json={"idToken": "tok-alice"})
    client.get("/logout")
    client.post("/login/session", json={"idToken": "tok-bob"})
    dirs = sorted(p.name for p in (tmp_path / "users").iterdir())
    assert dirs == ["uid-alice", "uid-bob"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth_flow.py -q`
Expected: FAIL — `create_app() got an unexpected keyword argument 'auth_config'`.

- [ ] **Step 3: Update `pyproject.toml`**

Add `itsdangerous` and `firebase-admin` to the `web` extra:

```toml
web = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "jinja2>=3.1",
    "python-multipart",
    "markdown>=3.5",
    "itsdangerous>=2.0",
    "firebase-admin>=6.0",
]
```

Install: `.venv\Scripts\python.exe -m pip install "itsdangerous>=2.0" "firebase-admin>=6.0"`

- [ ] **Step 4: Wire `create_app`**

In `aose/web/app.py`, add imports:

```python
from starlette.middleware.sessions import SessionMiddleware

from aose.web.auth.config import AuthConfig
from aose.web.auth.routes import router as auth_router
from aose.web.auth.verify import build_verifier
from aose.web.auth.whitelist import Whitelist
```

Change the signature:

```python
def create_app(
    data_dir: Path = DEFAULT_DATA_DIR,
    characters_dir: Path = DEFAULT_CHARACTERS_DIR,
    drafts_dir: Path = DEFAULT_DRAFTS_DIR,
    examples_dir: Path = DEFAULT_EXAMPLES_DIR,
    settings_path: Path = DEFAULT_SETTINGS_PATH,
    seed_from_examples: bool = True,
    auth_config: "AuthConfig | None" = None,
    auth_verifier=None,
) -> FastAPI:
```

Replace the `app.state.auth_config = None` line (from Task A3) with the wiring below. After the existing `app.state.*` assignments and before mounting static:

```python
    if auth_config is None:
        auth_config = AuthConfig.from_env(PROJECT_ROOT)
    app.state.auth_config = auth_config

    if auth_config is not None:
        app.state.auth_whitelist = Whitelist(auth_config.whitelist_path)
        app.state.auth_verifier = auth_verifier or build_verifier(auth_config)
```

Make example-seeding apply to the auth-off (global) dir only:

```python
    if seed_from_examples and auth_config is None:
        _bootstrap_characters(characters_dir, examples_dir)
```

Register the workspace middleware, then session middleware (added last → outermost → `request.session` is available inside the workspace middleware), then the auth router:

```python
    app.add_middleware(WorkspaceAuthMiddleware)
    if auth_config is not None:
        app.add_middleware(
            SessionMiddleware,
            secret_key=auth_config.session_secret,
            https_only=auth_config.cookie_secure,
            same_site="lax",
        )
        app.include_router(auth_router)
```

- [ ] **Step 5: Add ignores**

Append to `.gitignore`:

```
# hosted-auth (never commit invitee data / per-user data / service-account keys)
whitelist.txt
users/
*service-account*.json
```

- [ ] **Step 6: Run the flow test, then the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth_flow.py -q`
Expected: PASS.

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS — every pre-existing test still green (auth off by default). Ignore the known trailing `pytest-current` PermissionError.

- [ ] **Step 7: Commit**

```bash
git add aose/web/app.py pyproject.toml .gitignore tests/test_auth_flow.py
git commit -m "feat(auth): wire GCIP auth into create_app + session middleware"
```

---

## Phase E — Running locally & production smoke (no code)

### Local development with the Firebase Auth emulator

Daily dev is unchanged — auth off, plain uvicorn:

```powershell
.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload
```

To exercise the Google sign-in flow offline, run the emulator (needs Node + a Java runtime):

```powershell
npm install -g firebase-tools
firebase init emulators      # select Authentication
firebase emulators:start     # Auth on :9099, Emulator UI on :4000
```

Then start the app pointed at the emulator (separate terminal):

```powershell
$env:AOSE_AUTH                    = "1"
$env:AOSE_SESSION_SECRET          = "dev-session"
$env:AOSE_FIREBASE_PROJECT_ID     = "demo-aose"     # any id; emulator accepts it
$env:AOSE_FIREBASE_API_KEY        = "demo-key"       # any non-empty value for the emulator
$env:AOSE_FIREBASE_AUTH_DOMAIN    = "localhost"
$env:FIREBASE_AUTH_EMULATOR_HOST  = "localhost:9099" # makes backend + frontend use the emulator
$env:AOSE_COOKIE_INSECURE         = "1"              # allow the session cookie over http://localhost
.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload
```

- [ ] Create `whitelist.txt` at project root with the email you'll use in the emulator.
- [ ] Visit `http://localhost:8000` → redirected to `/login` → "Sign in with Google" → the emulator shows a fake account picker (no real Google) → add/select an account whose email is on the whitelist → you land on your seeded index. Non-whitelisted emails get "That Google account isn't on the invite list."

### Production smoke

- [ ] On the EC2 box set: `AOSE_AUTH=1`, `AOSE_SESSION_SECRET=<random>`, `AOSE_FIREBASE_PROJECT_ID=<real>`, `AOSE_FIREBASE_API_KEY=<real web key>`, `AOSE_FIREBASE_AUTH_DOMAIN=<project>.firebaseapp.com`, `GOOGLE_APPLICATION_CREDENTIALS=<path to service-account.json>`. Do **not** set `FIREBASE_AUTH_EMULATOR_HOST`.
  - Random secret: `.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"`
- [ ] Put your own + friends' Google emails in `whitelist.txt`.
- [ ] Run uvicorn behind the existing HTTPS reverse proxy; sign in with a real Google account on the whitelist; confirm a friend gets their own isolated (seeded) workspace.

No commit.

---

## Phase F — Export / import (self-serve backup)

### Task F1: Character export

**Files:**
- Modify: `aose/web/routes.py`
- Test: `tests/test_export_import.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_export_import.py
from pathlib import Path

from fastapi.testclient import TestClient

from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
EXAMPLES_DIR = PROJECT_ROOT / "examples"


def _client():
    app = create_app(data_dir=DATA_DIR, characters_dir=EXAMPLES_DIR)
    return TestClient(app)


def test_export_returns_character_json():
    resp = _client().get("/character/thorin/export")
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].endswith('filename="thorin.json"')
    assert resp.json()["name"] == "Thorin"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_export_import.py -q`
Expected: FAIL — 404 (route absent).

- [ ] **Step 3: Add the export route**

In `aose/web/routes.py`, add near the other `/character/{character_id}` GET routes:

```python
@router.get("/character/{character_id}/export")
async def character_export(request: Request, character_id: str):
    spec = _load_spec_or_404(request, character_id)
    headers = {"Content-Disposition": f'attachment; filename="{character_id}.json"'}
    return Response(
        content=json.dumps(spec.model_dump(mode="json"), indent=2),
        media_type="application/json",
        headers=headers,
    )
```

Add `import json` at the top of `routes.py` if not already present. `_load_spec_or_404` already exists (`routes.py:274`).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_export_import.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_export_import.py
git commit -m "feat(characters): JSON export route"
```

### Task F2: Character import

**Files:**
- Modify: `aose/web/routes.py`
- Test: `tests/test_export_import.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_export_import.py  (append)
def test_import_roundtrip(tmp_path):
    app = create_app(data_dir=DATA_DIR, characters_dir=tmp_path / "characters",
                     seed_from_examples=False)
    client = TestClient(app)
    src = TestClient(create_app(data_dir=DATA_DIR, characters_dir=EXAMPLES_DIR))
    payload = src.get("/character/thorin/export").content
    resp = client.post(
        "/import",
        files={"file": ("thorin.json", payload, "application/json")},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "Thorin" in client.get("/").text


def test_import_rejects_invalid_json(tmp_path):
    app = create_app(data_dir=DATA_DIR, characters_dir=tmp_path / "characters",
                     seed_from_examples=False)
    client = TestClient(app)
    resp = client.post("/import", files={"file": ("bad.json", b"{not valid", "application/json")})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_export_import.py -q`
Expected: FAIL — 404/405 (route absent).

- [ ] **Step 3: Add the import route**

In `aose/web/routes.py`, add the route and extend imports:

```python
@router.post("/import")
async def character_import(request: Request, file: UploadFile = File(...)):
    raw = await file.read()
    try:
        spec = CharacterSpec.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid character file: {exc}")
    characters_dir = request.state.characters_dir
    cid = unique_character_id(slugify(spec.name), characters_dir)
    save_character(cid, spec, characters_dir)
    return RedirectResponse(url=f"/character/{cid}", status_code=303)
```

Ensure these are imported at the top of `routes.py`:
- Extend `from fastapi import ...` with `File, UploadFile`.
- Extend the `from aose.characters.storage import ...` line with `slugify, unique_character_id`.
- Extend `from aose.models import ...` with `CharacterSpec`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_export_import.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_export_import.py
git commit -m "feat(characters): JSON import route with validation"
```

### Task F3: Surface export/import + sign-out in the UI

**Files:**
- Modify: `aose/web/templates/index.html`, `aose/web/templates/base.html`

- [ ] **Step 1: Inspect the templates** — read `aose/web/templates/index.html` and `base.html` to match existing markup/classes for the character list and header.

- [ ] **Step 2: Add a per-character export link** in `index.html`, alongside the existing sheet link:

```html
<a href="/character/{{ c.id }}/export">Export</a>
```

- [ ] **Step 3: Add an import form** near the character list in `index.html`:

```html
<form method="post" action="/import" enctype="multipart/form-data" class="import-form">
  <label>Import character <input type="file" name="file" accept="application/json" required></label>
  <button type="submit">Import</button>
</form>
```

- [ ] **Step 4: Add a sign-out link** in `base.html`, shown only when a session exists (renders nothing under auth-off):

```html
{% if request.session.get("email") %}
  <a href="/logout" class="logout-link">Sign out ({{ request.session["email"] }})</a>
{% endif %}
```

- [ ] **Step 5: Run the suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/web/templates/index.html aose/web/templates/base.html
git commit -m "feat(web): export/import + sign-out UI"
```

---

## Phase G — Docs

### Task G1: Update the living docs

**Files:**
- Modify: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`, `CLAUDE.md`

- [ ] **Step 1: ARCHITECTURE.md** — add a **"Hosting & auth"** subsystem section: the `auth_enabled`/`AuthConfig` flag (off by default); `WorkspaceAuthMiddleware` → `request.state.{characters_dir,drafts_dir,settings_path}` indirection; per-user `users/<uid>/` layout keyed by the **GCIP uid** (`safe_uid` guard); GCIP Google-only sign-in (Firebase JS on the login page → ID token → `FirebaseVerifier` (firebase-admin, lazy import) → whitelist check → our own `SessionMiddleware` cookie); the whitelist file as sole invite gate; **no email/SMTP/DNS**; the `FakeVerifier` test seam; the Firebase emulator for offline dev; and export/import as the backup escape hatch. Note the one ethos exception: the login page carries client-side JS (the rest of the app stays server-rendered).

- [ ] **Step 2: CHANGELOG.md** — add one dated row at the top:

```
| 2026-06-11 | Hosted auth & multi-tenancy (invite-only GCIP Google sign-in, per-user workspaces, export/import) | <branch> | 2026-06-11-hosted-auth-multitenancy |
```

- [ ] **Step 3: CLAUDE.md** — orientation only: note the new `aose/web/auth/` package in the layout table; add to storage-shapes that per-user workspaces live under `users/<uid>/` when `AOSE_AUTH` is set (mirroring root `characters/`, `drafts/`, `settings.json`), and that auth is off by default so the app is unchanged without it. No per-feature prose.

- [ ] **Step 4: Commit**

```bash
git add docs/ARCHITECTURE.md docs/CHANGELOG.md CLAUDE.md
git commit -m "docs: hosted auth & multi-tenancy (GCIP Google sign-in)"
```

---

## Self-Review notes

- **Spec coverage:** GCIP Google-only auth (Phase 0 prereqs + C verifier + D3 login page/session), invite-only (B2 whitelist + D3 `not invited` gate), per-user multi-tenancy (A workspace + D2 resolution keyed by GCIP uid), no email/DNS (Google-only throughout), HTTPS/secure cookie (Phase 0 + `cookie_secure`), offline dev + tests (Firebase emulator in Phase E; `FakeVerifier` in C1/D4), backup/orphan-mitigation (Phase F export/import). All present.
- **Auth-off invariant:** A1–A3 keep default behaviour and the full existing suite green; D4 re-runs the whole suite after wiring.
- **Type/name consistency:** `Workspace(characters_dir, drafts_dir, settings_path)`, `resolve_workspace(request)`, `normalise_email`, `safe_uid`, `Whitelist(path).allows(email)`, `VerifiedUser(uid, email, email_verified)`, `Verifier.verify(id_token)`, `FakeVerifier({token: VerifiedUser})`, `build_verifier(config)`, `AuthConfig.from_env(project_root)` + fields, `app.state.auth_{config,verifier,whitelist}`, session keys `uid`/`email` — used consistently across tasks (gate checks `uid`; resolution uses `uid`; sign-out UI uses `email`).
- **Open verification point:** D3's `login.html` assumes `base.html` exposes a `content` block; D3 Step 1 flags it, and D4 (`client.get("/")==200` after login) plus the Phase E emulator run confirm the page renders/works.
- **Dependency note:** `firebase-admin` is heavier than the rest of the stack but is imported lazily inside `FirebaseVerifier`, so tests (which inject `FakeVerifier`) never load it; it's only needed at runtime in prod/emulator.
```
