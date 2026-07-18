from __future__ import annotations

import json
import os
import secrets
import shutil
import stat
import time
from pathlib import Path

import uvicorn


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
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            if all(
                isinstance(payload.get(key), str) and len(payload[key]) >= 32
                for key in ("license_secret", "admin_token")
            ):
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
    temporary = config_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(config_path)
    config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
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

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()
