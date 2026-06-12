from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient
from starlette.requests import Request

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
