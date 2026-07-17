from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_test_settings(tmp_path: Path) -> Settings:
    return Settings(
        app_name="AKFES API",
        version="2.0.0-test",
        environment="test",
        host="127.0.0.1",
        port=8000,
        docs_enabled=False,
        cors_origins=("http://localhost:1420",),
        allowed_hosts=("testserver",),
        max_upload_bytes=1024,
        database_path=str(tmp_path / "health.sqlite3"),
        license_hmac_secret="test-license-secret-that-is-long-enough",
        admin_token="test-admin-token-that-is-long-enough",
        session_ttl_seconds=900,
        challenge_ttl_seconds=60,
    )


def test_health_endpoints_are_available(tmp_path: Path) -> None:
    client = TestClient(create_app(make_test_settings(tmp_path)))

    for path in ("/health", "/api/v2/health"):
        response = client.get(path)

        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "service": "AKFES API",
            "version": "2.0.0-test",
            "environment": "test",
        }
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-request-id"]


def test_docs_are_disabled_when_configured(tmp_path: Path) -> None:
    client = TestClient(create_app(make_test_settings(tmp_path)))

    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
