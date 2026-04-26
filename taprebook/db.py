"""SQLite connection + helpers for applying schema/views and running query files."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd

from taprebook.config import DB_PATH, SQL_DIR, QUERIES_DIR, ensure_data_dirs


@contextmanager
def get_connection(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """Context-managed SQLite connection with foreign keys enabled."""
    ensure_data_dirs()
    path = Path(db_path) if db_path else DB_PATH
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply_sql_file(conn: sqlite3.Connection, path: Path) -> None:
    """Execute all statements in a .sql file. Supports our multi-statement files."""
    sql_text = Path(path).read_text(encoding="utf-8")
    conn.executescript(sql_text)


def apply_schema(conn: sqlite3.Connection) -> None:
    """Apply schema, indexes, and views in order."""
    for fname in ("001_schema.sql", "002_indexes.sql", "003_views.sql"):
        apply_sql_file(conn, SQL_DIR / fname)


def run_query_file(conn: sqlite3.Connection, name: str) -> pd.DataFrame:
    """Run a named SQL file from sql/queries/ and return as DataFrame.

    >>> run_query_file(conn, 'no_show_rate_monthly')
    """
    path = QUERIES_DIR / f"{name}.sql"
    if not path.exists():
        raise FileNotFoundError(f"Query file not found: {path}")
    sql = path.read_text(encoding="utf-8")
    return pd.read_sql_query(sql, conn)
