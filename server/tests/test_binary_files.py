from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.request_security import RequestSecurityService

ADMIN_HEADERS = {
    "X-AKFES-Admin-Token": "test-admin-token-that-is-long-enough",
    "X-AKFES-Admin-Actor": "binary-test",
}


def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_name="AKFES API",
        version="2.0.0-test",
        environment="test",
        host="127.0.0.1",
        port=8000,
        docs_enabled=False,
        cors_origins=("http://localhost:1420",),
        allowed_hosts=("testserver",),
        max_upload_bytes=1024 * 1024,
        database_path=str(tmp_path / "binary.sqlite3"),
        license_hmac_secret="test-license-secret-that-is-long-enough",
        admin_token=ADMIN_HEADERS["X-AKFES-Admin-Token"],
        session_ttl_seconds=900,
        challenge_ttl_seconds=60,
        device_binding_required=True,
        pbkdf2_iterations=100_000,
    )


def signed_headers(
    client: TestClient,
    token: str,
    device_id: str,
    path: str,
    body: bytes,
    *,
    password: str,
    filename: str | None = None,
) -> dict[str, str]:
    challenge = client.post(
        "/api/v2/auth/challenge",
        headers={
            "Authorization": f"Bearer {token}",
            "X-AKFES-Device-ID": device_id,
        },
    ).json()["challenge"]
    signature = RequestSecurityService.calculate_signature(
        session_token=token,
        method="POST",
        path=path,
        challenge=challenge,
        body=body,
        device_id=device_id,
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream",
        "X-AKFES-Device-ID": device_id,
        "X-AKFES-Challenge": challenge,
        "X-AKFES-Signature": signature,
        "X-AKFES-Password": quote(password),
    }
    if filename is not None:
        headers["X-AKFES-Filename"] = quote(filename)
    return headers


def test_binary_encrypt_decrypt_round_trip(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path)))
    issued = client.post(
        "/api/v2/admin/licenses",
        headers=ADMIN_HEADERS,
        json={"duration_seconds": 3600, "label": "binary"},
    ).json()
    login = client.post(
        "/api/v2/auth/login",
        json={"license_key": issued["license_key"], "device_id": "binary-device"},
    ).json()
    token = login["session_token"]
    plaintext = b"AKFES binary payload\x00\x01" * 64

    encrypt_path = "/api/v2/files/encrypt-binary"
    encrypted = client.post(
        encrypt_path,
        headers=signed_headers(
            client,
            token,
            "binary-device",
            encrypt_path,
            plaintext,
            password="pass-1234",
            filename="report data.bin",
        ),
        content=plaintext,
    )
    assert encrypted.status_code == 200
    assert encrypted.headers["content-type"].startswith("application/octet-stream")
    assert encrypted.headers["x-akfes-filename"] == "report%20data.bin.akfes"
    assert b"AKFES binary payload" not in encrypted.content

    decrypt_path = "/api/v2/files/decrypt-binary"
    decrypted = client.post(
        decrypt_path,
        headers=signed_headers(
            client,
            token,
            "binary-device",
            decrypt_path,
            encrypted.content,
            password="pass-1234",
        ),
        content=encrypted.content,
    )
    assert decrypted.status_code == 200
    assert decrypted.content == plaintext
    assert decrypted.headers["x-akfes-filename"] == "report%20data.bin"


def test_binary_request_signature_rejects_modified_body(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path)))
    issued = client.post(
        "/api/v2/admin/licenses",
        headers=ADMIN_HEADERS,
        json={"duration_seconds": 3600},
    ).json()
    login = client.post(
        "/api/v2/auth/login",
        json={"license_key": issued["license_key"], "device_id": "binary-device"},
    ).json()
    path = "/api/v2/files/encrypt-binary"
    original = b"original body"
    headers = signed_headers(
        client,
        login["session_token"],
        "binary-device",
        path,
        original,
        password="pass-1234",
        filename="file.bin",
    )
    response = client.post(path, headers=headers, content=b"modified body")
    assert response.status_code == 401
