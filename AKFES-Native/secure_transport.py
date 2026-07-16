from __future__ import annotations

import hashlib
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests

from device_identity import device_id, public_key_b64, sign_b64


_PROTOCOL = "AKFES-OP-V2"
_CLIENT_VERSION = "2.0.0"
_ORIGINAL_GET = requests.get
_ORIGINAL_POST = requests.post
_INSTALLED = False


def _base_url(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _hash_file_entry(entry) -> tuple[str, int, str]:
    if isinstance(entry, tuple):
        filename = str(entry[0])
        payload = entry[1]
    else:
        filename = Path(getattr(entry, "name", "uploaded_file")).name
        payload = entry

    digest = hashlib.sha256()
    total = 0

    if isinstance(payload, (bytes, bytearray)):
        digest.update(payload)
        total = len(payload)
    else:
        position = payload.tell()
        while True:
            chunk = payload.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
        payload.seek(position)

    return filename, total, digest.hexdigest()


def _canonical_message(
    challenge: str,
    timestamp: int,
    mode: str,
    filename: str,
    file_size: int,
    file_sha256: str,
    password: str,
) -> bytes:
    password_sha256 = hashlib.sha256(password.encode("utf-8")).hexdigest()
    fields = [
        _PROTOCOL,
        challenge,
        str(timestamp),
        device_id(),
        mode,
        filename,
        str(file_size),
        file_sha256,
        password_sha256,
    ]
    return "\n".join(fields).encode("utf-8")


def _secure_get(url, *args, **kwargs):
    headers = dict(kwargs.pop("headers", {}) or {})
    headers.setdefault("X-AKFES-Client-Version", _CLIENT_VERSION)
    headers.setdefault("X-AKFES-Device-ID", device_id())
    return _ORIGINAL_GET(url, *args, headers=headers, **kwargs)


def _secure_post(url, *args, **kwargs):
    path = urlsplit(url).path.rstrip("/")
    headers = dict(kwargs.pop("headers", {}) or {})
    headers.setdefault("X-AKFES-Client-Version", _CLIENT_VERSION)
    headers.setdefault("X-AKFES-Device-ID", device_id())

    if path.endswith("/auth/login"):
        payload = dict(kwargs.pop("json", {}) or {})
        payload["device_public_key"] = public_key_b64()
        payload["device_id"] = device_id()
        payload["client_version"] = _CLIENT_VERSION
        return _ORIGINAL_POST(url, *args, json=payload, headers=headers, **kwargs)

    if path.endswith("/process"):
        authorization = headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            raise RuntimeError("AKFES session token is missing.")

        challenge_response = _ORIGINAL_POST(
            f"{_base_url(url)}/auth/challenge",
            headers={
                "Authorization": authorization,
                "X-AKFES-Client-Version": _CLIENT_VERSION,
                "X-AKFES-Device-ID": device_id(),
            },
            timeout=10,
        )
        if not challenge_response.ok:
            try:
                message = challenge_response.json().get("error", "보안 챌린지 발급에 실패했습니다.")
            except Exception:
                message = "보안 챌린지 발급에 실패했습니다."
            raise RuntimeError(message)

        challenge_data = challenge_response.json()
        challenge = str(challenge_data["challenge"])
        timestamp = int(time.time())
        data = dict(kwargs.get("data", {}) or {})
        mode = str(data.get("mode", ""))
        password = str(data.get("password", ""))
        files = kwargs.get("files", {}) or {}
        if "file" not in files:
            raise RuntimeError("Signed upload requires a file.")
        filename, file_size, file_sha256 = _hash_file_entry(files["file"])
        message = _canonical_message(
            challenge,
            timestamp,
            mode,
            filename,
            file_size,
            file_sha256,
            password,
        )

        headers.update(
            {
                "X-AKFES-Protocol": _PROTOCOL,
                "X-AKFES-Challenge": challenge,
                "X-AKFES-Timestamp": str(timestamp),
                "X-AKFES-File-Size": str(file_size),
                "X-AKFES-File-SHA256": file_sha256,
                "X-AKFES-Signature": sign_b64(message),
            }
        )

    return _ORIGINAL_POST(url, *args, headers=headers, **kwargs)


def install_requests_hardening() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    requests.get = _secure_get
    requests.post = _secure_post
    _INSTALLED = True
