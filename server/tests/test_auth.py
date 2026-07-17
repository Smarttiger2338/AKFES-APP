import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.request_security import RequestSecurityService

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
        challenge_ttl_seconds=60,
        device_binding_required=True,
    )


def issue_license(client: TestClient, *, label: str = "test") -> dict[str, object]:
    response = client.post(
        "/api/v2/admin/licenses",
        headers=ADMIN_HEADERS,
        json={"duration_seconds": 3600, "label": label},
    )
    assert response.status_code == 201
    return response.json()


def login_session(
    client: TestClient,
    license_key: str,
    *,
    device_id: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"license_key": license_key}
    if device_id is not None:
        payload["device_id"] = device_id
    response = client.post("/api/v2/auth/login", json=payload)
    assert response.status_code == 200
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

    missing_device = client.post(
        "/api/v2/auth/login",
        json={"license_key": license_key},
    )
    assert missing_device.status_code == 403

    login_body = login_session(client, license_key.lower(), device_id="device-01")
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

    missing_session_device = client.get(
        "/api/v2/auth/session",
        headers={"Authorization": f"Bearer {login_body['session_token']}"},
    )
    assert missing_session_device.status_code == 401

    wrong_device = client.get(
        "/api/v2/auth/session",
        headers={
            "Authorization": f"Bearer {login_body['session_token']}",
            "X-AKFES-Device-ID": "device-02",
        },
    )
    assert wrong_device.status_code == 401

    with sqlite3.connect(settings.database_path) as connection:
        stored_key_digest, stored_device_digest = connection.execute(
            "SELECT key_digest, bound_device_digest FROM licenses"
        ).fetchone()
    assert stored_key_digest != license_key
    assert license_key not in stored_key_digest
    assert stored_device_digest != "device-01"
    assert "device-01" not in stored_device_digest


def test_device_binding_reset_and_rebind(tmp_path: Path) -> None:
    client = TestClient(create_app(make_test_settings(tmp_path)))
    issued = issue_license(client, label="device-binding-test")
    license_id = int(issued["license_id"])
    license_key = str(issued["license_key"])

    first_login = login_session(client, license_key, device_id="device-first")
    first_token = str(first_login["session_token"])

    other_device_login = client.post(
        "/api/v2/auth/login",
        json={"license_key": license_key, "device_id": "device-second"},
    )
    assert other_device_login.status_code == 403
    assert "another device" in other_device_login.json()["detail"]

    listed = client.get("/api/v2/admin/licenses", headers=ADMIN_HEADERS)
    summary = next(item for item in listed.json() if item["license_id"] == license_id)
    assert summary["device_bound"] is True

    reset = client.post(
        f"/api/v2/admin/licenses/{license_id}/device-binding/reset",
        headers=ADMIN_HEADERS,
        json={"reason": "device replacement"},
    )
    assert reset.status_code == 200
    assert reset.json()["license_id"] == license_id

    old_session = client.get(
        "/api/v2/auth/session",
        headers={
            "Authorization": f"Bearer {first_token}",
            "X-AKFES-Device-ID": "device-first",
        },
    )
    assert old_session.status_code == 401

    second_login = login_session(client, license_key, device_id="device-second")
    assert second_login["device_id"] == "device-second"

    listed_after = client.get("/api/v2/admin/licenses", headers=ADMIN_HEADERS)
    rebound = next(item for item in listed_after.json() if item["license_id"] == license_id)
    assert rebound["device_bound"] is True
    assert rebound["active_session_count"] == 1

    audit = client.get("/api/v2/admin/audit", headers=ADMIN_HEADERS).json()
    actions = [entry["action"] for entry in audit]
    assert "license.device_binding.create" in actions
    assert "license.device_binding.reset" in actions
    reset_event = next(
        entry for entry in audit if entry["action"] == "license.device_binding.reset"
    )
    assert reset_event["actor"] == "test-operator"
    assert reset_event["details"]["reason"] == "device replacement"


def test_license_list_revoke_and_audit(tmp_path: Path) -> None:
    client = TestClient(create_app(make_test_settings(tmp_path)))
    issued = issue_license(client, label="revocation-test")
    license_id = int(issued["license_id"])
    license_key = str(issued["license_key"])

    login = login_session(client, license_key, device_id="device-01")
    session_token = login["session_token"]

    listed = client.get("/api/v2/admin/licenses", headers=ADMIN_HEADERS)
    assert listed.status_code == 200
    license_summary = next(
        item for item in listed.json() if item["license_id"] == license_id
    )
    assert license_summary["label"] == "revocation-test"
    assert license_summary["status"] == "active"
    assert license_summary["device_bound"] is True
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
        json={"license_key": license_key, "device_id": "device-01"},
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
    assert actions[0] == "license.revoke"
    assert "license.issue" in actions
    revoke_event = audit.json()[0]
    assert revoke_event["actor"] == "test-operator"
    assert revoke_event["target_id"] == str(license_id)
    assert revoke_event["details"]["reason"] == "test cleanup"


def test_one_time_challenge_and_request_signature(tmp_path: Path) -> None:
    client = TestClient(create_app(make_test_settings(tmp_path)))
    issued = issue_license(client, label="signature-test")
    login = login_session(
        client,
        str(issued["license_key"]),
        device_id="device-signing-01",
    )
    session_token = str(login["session_token"])
    common_headers = {
        "Authorization": f"Bearer {session_token}",
        "X-AKFES-Device-ID": "device-signing-01",
    }

    challenge_response = client.post(
        "/api/v2/auth/challenge",
        headers=common_headers,
    )
    assert challenge_response.status_code == 200
    challenge_body = challenge_response.json()
    challenge = challenge_body["challenge"]
    assert challenge_body["algorithm"] == "HMAC-SHA256"
    assert challenge_body["canonical_version"] == "AKFES-V2"

    body = json.dumps(
        {"message": "signed request"},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    signature = RequestSecurityService.calculate_signature(
        session_token=session_token,
        method="POST",
        path="/api/v2/auth/signed-check",
        challenge=challenge,
        body=body,
        device_id="device-signing-01",
    )
    signed_headers = {
        **common_headers,
        "Content-Type": "application/json",
        "X-AKFES-Challenge": challenge,
        "X-AKFES-Signature": signature,
    }

    verified = client.post(
        "/api/v2/auth/signed-check",
        headers=signed_headers,
        content=body,
    )
    assert verified.status_code == 200
    assert verified.json()["valid"] is True
    assert verified.json()["device_id"] == "device-signing-01"

    replay = client.post(
        "/api/v2/auth/signed-check",
        headers=signed_headers,
        content=body,
    )
    assert replay.status_code == 409

    second_challenge = client.post(
        "/api/v2/auth/challenge",
        headers=common_headers,
    ).json()["challenge"]
    invalid_signature_headers = {
        **common_headers,
        "Content-Type": "application/json",
        "X-AKFES-Challenge": second_challenge,
        "X-AKFES-Signature": "0" * 64,
    }
    invalid_signature = client.post(
        "/api/v2/auth/signed-check",
        headers=invalid_signature_headers,
        content=body,
    )
    assert invalid_signature.status_code == 401

    valid_after_failed_attempt = RequestSecurityService.calculate_signature(
        session_token=session_token,
        method="POST",
        path="/api/v2/auth/signed-check",
        challenge=second_challenge,
        body=body,
        device_id="device-signing-01",
    )
    retry_headers = {
        **invalid_signature_headers,
        "X-AKFES-Signature": valid_after_failed_attempt,
    }
    retry = client.post(
        "/api/v2/auth/signed-check",
        headers=retry_headers,
        content=body,
    )
    assert retry.status_code == 200

    third_challenge = client.post(
        "/api/v2/auth/challenge",
        headers=common_headers,
    ).json()["challenge"]
    original_body_signature = RequestSecurityService.calculate_signature(
        session_token=session_token,
        method="POST",
        path="/api/v2/auth/signed-check",
        challenge=third_challenge,
        body=body,
        device_id="device-signing-01",
    )
    tampered = client.post(
        "/api/v2/auth/signed-check",
        headers={
            **common_headers,
            "Content-Type": "application/json",
            "X-AKFES-Challenge": third_challenge,
            "X-AKFES-Signature": original_body_signature,
        },
        content=json.dumps(
            {"message": "tampered request"},
            separators=(",", ":"),
        ).encode("utf-8"),
    )
    assert tampered.status_code == 401


def test_admin_endpoints_require_token(tmp_path: Path) -> None:
    client = TestClient(create_app(make_test_settings(tmp_path)))

    assert client.get("/api/v2/admin/licenses").status_code == 401
    assert client.get("/api/v2/admin/audit").status_code == 401
    assert client.post(
        "/api/v2/admin/licenses/1/revoke",
        json={"reason": "unauthorized"},
    ).status_code == 401
    assert client.post(
        "/api/v2/admin/licenses/1/device-binding/reset",
        json={"reason": "unauthorized"},
    ).status_code == 401


def test_rejects_malformed_license_key(tmp_path: Path) -> None:
    client = TestClient(create_app(make_test_settings(tmp_path)))

    response = client.post(
        "/api/v2/auth/login",
        json={"license_key": "not-a-license", "device_id": "device-01"},
    )

    assert response.status_code == 401
