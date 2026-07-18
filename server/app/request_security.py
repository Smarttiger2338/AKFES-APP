from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from .license_service import InvalidSessionError, LicenseService


class ChallengeError(Exception):
    pass


class InvalidChallengeError(ChallengeError):
    pass


class InvalidSignatureError(ChallengeError):
    pass


@dataclass(frozen=True, slots=True)
class IssuedChallenge:
    challenge: str
    expires_at: int


@dataclass(frozen=True, slots=True)
class VerifiedRequest:
    session_id: int
    license_id: int
    device_id: str | None
    challenge_id: int


class RequestSecurityService:
    def __init__(
        self,
        *,
        license_service: LicenseService,
        challenge_ttl_seconds: int,
    ) -> None:
        self.license_service = license_service
        self.store = license_service.store
        self.challenge_ttl_seconds = challenge_ttl_seconds
        self.initialize()

    def initialize(self) -> None:
        with self.store.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS request_challenges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    challenge_digest TEXT NOT NULL UNIQUE,
                    session_id INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    used_at INTEGER,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_request_challenges_session_id
                    ON request_challenges(session_id);
                CREATE INDEX IF NOT EXISTS idx_request_challenges_expires_at
                    ON request_challenges(expires_at);
                """
            )

    @staticmethod
    def body_sha256(body: bytes) -> str:
        return hashlib.sha256(body).hexdigest()

    @staticmethod
    def canonical_message(
        *,
        method: str,
        path: str,
        challenge: str,
        body_sha256: str,
        device_id: str | None,
    ) -> str:
        return "\n".join(
            (
                "AKFES-V2",
                method.upper(),
                path,
                challenge,
                body_sha256.lower(),
                device_id or "",
            )
        )

    @classmethod
    def calculate_signature(
        cls,
        *,
        session_token: str,
        method: str,
        path: str,
        challenge: str,
        body: bytes,
        device_id: str | None,
    ) -> str:
        message = cls.canonical_message(
            method=method,
            path=path,
            challenge=challenge,
            body_sha256=cls.body_sha256(body),
            device_id=device_id,
        )
        return hmac.new(
            session_token.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def issue_challenge(
        self,
        *,
        session_token: str,
        device_id: str | None,
        now: int | None = None,
    ) -> IssuedChallenge:
        current_time = int(time.time()) if now is None else int(now)
        session = self.license_service.verify_session(
            session_token,
            device_id=device_id,
            now=current_time,
        )
        challenge = secrets.token_urlsafe(32)
        expires_at = min(session.expires_at, current_time + self.challenge_ttl_seconds)
        digest = self.license_service.digest("challenge", challenge)

        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT INTO request_challenges (
                    challenge_digest,
                    session_id,
                    created_at,
                    expires_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (digest, session.session_id, current_time, expires_at),
            )
            connection.execute(
                """
                DELETE FROM request_challenges
                WHERE expires_at <= ? OR used_at IS NOT NULL
                """,
                (current_time - 300,),
            )

        return IssuedChallenge(challenge=challenge, expires_at=expires_at)

    def verify_request(
        self,
        *,
        session_token: str,
        challenge: str,
        signature: str,
        method: str,
        path: str,
        body: bytes,
        device_id: str | None,
        now: int | None = None,
    ) -> VerifiedRequest:
        current_time = int(time.time()) if now is None else int(now)
        session = self.license_service.verify_session(
            session_token,
            device_id=device_id,
            now=current_time,
        )
        challenge_value = challenge.strip()
        signature_value = signature.strip().lower()
        if not challenge_value or len(challenge_value) > 256:
            raise InvalidChallengeError("Invalid challenge")
        if len(signature_value) != 64:
            raise InvalidSignatureError("Invalid request signature")

        expected_signature = self.calculate_signature(
            session_token=session_token,
            method=method,
            path=path,
            challenge=challenge_value,
            body=body,
            device_id=session.device_id,
        )
        if not hmac.compare_digest(signature_value, expected_signature):
            raise InvalidSignatureError("Invalid request signature")

        challenge_digest = self.license_service.digest("challenge", challenge_value)
        with self.store.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE request_challenges
                SET used_at = ?
                WHERE challenge_digest = ?
                  AND session_id = ?
                  AND used_at IS NULL
                  AND expires_at > ?
                """,
                (current_time, challenge_digest, session.session_id, current_time),
            )
            if cursor.rowcount != 1:
                raise InvalidChallengeError("Challenge is invalid, expired, or already used")
            row = connection.execute(
                """
                SELECT id
                FROM request_challenges
                WHERE challenge_digest = ?
                """,
                (challenge_digest,),
            ).fetchone()

        if row is None:
            raise InvalidChallengeError("Challenge could not be resolved")
        return VerifiedRequest(
            session_id=session.session_id,
            license_id=session.license_id,
            device_id=session.device_id,
            challenge_id=int(row["id"]),
        )
