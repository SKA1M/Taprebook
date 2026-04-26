"""ETL load layer — write DataFrames into the SQLite warehouse.

All loaders use INSERT OR REPLACE keyed on the table's primary key so the
pipeline is idempotent: re-running on the same CSVs does not duplicate rows.
"""
from __future__ import annotations

import sqlite3
from typing import Iterable

import pandas as pd


# Which PK to use for idempotent upserts per table
_PK_MAP = {
    "clinics":        "clinic_id",
    "patients":       "patient_id",
    "templates":      "template_id",
    "appointments":   "appt_id",
}


def _replace_table(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> int:
    """INSERT OR REPLACE rows. Returns row count inserted."""
    if df.empty:
        return 0
    cols = list(df.columns)
    placeholders = ",".join(["?"] * len(cols))
    col_list = ",".join(cols)
    sql = f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})"
    rows = df.where(pd.notna(df), None).to_records(index=False).tolist()
    conn.executemany(sql, rows)
    return len(rows)


def _append_table(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> int:
    """INSERT rows (events / template_sends are append-only logs)."""
    if df.empty:
        return 0
    cols = [c for c in df.columns if c != f"{table[:-1]}_id"]  # drop autoincrement PK if present
    # Simpler: just use all columns the DF has; if PK provided, SQLite will honor it.
    cols = list(df.columns)
    placeholders = ",".join(["?"] * len(cols))
    col_list = ",".join(cols)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
    rows = df.where(pd.notna(df), None).to_records(index=False).tolist()
    conn.executemany(sql, rows)
    return len(rows)


def load_dimensions(conn: sqlite3.Connection, data: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Load dimension tables (clinics, patients, templates) via upsert."""
    counts = {}
    for table in ("clinics", "patients", "templates"):
        counts[table] = _replace_table(conn, table, data[table])
    return counts


def load_facts(conn: sqlite3.Connection, data: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Load fact tables.

    appointments use upsert on appt_id (may be updated with new status).
    events, template_sends, ab_assignments are append-only.
    """
    counts = {}
    counts["appointments"] = _replace_table(conn, "appointments", data["appointments"])
    # Truncate append-only tables first to keep this script idempotent on sample data
    conn.execute("DELETE FROM events;")
    conn.execute("DELETE FROM template_sends;")
    conn.execute("DELETE FROM ab_assignments;")
    counts["events"]         = _append_table(conn, "events", data["events"])
    counts["template_sends"] = _append_table(conn, "template_sends", data["template_sends"])
    counts["ab_assignments"] = _append_table(conn, "ab_assignments", data["ab_assignments"])
    return counts
