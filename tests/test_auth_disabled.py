from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient
from starlette.requests import Request

from aose.web.auth.config import AuthConfig
from aose.web.auth.middleware import WorkspaceAuthMiddleware
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


def test_middleware_sets_request_state_when_auth_off(tmp_path):
    app = FastAPI()
    app.state.auth_config = None
    app.state.characters_dir = tmp_path / "characters"
    app.state.drafts_dir = tmp_path / "drafts"
    app.state.settings_path = tmp_path / "settings.json"
    app.add_middleware(WorkspaceAuthMiddleware)

    @app.get("/probe")
    def probe(request: Request) -> PlainTextResponse:
        return PlainTextResponse(str(request.state.characters_dir))

    client = TestClient(app)
    resp = client.get("/probe")
    assert resp.status_code == 200
    assert resp.text.endswith("characters")


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
