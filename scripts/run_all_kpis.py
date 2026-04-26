"""Run every SQL query in sql/queries/ and print its results.

Usage:
    python scripts/run_all_kpis.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from taprebook.config import QUERIES_DIR
from taprebook.db import get_connection, run_query_file


# Order matters only for readability — group by theme
QUERY_ORDER = [
    "monthly_kpi_summary",
    "no_show_rate_monthly",
    "funnel_conversion",
    "cohort_recall",
    "template_health",
    "ab_test_reminder_cadence",
]


def main() -> None:
    # Pick up any queries added later even if not in QUERY_ORDER
    all_queries = [p.stem for p in sorted(QUERIES_DIR.glob("*.sql"))]
    ordered = QUERY_ORDER + [q for q in all_queries if q not in QUERY_ORDER]

    with get_connection() as conn:
        for q in ordered:
            if q not in all_queries:
                continue
            print("\n" + "=" * 80)
            print(f"  {q}")
            print("=" * 80)
            try:
                df = run_query_file(conn, q)
                if df.empty:
                    print("  (no rows)")
                else:
                    # Keep output readable in a terminal
                    with_max_cols = df.copy()
                    print(with_max_cols.to_string(index=False))
            except Exception as e:
                print(f"  ERROR: {e}")


if __name__ == "__main__":
    main()
