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
        database_path=str(tmp_path / "logout.sqlite3"),
        license_hmac_secret="test-license-secret-that-is-long-enough",
        admin_token=ADMIN_TOKEN,
        session_ttl_seconds=900,
        challenge_ttl_seconds=60,
        device_binding_required=True,
    )


def issue_license(client: TestClient) -> str:
    response = client.post(
        "/api/v2/admin/licenses",
        headers=ADMIN_HEADERS,
        json={"duration_seconds": 3600, "label": "logout-test"},
    )
    assert response.status_code == 201
    return str(response.json()["license_key"])


def login(client: TestClient, license_key: str, device_id: str) -> dict[str, object]:
    response = client.post(
        "/api/v2/auth/login",
        json={"license_key": license_key, "device_id": device_id},
    )
    assert response.status_code == 200
    return response.json()


def auth_headers(session: dict[str, object], device_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {session['session_token']}",
        "X-AKFES-Device-ID": device_id,
    }


def test_logout_revokes_only_current_session_and_deletes_unused_challenges(
    tmp_path: Path,
) -> None:
    settings = make_test_settings(tmp_path)
    client = TestClient(create_app(settings))
    license_key = issue_license(client)
    first_session = login(client, license_key, "device-logout")
    second_session = login(client, license_key, "device-logout")
    first_headers = auth_headers(first_session, "device-logout")
    second_headers = auth_headers(second_session, "device-logout")

    first_challenge = client.post("/api/v2/auth/challenge", headers=first_headers)
    second_challenge = client.post("/api/v2/auth/challenge", headers=second_headers)
    assert first_challenge.status_code == 200
    assert second_challenge.status_code == 200

    logout = client.post("/api/v2/auth/logout", headers=first_headers)
    assert logout.status_code == 200
    body = logout.json()
    assert body["logged_out"] is True
    assert body["deleted_challenges"] == 1

    revoked_session = client.get("/api/v2/auth/session", headers=first_headers)
    assert revoked_session.status_code == 401

    repeated_logout = client.post("/api/v2/auth/logout", headers=first_headers)
    assert repeated_logout.status_code == 401

    remaining_session = client.get("/api/v2/auth/session", headers=second_headers)
    assert remaining_session.status_code == 200
    assert remaining_session.json()["valid"] is True

    with sqlite3.connect(settings.database_path) as connection:
        active_challenges = connection.execute(
            "SELECT COUNT(*) FROM request_challenges WHERE used_at IS NULL"
        ).fetchone()[0]
        revoked_sessions = connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE revoked_at IS NOT NULL"
        ).fetchone()[0]
    assert active_challenges == 1
    assert revoked_sessions == 1

    audit = client.get("/api/v2/admin/audit", headers=ADMIN_HEADERS)
    assert audit.status_code == 200
    logout_event = next(
        entry for entry in audit.json() if entry["action"] == "session.logout"
    )
    assert logout_event["actor"] == "client"
    assert logout_event["target_type"] == "session"
    assert logout_event["details"]["deleted_challenges"] == 1
    assert "session_token" not in str(logout_event)


def test_logout_requires_matching_device(tmp_path: Path) -> None:
    client = TestClient(create_app(make_test_settings(tmp_path)))
    session = login(client, issue_license(client), "device-correct")

    missing_device = client.post(
        "/api/v2/auth/logout",
        headers={"Authorization": f"Bearer {session['session_token']}"},
    )
    assert missing_device.status_code == 401

    wrong_device = client.post(
        "/api/v2/auth/logout",
        headers=auth_headers(session, "device-wrong"),
    )
    assert wrong_device.status_code == 401

    still_valid = client.get(
        "/api/v2/auth/session",
        headers=auth_headers(session, "device-correct"),
    )
    assert still_valid.status_code == 200
