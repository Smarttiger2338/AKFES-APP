from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LicenseRecord:
    license_id: int
    expires_at: int
    revoked_at: int | None


@dataclass(frozen=True, slots=True)
class LicenseSummary:
    license_id: int
    label: str | None
    created_at: int
    expires_at: int
    revoked_at: int | None
    active_session_count: int


@dataclass(frozen=True, slots=True)
class SessionRecord:
    session_id: int
    license_id: int
    expires_at: int
    device_id: str | None


@dataclass(frozen=True, slots=True)
class AuditRecord:
    audit_id: int
    action: str
    actor: str
    target_type: str
    target_id: str | None
    details: dict[str, object]
    created_at: int


class LicenseStore:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        if database_path != ":memory:":
            Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS licenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_digest TEXT NOT NULL UNIQUE,
                    label TEXT,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    revoked_at INTEGER
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_digest TEXT NOT NULL UNIQUE,
                    license_id INTEGER NOT NULL,
                    device_id TEXT,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    revoked_at INTEGER,
                    FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT,
                    details_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_licenses_expires_at
                    ON licenses(expires_at);
                CREATE INDEX IF NOT EXISTS idx_sessions_expires_at
                    ON sessions(expires_at);
                CREATE INDEX IF NOT EXISTS idx_sessions_license_id
                    ON sessions(license_id);
                CREATE INDEX IF NOT EXISTS idx_audit_created_at
                    ON audit_log(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_action
                    ON audit_log(action);
                """
            )

    def create_license(
        self,
        *,
        key_digest: str,
        label: str | None,
        created_at: int,
        expires_at: int,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO licenses (key_digest, label, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (key_digest, label, created_at, expires_at),
            )
            return int(cursor.lastrowid)

    def find_license(self, key_digest: str) -> LicenseRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, expires_at, revoked_at
                FROM licenses
                WHERE key_digest = ?
                """,
                (key_digest,),
            ).fetchone()
        if row is None:
            return None
        return LicenseRecord(
            license_id=int(row["id"]),
            expires_at=int(row["expires_at"]),
            revoked_at=int(row["revoked_at"]) if row["revoked_at"] is not None else None,
        )

    def list_licenses(self, *, limit: int, offset: int, now: int) -> list[LicenseSummary]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    licenses.id,
                    licenses.label,
                    licenses.created_at,
                    licenses.expires_at,
                    licenses.revoked_at,
                    COUNT(sessions.id) AS active_session_count
                FROM licenses
                LEFT JOIN sessions
                    ON sessions.license_id = licenses.id
                   AND sessions.revoked_at IS NULL
                   AND sessions.expires_at > ?
                GROUP BY licenses.id
                ORDER BY licenses.id DESC
                LIMIT ? OFFSET ?
                """,
                (now, limit, offset),
            ).fetchall()
        return [
            LicenseSummary(
                license_id=int(row["id"]),
                label=str(row["label"]) if row["label"] is not None else None,
                created_at=int(row["created_at"]),
                expires_at=int(row["expires_at"]),
                revoked_at=int(row["revoked_at"]) if row["revoked_at"] is not None else None,
                active_session_count=int(row["active_session_count"]),
            )
            for row in rows
        ]

    def revoke_license(self, *, license_id: int, revoked_at: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE licenses
                SET revoked_at = ?
                WHERE id = ? AND revoked_at IS NULL
                """,
                (revoked_at, license_id),
            )
            if cursor.rowcount == 0:
                return False
            connection.execute(
                """
                UPDATE sessions
                SET revoked_at = ?
                WHERE license_id = ? AND revoked_at IS NULL
                """,
                (revoked_at, license_id),
            )
            return True

    def create_session(
        self,
        *,
        token_digest: str,
        license_id: int,
        device_id: str | None,
        created_at: int,
        expires_at: int,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO sessions (
                    token_digest,
                    license_id,
                    device_id,
                    created_at,
                    expires_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (token_digest, license_id, device_id, created_at, expires_at),
            )
            return int(cursor.lastrowid)

    def find_session(self, token_digest: str) -> SessionRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    sessions.id,
                    sessions.license_id,
                    sessions.device_id,
                    sessions.expires_at
                FROM sessions
                JOIN licenses ON licenses.id = sessions.license_id
                WHERE sessions.token_digest = ?
                  AND sessions.revoked_at IS NULL
                  AND licenses.revoked_at IS NULL
                """,
                (token_digest,),
            ).fetchone()
        if row is None:
            return None
        return SessionRecord(
            session_id=int(row["id"]),
            license_id=int(row["license_id"]),
            device_id=str(row["device_id"]) if row["device_id"] is not None else None,
            expires_at=int(row["expires_at"]),
        )

    def record_audit(
        self,
        *,
        action: str,
        actor: str,
        target_type: str,
        target_id: str | None,
        details: dict[str, object],
        created_at: int,
    ) -> int:
        details_json = json.dumps(details, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO audit_log (
                    action,
                    actor,
                    target_type,
                    target_id,
                    details_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (action, actor, target_type, target_id, details_json, created_at),
            )
            return int(cursor.lastrowid)

    def list_audit(self, *, limit: int, offset: int) -> list[AuditRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, action, actor, target_type, target_id, details_json, created_at
                FROM audit_log
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [
            AuditRecord(
                audit_id=int(row["id"]),
                action=str(row["action"]),
                actor=str(row["actor"]),
                target_type=str(row["target_type"]),
                target_id=str(row["target_id"]) if row["target_id"] is not None else None,
                details=json.loads(str(row["details_json"])),
                created_at=int(row["created_at"]),
            )
            for row in rows
        ]
