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
