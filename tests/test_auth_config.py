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
    monkeypatch.setenv("AOSE_SESSION_SECRET", "emulator-secret")
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099")
    cfg = AuthConfig.from_env(project_root=tmp_path)
    assert cfg.use_emulator is True
    assert cfg.emulator_host == "localhost:9099"


def test_from_env_raises_on_empty_session_secret(monkeypatch, tmp_path):
    import pytest
    monkeypatch.setenv("AOSE_AUTH", "1")
    monkeypatch.delenv("AOSE_SESSION_SECRET", raising=False)
    with pytest.raises(ValueError, match="AOSE_SESSION_SECRET"):
        AuthConfig.from_env(project_root=tmp_path)
