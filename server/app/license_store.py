from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LicenseRecord:
    license_id: int
    expires_at: int
    revoked_at: int | None


@dataclass(frozen=True, slots=True)
class SessionRecord:
    session_id: int
    license_id: int
    expires_at: int
    device_id: str | None


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

                CREATE INDEX IF NOT EXISTS idx_licenses_expires_at
                    ON licenses(expires_at);
                CREATE INDEX IF NOT EXISTS idx_sessions_expires_at
                    ON sessions(expires_at);
                CREATE INDEX IF NOT EXISTS idx_sessions_license_id
                    ON sessions(license_id);
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
