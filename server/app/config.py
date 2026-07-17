from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

_DEVELOPMENT_LICENSE_SECRET = "development-only-license-secret-change-me"
_DEVELOPMENT_ADMIN_TOKEN = "development-only-admin-token-change-me"


def _csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return default
    values = tuple(value.strip() for value in raw.split(",") if value.strip())
    if not values:
        raise RuntimeError(f"{name} must contain at least one value")
    return values


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean value")


def _integer(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _required_production_secret(
    name: str,
    *,
    environment: str,
    development_default: str,
    minimum_length: int = 32,
) -> str:
    value = os.getenv(name, development_default).strip()
    if len(value) < minimum_length:
        raise RuntimeError(f"{name} must contain at least {minimum_length} characters")
    if environment == "production" and value == development_default:
        raise RuntimeError(f"{name} must be explicitly configured in production")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    version: str
    environment: str
    host: str
    port: int
    docs_enabled: bool
    cors_origins: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    max_upload_bytes: int
    database_path: str
    license_hmac_secret: str
    admin_token: str
    session_ttl_seconds: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    environment = os.getenv("AKFES_ENVIRONMENT", "development").strip().lower()
    if environment not in {"development", "test", "production"}:
        raise RuntimeError("AKFES_ENVIRONMENT must be development, test, or production")

    return Settings(
        app_name="AKFES API",
        version="2.0.0",
        environment=environment,
        host=os.getenv("AKFES_HOST", "127.0.0.1").strip(),
        port=_integer("AKFES_PORT", 8000, minimum=1, maximum=65_535),
        docs_enabled=_boolean("AKFES_DOCS_ENABLED", environment != "production"),
        cors_origins=_csv(
            "AKFES_CORS_ORIGINS",
            (
                "http://localhost:1420",
                "http://127.0.0.1:1420",
                "http://tauri.localhost",
                "tauri://localhost",
            ),
        ),
        allowed_hosts=_csv(
            "AKFES_ALLOWED_HOSTS",
            ("127.0.0.1", "localhost", "testserver"),
        ),
        max_upload_bytes=_integer(
            "AKFES_MAX_UPLOAD_BYTES",
            100 * 1024 * 1024,
            minimum=1,
            maximum=2 * 1024 * 1024 * 1024,
        ),
        database_path=os.getenv("AKFES_DATABASE_PATH", "data/akfes.sqlite3").strip(),
        license_hmac_secret=_required_production_secret(
            "AKFES_LICENSE_HMAC_SECRET",
            environment=environment,
            development_default=_DEVELOPMENT_LICENSE_SECRET,
        ),
        admin_token=_required_production_secret(
            "AKFES_ADMIN_TOKEN",
            environment=environment,
            development_default=_DEVELOPMENT_ADMIN_TOKEN,
        ),
        session_ttl_seconds=_integer(
            "AKFES_SESSION_TTL_SECONDS",
            900,
            minimum=60,
            maximum=86_400,
        ),
    )
