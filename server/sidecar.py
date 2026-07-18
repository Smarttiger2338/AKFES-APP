from __future__ import annotations

import base64
import ctypes
import json
import os
import secrets
import shutil
import stat
import time
from ctypes import wintypes
from pathlib import Path

import uvicorn


class DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def protect_payload(content: str) -> str:
    if os.name != "nt":
        return base64.b64encode(content.encode("utf-8")).decode("ascii")

    payload = content.encode("utf-8")
    input_buffer = ctypes.create_string_buffer(payload)
    input_blob = DataBlob(len(payload), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output_blob = DataBlob()

    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    ):
        raise OSError("Windows failed to protect local server config.")

    try:
        encrypted = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        return base64.b64encode(encrypted).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


def unprotect_payload(payload: str) -> str:
    encrypted = base64.b64decode(payload)
    if os.name != "nt":
        return encrypted.decode("utf-8")

    input_buffer = ctypes.create_string_buffer(encrypted)
    input_blob = DataBlob(len(encrypted), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output_blob = DataBlob()

    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    ):
        raise OSError("Windows failed to unprotect local server config.")

    try:
        decrypted = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        return decrypted.decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


def is_valid_runtime_config(payload: object) -> bool:
    return isinstance(payload, dict) and all(
        isinstance(payload.get(key), str) and len(payload[key]) >= 32
        for key in ("license_secret", "admin_token")
    )


def read_runtime_config(config_path: Path) -> dict[str, str]:
    stored = json.loads(config_path.read_text(encoding="utf-8"))
    if is_valid_runtime_config(stored):
        return stored

    if (
        isinstance(stored, dict)
        and stored.get("version") == 2
        and stored.get("protected") is True
        and isinstance(stored.get("payload"), str)
    ):
        payload = json.loads(unprotect_payload(stored["payload"]))
        if is_valid_runtime_config(payload):
            return payload

    raise ValueError("Local server config is invalid.")


def write_runtime_config(config_path: Path, payload: dict[str, str]) -> None:
    envelope = {
        "version": 2,
        "protected": True,
        "protection": "windows-dpapi-current-user" if os.name == "nt" else "base64-local-dev",
        "payload": protect_payload(json.dumps(payload, separators=(",", ":"))),
    }
    temporary = config_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    temporary.replace(config_path)
    config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def app_data_directory() -> Path:
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
    if base:
        return Path(base) / "AKFES"
    return Path.home() / ".akfes"


def load_or_create_runtime_config(directory: Path) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    config_path = directory / "server-runtime.json"
    if config_path.exists():
        try:
            payload = read_runtime_config(config_path)
            write_runtime_config(config_path, payload)
            return payload
        except (OSError, ValueError, TypeError):
            pass
        backup_path = directory / f"server-runtime.invalid-{int(time.time())}.json"
        shutil.copy2(config_path, backup_path)

    payload = {
        "license_secret": secrets.token_urlsafe(48),
        "admin_token": secrets.token_urlsafe(48),
        "created_at": str(int(time.time())),
    }
    write_runtime_config(config_path, payload)
    return payload


def configure_environment() -> None:
    directory = app_data_directory()
    runtime = load_or_create_runtime_config(directory)
    os.environ.setdefault("AKFES_ENVIRONMENT", "production")
    os.environ.setdefault("AKFES_HOST", "127.0.0.1")
    os.environ.setdefault("AKFES_PORT", "8000")
    os.environ.setdefault("AKFES_DOCS_ENABLED", "false")
    os.environ.setdefault("AKFES_ALLOWED_HOSTS", "127.0.0.1,localhost")
    os.environ.setdefault(
        "AKFES_CORS_ORIGINS",
        "http://tauri.localhost,tauri://localhost,http://127.0.0.1:1420,http://localhost:1420,http://127.0.0.1:5174,http://localhost:5174",
    )
    os.environ.setdefault("AKFES_DATABASE_PATH", str(directory / "akfes.sqlite3"))
    os.environ.setdefault("AKFES_LICENSE_HMAC_SECRET", runtime["license_secret"])
    os.environ.setdefault("AKFES_ADMIN_TOKEN", runtime["admin_token"])


def main() -> None:
    configure_environment()
    from app.main import app

    port = int(os.getenv("AKFES_PORT", "8000"))
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()
