import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ADMIN_TOKEN = "test-admin-token-that-is-long-enough"


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
        database_path=str(tmp_path / "auth.sqlite3"),
        license_hmac_secret="test-license-secret-that-is-long-enough",
        admin_token=ADMIN_TOKEN,
        session_ttl_seconds=900,
    )


def test_license_issue_login_and_session_status(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path)
    client = TestClient(create_app(settings))

    unauthorized = client.post(
        "/api/v2/admin/licenses",
        json={"duration_seconds": 3600, "label": "test"},
    )
    assert unauthorized.status_code == 401

    issued = client.post(
        "/api/v2/admin/licenses",
        headers={"X-AKFES-Admin-Token": ADMIN_TOKEN},
        json={"duration_seconds": 3600, "label": "test"},
    )
    assert issued.status_code == 201
    issued_body = issued.json()
    license_key = issued_body["license_key"]
    assert license_key.startswith("AKFES-")
    assert issued_body["expires_at"] > issued_body["created_at"]

    invalid_login = client.post(
        "/api/v2/auth/login",
        json={"license_key": "AKFES-AAAAA-BBBBB-CCCCC-DDDDD"},
    )
    assert invalid_login.status_code == 401

    login = client.post(
        "/api/v2/auth/login",
        json={"license_key": license_key.lower(), "device_id": "device-01"},
    )
    assert login.status_code == 200
    login_body = login.json()
    assert login_body["session_token"]
    assert login_body["device_id"] == "device-01"
    assert login_body["session_expires_at"] <= login_body["license_expires_at"]

    session = client.get(
        "/api/v2/auth/session",
        headers={
            "Authorization": f"Bearer {login_body['session_token']}",
            "X-AKFES-Device-ID": "device-01",
        },
    )
    assert session.status_code == 200
    assert session.json()["valid"] is True

    wrong_device = client.get(
        "/api/v2/auth/session",
        headers={
            "Authorization": f"Bearer {login_body['session_token']}",
            "X-AKFES-Device-ID": "device-02",
        },
    )
    assert wrong_device.status_code == 401

    with sqlite3.connect(settings.database_path) as connection:
        stored_digest = connection.execute("SELECT key_digest FROM licenses").fetchone()[0]
    assert stored_digest != license_key
    assert license_key not in stored_digest


def test_rejects_malformed_license_key(tmp_path: Path) -> None:
    client = TestClient(create_app(make_test_settings(tmp_path)))

    response = client.post(
        "/api/v2/auth/login",
        json={"license_key": "not-a-license"},
    )

    assert response.status_code == 401
