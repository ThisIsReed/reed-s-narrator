"""SQLite database bootstrap and migration helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


class SQLiteDatabase:
    """Manage SQLite connections and one-way SQL migrations."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    @property
    def path(self) -> Path:
        return self._db_path

    def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            self._ensure_migration_table(connection)
            self._apply_pending_migrations(connection)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _ensure_migration_table(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )

    def _apply_pending_migrations(self, connection: sqlite3.Connection) -> None:
        applied = self._load_applied_versions(connection)
        for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if migration_path.name in applied:
                continue
            script = migration_path.read_text(encoding="utf-8").strip()
            if not script:
                raise ValueError(f"migration is empty: {migration_path}")
            connection.executescript(script)
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)",
                (migration_path.name,),
            )
        connection.commit()

    def _load_applied_versions(self, connection: sqlite3.Connection) -> set[str]:
        cursor = connection.execute("SELECT version FROM schema_migrations")
        return {row["version"] for row in cursor.fetchall()}
