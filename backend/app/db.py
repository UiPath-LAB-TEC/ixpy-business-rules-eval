from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3

from .config import get_settings


MIGRATIONS_DIR = Path(__file__).resolve().parent / "sql" / "migrations"
VIEWS_DIR = Path(__file__).resolve().parent / "sql" / "views"
SEEDS_DIR = Path(__file__).resolve().parent / "sql" / "seeds"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(db_path: Path | None = None):
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply_sql_dir(conn: sqlite3.Connection, directory: Path) -> list[str]:
    applied: list[str] = []
    for path in sorted(directory.glob("*.sql")):
        conn.executescript(path.read_text())
        applied.append(path.name)
    return applied


def apply_migrations(db_path: Path | None = None) -> list[str]:
    with transaction(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migration (
                name TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied: list[str] = []
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            already = conn.execute(
                "SELECT 1 FROM schema_migration WHERE name = ?",
                (path.name,),
            ).fetchone()
            if already:
                continue
            conn.executescript(path.read_text())
            conn.execute("INSERT INTO schema_migration (name) VALUES (?)", (path.name,))
            applied.append(path.name)
        apply_sql_dir(conn, VIEWS_DIR)
        apply_sql_dir(conn, SEEDS_DIR)
        return applied


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]

