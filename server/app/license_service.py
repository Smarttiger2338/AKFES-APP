from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from .license_store import LicenseStore, SessionRecord


class LicenseError(Exception):
    pass


class InvalidLicenseError(LicenseError):
    pass


class ExpiredLicenseError(LicenseError):
    pass


class RevokedLicenseError(LicenseError):
    pass


class InvalidSessionError(LicenseError):
    pass


@dataclass(frozen=True, slots=True)
class IssuedLicense:
    license_key: str
    license_id: int
    created_at: int
    expires_at: int


@dataclass(frozen=True, slots=True)
class IssuedSession:
    session_token: str
    license_id: int
    license_expires_at: int
    session_expires_at: int
    device_id: str | None


class LicenseService:
    def __init__(
        self,
        *,
        store: LicenseStore,
        hmac_secret: str,
        session_ttl_seconds: int,
    ) -> None:
        self.store = store
        self.secret = hmac_secret.encode("utf-8")
        self.session_ttl_seconds = session_ttl_seconds

    def digest(self, namespace: str, value: str) -> str:
        payload = f"{namespace}:{value}".encode("utf-8")
        return hmac.new(self.secret, payload, hashlib.sha256).hexdigest()

    @staticmethod
    def normalize_license_key(value: str) -> str:
        return value.strip().upper()

    @staticmethod
    def normalize_device_id(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > 128:
            raise ValueError("device_id must not exceed 128 characters")
        return normalized

    @staticmethod
    def generate_license_key() -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        groups = [
            "".join(secrets.choice(alphabet) for _ in range(5))
            for _ in range(4)
        ]
        return f"AKFES-{'-'.join(groups)}"

    def issue_license(
        self,
        *,
        duration_seconds: int,
        label: str | None = None,
        now: int | None = None,
    ) -> IssuedLicense:
        if duration_seconds < 60:
            raise ValueError("duration_seconds must be at least 60")
        created_at = int(time.time()) if now is None else int(now)
        expires_at = created_at + int(duration_seconds)
        normalized_label = label.strip()[:120] if label and label.strip() else None

        for _ in range(5):
            license_key = self.generate_license_key()
            try:
                license_id = self.store.create_license(
                    key_digest=self.digest("license", license_key),
                    label=normalized_label,
                    created_at=created_at,
                    expires_at=expires_at,
                )
            except Exception as error:
                if "UNIQUE constraint failed" in str(error):
                    continue
                raise
            return IssuedLicense(
                license_key=license_key,
                license_id=license_id,
                created_at=created_at,
                expires_at=expires_at,
            )

        raise RuntimeError("Could not generate a unique license key")

    def authenticate(
        self,
        *,
        license_key: str,
        device_id: str | None = None,
        now: int | None = None,
    ) -> IssuedSession:
        current_time = int(time.time()) if now is None else int(now)
        normalized_key = self.normalize_license_key(license_key)
        if not normalized_key.startswith("AKFES-") or len(normalized_key) != 29:
            raise InvalidLicenseError("Invalid license key")

        record = self.store.find_license(self.digest("license", normalized_key))
        if record is None:
            raise InvalidLicenseError("Invalid license key")
        if record.revoked_at is not None:
            raise RevokedLicenseError("License has been revoked")
        if record.expires_at <= current_time:
            raise ExpiredLicenseError("License has expired")

        normalized_device_id = self.normalize_device_id(device_id)
        session_expires_at = min(
            record.expires_at,
            current_time + self.session_ttl_seconds,
        )
        session_token = secrets.token_urlsafe(48)
        self.store.create_session(
            token_digest=self.digest("session", session_token),
            license_id=record.license_id,
            device_id=normalized_device_id,
            created_at=current_time,
            expires_at=session_expires_at,
        )
        return IssuedSession(
            session_token=session_token,
            license_id=record.license_id,
            license_expires_at=record.expires_at,
            session_expires_at=session_expires_at,
            device_id=normalized_device_id,
        )

    def verify_session(
        self,
        session_token: str,
        *,
        device_id: str | None = None,
        now: int | None = None,
    ) -> SessionRecord:
        current_time = int(time.time()) if now is None else int(now)
        token = session_token.strip()
        if not token:
            raise InvalidSessionError("Missing session token")

        record = self.store.find_session(self.digest("session", token))
        if record is None or record.expires_at <= current_time:
            raise InvalidSessionError("Invalid or expired session")

        normalized_device_id = self.normalize_device_id(device_id)
        if record.device_id is not None and not hmac.compare_digest(
            record.device_id,
            normalized_device_id or "",
        ):
            raise InvalidSessionError("Session device does not match")
        return record
