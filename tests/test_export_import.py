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
