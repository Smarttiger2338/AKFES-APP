import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ADMIN_TOKEN = "test-admin-token-that-is-long-enough"
ADMIN_HEADERS = {
    "X-AKFES-Admin-Token": ADMIN_TOKEN,
    "X-AKFES-Admin-Actor": "test-operator",
}


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


def issue_license(client: TestClient, *, label: str = "test") -> dict[str, object]:
    response = client.post(
        "/api/v2/admin/licenses",
        headers=ADMIN_HEADERS,
        json={"duration_seconds": 3600, "label": label},
    )
    assert response.status_code == 201
    return response.json()


def test_license_issue_login_and_session_status(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path)
    client = TestClient(create_app(settings))

    unauthorized = client.post(
        "/api/v2/admin/licenses",
        json={"duration_seconds": 3600, "label": "test"},
    )
    assert unauthorized.status_code == 401

    issued_body = issue_license(client)
    license_key = str(issued_body["license_key"])
    assert license_key.startswith("AKFES-")
    assert int(issued_body["expires_at"]) > int(issued_body["created_at"])

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


def test_license_list_revoke_and_audit(tmp_path: Path) -> None:
    client = TestClient(create_app(make_test_settings(tmp_path)))
    issued = issue_license(client, label="revocation-test")
    license_id = int(issued["license_id"])
    license_key = str(issued["license_key"])

    login = client.post(
        "/api/v2/auth/login",
        json={"license_key": license_key, "device_id": "device-01"},
    )
    assert login.status_code == 200
    session_token = login.json()["session_token"]

    listed = client.get("/api/v2/admin/licenses", headers=ADMIN_HEADERS)
    assert listed.status_code == 200
    license_summary = next(
        item for item in listed.json() if item["license_id"] == license_id
    )
    assert license_summary["label"] == "revocation-test"
    assert license_summary["status"] == "active"
    assert license_summary["active_session_count"] == 1
    assert "license_key" not in license_summary

    revoked = client.post(
        f"/api/v2/admin/licenses/{license_id}/revoke",
        headers=ADMIN_HEADERS,
        json={"reason": "test cleanup"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["license_id"] == license_id

    session_after_revoke = client.get(
        "/api/v2/auth/session",
        headers={
            "Authorization": f"Bearer {session_token}",
            "X-AKFES-Device-ID": "device-01",
        },
    )
    assert session_after_revoke.status_code == 401

    login_after_revoke = client.post(
        "/api/v2/auth/login",
        json={"license_key": license_key},
    )
    assert login_after_revoke.status_code == 403

    listed_after_revoke = client.get("/api/v2/admin/licenses", headers=ADMIN_HEADERS)
    revoked_summary = next(
        item for item in listed_after_revoke.json() if item["license_id"] == license_id
    )
    assert revoked_summary["status"] == "revoked"
    assert revoked_summary["revoked_at"] is not None
    assert revoked_summary["active_session_count"] == 0

    duplicate_revoke = client.post(
        f"/api/v2/admin/licenses/{license_id}/revoke",
        headers=ADMIN_HEADERS,
        json={"reason": "duplicate"},
    )
    assert duplicate_revoke.status_code == 404

    audit = client.get("/api/v2/admin/audit", headers=ADMIN_HEADERS)
    assert audit.status_code == 200
    actions = [entry["action"] for entry in audit.json()]
    assert actions[:2] == ["license.revoke", "license.issue"]
    revoke_event = audit.json()[0]
    assert revoke_event["actor"] == "test-operator"
    assert revoke_event["target_id"] == str(license_id)
    assert revoke_event["details"]["reason"] == "test cleanup"


def test_admin_endpoints_require_token(tmp_path: Path) -> None:
    client = TestClient(create_app(make_test_settings(tmp_path)))

    assert client.get("/api/v2/admin/licenses").status_code == 401
    assert client.get("/api/v2/admin/audit").status_code == 401
    assert client.post(
        "/api/v2/admin/licenses/1/revoke",
        json={"reason": "unauthorized"},
    ).status_code == 401


def test_rejects_malformed_license_key(tmp_path: Path) -> None:
    client = TestClient(create_app(make_test_settings(tmp_path)))

    response = client.post(
        "/api/v2/auth/login",
        json={"license_key": "not-a-license"},
    )

    assert response.status_code == 401
