"""End-to-end pipeline smoke test.

Builds a throwaway DB from scratch, verifies every KPI query runs.
"""
from __future__ import annotations

import pandas as pd

from taprebook.db import apply_schema, run_query_file
from taprebook.etl.extract import load_all_sample
from taprebook.etl.load import load_dimensions, load_facts


def test_pipeline_end_to_end(tmp_path, monkeypatch):
    """Full extract → transform → load → query cycle on a clean DB."""
    import sqlite3
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("taprebook.config.DB_PATH", db_path)
    monkeypatch.setattr("taprebook.db.DB_PATH", db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        apply_schema(conn)

        data = load_all_sample()
        load_dimensions(conn, data)
        load_facts(conn, data)

        # Sanity: at least one row per table
        for table in ("clinics", "patients", "appointments", "events", "template_sends"):
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count > 0, f"{table} is empty"

        # Every query file executes without error
        for q in ("monthly_kpi_summary", "no_show_rate_monthly", "funnel_conversion",
                  "cohort_recall", "template_health", "ab_test_reminder_cadence"):
            df = run_query_file(conn, q)
            assert isinstance(df, pd.DataFrame)
        conn.commit()
    finally:
        conn.close()


def test_ab_test_shows_treatment_lift():
    """The synthetic generator plants a ~6pp treatment lift; verify it comes through."""
    import sqlite3
    from taprebook.config import DB_PATH

    if not DB_PATH.exists():
        import pytest
        pytest.skip("Main DB not initialized — run `make init-db` first")

    conn = sqlite3.connect(DB_PATH)
    try:
        df = run_query_file(conn, "ab_test_reminder_cadence")
    finally:
        conn.close()

    control    = df[df["variant"] == "control"].iloc[0]
    treatment  = df[df["variant"] == "treatment"].iloc[0]

    # Both arms got enough samples (synthetic data is ~280/arm)
    assert control["n"] > 100
    assert treatment["n"] > 100
    # Treatment should outperform control (direction, not magnitude — allow some RNG jitter)
    assert treatment["kept_rate_pct"] > control["kept_rate_pct"]
