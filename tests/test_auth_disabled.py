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
